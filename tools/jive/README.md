# Jive — conversation synthesis worker

Reads the conversation ledger and produces a running "state of everything":
a summary, duplicate detection (same request across sessions), and
related-item links. Deterministic — no model, no cloud.

## Layout

- `jive.py` — the worker. `run` processes new captures/tasks; `status` shows the watermark.
- `capture.py` — the sanctioned writer for the ledger. Agents call it after each turn.
- `schema.sql` — idempotent schema (ledger, flags, links, summaries, watermark state).

## The on-demand rule

Jive runs only when there is new input. A watermark
(`successbrian_os.jive_state`: `last_capture_id` + `last_run_at`) tracks
what has been processed. A run with nothing new exits silently and writes
nothing — no junk summary rows.

## Usage

```bash
# one-time setup (idempotent)
psql -d ecosystem_central -f tools/jive/schema.sql

# check state
python3 tools/jive/jive.py status

# process new input (cron calls this every 30 min; exits quietly when idle)
python3 tools/jive/jive.py run

# preview without writing
python3 tools/jive/jive.py run --dry-run

# an agent records a turn
python3 tools/jive/capture.py --session abc123 --agent altair \
  --user "what is the cheapest adequate X79 RAM option" \
  --assistant "8x32GB DDR4-3200 RDIMMs, one per channel" \
  --model morpheus
```

## Wiring the capture feed (for agent builders)

After each chat turn, call `capture.py` (or import `capture()`) with the
session id, agent name, user message, and response. That is the entire
contract — jive picks the row up on its next run. See `capture.py` NOTES
for what not to record.
