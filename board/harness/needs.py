"""
Evening needs-pass: fire up each seat BEFORE the meeting day and ask what it
needs to know.

WHY (Brian 2026-10-08):
    Seats should bring what they need to know to the table. The morning
    session is for decisions, not discovery — so the evening before, each
    seat gets one short call: "what do you need to know to make your calls
    tomorrow?" The answers go into a research queue; overnight research
    (Altair's routines) fills them; the morning brief carries the answers.

CALLED BY:
    - New evening cron (~20:00): python3 -m board.harness.needs board/config/brian.yaml
    - Humans, manually.

NOTES:
    Writes board-needs-<tag>.jsonl into the minutes/inbox dir (same place the
    morning minutes land) so Altair's overnight routines find it. One line per
    need: {session_tag, seat, need, status}. Research marks status=answered and
    fills answer. The morning BriefBuilder's pull_overnight_answers() puller
    reads the answered needs into the shared brief. Short calls (150 tokens)
    keep this cheap; it is discovery, not deliberation.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .seats import Seat, load_config
from .worker import ModelWorker

NEEDS_RE = re.compile(r"^\s*NEEDS\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class SeatNeeds:
    seat_title: str
    needs: list[str] = field(default_factory=list)
    raw: str = ""


def parse_needs(raw: str) -> list[str]:
    out = []
    for m in NEEDS_RE.finditer(raw or ""):
        need = (m.group(1) or "").strip()
        if not need or re.match(r"^(nothing|none|n/a)\b", need, re.I):
            continue
        if len(need) < 8:
            continue
        out.append(need)
    # Deduplicate, preserve order.
    seen, uniq = set(), []
    for n in out:
        if n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)
    return uniq[:3]  # cap: 3 needs per seat per evening


class NeedsCollector:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.seats = [Seat.from_dict(s) for s in self.cfg.get("seats", [])]
        m = self.cfg.get("model", {})
        r = self.cfg.get("retry", {})
        # Short, cheap discovery calls — reuse the blocking worker so a slow
        # API is waited on, not skipped.
        self.worker = ModelWorker(
            base_url=m.get("base_url", "http://127.0.0.1:11437"),
            model=m.get("name", "morpheus"),
            timeout_s=int(m.get("timeout_s", 180)),
            max_tokens=150,
            temperature=0.7,
            via=m.get("via", "direct"),
            retry_base_s=float(r.get("base_s", 30)),
            retry_cap_s=float(r.get("cap_s", 300)),
        )
        # Tag for TOMORROW's session (this runs the evening before).
        tomorrow = datetime.now() + timedelta(days=1)
        self.tag = "board-" + tomorrow.strftime("%Y%m%d")
        self.out_dir = os.path.expanduser(
            self.cfg.get("minutes_dir", "~/workspace/altair-brain/inbox"))

    def _needs_prompt(self, seat: Seat) -> str:
        return (
            f"You are the {seat.title}. Your mandate: {seat.mandate}\n\n"
            f"Tomorrow morning you sit on the board of directors and make "
            f"2-3 binding calls in your domain. Tonight, one question only:\n"
            f"what do you NEED TO KNOW to make those calls well?\n"
            f"List up to 3 items, one per line, each starting with 'NEEDS:'.\n"
            f"Be specific (a metric, a fact, a status — not a topic).\n"
            f"If you have everything you need, write 'NEEDS: nothing'."
        )

    def collect(self) -> list[SeatNeeds]:
        import time
        results = []
        for seat in self.seats:
            print(f"[needs] asking {seat.title} ...", flush=True)
            # Blocking wait like the morning session: a slow API is waited
            # on, never skipped (Brian 2026-10-08).
            attempt, backoff = 0, self.worker.retry_base_s
            raw = ""
            while True:
                attempt += 1
                try:
                    raw = self.worker._post(
                        self.worker._payload(seat.system_prompt(),
                                             self._needs_prompt(seat)))
                    break
                except Exception as e:  # noqa: BLE001 - wait, retry
                    print(f"[needs] {seat.title}: attempt {attempt} transport "
                          f"error; waiting {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.worker.retry_cap_s)
            needs = parse_needs(raw)
            print(f"[needs] {seat.title}: {len(needs)} need(s)", flush=True)
            results.append(SeatNeeds(seat.title, needs, raw))
        return results

    def write_queue(self, results: list[SeatNeeds]) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, f"board-needs-{self.tag}.jsonl")
        with open(path, "w") as f:
            for r in results:
                for need in r.needs:
                    f.write(json.dumps({
                        "session_tag": self.tag,
                        "seat": r.seat_title,
                        "need": need,
                        "status": "new",
                        "answer": "",
                    }) + "\n")
        n = sum(len(r.needs) for r in results)
        print(f"[needs] wrote {n} need(s) to {path}")
        return path


def read_answered_needs(tag: str, inbox_dir: str) -> list[dict]:
    """Read answered needs for a session tag (morning brief puller)."""
    path = os.path.join(os.path.expanduser(inbox_dir),
                        f"board-needs-{tag}.jsonl")
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("status") == "answered" and d.get("answer"):
                    out.append(d)
    except (OSError, json.JSONDecodeError):
        pass
    return out


if __name__ == "__main__":
    import sys

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "board/config/brian.yaml"
    collector = NeedsCollector(cfg_path)
    results = collector.collect()
    collector.write_queue(results)
