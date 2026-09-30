# Idea Evaluation System — generic design for a multi-business entrepreneur

A solopreneur running several income streams collects business ideas
constantly — from research, competitors, conversations, idle thought.
Without a system, ideas live in scattered notes, can't be compared, the
loudest idea wins instead of the best one, and scarce hours get spread
across too many half-started things. This spec describes a generic system
that fixes that. It is the design behind `tools/ventures/` (the reference
implementation, built for one entrepreneur); everything here is written to
work for any multi-business owner.

## Principles

1. **Ideas are inventory, not commitments.** Capturing is cheap; starting
   is expensive. The system must make capture nearly free and starting
   deliberate.
2. **Compare, don't just collect.** Every idea gets the same structured
   look, so a blog niche and a consulting offer can be weighed against
   each other honestly.
3. **The system evaluates; the human decides.** Scores propose, the
   entrepreneur disposes. No software ever starts, kills, or funds
   anything on its own.
4. **Hours are the real budget.** Money matters, but for a solopreneur
   time is the binding constraint. Every evaluation is ultimately a
   question about hours.
5. **Portfolio thinking.** A new idea is judged against the existing
   streams, not in a vacuum. A great idea at the wrong time is a bad idea.

## Lifecycle

```
capture → flesh out → evaluate → decide → goal | shelve
  raw       fleshed     scored     drafted
```

- **Capture** (seconds): title, raw pitch, stream tags. No friction —
  friction here loses ideas.
- **Flesh out** (guided): a fixed questionnaire builds a structured
  profile — problem, customer, offer, revenue model, price point,
  startup cost, weekly hours, stream fit, risks, first 3 steps, notes.
  An optional local-AI pass asks tailored follow-up questions to fill
  gaps. Anything unknown stays blank rather than guessed.
- **Evaluate** (deterministic): the rubric below produces a score, a
  band, and a per-dimension breakdown. Every point traces to a profile
  field; nothing is a black box.
- **Decide** (human): strong ideas become goal drafts; thin ones go back
  for answers or a small cheap test; weak ones are shelved *with the
  reason written down* so the thinking isn't lost.
- **Goal** (approved only): a draft becomes a tracked goal with
  milestones — validate the customer, take the first steps, first
  dollar in, then a scheduled keep/fix/shelve review.

## The evaluation rubric

100 points, five dimensions. Tunable per entrepreneur; the defaults:

- **Clarity (20)** — is the picture complete? Filled core fields over
  total core fields. Rewards doing the homework.
- **Economics (25)** — startup-cost bands (cheaper starts score higher),
  a real price point, margin signal, and estimated time to first dollar.
- **Time fit (20)** — weekly hours the idea needs versus the
  entrepreneur's genuinely available hours. An idea that needs 20
  hours from someone who has 6 is a fantasy, scored as one.
- **Stream synergy (20)** — reuses existing streams, audience, or skills
  scores higher. Includes a **cannibalization check**: if the idea
  competes with an existing stream for the same customer or the same
  hour, the system flags it instead of quietly scoring it well.
- **Risk load (15)** — named risks are healthy (writing them down scores
  better than ignoring them), adjusted for **reversibility**: an idea
  that can be killed cheaply outranks one that can't.

**Bands, not verdicts:** strong (70+), consider (45–69),
reshape-or-shelve (below 45), needs-answers (profile too thin to judge —
explicitly *not* a verdict on the idea, just "come back with answers").

## Portfolio view (the multi-business part)

This is what makes it a *multi-business* system rather than an idea list:

- **One board:** every active idea and every existing stream, each tagged
  with its streams and weekly hours.
- **Hour budget:** committed hours summed against available hours. A new
  idea must fit the budget or explicitly displace something. The system
  shows the trade, it doesn't make it.
- **The "one river" nudge:** when the board shows several parallel
  zero-dollar efforts, the system says so plainly and recommends getting
  one stream to first dollar before starting the next. Advice, not a lock.
- **Synergy map:** which ideas feed which streams. An idea that feeds two
  existing streams outranks an equally-scored idea that feeds none —
  the portfolio compounds.

## Prospecting (finding ideas you already have)

Entrepreneurs forget their own ideas. The system re-scans the owner's
existing records on demand — notes databases, decision logs, document
libraries — with transparent keyword/prefix rules, dedupes against the
ideas table, and proposes candidates for capture. Anything it can't
classify confidently is reported, not silently captured.

## What the system does NOT do

- Not a business-plan generator. It structures thinking; it doesn't
  write the plan.
- Never auto-starts, auto-funds, or auto-kills anything. Promotion to a
  goal requires explicit human approval.
- Never deletes shelved ideas. Shelved means parked with a reason,
  searchable when circumstances change.
- No cloud dependency, no per-idea cost. The rubric is pure code;
  any AI assist is local and optional.

## Data model (generic)

- **streams** — the entrepreneur's own income-stream registry
  (user-configured, e.g. content, services, products, investing).
- **ideas** — id, title, raw pitch, status
  (raw/fleshed/scored/drafted/active/shelved), profile (structured JSON),
  score (total, band, breakdown), stream tags, timestamps.
- **goal_drafts** — idea → draft goal (title, description, milestones),
  status draft/approved/created. Approved drafts become real tracked
  goals; the tracking itself lives wherever the entrepreneur tracks goals.

## Reference implementation

`tools/ventures/` in this repo — `ideas.py` (lifecycle CLI),
`prospect.py` (idea prospecting), `scoring.py` (rubric), `goals.py`
(draft builder). Built for one entrepreneur; this spec is the generic
system it implements.
