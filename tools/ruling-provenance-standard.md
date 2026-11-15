# The Ruling-Provenance Standard

*Fleet standard, 2026-11-15. Ordered by Brian: "whatever system created
that ruling needs to be evaluated — and improved." Guard machinery:
`tools/ruling_audit.py` (PM project `sbos-ruling-audit`, QA check 687).
Full evaluation: `~/workspace/builds/ruling-pipeline-audit-2026-11-15.md`.*

## The failure this standard exists to prevent

**Assistant interpretation hardened into Brian's record.** A writer
reads Brian's words, interprets them, and records the interpretation
with the authority of a ruling. Downstream work then consumes the
record — never the words — and the interpretation compounds.

Known specimens:

1. **The systeme.io "platform ruling"** (2026-10-28 → corrected
   2026-11-15). Brian: "we need to plan an aoem blog. a systeme.io blog
   for sure." The daily log recorded `[decision|high] … PLATFORM
   DECIDED … the AoEM blog will be a SYSTEME.IO blog (not Wix)`.
   Brian's correction: "systeme.io blog is a blog about systeme.io —
   it is not a ruling on which platform to use." The misreading drove
   a planning package, an evaluation recommendation, and a
   "contradiction" flag against a database row that had done nothing
   wrong.
2. **The Atlas "one sentence" summary rule** — an assistant's
   tightening of the 2026-10-20 store discipline, reported back as
   Brian's rule. Corrected by Brian 2026-11-14.
3. **The P40 in the Mistral seat spec** — an assistant recommendation
   recorded as if Brian had chosen it.
4. **"David Foesch is NOT Rolodex David"** — absence of a record
   converted into a negative fact.

## The standard

1. **A ruling carries its words.** Any entry tagged ruling / decision /
   directive — in a daily log, in MEMORY.md, in a capture, in a
   planning document — must quote Brian's verbatim words for the point
   being recorded. If his exact words are not available, the headline
   must carry the label **INTERPRETATION** (or be filed as a proposal).
   An unlabeled, unquoted ruling claim is a defect, and
   `ruling_audit.py` flags it as the no-quote class.
2. **The claim asserts no more than the quote plainly carries.**
   Read the quote literally before writing the claim. In particular:
   a quote that *names or mentions* a thing is not a *decision about
   that thing's properties* (platform, owner, price, scope, partner).
   A wish is not a plan. A topic is not a ruling.
3. **Hedges travel.** If Brian said "I believe", "likely", "might",
   "potentially", the claim records a belief / likelihood / possibility
   — never the flattened fact.
4. **Absence is not a negative.** No record of X is recorded as
   "not on record", never as "X is not / does not / never".
5. **Consumers re-read the words.** Before any downstream artifact
   (planning package, evaluation, brief, registry flag, MEMORY.md
   promotion) repeats a ruling, the writer re-reads Brian's quoted
   words in the source entry — not the entry's headline, not another
   artifact's summary of it. A contradiction flag against another
   record (a database row, a person's statement) may only be asserted
   after that re-read; if the words don't plainly carry the claim, the
   flag is filed against the *entry*, as a question, not against the
   other record as an error.
6. **Promotion preserves provenance.** When a daily-log entry is
   promoted into MEMORY.md, the quote (or the INTERPRETATION label)
   travels with the claim, along with the source date. MEMORY.md is a
   curation of the logs, not a new authority above them.
7. **Corrections are appended, dated, and attributed** — never silent
   rewrites. The original text stands as history; the correction names
   what it supersedes. (Existing practice; this standard makes it a
   requirement, and it is how specimens 1–2 above were closed.)

## Where this standard lives

- This doc (fleet canonical): `successbrian-os/tools/ruling-provenance-standard.md`
- The seats' filing skill: `tools/atlas/atlas-manage-skill/SKILL.md`
  (rule: rulings filed without Brian's verbatim words are labeled
  INTERPRETATION at filing time)
- The main writer's operating manual: `~/AGENTS.md` lessons
- The audit report that created it:
  `~/workspace/builds/ruling-pipeline-audit-2026-11-15.md`

## The guard

`tools/ruling_audit.py` scans the daily logs + MEMORY.md, extracts
every ruling/decision claim and its quotes, and runs Brian's
deliberation flow over them: Penny/Morpheus-class sweep (does the
claim follow, read plainly, from the quoted words alone?), then a
Sonic-class deep pass over everything the sweep flags plus a 10%
audit sample of what it passed. Output classes: **clean**,
**interpretation-risk** (flagged, with the quote, for the fact-check
desk — never auto-corrected), **no-quote** (risk class of its own),
**unresolved**. Weekly QA (check 687) runs the tool's selftest +
extract; a PASS means the tool ran — flags are reported, not gated.
