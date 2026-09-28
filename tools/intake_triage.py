#!/usr/bin/env python3
"""
Intake triage worker: research pending intake items, score relevance, resolve.

PURPOSE:
    Drain the intake_items queue. Every incoming item (notification, email,
    calendar event, offer, intel) sits in the table as 'pending' until this
    worker researches what it actually is and scores whether it matters to
    Brian. Relevant items surface to the second brain (so the board's morning
    brief and digests pick them up); everything else stays in the table,
    researched but silent.

WHY:
    Brian 2026-09-27: incoming volume never implies importance. Notifications,
    emails, offers, and intel arrive constantly; treating arrival as priority
    is how noise becomes the day's agenda. The intake queue is the airlock:
    nothing reaches Brian, the board, or the digests until triage has
    researched it and judged it relevant. Strict by design — most incoming
    is noise, and the worker must be comfortable saying so.

CALLED BY:
    - A triage driver with web-research tooling (today: an agent; future:
      the triage cron Brian hasn't scheduled yet). Driver flow:
        1. intake_triage.py --pending --limit N   -> JSON of pending items
        2. research each item (1-2 web searches: who is the sender, what is
           the domain/offer, is it tied to Brian's world?)
        3. intake_triage.py --resolve ID --status relevant|not_relevant
             --relevance 0.0-1.0 --notes "..."
    - Humans: --stats for queue health, --dry-run to preview.

NOTES:
    - Web research is done by the DRIVER, not this script: there is no
      server-side search API on the VM, and 1-2 cheap searches per item is a
      judgment call an agent makes. This script is pure queue mechanics so it
      stays testable and idempotent.
    - Idempotent: --resolve only touches rows still 'pending'. Re-running a
      resolve on an already-resolved row is a no-op (reported, not an error).
    - 'relevant' also writes a second_brain observation (category
      observation, tags intake) via tools/second_brain.py as a subprocess —
      same pattern as the board harness's SecondBrainSink.
    - Relevance rubric (for drivers): 0.0-0.3 noise/unsolicited/unrelated;
      0.4-0.6 possibly interesting but not actionable; 0.7-1.0 actionable or
      genuinely tied to Brian's work (blog network, MLM GotBackup/Oliabo,
      affiliate, hardware flipping, trading, home lab, job hunt).
    - Table lives in the public schema of the ecosystem_central database
      (public.intake_items), despite the 'ecosystem_central.' prefix in older
      notes — verified 2026-09-27.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"
SECOND_BRAIN = Path(__file__).resolve().parent / "second_brain.py"

VALID_STATUSES = ("relevant", "not_relevant", "archived")


def esc(s: str) -> str:
    return s.replace("'", "''")


def pg(query: str, timeout: int = 60) -> str:
    out = subprocess.run(
        [str(KSSH), f'psql -d ecosystem_central -t -A -c "{query}"'],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def pending(limit: int) -> list[dict]:
    rows = pg(
        "SELECT id, source, source_id, received_at, title, sender, url, raw "
        f"FROM public.intake_items WHERE status='pending' "
        f"ORDER BY received_at ASC LIMIT {int(limit)};"
    )
    items = []
    for line in rows.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 7)
        items.append({
            "id": int(parts[0]), "source": parts[1],
            "source_id": parts[2] or None, "received_at": parts[3],
            "title": parts[4] or None, "sender": parts[5] or None,
            "url": parts[6] or None,
            "raw": json.loads(parts[7]) if parts[7] else None,
        })
    return items


def stats() -> dict:
    rows = pg(
        "SELECT status, count(*) FROM public.intake_items GROUP BY status;"
    )
    out = {"pending": 0, "researching": 0, "relevant": 0,
           "not_relevant": 0, "archived": 0}
    for line in rows.splitlines():
        if "|" in line:
            s, c = line.split("|", 1)
            out[s.strip()] = int(c)
    return out


def resolve(item_id: int, status: str, relevance: float, notes: str,
            dry_run: bool = False) -> str:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    if not (0.0 <= relevance <= 1.0):
        raise ValueError("relevance must be 0.0-1.0")

    cur = pg(f"SELECT status, title FROM public.intake_items WHERE id={int(item_id)};")
    if not cur:
        return f"id {item_id}: not found"
    cur_status = cur.split("|", 1)[0].strip()
    if cur_status != "pending":
        return f"id {item_id}: already '{cur_status}' — no-op (idempotent)"

    if dry_run:
        return (f"id {item_id}: DRY RUN would set status={status} "
                f"relevance={relevance} notes={notes[:60]!r}")

    pg(
        "UPDATE public.intake_items SET status='" + esc(status) + "', "
        f"relevance={relevance}, research_notes='{esc(notes)}', "
        "researched_at=now(), researched_by='intake_triage' "
        f"WHERE id={int(item_id)} AND status='pending';"
    )

    extra = ""
    if status == "relevant":
        title = cur.split("|", 1)[1].strip() if "|" in cur else f"item {item_id}"
        r = subprocess.run(
            [sys.executable, str(SECOND_BRAIN),
             "--topic", f"Intake relevant: {title[:120]}",
             "--content", notes[:1500],
             "--category", "observation",
             "--confidence", "medium",
             "--source", "intake-triage",
             "--tags", "intake"],
            capture_output=True, text=True, timeout=90,
        )
        extra = " + second_brain" if r.returncode == 0 else \
            f" (second_brain FAILED: {r.stderr.strip()[:120]})"
    return f"id {item_id}: resolved {status} relevance={relevance}{extra}"


def main() -> int:
    p = argparse.ArgumentParser(description="Intake triage queue worker")
    p.add_argument("--pending", action="store_true",
                   help="list pending items as JSON (oldest first)")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--resolve", type=int, metavar="ID",
                   help="resolve one pending item")
    p.add_argument("--status", choices=VALID_STATUSES)
    p.add_argument("--relevance", type=float, default=0.0)
    p.add_argument("--notes", default="")
    p.add_argument("--stats", action="store_true",
                   help="show queue counts by status")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.stats:
        print(json.dumps(stats(), indent=2))
        return 0
    if a.pending:
        print(json.dumps(pending(a.limit), indent=2))
        return 0
    if a.resolve is not None:
        if not a.status:
            print("--status required with --resolve", file=sys.stderr)
            return 2
        print(resolve(a.resolve, a.status, a.relevance, a.notes, a.dry_run))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
