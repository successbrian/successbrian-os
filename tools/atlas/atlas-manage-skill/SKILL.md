---
name: atlas-manage
description: File intel into SuccessBrian OS the moment it surfaces — Intel Bridge captures, Atlas summaries and edges, registry notes, PM projects/tasks — via the shared atlas_manage tool. Use whenever a session uncovers substantive facts, decisions, people, dates, or open items, or when Brian rules/corrects something.
tags: [ecosystem, atlas, filing, intel-bridge, provenance]
category: ecosystem
version: 1.0.0
author: Spencer (fleet build, 2026-11-15)
---

# Atlas Manage — the seat's filing hand

You are a seat in Brian's fleet. Seats are interchangeable; the record
is not. When your work uncovers intel, the ecosystem only knows what
you file — and it only counts if you file it **in the same pass it
arises**, through the sanctioned write paths, with your own seat name
as provenance.

The tool is seat-generic and lives with the fleet's shared code:

```
/usr/bin/python3 /home/successbrian/successbrian-os/tools/atlas/atlas_manage.py <op> --actor <your-seat-name> ...
```

Always pass `--actor` with YOUR seat name (the name in your profile /
IDENTITY). Never file under another seat's name.

Canonical source of this skill:
`successbrian-os/tools/atlas/atlas-manage-skill/SKILL.md` — the copy in
your profile is an installation; the fleet copy governs.

## Brian's rules that govern every filing

1. **Everything dumps** (Brian, 2026-11-14): "chat agents should dump
   dump dump. intel workers dump. everything dumps. the ecosystem
   manages the rest from there." Producers never filter or curate at
   the source. Classification, dedupe, synthesis, and verification
   are downstream work. A dump is part of the turn, not a later chore.
   If it mattered enough to learn, it matters enough to dump — raw,
   now.
2. **Atlas summaries have no sentence limit** (Brian's correction,
   2026-11-14): "i'm not a stickler on the atlas summary — why would
   i have said one sentence only?" A node summary should genuinely
   summarize — state, stakes, pointers — as fully as usefulness
   requires. The discipline underneath: Atlas holds structure +
   pointers + real summaries and must not become a second unversioned
   home for the long-form record, which lives in git docs and
   captures.
3. **Graph, not a tree** (Brian, 2026-10-23): model everything as
   nodes with multiple typed edges. A single path (a funnel, a
   sponsor line, a build order) is one path through the graph, never
   the whole structure. When you learn a relationship, assert the
   edge; expect cross-links and cycles.
4. **Do not guess** (Brian, 2026-10-27). If it isn't in the record or
   verified live, it is UNKNOWN — say so in the filing. **Not knowing
   is not the same as not** (2026-10-23): an absence of record is
   recorded as "not on record", never converted into a negative fact.
5. **Proposals stay proposals.** Your recommendations, assemblies,
   and sharpenings are labeled as yours until Brian explicitly rules
   them. Never write a suggestion into the record as his ruling.
   Preserve Brian's hedges ("I believe", "likely", "might") verbatim.
6. **Nothing goes outward.** These tools write only inside the
   ecosystem. Filing never sends, posts, buys, or contacts anyone.

7. **Rulings carry Brian's words, or the INTERPRETATION label**
   (ruling-provenance standard, 2026-11-15; full text:
   `tools/ruling-provenance-standard.md`). When you file a ruling,
   decision, or directive, quote Brian's verbatim words for the point
   being recorded. If his exact words are not available to you, the
   filing's headline must carry the label **INTERPRETATION** — an
   unlabeled, unquoted ruling claim is a defect (the failure family:
   assistant interpretation hardened into Brian's record; specimen:
   the systeme.io "platform ruling", corrected by Brian 2026-11-15).
   The claim asserts no more than the quote plainly carries: a quote
   that names or mentions a thing is not a decision about that thing's
   platform, owner, price, or scope. Hedges in his words ("I believe",
   "likely", "might") stay in the claim. Before repeating a ruling
   from the record, re-read the quoted words in the source entry —
   not the headline, not another artifact's summary of it.

## The filing checklist — where each datum lives

Run the applicable lines in the same pass the intel arises:

- **Raw learning, rulings, corrections, observations** → Intel Bridge:
  `atlas_manage.py capture --actor <seat> --title "<title>" --context "<where this came from>" --raw "<the substance, Brian's words verbatim where he ruled>"`
- **A node's state changed** → Atlas summary:
  `summary-set --node <key> --summary "<full current summary>"` for a
  rewrite, or `summary-append --node <key> --text "<what changed>"`
  for a dated update on a sound summary.
- **A relationship became known** → typed edge:
  `edge --from <key> --to <key> --type <edge-type> --notes "<evidence>"`
- **New work / a blocker** → make it ecosystem-visible:
  `task-add --node <key> --title "<the work or blocker>"`, and for a
  durable build, `pm-register --key <project-key> --title "<title>"`
  (+ `pm-check` for its QA). Unregistered = invisible.
- **A registry record needs a correction** → append, never rewrite:
  `note-append --slug <blog-slug> --note "<correction, dated by the tool>"`
  (campaignsdesk.blogs; history is append-only).
- **A durable fact for your own reasoning** → the second-brain writer
  (`tools/second_brain.py`) as before — AND a bridge capture. The
  second brain is your memory; the bridge is the ecosystem's mouth.
  One without the other is the failure mode this skill exists to end.

## Your safety-net hooks (know they exist)

If your seat has the hooks wired, three shell hooks ride along:
a once-per-session reminder of this rule (first turn); a ledger entry
whenever you run the second-brain writer; and a session-finalize sweep
that files a **missed-filing flag** into the bridge if you wrote to
the second brain but filed no capture in the same window. The flag is
visibility, not punishment — if one lands on you, file the substance
properly and move on.

## Worked shape

Brian rules in your chat: "the community blog comes first; the paid
tool is built for the audience it creates." Same pass, you file:
(1) a capture with his sentence verbatim in `--raw`; (2) a
summary-append on the blog's project node stating the sequence is now
ruled; (3) an edge if a new relationship was named; (4) a task-add for
any blocker the ruling created or killed. Then you answer Brian. The
filing is not a follow-up task — it is part of the turn.
