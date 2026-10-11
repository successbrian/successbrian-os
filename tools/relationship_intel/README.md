# relationship_intel / P5 — field capture loop ("the new Vera", supplement input)

Brian is a sensor the systems lack. The pipeline requests specific captures
("capture X's friends list"), he screenshots + uploads via chat, the graph
absorbs them.

## Components

| File | Runs on | What |
|---|---|---|
| `schema.sql` | k11 (people_unified) | proposals (P4 contract), missions, file manifest |
| `p5_missions.py` | k11 | REQUEST: consume `status='proposed'` proposals -> `podcast_questions` `kind='mission'` / `answer_type='free_text'` rows; completion check |
| `p5_ingest.py` | k11 | INGEST: tesseract OCR -> regex extraction (Penny fallback) -> match/create -> typed edges |
| `p5_hourly.sh` | k11 | hourly wrapper: missions poll + completions + ingest |
| `p5_pipe.sh` | Hatch VM | DUMB rsync: `media_library/captures/` -> k11 `captures_intake/` (no intelligence, no tokens) |
| `relationship-intel-p5.cron` | k11 /etc/cron.d | schedule: `45 * * * *` (staggered; :45 verified free) |
| `docs/ALTAIR_HANDOFF.md` | — | knowledge-bridge subject/body format for the Saturday spoken reinforcement |

## Mission lifecycle

1. P4 writes `people.capture_mission_proposals` (status='proposed'). Ops backdoor:
   `p5_missions.py --local-queue proposals.json` stages ad-hoc proposals.
2. Hourly: `--poll` creates the mission row
   (`successbrian_os.podcast_questions`, kind='mission', answer_type='free_text'),
   resolves/creates the target's `people.people` row, records
   `people.field_capture_missions`, flips proposal to 'requested'.
   Backup channel on primary failure: `successbrian_os.pending_questions`
   (asked_by='spencer'), proposal -> 'requested_backup'.
3. Friday research writes the Altair bridge row (see docs/ALTAIR_HANDOFF.md);
   Saturday Altair speaks the mission.
4. Brian screenshots + uploads to chat -> `~/workspace/user/media_library/captures/`
   -> dumb pipe (Hatch :35) -> `/home/successbrian/captures_intake/` on k11.
   File naming convention: `mission<id>_<seq>.png` (e.g. `mission17_01.png`).
   Files without a mission id attach to the newest OPEN mission; with no open
   mission they park in `needs_review/` — no edges fabricated.
5. Hourly :45: OCR -> extraction -> match/create -> typed edges in
   `people.social_connections` with `source='field_capture:<mission_id>'`,
   `relation_type` friend/follower/following, confidence summarized on the file
   manifest (`people.field_capture_files.notes`; social_connections has no
   notes column).
6. Brian answers the mission row free_text ("done, N screenshots") ->
   `--check-completions` marks it complete.

## Graph, not tree

Nodes keep multi-facet `tags[]`; `add_tags()` is additive-only — matched
people keep every existing tag. Edges are typed (platform, relation_type,
source). No single-category column anywhere in this pipeline.

## Dedupe (adapted from tools/people_migrate/migrate_oliabo_leads.py)

- Handle hit in `people.social_profiles` -> name-verified (migrate verdict
  logic): match or `dup_sparse` links; conflict -> new tagged row, never a
  silent merge.
- Else exact normalized-name hit in `people.people` (first+last).
- Else create: source='field_capture', tags=['field_capture'] (+ capture_target
  for mission targets), handle/platform in extra_data.
- Edge dedupe: same target + relation_type + name/handle + field_capture
  source prefix -> skip.

## Extraction ladder (deterministic first)

1. Regex on OCR text: `@handle` tokens + Title-Case name lines, UI-noise
   filtered (friends/followers/search/follow/menu words, counts, timestamps).
2. Penny 7B (127.0.0.1:11438) ONLY when regex finds zero names from >= 20
   chars of OCR text. There is no vision model on the free ladder today, so
   tesseract is a hard dependency — its absence fails loudly, never silently.

## Ops

```bash
# request side
python3 p5_missions.py --poll --check-completions
python3 p5_missions.py --list-open
python3 p5_missions.py --local-queue /path/to/proposals.json

# ingest one file (testing)
/home/successbrian/captures_intake  # drop mission<id>_01.png here
python3 p5_ingest.py --once /home/successbrian/captures_intake/mission<id>_01.png

# logs
tail -f /home/successbrian/logs/relationship_intel/p5_hourly.log
```

## Known v1 limits (refine, don't silently discard)

- Exact-name matching only (no fuzzy); misspellings create dup rows tagged for
  review.
- Edges are one-directional (target -> connection); reciprocal edges deferred.
- Unassigned captures park in `needs_review/` rather than guessing.
- `podcast_questions` has no proposal/mission columns; the P5 mapping table
  carries the link (cross-DB, so no FK — documented, not hidden).
