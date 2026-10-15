# tools/spencer/

Spencer's home inside successbrian-os: the senior advisor's role spec,
routine registry, and working-state contract.

## Layout

- `ROLE.md` — who Spencer is in the org chart, what he owns, his decision
  boundaries, and how he communicates. The human-readable contract.
- `routines.yaml` — registry of Spencer's recurring routines: every cron he
  runs, what it produces, and where the output lands. The machine-readable
  contract. The cron scheduler remains the source of truth for timing; this
  file is the catalog.
- Working state lives in PostgreSQL, not here:
  - `successbrian_os.spencer_state` (key/value working state)
  - `successbrian_os.spencer_threads` (open threads Spencer is carrying)

## Why this exists

Spencer was the only agent without a formal home in the repo — writing to its
tables daily but defined nowhere. This directory makes his responsibilities,
routines, and state legible to Brian, to the other agents, and to future
Spencer instances reading cold.

## Rules for editing

- No secrets in this directory, ever. successbrian-os is public.
- `routines.yaml` describes reality: every entry must match an actual cron
  (see `cron.list`). Never document a guess as a fact.
- Decision boundaries in `ROLE.md` change only on Brian's explicit call.
