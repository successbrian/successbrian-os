#!/usr/bin/env python3
"""gamma_queue_keeper.py — keep Gamma's clerk queue fed, from SBOS.

Brian's standing rule (2026-11-10): feed the road first — Gamma
must never sit idle while work it can do is waiting. This keeper
ran as a cloud-agent (Muse) cron until 2026-11-17; Brian ruled
"my ecosystem should do the work, not muse", so it lives here now,
on alpha, every 30 minutes.

What it does (a faithful port of the cron, two fixes included):
- Counts the clerk lane depth (reap_infer pending/processing at
  priority >= 5) and the raw capture pile.
- Fills the lane up to 5, one capture per reap_infer event, using
  the PROMPT V2 template verbatim (tested 2026-11-11: v2 10/10 vs
  v1 4/10), max_tokens 100, probe_id 'queue-keeper-reap'.
- FIX 1 — dedup is EXACT-TITLE: a capture counts as fed only when
  an existing event's embedded "Item title:" equals its title.
  The cron's substring match against payload::text both MISSED
  titles containing a double quote (JSON escapes it) and BLOCKED
  titles that merely appear inside another event's text.
- FIX 2 — reporting lives in the ecosystem: every run writes its
  heartbeat directly into Lyra's table (worker
  'gamma-queue-keeper'); new gamma job failures file ONE Intel
  Bridge capture per run. No chat lines.
- FIX 3 (B24, 2026-11-21) — dedup is TIME-SCOPED: a capture is
  blocked only by an event fed AFTER the capture was created.
  The 2026-11-17 port dropped improvement_log row 40's fix, so a
  same-title event fed BEFORE a capture blocked it for 14 days —
  recurring titles (e.g. '[agent-cycle:ceo] N QA checks failing')
  never reached gamma again. fed_event_times() maps each title
  to its latest fed event's created_at; is_blocked() compares
  against the capture's own created_at.
- NEVER inserts clerk_deep_pass (handler broken, cap 700 —
  SPENCER-NOTE-003). Never more than 5 in line or 5 per run.

Modes: run | dry-run | selftest.
"""
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

WORKER = "gamma-queue-keeper"
LANE_CAP = 5

PROMPT_HEAD = """Classify this one item into exactly one routing. Reply with exactly one single line, nothing else, in this shape: ROUTING: <one word: board, kick-aside, intel, or discard> - <one short sentence saying why, tied to a specific fact in the item>. Do not add a second line.

What the words mean:
- board: the item needs a decision or action by a person — something to buy, sell, join, approve, or reply to. A marketplace want-to-buy or for-sale post for hardware we track counts as board.
- intel: the item is outside-world knowledge worth keeping — news, market or price data, company or crypto developments, security warnings about outside products. File it.
- kick-aside: the item might matter but does not fit board or intel and should not be thrown away — park it for a second look. Use only when you cannot place it in board or intel.
- discard: the item has no lasting value — internal system messages, status or error notices about our own internal processes, routine internal scheduling snapshots that repeat and are replaced by the next one, duplicates.

Rules:
1. News about the outside world is intel, even when it mixes topics. Never call a news item fake or discard it just because it covers two topics.
2. Internal notices that one of our own packages or processes failed or could not reach agreement are discard — always, every time.
3. Routine daily statistics or price reports about a real company or asset are intel — always, every time, for every company.
4. Security warnings and emergency patches for outside crypto or software products are intel.
5. Internal hourly scheduling lists (priority resort / hourly order) are discard: they repeat every hour and the next one replaces them.
6. If torn between intel and kick-aside, choose intel. If torn between discard and kick-aside for an internal system notice, choose discard.

Examples:
- Title: 'Miniflux: BitGo Q3 profit nearly doubles' (news about a company's results) -> ROUTING: intel - Outside company financial news worth filing.
- Title: 'DECIDER ESCALATION: package #52 could not reach agreement' -> ROUTING: discard - Internal notice about our own process failing, no lasting value.
- Title: '[WTB] DDR4 ECC memory, 2 GPUs' -> ROUTING: board - A buy post for tracked hardware needs a person to decide and act.
- Title: 'HOURLY ORDER — priority resort' (our hourly task list) -> ROUTING: discard - Internal schedule snapshot that repeats hourly and is replaced by the next.

Item title: """

TITLE_RX = re.compile(r"Item title: (.*?)\. Item text: ", re.S)


def embedded_title(prompt):
    m = TITLE_RX.search(prompt or "")
    return m.group(1) if m else None


def lane_depth():
    return sbos_common.pg_one(
        "SELECT count(*) FROM bus.events WHERE target='gamma' "
        "AND event_type='reap_infer' AND status IN "
        "('pending','processing') AND priority >= 5")


def fed_event_times():
    """title -> created_at of the LATEST reap_infer event carrying it.

    14-day window as before, but the time is kept: only an event fed
    at or after a capture's own created_at blocks that capture.
    """
    rows = sbos_common.pg_rows(
        "SELECT payload->>'prompt', created_at FROM bus.events "
        "WHERE event_type='reap_infer' AND created_at >= "
        "now() - interval '14 days'")
    out = {}
    for prompt, created_at in rows:
        t = embedded_title(prompt)
        if t is not None:
            if t not in out or created_at > out[t]:
                out[t] = created_at
    return out


def is_blocked(title, capture_created_at, fed_times):
    """True only when a same-title event was fed at/after the capture.

    A same-title event fed BEFORE the capture must not block it:
    the capture is new information about a recurring title.
    """
    fed_at = fed_times.get(title)
    if fed_at is None or capture_created_at is None:
        return False
    return fed_at >= capture_created_at


def raw_captures():
    return sbos_common.pg_rows(
        "SELECT id, title, raw_text, created_at "
        "FROM atlas.scattered_captures "
        "WHERE status='raw' ORDER BY created_at ASC")


def insert_event(title, raw_text):
    prompt = PROMPT_HEAD + title + ". Item text: " + (raw_text or "")
    sbos_common.pg_exec(
        "INSERT INTO bus.events (event_type, source, target, "
        "payload, priority) VALUES ('reap_infer', 'spencer', "
        "'gamma', jsonb_build_object('prompt', %s, 'max_tokens', "
        "100, 'thinking', false, 'probe_id', 'queue-keeper-reap'), "
        "5)", (prompt,))


def new_failures():
    return sbos_common.pg_rows(
        "SELECT id, last_error FROM bus.events WHERE "
        "target='gamma' AND status='failed' AND completed_at > "
        "now() - interval '35 minutes' ORDER BY id")


def heartbeat(summary):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.worker_heartbeats "
        "(worker_name, last_heartbeat, last_status, last_error, "
        "is_important, last_run_output) VALUES "
        "(%s, now(), 'ok', NULL, true, %s) "
        "ON CONFLICT (worker_name) DO UPDATE SET "
        "last_heartbeat = now(), last_status = 'ok', "
        "last_error = NULL, last_run_output = "
        "EXCLUDED.last_run_output", (WORKER, summary))


def capture(title, body):
    sbos_common.pg_exec(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s)",
        (title, body,
         "Filed by tools/gamma_queue_keeper.py on alpha (the clerk "
         "queue keeper, moved into SBOS 2026-11-17)."))


def run(dry=False):
    depth = lane_depth()
    pile = raw_captures()
    already = fed_event_times()
    fed = 0
    for cid, title, raw_text, created_at in pile:
        if depth >= LANE_CAP or fed >= LANE_CAP:
            break
        if is_blocked(title, created_at, already):
            continue
        if dry:
            print(f"  would feed capture {cid}: {title[:60]}")
        else:
            insert_event(title, raw_text)
            depth = lane_depth()
        # The just-fed event is now the latest for this title, so a
        # second same-title capture in this run is still fed once.
        already[title] = datetime.now(timezone.utc)
        fed += 1
    fails = new_failures()
    summary = (f"fed {fed} item(s), {len(pile)} in the pile, "
               f"{depth} jobs in line")
    print("Queue keeper: " + summary)
    if dry:
        return 0
    heartbeat(summary + (f"; {len(fails)} new failure(s)"
                         if fails else ""))
    if fails:
        lines = [f"event {eid}: {err}" for eid, err in fails]
        capture("GAMMA JOB FAILURE — keeper report",
                "New failed gamma events in the last 35 minutes:\n"
                + "\n".join(lines))
        print(f"  filed failure capture for {len(fails)} event(s)")
    return 0


def selftest():
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    p = PROMPT_HEAD + 'He said "no" today' + ". Item text: body"
    check("extract plain title",
          embedded_title(PROMPT_HEAD + "Simple title"
                         + ". Item text: x"), "Simple title")
    check("extract quoted title", embedded_title(p),
          'He said "no" today')
    check("no prompt no title", embedded_title(""), None)
    # Time-scoped dedup (B24): only a post-capture event blocks.
    before = datetime(2026, 11, 15, 4, 58, tzinfo=timezone.utc)
    cap_at = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    fed_map = {"[agent-cycle:ceo] 124 QA checks failing": before}
    check("pre-capture event does NOT block",
          is_blocked("[agent-cycle:ceo] 124 QA checks failing",
                     cap_at, fed_map), False)
    fed_map["[agent-cycle:ceo] 124 QA checks failing"] = after
    check("post-capture event DOES block",
          is_blocked("[agent-cycle:ceo] 124 QA checks failing",
                     cap_at, fed_map), True)
    check("same-instant event blocks (>=)",
          is_blocked("T", cap_at, {"T": cap_at}), True)
    check("no event for title does NOT block",
          is_blocked("Unseen title", cap_at, fed_map), False)
    check("substring title is NOT a dedup hit",
          is_blocked("HOURLY ORDER", cap_at,
                     {"HOURLY ORDER — priority resort": after}), False)
    check("exact title IS a dedup hit",
          is_blocked("HOURLY ORDER — priority resort", cap_at,
                     {"HOURLY ORDER — priority resort": after}), True)
    check("prompt head carries v2 shape",
          "ROUTING:" in PROMPT_HEAD and "kick-aside" in PROMPT_HEAD,
          True)
    print("KEEPER SELFTEST:", "OK" if not failures
          else f"FAILED: {failures}")
    return 0 if not failures else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "selftest":
        return selftest()
    if mode == "dry-run":
        return run(dry=True)
    if mode == "run":
        return run()
    print("usage: gamma_queue_keeper.py [run|dry-run|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
