# AnythingLLM Cleanup Automation — Specification v1

**Author:** Spencer · **For:** Altair (k11-alpha) to build · **Consumer:** Spencer (polls reports)
**Status:** Draft — ready for Altair to implement

## Background

Brian's AnythingLLM "second brain" is messy: duplicates, orphans, uncategorized
documents, workspaces with no clear taxonomy. Division of labor: **Spencer designs
the cleanup passes, Altair builds the automation** (Python, scheduled jobs).
Brian approves anything destructive.

AnythingLLM evicts stale data on its own over time — the automation works *with*
that, never against it. The mess is structural (dupes, orphans, no taxonomy),
not staleness.

## Ground rules (non-negotiable)

1. **Quarantine, never delete.** Suspect documents move to a `quarantine`
   workspace. Nothing is hard-deleted by automation. Ever.
2. **Dry-run first.** Every job defaults to dry-run, producing a report. Live
   mode needs an explicit flag AND a previously reviewed report.
3. Destructive actions (empty quarantine, drop a workspace) need Brian's
   explicit approval, relayed via Spencer. No exceptions.
4. Every action logs what / when / why / before-and-after location. Keep logs 90 days.
5. Jobs run on schedule (nightly, low-traffic hours America/Chicago) — not on poll.
6. Altair holds the AnythingLLM API key server-side; it never appears in reports,
   logs, or repos.

## Job 1 — Dedup scan

- **What:** find duplicate and near-duplicate documents.
- **How:** group by normalized title; within groups compare content hashes
  (exact matches) and simhash/MinHash (near matches). Similarity threshold via
  env (`DEDUP_THRESHOLD`, default 0.92).
- **Output:** groups with similarity scores, locations, and a recommended keeper
  (rule: most-cited wins, tie → newest).
- **Live action:** move losers to `quarantine`, keeper stays. Never auto-delete.

## Job 2 — Orphan & hygiene scan

- Documents in no workspace → suggest a workspace by keyword classifier; low
  confidence → park in `unsorted` workspace for review.
- Empty workspaces → flag for Brian's review. Never drop automatically.
- Workspaces over `WORKSPACE_SIZE_THRESHOLD` documents (default 2000) → flag
  for splitting, with a suggested split.

## Job 3 — Embedding health

- Documents with missing or failed embeddings → re-embed.
- Report counts per run. If the failure *rate* spikes vs. the rolling average,
  that's a pipeline problem, not a data problem — raise severity to `warn` and
  say so in the report.

## Job 4 — Staleness visibility

- Don't fight AnythingLLM's own eviction — **report** it. Track what's aging out
  vs. what's lingering past `EXPECTED_TTL_DAYS` (default 180) without being
  touched or cited. The lingering set is the real mess candidate.
- Output: counts + sample titles of lingering docs per workspace.

## Reporting — `GET /library/cleanup-report`

Spencer polls this daily. Follows the gateway's auth and envelope conventions.

Response `data`:

```json
{
  "generated_at": "2026-09-27T12:00:00Z",
  "jobs": {
    "dedup":      {"ran_at": "...", "mode": "dry-run", "duplicates_found": 12, "quarantined": 0},
    "hygiene":    {"ran_at": "...", "mode": "dry-run", "orphans": 34, "empty_workspaces": 2},
    "embeddings": {"ran_at": "...", "re_embedded": 5, "failure_rate": 0.004},
    "staleness":  {"ran_at": "...", "lingering": 210}
  },
  "findings": [
    {"severity": "info", "job": "dedup", "summary": "12 duplicate groups, 31 docs would move to quarantine"}
  ],
  "needs_brian": [
    {"action": "drop workspace 'old-crypto-2' (empty 90+ days)", "requested_at": "..."}
  ]
}
```

- `severity` ∈ `info` | `warn` | `action-needed`.
- `needs_brian` is the approval queue — Spencer relays these to Brian; nothing
  there executes until he says so.

## Suggested implementation (Altair's choice)

- Python scripts, one per job + a reporter that writes the JSON the endpoint serves.
- `systemd` timers (or cron) nightly ~03:00 America/Chicago.
- Config via env: thresholds, dry-run flag, quarantine workspace name.
- Endpoint served by the same gateway as the other APIs (`/api/v1/library/cleanup-report`).

## Spencer-side polling

| Feed | Cadence | On signal |
|---|---|---|
| `/library/cleanup-report` | daily | `action-needed` → relay to Brian; `needs_brian` non-empty → ask Brian for approvals |
