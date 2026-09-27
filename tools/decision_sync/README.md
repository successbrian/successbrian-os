# Decision Sync

Keeps Brian's decisions, build plans, and AnythingLLM in agreement.

## How it works

```
altair.brian_decisions (PostgreSQL — source of truth)
        │
        ▼
    sync.py ──→ decisions-digest.md ──→ AnythingLLM (searchable view)
        │
        └──→ conflict-report.md (decisions vs build plans)
```

1. **Pull** all decisions from `altair.brian_decisions`, newest first.
2. **Render** a digest doc, grouped by topic.
3. **Cross-check** decisions against `*_build_plan` tables. Flags gaps
   (decision mentions something not in the plan), mismatches (plan says
   X, decision says Y), and stale notes.
4. **Stage** docs locally. **Push** to AnythingLLM when `ANYTHINGLLM_API_KEY`
   is set (graceful skip otherwise).

## Usage

```bash
python3 sync.py --dry-run   # preview, touch nothing
python3 sync.py             # write to staging/
python3 sync.py --push      # also push to AnythingLLM
```

## Rules

- PostgreSQL is the source of truth. Docs are the searchable view.
- Conflicts are **flags for Brian's review** — nothing auto-changes.
- Quarantine, never delete. Dry-run by default.

## Adding new cross-checks

Edit `detect_x79_conflicts()` (or add `detect_<topic>_conflicts()`).
Code owns the workflow — hard-code the rules, don't overthink.
