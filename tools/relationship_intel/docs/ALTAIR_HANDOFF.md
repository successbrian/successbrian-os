# Altair spoken-reinforcement handoff — P5 field missions (Saturday dialogue)

This is DOCUMENTATION of a handoff, not a build. The Saturday dialogue itself
is Altair's; P5 only specifies the message format that carries the week's
mission from the pipeline to him.

## Channel

`altair.knowledge_bridge` in ecosystem_central (columns: id, sender, target,
subject, body, urgency, created_at, read_at). Altair's Saturday dialogue
reads unread rows; the established pattern is the same one the 'Talk to the
crew' box uses.

Writer side (whoever runs the Saturday segment research — P6 or the
coordinator): one row per open mission, written Friday alongside the segment
research.

## Row format

- `sender`: 'spencer' (or the pipeline service account that authors it)
- `target`: 'altair'
- `urgency`: 'normal' (a mission expiring this week may use 'high')
- `subject`: `[sat-dialogue] field mission #<mission_id> — <target_name>`
- `body`: plain text with three blocks, in this order:

```
MISSION (for Brian, spoken):
  This week's field mission: capture <what_to_capture> for <target_name>.
  <one-line instruction, e.g. "Screenshot each scroll page of the friends
  list so names and handles are visible.">

HOW TO COMPLETE (spoken, brief):
  Upload the screenshots here in chat, then answer the mission question with
  "done, N screenshots".

INTEL NOTE (not spoken; context for Altair only):
  Mission <mission_id> created <date> from proposal <proposal_id> (<reason>).
  Edges will land in people.social_connections as source='field_capture:<mission_id>'.
  If Brian asks why this target: <reason from the proposal>.
```

## Lifecycle

1. P4 proposes -> P5 creates mission row (kind='mission', answer_type='free_text').
2. Friday research writes the bridge row above.
3. Saturday: Altair speaks the MISSION + HOW TO COMPLETE blocks verbatim-ish;
   the INTEL NOTE stays unsaid (it's his briefing).
4. Brian screenshots + uploads to chat (media_library/captures/) -> dumb pipe
   -> k11 ingestion. He answers the mission row free_text ("done, N
   screenshots") -> P5 marks it complete at the next hourly pass.
5. If a mission is still open the following Friday, the research step re-sends
   with urgency='high' and a one-line "still open" note; after two weeks it is
   marked stale (status='stale') and dropped from the dialogue.

## Why not a podcast question read-out only

The mission row lives in podcast_questions, but Brian interacts with the
podcast UI on his own schedule. The Saturday spoken mention is the
reinforcement: he hears it, he does it that weekend, the captures land while
the mission is fresh. The dialogue is the trigger; the question row is the
receipt.
