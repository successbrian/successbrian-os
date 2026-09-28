"""
Dry-run: verify 2 seats end-to-end against Morpheus before wiring the cron.

WHY:
    The harness must be proven against the real model, not mocks — the Sep
    2026 failure mode was a board that "worked" in theory while producing
    nothing. This runs Chief MLM Officer (wave 1) then CFO (wave 2, fed the
    MLM output as context) with a canned test brief, and prints latencies,
    parsed calls, and gate verdicts. If this passes, the session machinery
    is sound; the 3:30 AM cron runs the full 9 seats.

CALLED BY:
    Humans, manually: python3 board/test_dryrun.py [--config board/config/brian.yaml]

NOTES:
    Uses a canned brief (no kssh/psql dependency) so the test isolates the
    worker + parse + gate path. Does NOT touch second_brain (sink is jsonl
    to /tmp). Morpheus measured ~75s/call; timeout 180s per call.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from board.harness.brief import Brief
from board.harness.gate import apply_gate
from board.harness.seats import Seat, load_config
from board.harness.worker import ModelWorker

TEST_BRIEF = """[night_shift]
No night-shift report found in the inbox (test brief).

[recent_decisions]
- Board harness built; 9 seats configured (high, 2026-09-27)

[mlm]
GotBackup signups flat 3 days at ~4/day. Oliabo volume up 12% this week.
One affiliate asked about white-label pricing. New-lead email sequence
not updated in 6 weeks.
"""

TEST_WAVE1_CONTEXT = """Chief MLM Officer:
- Refresh the GotBackup new-lead email sequence this week. (why: 6 weeks stale, flat signups)
- Pilot white-label pricing for the requesting affiliate. (why: tests a new revenue lever)"""


def main() -> int:
    cfg_path = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else "board/config/brian.yaml"
    cfg = load_config(cfg_path)
    m = cfg["model"]
    worker = ModelWorker(
        base_url=m["base_url"], model=m["name"], timeout_s=180,
        via=m.get("via", "direct"),
    )
    seats = {s["title"]: Seat.from_dict(s) for s in cfg["seats"]}

    mlm = seats["Chief MLM Officer"]
    cfo = seats["Chief Financial Officer"]

    print(f"== {mlm.title} (wave 1) ==")
    r1 = worker.run_seat(mlm, TEST_BRIEF)
    print(f"ok={r1.ok} latency={r1.latency_s:.0f}s attempts={r1.attempts}")
    for c, r in r1.calls:
        print(f"  CALL: {c}\n  WHY:  {r}")
    if not r1.ok:
        print(f"  NOTE: {r1.note}")
        return 1

    print(f"\n== {cfo.title} (wave 2, fed wave-1 output) ==")
    r2 = worker.run_seat(cfo, TEST_BRIEF, TEST_WAVE1_CONTEXT)
    print(f"ok={r2.ok} latency={r2.latency_s:.0f}s attempts={r2.attempts}")
    for c, r in r2.calls:
        g = apply_gate(c, r, cfo.title, 0.90, brief_had_state=True)
        print(f"  CALL: {c}\n  WHY:  {r}\n  GATE: {g.verdict} ({g.confidence:.2f}) — {g.reason}")
    if not r2.ok:
        print(f"  NOTE: {r2.note}")
        return 1

    print("\nDRY-RUN PASS: worker + parse + gate all functional against Morpheus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
