#!/usr/bin/env python3
"""Calendar carry-forward engine — SuccessBrian OS.

Brian's law (2026-10-27, Atlas decision:calendar-carries-forward):
"if we miss them or don't cover all of them we reschedule the ones we
miss." This is how the calendar operates: a missed item NEVER vanishes
and is never counted as handled — it carries forward and gets
rescheduled; timelines recalculate around the carry. An item leaves
the list only by being covered/decided (a terminal status) or by
Brian explicitly cancelling it.

Reads successbrian_os.life_calendar (ecosystem_central). Writes:
  - successbrian_os.calendar_carry_forward — the carry ledger
    (item id, original date, carried-to date, carry count, reason).
  - life_calendar.event_date advances for carried items; the original
    date is preserved in the ledger and stamped into the item's notes.

Hard dates (is_hard_date) are NEVER moved: a missed hard date is
flagged in the ledger as MISSED HARD DATE — a missed pre-event window
is surfaced (and, per the law, transforms, e.g. pre -> recap) rather
than silently slid or dropped.

Usage:
  carry_forward.py            dry run (default): report what WOULD carry
  carry_forward.py --apply    perform the carries (idempotent per day)
  carry_forward.py --report   ledger report: carried items, missed hard
                              dates, pile-ups (carried 3+ times), and
                              superseded candidates among missed items
  carry_forward.py selftest   offline checks of the decision logic

Idempotency: a carried item's event_date becomes today, so it no
longer qualifies as missed on a re-run the same day; the ledger's
UNIQUE(item_id, original_date, kind) makes duplicate rows impossible.
"""

import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

CHI = ZoneInfo("America/Chicago")
DB = "ecosystem_central"

# Only clearly-terminal statuses close an item. Anything else — and
# anything unknown — counts as OPEN (not knowing != closed).
TERMINAL_STATUSES = {
    "done", "completed", "complete", "cancelled", "canceled",
    "closed", "resolved", "dropped", "archived",
}

PILEUP_THRESHOLD = 3

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.calendar_carry_forward (
    id              serial PRIMARY KEY,
    item_id         integer NOT NULL,
    item_title      text,
    kind            text NOT NULL,  -- 'carried' | 'missed_hard_date'
    original_date   date NOT NULL,
    carried_to_date date,
    carry_count     integer NOT NULL DEFAULT 0,
    detected_at     timestamptz NOT NULL DEFAULT now(),
    reason          text,
    UNIQUE (item_id, original_date, kind)
);
"""


def today_chicago():
    return datetime.now(CHI).date()


def is_open(status):
    return (status or "").strip().lower() not in TERMINAL_STATUSES


def carry_target(event_dt, today):
    """Same local time-of-day, on `today` (America/Chicago)."""
    local = event_dt.astimezone(CHI)
    return datetime.combine(today, time(local.hour, local.minute,
                                         local.second), tzinfo=CHI)


def detect_missed(today):
    """Open life_calendar items whose local event date is before today."""
    rows = sbos_common.pg_rows(
        """
        SELECT id, title, event_date, end_date, event_type, status,
               is_hard_date, notes
        FROM successbrian_os.life_calendar
        WHERE (event_date AT TIME ZONE 'America/Chicago')::date < %s
        ORDER BY event_date, id
        """,
        (today,), user="postgres", dbname=DB)
    return [r for r in rows if is_open(r[5])]


def superseded_titles(today):
    """Titles that also have a current/future instance — the past rows
    are dated instances of something still live, not standalone items."""
    rows = sbos_common.pg_rows(
        """
        SELECT DISTINCT title FROM successbrian_os.life_calendar
        WHERE (event_date AT TIME ZONE 'America/Chicago')::date >= %s
        """,
        (today,), user="postgres", dbname=DB)
    return {r[0] for r in rows}


def prior_carries(item_id):
    n = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.calendar_carry_forward "
        "WHERE item_id = %s AND kind = 'carried'",
        (item_id,), user="postgres", dbname=DB)
    return int(n or 0)


def ensure_ledger():
    sbos_common.pg_exec(LEDGER_DDL, user="postgres", dbname=DB)


def plan(today):
    missed = detect_missed(today)
    live_titles = superseded_titles(today)
    out = []
    for (iid, title, ev, end, etype, status, hard, notes) in missed:
        out.append({
            "id": iid, "title": title, "event_date": ev, "end_date": end,
            "event_type": etype, "status": status, "hard": bool(hard),
            "superseded_candidate": title in live_titles,
            "prior_carries": prior_carries(iid),
        })
    return out


def apply_carries(today, items):
    """Perform the carries in one transaction. Returns (carried, flagged)."""
    conn = sbos_common.connect(user="postgres", dbname=DB)
    carried = flagged = 0
    try:
        cur = conn.cursor()
        for it in items:
            orig_date = it["event_date"].astimezone(CHI).date()
            if it["hard"]:
                cur.execute(
                    """
                    INSERT INTO successbrian_os.calendar_carry_forward
                        (item_id, item_title, kind, original_date,
                         carried_to_date, carry_count, reason)
                    VALUES (%s, %s, 'missed_hard_date', %s, NULL, %s, %s)
                    ON CONFLICT (item_id, original_date, kind) DO NOTHING
                    """,
                    (it["id"], it["title"], orig_date, it["prior_carries"],
                     "hard date missed — flagged, not moved"))
                flagged += cur.rowcount
                continue
            n = it["prior_carries"] + 1
            cur.execute(
                """
                INSERT INTO successbrian_os.calendar_carry_forward
                    (item_id, item_title, kind, original_date,
                     carried_to_date, carry_count, reason)
                VALUES (%s, %s, 'carried', %s, %s, %s, %s)
                ON CONFLICT (item_id, original_date, kind) DO NOTHING
                """,
                (it["id"], it["title"], orig_date, today, n,
                 "missed item carried forward per the calendar law"))
            if cur.rowcount == 0:
                continue  # this exact carry already recorded — idempotent
            new_ev = carry_target(it["event_date"], today)
            new_end = None
            if it["end_date"] is not None:
                delta = today - orig_date
                new_end = it["end_date"] + timedelta(days=delta.days)
            stamp = (f"[carry-forward {today.isoformat()}: moved from "
                     f"{orig_date.isoformat()} (carry #{n}) — calendar "
                     f"carry-forward law]")
            cur.execute(
                """
                UPDATE successbrian_os.life_calendar
                SET event_date = %s, end_date = %s,
                    notes = CASE WHEN notes IS NULL OR notes = ''
                                 THEN %s ELSE notes || E'\\n' || %s END
                WHERE id = %s
                """,
                (new_ev, new_end, stamp, stamp, it["id"]))
            carried += 1
        conn.commit()
    finally:
        conn.close()
    return carried, flagged


def fmt_item(it):
    d = it["event_date"].astimezone(CHI).date().isoformat()
    tags = []
    if it["hard"]:
        tags.append("HARD DATE — flag, do not move")
    if it["superseded_candidate"]:
        tags.append("SUPERSEDED CANDIDATE (a current/future instance "
                    "of this title exists)")
    if it["prior_carries"]:
        tags.append(f"prior carries: {it['prior_carries']}")
    return (f"  #{it['id']} [{d}] ({it['event_type']}) {it['title']}"
            + (f"  — {'; '.join(tags)}" if tags else ""))


def report(today, items=None):
    print(f"Calendar carry-forward report — today (America/Chicago): "
          f"{today.isoformat()}")
    rows = sbos_common.pg_rows(
        """
        SELECT kind, count(*) FROM successbrian_os.calendar_carry_forward
        GROUP BY kind ORDER BY kind
        """, user="postgres", dbname=DB)
    print("Ledger totals:", ", ".join(f"{k}={n}" for k, n in rows) or "empty")
    hard = sbos_common.pg_rows(
        """
        SELECT item_id, item_title, original_date
        FROM successbrian_os.calendar_carry_forward
        WHERE kind = 'missed_hard_date' ORDER BY original_date
        """, user="postgres", dbname=DB)
    if hard:
        print("Missed hard dates (flagged, never moved):")
        for iid, title, od in hard:
            print(f"  #{iid} [{od}] {title}")
    piles = sbos_common.pg_rows(
        """
        SELECT item_id, item_title, max(carry_count)
        FROM successbrian_os.calendar_carry_forward
        WHERE kind = 'carried' GROUP BY item_id, item_title
        HAVING max(carry_count) >= %s ORDER BY 3 DESC
        """, (PILEUP_THRESHOLD,), user="postgres", dbname=DB)
    if piles:
        print(f"Pile-ups (carried {PILEUP_THRESHOLD}+ times):")
        for iid, title, n in piles:
            print(f"  #{iid} carried {n}x — {title}")
    if items is not None:
        print(f"Currently missed & open: {len(items)}")
        for it in items:
            print(fmt_item(it))


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    check("scheduled is open", is_open("scheduled"))
    check("planned is open", is_open("planned"))
    check("unknown status is open", is_open("weird-status"))
    check("empty status is open", is_open(None) and is_open(""))
    check("done is closed", not is_open("done"))
    check("Cancelled (any case) is closed", not is_open("Cancelled"))
    sample = datetime(2026, 10, 24, 19, 30, tzinfo=CHI)
    tgt = carry_target(sample, today_chicago())
    check("carry target keeps time-of-day",
          (tgt.hour, tgt.minute) == (19, 30))
    check("carry target is today", tgt.date() == today_chicago())
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    today = today_chicago()
    if argv and argv[0] == "selftest":
        return selftest()
    ensure_ledger()
    items = plan(today)
    if "--apply" in argv:
        carried, flagged = apply_carries(today, items)
        print(f"APPLIED: {carried} carried to {today.isoformat()}, "
              f"{flagged} missed hard dates flagged.")
        report(today, plan(today))
        return 0
    if "--report" in argv:
        report(today, items)
        return 0
    # default: dry run — no writes beyond ensuring the ledger exists
    print(f"DRY RUN — nothing will be changed. "
          f"{len(items)} missed & open item(s):")
    for it in items:
        verb = "FLAG (hard date)" if it["hard"] else "WOULD CARRY"
        print(f"  {verb} → {fmt_item(it).strip()}")
    hard_n = sum(1 for i in items if i["hard"])
    print(f"Summary: {len(items) - hard_n} would carry to "
          f"{today.isoformat()}, {hard_n} hard date(s) would be flagged.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
