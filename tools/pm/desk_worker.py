#!/usr/bin/env python3
"""Desk worker — slice 5 of the coded-loop upgrade (SBOS main PM).

The CampaignsDesk pass Brian ruled on (four times a day): the desk had
intake with no owning worker; now its signals flow into the PM, which
owns the work from there.

Each pass:
  1. Takes up to BATCH unprocessed campaignsdesk.signals (oldest first)
     and files each as a PM step (kind 'desk', priority 35 — below live
     work; the claim starvation guard surfaces them over time). The
     signal is then marked processed: handed off, with the PM step as
     its receipt. Deduped by step key, so re-runs never double-file.
  2. Ensures known DealsDesk follow-up work exists as a PM step
     (the stale-sweep that never got a scheduler).
  3. Writes one decision to the stream when it filed anything.

The worker prepares and hands off; it never publishes — Brian's
approval rule for anything audience-facing stands. Deterministic code;
the LLM-shaped desk work (briefs, angles) routes later per the DeepSeek
ruling: subprocesses when balance allows, gameplan steps when empty.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

BATCH = 10


def run_pass():
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        """SELECT id, kind, title FROM campaignsdesk.signals
            WHERE processed_at IS NULL ORDER BY created_at LIMIT %s""",
        (BATCH,))
    rows = cur.fetchall()
    filed = 0
    for r in rows:
        sid = r["id"] if isinstance(r, dict) else r[0]
        kind = r["kind"] if isinstance(r, dict) else r[1]
        title = (r["title"] if isinstance(r, dict) else r[2]) or "(untitled signal)"
        key = f"desk-signal-{sid}"
        cur.execute("SELECT 1 FROM successbrian_os.pm_steps WHERE step_key=%s", (key,))
        if cur.fetchone() is None:
            pm_core.add_step(
                cur, key, f"CampaignsDesk signal ({kind}): {title}"[:300],
                kind="desk", origin="system", priority=35,
                payload={"signal_id": sid, "signal_kind": kind})
            filed += 1
        cur.execute(
            "UPDATE campaignsdesk.signals SET processed_at=now() WHERE id=%s",
            (sid,))
    # DealsDesk handoff: known open follow-up becomes a PM step, once.
    cur.execute(
        "SELECT 1 FROM successbrian_os.pm_steps WHERE step_key=%s",
        ("desk-dealsdesk-stale-sweep",))
    if cur.fetchone() is None:
        pm_core.add_step(
            cur, "desk-dealsdesk-stale-sweep",
            "DealsDesk: stale-sweep has no scheduler — wire it or retire it",
            kind="build", origin="system", priority=45,
            payload={"source": "dealsdesk leftover, 2026-10-22"})
        filed += 1
    if filed:
        pm_core.decide(cur, "desk-worker",
                       f"Desk pass: filed {filed} item(s) into the PM "
                       f"({len(rows)} CampaignsDesk signal(s) handed off)",
                       origin="system")
    c.commit()
    c.close()
    print(f"desk pass: {len(rows)} signal(s) read, {filed} item(s) filed")
    return filed


def main():
    run_pass()
    return 0


if __name__ == "__main__":
    sys.exit(main())
