"""Split log — the decider layer's disagreement record (2026-10-25).

Built under Brian's direction (2026-10-25 10:10 CDT: resolve splits
without sending issues to him) and the same day's research synthesis:
when Altair and Meghan still disagree after research, the split is
worked through a fixed ladder instead of landing on Brian's desk.
This module is the RECORD of that work: every split gets a locus
class (WHY they split), the ladder steps taken, and the resolution.
Recurring loci are upstream problems (framing, research quality,
missing standing rules) — the log is how the morning loop sees them.

Ladder (research-ranked, adapted to two unanimous deciders):
  1. decompose   — split the split into sub-questions / assumptions /
                   weights; each decider answers blind; re-litigate
                   only the exact locus.
  2. precedent   — prior decisions + Brian's standing priority order;
                   if a rule covers it, apply it and cite it.
  3. mind_test   — both state in advance what evidence would flip
                   them; run exactly that check with tools; abide.
  4. blind_exchange — steelman + key-assumptions check + premortem,
                   justifications only, then a blind re-vote. One
                   round; no open thread, no third round.
  5. judge_diagnostic — a small cross-family panel advises on a
                   leftover FACTUAL point only; never a deciding
                   vote, never on a value question.
  6. fallback    — still split: reversible -> least-regret pilot
                   (bounded, monitored, expiry; outcomes judge it);
                   irreversible -> wait, and escalate.

Escalation to Brian happens ONLY when: the item is irreversible and
still split after the ladder; or two standing rules collide with no
precedence covering them (his answer becomes a new standing rule);
or the mind-changing test cannot be run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

LOCUS_CLASSES = (
    "weights",    # (a) the two weigh priorities differently
    "research",   # (b) research is soft / conflicting / stale
    "scope",      # (c) research opened a new scope question
    "risk",       # (d) act-now-vs-wait: risk appetite, not fact
    "rules",      # (e) two standing rules collide
    "misread",    # (f) one side misread or anchored
    "framing",    # (g) the packet was framed around the wrong problem
)

LADDER = ("decompose", "precedent", "mind_test", "blind_exchange",
          "judge_diagnostic", "fallback_pilot", "fallback_wait",
          "escalate")

# Which ladder steps a locus class walks, in order. Factual loci lean
# on decomposition and evidence; value loci lean on precedent and the
# reversibility fallback; a rules collision with no precedent exits
# early to Brian (his answer becomes the missing standing rule).
ROUTES = {
    "misread":  ("decompose", "mind_test", "blind_exchange",
                 "judge_diagnostic", "fallback_pilot", "fallback_wait"),
    "framing":  ("decompose", "blind_exchange", "precedent",
                 "fallback_pilot", "fallback_wait"),
    "research": ("decompose", "mind_test", "blind_exchange",
                 "judge_diagnostic", "fallback_pilot", "fallback_wait"),
    "scope":    ("decompose", "precedent", "blind_exchange",
                 "fallback_pilot", "fallback_wait"),
    "weights":  ("precedent", "blind_exchange",
                 "fallback_pilot", "fallback_wait"),
    "risk":     ("precedent", "blind_exchange",
                 "fallback_pilot", "fallback_wait"),
    "rules":    ("precedent", "escalate"),
}


def route_for(locus: str) -> tuple:
    """The ladder route for a locus class (defaults to the full
    factual route for an unknown class)."""
    return ROUTES.get(locus, ROUTES["research"])


class SplitLog:
    """Append-only split record (board-splits.jsonl in the minutes
    dir). One row per ladder step; state() folds the rows into the
    current picture per item: locus, steps taken, resolution."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def record(self, item_key: str, locus: str, step: str,
               detail: str = "", resolution: str = "",
               session_tag: str = "") -> None:
        if locus not in LOCUS_CLASSES:
            raise ValueError(f"unknown locus class: {locus!r}")
        if step not in LADDER:
            raise ValueError(f"unknown ladder step: {step!r}")
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        row = {"event": "split_step", "item_key": item_key,
               "locus": locus, "step": step, "detail": detail,
               "resolution": resolution, "session_tag": session_tag,
               "ts": datetime.now(timezone.utc).isoformat()}
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _rows(self):
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            return

    def state(self) -> dict:
        out: dict = {}
        for row in self._rows():
            if row.get("event") != "split_step":
                continue
            st = out.setdefault(row["item_key"], {
                "locus": row["locus"], "steps": [], "resolution": ""})
            st["steps"].append(row["step"])
            if row.get("resolution"):
                st["resolution"] = row["resolution"]
        return out

    def open_splits(self) -> dict:
        return {k: v for k, v in self.state().items()
                if not v["resolution"]}

    def locus_counts(self) -> dict:
        counts: dict = {}
        for v in self.state().values():
            counts[v["locus"]] = counts.get(v["locus"], 0) + 1
        return counts
