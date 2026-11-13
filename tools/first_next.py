#!/usr/bin/env python3
"""first_next.py — the scatter judgement consumer.

Brian's ruling (2026-11-12 19:22 CST): SuccessBrian OS must
understand what is what, file/sort/grade all of Brian's scatter,
and make a firm judgement — "DO THIS ONE FIRST", second, third —
because Brian is too scattered to know what needs to finish
first, and he will scatter forever. That is the design condition,
not a problem to fix in Brian.

Existing machinery this builds on (audited live 2026-11-12):
  - the clerk sweeps the Intel Bridge hourly and sorts scatter
    (board / Altair / wf3-keeping workflows);
  - tools/priority_pass.py's hourly resort ranks open work into
    successbrian_os.priority_order (running, current, mostly
    Sonic-adjusted) and writes engine-queue priorities back.

THE GAP this module closes (audit 2026-11-12): nothing downstream
READS priority_order. The board agenda, the daily director, and
the Altair heartbeat each keep their own order; the hourly order
was written to a table whose only reader was a human CLI, and
its HOURLY ORDER captures looped back into the raw scatter pile.

This module is the consumer:
  1. Reads the latest hour's WORK block from priority_order.
  2. Re-tiers the top items by Brian's PRIORITY STACK
     (2026-10-21, board CHARTER — the one order everything
     reads): (1) expiring life gates inside their window;
     (2) income toward freedom; (3) unblocking decisions;
     (4) family/inheritance legibility; (5) ecosystem work in
     service of 1-4, hygiene last. Deterministic word rules —
     the tier's reason is its matched words, stated in words.
     Within a tier, the resort's rank stands.
  3. Adds the SIFT summary — what the clerk filed in the last
     24h and the raw scatter backlog — so the judgement carries
     "all of our sources tell us this", not just one queue.
  4. Writes the judgement to its own table
     (successbrian_os.first_next_judgement, idempotent per
     order-hour) and files ONE capture per day into the Intel
     Bridge — the path the clerk triages and the passup lane
     carries to decider packages, i.e. the existing route to
     the agents who talk to Brian.
  5. Items waiting on Brian (the resort's waiting block) are
     surfaced separately as the UNSORTABLE — Brian's standing
     role — never ranked as workable work.

It never mutates a task label, a queue priority, a step, or the
calendar. The engine-queue write-back remains the resort's job;
this module judges and reports.

CLI:
  first_next.py run [--no-file]   judge the latest order hour
  first_next.py show              print the latest judgement
  first_next.py selftest
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

JUDGEMENT_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.first_next_judgement (
    id serial PRIMARY KEY,
    order_hour timestamptz NOT NULL,
    rank integer NOT NULL,
    block text NOT NULL DEFAULT 'work',
    stack_tier integer,
    stack_reason text,
    source_type text NOT NULL,
    source_id integer,
    title text,
    resort_rank integer,
    score integer,
    sonic_note text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS first_next_hour_idx
    ON successbrian_os.first_next_judgement (order_hour, rank);
"""

# Brian's priority stack (2026-10-21 CHARTER), as word rules.
# The reason recorded for a tier is its matched words — the
# judgement explains itself in words, like the clerk's stamps.
STACK = [
    (1, "expiring life gate",
     ["overdue", "deadline", "expires", "expiring",
      "final notice", "past due", "last day"]),
    (2, "income toward freedom",
     ["$", "revenue", "income", "sales", "sell", "dealsdesk",
      "gotbackup", "trafficstreemz", "contactflowcrm", "oliabo",
      "sponsor", "commission", "customer", "monetize", "deal "]),
    (3, "unblocking decision",
     ["prerequisite", "prereq", "blocks", "unblock", "unblocks",
      "approve", "approval", "rule:", "decision", "gate"]),
    (4, "family / inheritance legibility",
     ["family", "inheritance", "estate", "meghan", "daughter",
      "mother", "sister", "niece"]),
]

TIER5 = (5, "ecosystem work in service of the tiers above")


def stack_tier(text):
    """(tier, label, matched words) for title + note text."""
    low = " " + (text or "").lower() + " "
    for tier, label, words in STACK:
        hits = [w for w in words if w in low]
        if hits:
            return tier, label, hits
    return TIER5[0], TIER5[1], []


def tier_items(work_rows):
    """Re-tier priority_order work rows by the stack. Within a
    tier the resort rank stands (stable sort)."""
    out = []
    for r in work_rows:
        rank, source, sid, title, score, note = r
        tier, label, hits = stack_tier(
            (title or "") + " " + (note or ""))
        out.append({
            "resort_rank": rank, "source": source, "id": sid,
            "title": title, "score": score, "sonic_note": note,
            "tier": tier, "tier_label": label, "hits": hits})
    out.sort(key=lambda c: (c["tier"], c["resort_rank"]))
    return out


def sift_summary():
    """What the clerk has filed lately + the raw backlog — the
    'all of our sources' snapshot that rides with the judgement."""
    raw_n, oldest = sbos_common.pg_one(
        "SELECT count(*) FROM atlas.scattered_captures "
        "WHERE status = 'raw'"), None
    row = sbos_common.pg_rows(
        "SELECT min(created_at) FROM atlas.scattered_captures "
        "WHERE status = 'raw'")
    if row and row[0][0]:
        oldest = row[0][0]
    filed = sbos_common.pg_rows(
        "SELECT coalesce(recommendation, '(unrouted)'), count(*) "
        "FROM atlas.scattered_captures "
        "WHERE created_at > now() - interval '24 hours' "
        "AND status <> 'raw' GROUP BY 1 ORDER BY 2 DESC")
    return {"raw_backlog": int(raw_n or 0), "oldest_raw": oldest,
            "filed_24h": [(r[0], int(r[1])) for r in filed]}


def latest_order():
    hour = sbos_common.pg_one(
        "SELECT max(hour) FROM successbrian_os.priority_order")
    if not hour:
        return None, [], []
    work = sbos_common.pg_rows(
        "SELECT rank, source_type, source_id, title, score, "
        "sonic_note FROM successbrian_os.priority_order "
        "WHERE hour = %s AND block = 'work' ORDER BY rank",
        (hour,))
    waiting = sbos_common.pg_rows(
        "SELECT source_type, source_id, title FROM "
        "successbrian_os.priority_order WHERE hour = %s "
        "AND block = 'waiting' ORDER BY rank", (hour,))
    return hour, work, waiting


def judge():
    sbos_common.pg_exec(JUDGEMENT_DDL)
    hour, work, waiting = latest_order()
    if hour is None:
        print("no priority order yet — the resort has not run")
        return None
    judged = tier_items(work)
    sbos_common.pg_exec(
        "DELETE FROM successbrian_os.first_next_judgement "
        "WHERE order_hour = %s", (hour,))
    rank = 0
    for c in judged:
        rank += 1
        reason = (f"stack tier {c['tier']} ({c['tier_label']})"
                  + (f" — matched: {', '.join(c['hits'][:4])}"
                     if c["hits"] else " — no higher tier matched")
                  + f"; resort rank {c['resort_rank']}")
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.first_next_judgement "
            "(order_hour, rank, block, stack_tier, stack_reason, "
            "source_type, source_id, title, resort_rank, score, "
            "sonic_note) VALUES (%s,%s,'work',%s,%s,%s,%s,%s,%s,"
            "%s,%s)",
            (hour, rank, c["tier"], reason, c["source"], c["id"],
             c["title"], c["resort_rank"], c["score"],
             c["sonic_note"]))
    for source, sid, title in waiting:
        rank += 1
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.first_next_judgement "
            "(order_hour, rank, block, stack_tier, stack_reason, "
            "source_type, source_id, title) VALUES "
            "(%s,%s,'waiting',NULL,'waiting on Brian — the "
            "unsortable; surfaced, never ranked as work',%s,%s,%s)",
            (hour, rank, source, sid, title))
    return hour, judged, waiting, sift_summary()


def render(hour, judged, waiting, sift):
    lines = [f"FIRST NEXT — judgement for order hour "
             f"{hour:%Y-%m-%d %H:00}"]
    names = ["DO THIS ONE FIRST", "SECOND", "THIRD"]
    for i, c in enumerate(judged[:3]):
        label = names[i] if i < 3 else f"#{i + 1}"
        lines.append(
            f"{label}: [{c['source']}#{c['id']}] {c['title']}")
        lines.append(
            f"   why: stack tier {c['tier']} ({c['tier_label']})"
            + (f", matched {', '.join(c['hits'][:4])}"
               if c["hits"] else "")
            + f"; was resort rank {c['resort_rank']}"
            + (f"; sonic: {c['sonic_note']}" if c["sonic_note"]
               else ""))
    if len(judged) > 3:
        lines.append(f"Then {len(judged) - 3} more work items in "
                     "stack order (table: first_next_judgement).")
    if waiting:
        lines.append("WAITING ON BRIAN (the unsortable — his "
                     "standing role, not ranked as work):")
        for source, sid, title in waiting:
            lines.append(f"   - [{source}#{sid}] {title}")
    lines.append(
        f"SCATTER SIFT: raw backlog {sift['raw_backlog']} "
        f"(oldest {sift['oldest_raw']:%Y-%m-%d %H:%M} "
        f"if any). Filed in the last 24h: "
        + (", ".join(f"{k} {v}" for k, v in sift["filed_24h"])
           if sift["filed_24h"] else "nothing"))
    if not sift["oldest_raw"]:
        lines[-1] = (f"SCATTER SIFT: raw backlog "
                     f"{sift['raw_backlog']}. Filed in the last "
                     "24h: "
                     + (", ".join(f"{k} {v}"
                                  for k, v in sift["filed_24h"])
                        if sift["filed_24h"] else "nothing"))
    return "\n".join(lines)


def file_capture(hour, judged, text):
    """One capture per day into the Intel Bridge (deduped by
    title). The clerk triages it; the passup lane carries
    promoted/refined captures to decider packages — the existing
    route to the agents who talk to Brian."""
    import base64 as b64
    import subprocess

    def b64sql(s):
        return ("convert_from(decode('%s','base64'),'UTF8')"
                % b64.b64encode(s.encode()).decode())

    top = judged[0] if judged else None
    title = (f"FIRST NEXT {hour:%Y-%m-%d} — DO THIS ONE FIRST: "
             + ((top["title"] or "")[:80] if top else "none"))
    exists = sbos_common.pg_one(
        "SELECT count(*) FROM atlas.scattered_captures "
        "WHERE title = %s", (title,))
    if exists:
        return None
    context = ("Filed by first_next (Brian's ruling 2026-11-12: "
               "the system files/sorts/grades all scatter and "
               "makes a firm judgement — first, second, third). "
               "Source: latest priority_order hour, re-tiered "
               "by the 2026-10-21 priority stack.")
    sql = ("insert into atlas.scattered_captures "
           "(title, raw_text, context, status) values "
           f"({b64sql(title)}, {b64sql(text)}, "
           f"{b64sql(context)}, 'raw') returning id")
    p = subprocess.run(["psql", "-d", "ecosystem_central", "-t",
                        "-A", "-c", sql], capture_output=True,
                       text=True, timeout=60)
    out = (p.stdout or "").strip().splitlines()
    return out[0] if out else ""


def run(do_file=True):
    got = judge()
    if got is None:
        return 1
    hour, judged, waiting, sift = got
    text = render(hour, judged, waiting, sift)
    print(text)
    if do_file:
        cid = file_capture(hour, judged, text)
        if cid:
            print(f"judgement filed as capture #{cid}")
        else:
            print("judgement capture already filed today")
    return 0


def show():
    rows = sbos_common.pg_rows(
        "SELECT order_hour, rank, block, stack_tier, "
        "stack_reason, source_type, source_id, title, "
        "resort_rank, sonic_note FROM "
        "successbrian_os.first_next_judgement "
        "WHERE order_hour = (SELECT max(order_hour) FROM "
        "successbrian_os.first_next_judgement) ORDER BY rank")
    if not rows:
        print("no judgement yet — run: first_next.py run")
        return
    print(f"judgement for order hour {rows[0][0]:%Y-%m-%d %H:00}")
    for r in rows:
        if r[2] == "waiting":
            print(f"   WAITING ON BRIAN: [{r[5]}#{r[6]}] {r[7]}")
        elif r[1] <= 10:
            print(f"{r[1]:>2}. [{r[5]}#{r[6]}] {r[7]}")
            print(f"     {r[4]}"
                  + (f"; sonic: {r[9]}" if r[9] else ""))


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    t, label, hits = stack_tier("Invoice overdue — final notice")
    check("overdue item lands in tier 1", t == 1)
    t, label, hits = stack_tier(
        "Drive the blast — 47d overdue with direct revenue "
        "impact")
    check("tier 1 beats tier 2 when both match", t == 1)
    t, label, hits = stack_tier("GotBackup sponsor follow-up")
    check("goal-named income item lands in tier 2", t == 2)
    t, label, hits = stack_tier(
        "Build the dedicated box (PREREQUISITE) — dealsdesk")
    check("income beats unblocking when both match", t == 2)
    t, label, hits = stack_tier("APPROVE the crossover article")
    check("approve item lands in tier 3", t == 3)
    t, label, hits = stack_tier("Sort the estate paperwork")
    check("estate item lands in tier 4", t == 4)
    t, label, hits = stack_tier("Water the plants")
    check("unmatched item lands in tier 5", t == 5)
    rows = [(6, "task", 1, "zeta hygiene sweep", 10, None),
            (7, "task", 2, "alpha overdue invoice", 10, None),
            (8, "task", 3, "beta routine cleanup", 10, None)]
    judged = tier_items(rows)
    check("re-tier promotes the tier-1 item to first",
          judged[0]["id"] == 2)
    check("within a tier the resort rank stands",
          [c["id"] for c in judged[1:]] == [1, 3])
    check("judgement table ddl names the table",
          "first_next_judgement" in JUDGEMENT_DDL)
    check("the stack has four ruled tiers above ecosystem",
          len(STACK) == 4 and TIER5[0] == 5)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if argv and argv[0] == "selftest":
        return selftest()
    if argv and argv[0] == "show":
        show()
        return 0
    if argv and argv[0] == "run":
        return run(do_file="--no-file" not in argv)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
