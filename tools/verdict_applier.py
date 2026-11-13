#!/usr/bin/env python3
"""Verdict Applier — closes the gamma clerk loop.

REAP (on gamma) judges raw captures one line at a time through bus
reap_infer events (probe 'queue-keeper-reap', fed by the queue keeper).
Until 2026-11-13 nothing applied those verdicts: judged captures sat at
status='raw' indefinitely (121 raw, 98 already judged, when Brian
ordered the fix). The earlier bulk applies (2026-11-10/11/12) were
one-off acts by an unidentified mechanism; this tool is the standing one.

For each done keeper event, the verdict text is read from the outbox
inference_result row. Only GOOD verdicts apply — Brian's quality rule:
exactly one line, 'ROUTING: <word> - <reason in words tied to the item>'.
Bare routings, code fences, and chatter are skipped and counted; their
captures stay raw.

An applied verdict writes the same shape as the 2026-11-10 applies:
  status='triaged', recommendation=<mapped routing>,
  score_reasons=<REAP's reason>,
  ruling_why='gamma reap_infer event <id> (<date>, one-line classify)',
  depth=<scattered_brain.depth_for(title, raw, context)> — the same
  deterministic rule the clerk's triage stamps, so gamma-classified
  captures never land 'unclassified' (fixed 2026-11-13, cycle 191:
  26 captures had piled up unclassified because apply() never
  stamped depth),
  triaged_at=now().
Mapping: board->promote-candidate, intel->wf3-kept, kick-aside->park,
discard->discard-candidate. Nothing is deleted — a discard verdict makes
a discard CANDIDATE, never a deletion.

Modes: run | dry-run | selftest. Cron on alpha: every 30 minutes.
"""
import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
sys.path.insert(0, "/home/successbrian/successbrian-os/tools/atlas")
import sbos_common  # noqa: E402
from scattered_brain import depth_for  # noqa: E402

ROUTING_MAP = {
    "board": "promote-candidate",
    "intel": "wf3-kept",
    "kick-aside": "park",
    "discard": "discard-candidate",
}
VERDICT_RE = re.compile(
    r"^ROUTING: (board|kick-aside|intel|discard) - (.+)$")
TITLE_RE = re.compile(r"Item title: (.*?)\. Item text: ", re.S)


def parse_verdict(text):
    """(routing, reason) for a GOOD verdict line, else None."""
    if not text:
        return None
    line = text.strip()
    if "\n" in line:
        return None
    m = VERDICT_RE.match(line)
    if not m:
        return None
    reason = m.group(2).strip()
    if len(reason.split()) < 3:
        return None
    return m.group(1), reason


def extract_title(prompt):
    m = TITLE_RE.search(prompt or "")
    return m.group(1) if m else None


def rowval(row, key, idx):
    return row[key] if isinstance(row, dict) else row[idx]


def load_verdicts():
    """event_id -> verdict text, from outbox inference_result rows."""
    rows = sbos_common.pg_rows(
        "SELECT body FROM successbrian_os.outbox "
        "WHERE message_type = 'inference_result' "
        "AND created_at > now() - interval '30 days'")
    out = {}
    for r in rows:
        body = rowval(r, "body", 0)
        try:
            data = json.loads(body)
        except Exception:
            continue
        if data.get("event_type") != "reap_infer" or not data.get("ok"):
            continue
        text = (data.get("result") or {}).get("text")
        if text:
            out[data.get("event_id")] = text
    return out


def done_keeper_events():
    return sbos_common.pg_rows(
        "SELECT id, payload->>'prompt' AS prompt, completed_at "
        "FROM bus.events WHERE event_type = 'reap_infer' "
        "AND payload->>'probe_id' = 'queue-keeper-reap' "
        "AND status = 'done' ORDER BY id DESC")


def find_raw_capture(title):
    """(id, title, raw_text, context) for the oldest raw capture with
    this title, else None."""
    return sbos_common.pg_one(
        "SELECT id, title, raw_text, context "
        "FROM atlas.scattered_captures "
        "WHERE status = 'raw' AND title = %s "
        "ORDER BY created_at ASC LIMIT 1", (title,))


def apply(capture_id, event_id, event_date, routing, reason, depth, dry):
    if dry:
        return
    sbos_common.pg_exec(
        "UPDATE atlas.scattered_captures SET status = 'triaged', "
        "recommendation = %s, score_reasons = %s, ruling_why = %s, "
        "depth = %s, "
        "triaged_at = now() WHERE id = %s AND status = 'raw'",
        (ROUTING_MAP[routing], reason,
         f"gamma reap_infer event {event_id} "
         f"({event_date}, one-line classify)", depth, capture_id))


def run(dry=False):
    verdicts = load_verdicts()
    events = done_keeper_events()
    applied = {}
    skipped_bad = 0
    skipped_orphan = 0
    seen_titles = set()
    for ev in events:
        eid = rowval(ev, "id", 0)
        prompt = rowval(ev, "prompt", 1)
        completed = rowval(ev, "completed_at", 2)
        title = extract_title(prompt)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        parsed = parse_verdict(verdicts.get(eid))
        if not parsed:
            skipped_bad += 1
            continue
        capture = find_raw_capture(title)
        if capture is None:
            skipped_orphan += 1
            continue
        capture_id, cap_title, cap_raw, cap_ctx = capture
        depth = depth_for(cap_title, cap_raw, cap_ctx)
        routing, reason = parsed
        date_s = (completed.strftime("%Y-%m-%d")
                  if hasattr(completed, "strftime") else "unknown")
        apply(capture_id, eid, date_s, routing, reason, depth, dry)
        applied[routing] = applied.get(routing, 0) + 1
    raw_left = sbos_common.pg_one(
        "SELECT count(*) FROM atlas.scattered_captures "
        "WHERE status = 'raw'")
    split = ", ".join(f"{k} {v}" for k, v in sorted(applied.items()))
    print(f"[{'DRY' if dry else 'APPLIED'}] {sum(applied.values())} "
          f"verdicts ({split or 'none'}); skipped {skipped_bad} "
          f"unparseable, {skipped_orphan} no-raw-match; "
          f"raw remaining {raw_left}")
    return 0


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    good = parse_verdict(
        "ROUTING: intel - Outside company news worth filing.")
    check("good verdict parses",
          good == ("intel", "Outside company news worth filing."))
    check("bare routing rejected",
          parse_verdict("ROUTING: intel") is None)
    check("short reason rejected",
          parse_verdict("ROUTING: intel - news") is None)
    check("two-line rejected",
          parse_verdict("ROUTING: intel - a real reason here\n"
                        "second line") is None)
    check("code fence rejected",
          parse_verdict("```python") is None)
    check("chatter rejected",
          parse_verdict("The road is open.") is None)
    check("title extracts",
          extract_title("... Item title: Some Title Here. "
                        "Item text: body") == "Some Title Here")
    check("mapping covers all four routings",
          set(ROUTING_MAP) == {"board", "intel", "kick-aside",
                               "discard"})
    check("depth: cycle title is system_self",
          depth_for("Spencer cycle: 131 QA checks failing")
          == "system_self")
    check("depth: plain title defaults team_working",
          depth_for("Miniflux: Bitcoin holds below $70K")
          == "team_working")
    check("depth: brian marker escalates (title-only)",
          depth_for("BRIAN TO DO - rule on the queue")
          == "brian_decision")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if argv and argv[0] == "selftest":
        return selftest()
    if argv and argv[0] == "dry-run":
        return run(dry=True)
    if argv and argv[0] == "run":
        return run(dry=False)
    print("usage: verdict_applier.py run | dry-run | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
