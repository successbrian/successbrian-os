"""
Evening needs-pass: fire up each seat BEFORE the meeting day and ask what it
needs to know.

WHY (Brian 2026-10-08):
    Seats should bring what they need to know to the table. The morning
    session is for decisions, not discovery — so the evening before, each
    seat gets one short call analyzing its domain: "is there a NEW type of
    report I need?" (REPORT:) and "what news/trends do I want MORE DETAIL on?"
    (DETAIL:). Before asking new things, the seat REVIEWS its previous
    requests: SATISFIED: lines close out answers/reports that met its goal;
    anything that missed gets honed with a refined REPORT:/DETAIL: follow-up.
    The answers go into a research queue; overnight research (Altair's
    routines) fills DETAILs; REPORTs become instrumentation requests
    (new pullers/reports to build). The morning brief carries answered DETAILs
    plus the open REPORT backlog.

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
SATISFIED_RE = re.compile(r"^\s*SATISFIED\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
REPORT_RE = re.compile(r"^\s*REPORT\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
DETAIL_RE = re.compile(r"^\s*DETAIL\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class SeatNeeds:
    seat_title: str
    needs: list[dict] = field(default_factory=list)  # [{kind, need}]
    raw: str = ""


def _clean_need(text: str) -> str:
    text = (text or "").strip()
    if not text or re.match(r"^(nothing|none|n/a)\b", text, re.I):
        return ""
    return text if len(text) >= 8 else ""


def parse_needs(raw: str) -> list[dict]:
    """Parse a seat's discovery output into [{kind, need}].
    kind = 'report' (REPORT: — a NEW type of report the seat wants built) or
           'detail' (DETAIL: or NEEDS: — news/trends/topics it wants more on).
    """
    out = []
    for m in REPORT_RE.finditer(raw or ""):
        need = _clean_need(m.group(1))
        if need:
            out.append({"kind": "report", "need": need})
    for pattern in (DETAIL_RE, NEEDS_RE):
        for m in pattern.finditer(raw or ""):
            need = _clean_need(m.group(1))
            if need:
                out.append({"kind": "detail", "need": need})
    # Deduplicate, preserve order.
    seen, uniq = set(), []
    for d in out:
        key = (d["kind"], d["need"].lower())
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    return uniq[:5]  # cap: 5 needs per seat per evening


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

    def _needs_prompt(self, seat: Seat, previous: list[dict]) -> str:
        prev_lines = []
        for d in previous[-10:]:
            status = d.get("status", "new")
            ans = (d.get("answer") or "")[:160]
            prev_lines.append(
                f"- [{d.get('kind', 'detail')}] {d.get('need')} "
                f"(status: {status}{'; answer: ' + ans if ans else ''})")
        prev_block = ("\nYOUR PREVIOUS REQUESTS (review each):\n" + "\n".join(prev_lines)
                      if prev_lines else
                      "\nYou have no previous requests.")
        return (
            f"You are the {seat.title}. Your mandate: {seat.mandate}\n"
            f"{prev_block}\n\n"
            f"Tomorrow morning you sit on the board of directors and make "
            f"2-3 binding calls in your domain. Two jobs tonight:\n"
            f"(1) REVIEW: for each previous request above, did the answer or "
            f"built report meet your goal? If yes, write 'SATISFIED: <short "
            f"ref>'. If it missed the mark, hone it with a new REPORT:/DETAIL: "
            f"line below.\n"
            f"(2) NEW: analyze YOUR domain — is there a NEW type of report "
            f"you need that does not exist ('REPORT: ...')? What news, "
            f"trends, or topics do you want to know MORE about ('DETAIL: ...')?\n"
            f"Up to 5 REPORT:/DETAIL: items total. Be specific. If your "
            f"domain is fully covered and all previous requests satisfied, "
            f"write 'NEEDS: nothing'."
        )

    def collect(self) -> list[SeatNeeds]:
        import time
        results = []
        for seat in self.seats:
            print(f"[needs] asking {seat.title} ...", flush=True)
            previous = read_recent_needs(seat.title, self.out_dir)
            # Blocking wait like the morning session: a slow API is waited
            # on, never skipped (Brian 2026-10-08).
            attempt, backoff = 0, self.worker.retry_base_s
            raw = ""
            while True:
                attempt += 1
                try:
                    raw = self.worker._post(
                        self.worker._payload(seat.system_prompt(),
                                             self._needs_prompt(seat, previous)))
                    break
                except Exception:  # noqa: BLE001 - wait, retry
                    print(f"[needs] {seat.title}: attempt {attempt} transport "
                          f"error; waiting {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.worker.retry_cap_s)
            needs = parse_needs(raw)
            # Review step: SATISFIED lines close out previous requests whose
            # answers/reports met the seat's goal.
            satisfied_n = 0
            files = []
            for d in previous:
                if d["_file"] not in files:
                    files.append(d["_file"])
            for ref in parse_satisfied(raw):
                for path in files:
                    if mark_satisfied(path, ref):
                        satisfied_n += 1
                        break
            print(f"[needs] {seat.title}: {len(needs)} need(s), "
                  f"{satisfied_n} previous marked satisfied", flush=True)
            results.append(SeatNeeds(seat.title, needs, raw))
        return results

    def write_queue(self, results: list[SeatNeeds]) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, f"board-needs-{self.tag}.jsonl")
        with open(path, "w") as f:
            for r in results:
                for d in r.needs:
                    f.write(json.dumps({
                        "session_tag": self.tag,
                        "seat": r.seat_title,
                        "kind": d["kind"],
                        "need": d["need"],
                        "status": "new",
                        "answer": "",
                    }) + "\n")
        n = sum(len(r.needs) for r in results)
        print(f"[needs] wrote {n} need(s) to {path}")
        return path


def read_answered_needs(tag: str, inbox_dir: str) -> list[dict]:
    """Read answered DETAIL needs for a session tag (morning brief puller)."""
    return read_needs(tag, inbox_dir, kind="detail", status="answered")


def read_open_reports(tag: str, inbox_dir: str) -> list[dict]:
    """Read REPORT needs not yet built (instrumentation backlog)."""
    out = read_needs(tag, inbox_dir, kind="report")
    return [d for d in out if d.get("status") in ("new", "acknowledged")]


def parse_satisfied(raw: str) -> list[str]:
    """Parse SATISFIED: lines — refs to previous needs that met the seat's goal."""
    out = []
    for m in SATISFIED_RE.finditer(raw or ""):
        ref = _clean_need(m.group(1))
        if ref:
            out.append(ref)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


_STOP = {"the", "a", "an", "of", "on", "for", "to", "in", "and", "or", "my"}


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if t and t not in _STOP}


def _match_score(ref: str, need: str) -> float:
    """Token recall: fraction of the ref's significant tokens found in need."""
    rt, nt = _tokens(ref), _tokens(need)
    if not rt:
        return 0.0
    return len(rt & nt) / len(rt)


def read_recent_needs(seat_title: str, inbox_dir: str, days: int = 7) -> list[dict]:
    """All needs this seat raised in recent queue files (for the review step)."""
    import glob
    out = []
    pattern = os.path.join(os.path.expanduser(inbox_dir), "board-needs-*.jsonl")
    for path in sorted(glob.glob(pattern))[-days:]:
        for d in read_needs(os.path.basename(path)[len("board-needs-"):-len(".jsonl")],
                            inbox_dir):
            if d.get("seat") == seat_title:
                d["_file"] = path
                out.append(d)
    return out


def mark_satisfied(path: str, ref: str) -> bool:
    """Mark the need in path best matching ref as satisfied. Returns True if matched."""
    nref = _norm(ref)
    try:
        with open(path) as f:
            lines = [l for l in f if l.strip()]
    except OSError:
        return False
    best, best_key = -1, None
    parsed = []
    for i, line in enumerate(lines):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            parsed.append((line, None))
            continue
        parsed.append((line, d))
        if not d or d.get("status") == "satisfied":
            continue
        score = _match_score(ref, d.get("need", ""))
        if score >= 0.6 and score > best:
            best, best_key = score, i
    if best_key is None:
        return False
    line, d = parsed[best_key]
    d["status"] = "satisfied"
    parsed[best_key] = (json.dumps(d) + "\n", d)
    with open(path, "w") as f:
        for new_line, _ in parsed:
            f.write(new_line if new_line.endswith("\n") else new_line + "\n")
    return True


def read_needs(tag: str, inbox_dir: str, kind: str | None = None,
               status: str | None = None) -> list[dict]:
    """Read needs for a session tag, optionally filtered."""
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
                if kind and d.get("kind", "detail") != kind:
                    continue
                if status and d.get("status") != status:
                    continue
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
