# Venture toolkit (tools/ventures/)

Helps a multi-income-stream solopreneur take a raw business idea all the way
to a tracked goal. Built per Brian 2026-09-30: successbrian-os should help an
entrepreneur flesh out business ideas, document them in the database, then
help build goals the way he and Spencer do it.

## Lifecycle

```
capture  ->  flesh  ->  score  ->  promote  ->  (Spencer creates the goal)
  raw       fleshed    scored      drafted
```

1. **capture** — one-liner title + pitch, optional stream tags. Status `raw`.
2. **flesh** — guided questionnaire (11 fields: problem, customer, offer,
   revenue model, price point, startup cost, weekly hours, stream fit, risks,
   first 3 steps, notes). `--answers-json` for non-interactive use.
   `questions` asks local Morpheus for 5 tailored follow-ups on the pitch.
   Status `fleshed`.
3. **score** — deterministic rubric, 0–100, band strong / consider /
   reshape-or-shelve / **needs-answers** (the last means the profile is too
   thin to judge yet — not a verdict on the idea). The score proposes; the
   entrepreneur decides.
   Status `scored`.
4. **promote** — builds a goal draft (title, description, milestones:
   validate → first steps → first dollar → 30-day review) into
   `successbrian_os.goal_drafts`. Status `drafted`. Spencer creates the real
   tracked goal from an approved draft — code drafts, human approves.

## Prospector (tools/ventures/prospect.py)

Brian 2026-09-30: "can it dig through my ideas in my database and anythingllm
and find a bunch?" `prospect.py scan` sweeps `altair.brian_learnings`
(BLOG:/[tag] prefixes, venture keywords), `altair.brian_decisions` (CMS/blog/
launch questions), and AnythingLLM workspace docs (read-only SQLite) for
idea-like rows, dedupes against the ventures table, and `capture --ids ...`
inserts the approved ones. `--first-pass` parses a blog learning's own text
into an honest starter profile (offer, traffic angle, monetization, effort,
edge) — anything it can't know stays blank for the entrepreneur.

## Rules

- Everything lives in the DB (`successbrian_os.ventures`, `goal_drafts`).
  No markdown for ideas or decisions.
- Local-first: Morpheus questions are optional and free; everything else is
  pure Python.
- No model decides anything. The rubric is transparent and tunable
  (see scoring.py).
