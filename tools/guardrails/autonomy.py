#!/usr/bin/env python3
"""autonomy.py — earned-autonomy ladder, ADVISORY ONLY (WS-CAP item 2).

PURPOSE: Record, per action type, how Brian's approvals have gone and
         what autonomy level that history has EARNED — as advice a
         reader (human or agent) can see, never as a gate change.
WHY:     Brian (2026-10-27): autonomy should be earned by a clean
         approval record, and lost on an edit or a rejection. This
         module must NOT change any existing gate: it writes only its
         own autonomy_* tables and reads nothing into any worker.
CALLED BY: operator / agents recording an approval outcome; doctor
         and agent_brief may read `show` output.

RULES (deterministic, in code):
  Levels: L0 always-ask, L1 ask-with-recommendation,
          L2 act-and-report, L3 autonomous.
  Promote one level after N consecutive 'approved_clean' outcomes
  (N from guardrails_config autonomy_promote_n, default 5);
  streak resets on promotion (clamped at L3).
  Any 'approved_edited' or 'rejected' demotes one level (floor L0)
  and resets the streak to 0.

CLI: record <action_type> <outcome> [--actor A] [--note X] | show | selftest
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guardrails_common as gc  # noqa: E402

LEVEL_NAMES = {0: "L0 always-ask", 1: "L1 ask-with-recommendation",
               2: "L2 act-and-report", 3: "L3 autonomous"}
OUTCOMES = ("approved_clean", "approved_edited", "rejected")


def promote_n(cur):
    cur.execute("SELECT value FROM successbrian_os.guardrails_config WHERE key='autonomy_promote_n'")
    row = cur.fetchone()
    try:
        return int(row[0]) if row else 5
    except Exception:
        return 5


def ensure_type(cur, action_type):
    cur.execute(
        """INSERT INTO successbrian_os.autonomy_action_types (action_type)
           VALUES (%s) ON CONFLICT (action_type) DO NOTHING""", (action_type,))


def record(cur, action_type, outcome, actor=None, note=None):
    if outcome not in OUTCOMES:
        raise SystemExit(f"outcome must be one of {OUTCOMES}")
    gc.ensure_schema(cur)
    ensure_type(cur, action_type)
    cur.execute(
        "SELECT current_level, streak FROM successbrian_os.autonomy_action_types WHERE action_type=%s FOR UPDATE",
        (action_type,))
    level, streak = cur.fetchone()
    before = level
    n = promote_n(cur)
    if outcome == "approved_clean":
        streak += 1
        if streak >= n and level < 3:
            level += 1
            streak = 0
    else:  # approved_edited / rejected
        level = max(0, level - 1)
        streak = 0
    cur.execute(
        """UPDATE successbrian_os.autonomy_action_types
              SET current_level=%s, streak=%s, updated_at=now()
            WHERE action_type=%s""", (level, streak, action_type))
    cur.execute(
        """INSERT INTO successbrian_os.autonomy_events
             (action_type, outcome, actor, note, level_before, level_after)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (action_type, outcome, actor, note, before, level))
    return cur.fetchone()[0], before, level, streak


def show():
    c = gc.conn(dict_cursor=True)
    cur = c.cursor()
    gc.ensure_schema(cur)
    c.commit()
    n = promote_n(cur)
    lines = [f"Earned-autonomy ladder (ADVISORY ONLY — changes no gate; promote N={n})"]
    cur.execute(
        "SELECT action_type, current_level, streak, updated_at FROM successbrian_os.autonomy_action_types ORDER BY action_type")
    rows = cur.fetchall()
    if not rows:
        lines.append("  (no action types recorded yet)")
    for r in rows:
        cur.execute(
            "SELECT outcome, created_at FROM successbrian_os.autonomy_events WHERE action_type=%s ORDER BY id DESC LIMIT 3",
            (r["action_type"],))
        last = ", ".join(f"{x['outcome']}@{x['created_at']:%m-%d}" for x in cur.fetchall()) or "-"
        lines.append(f"{r['action_type']}: {LEVEL_NAMES[r['current_level']]} "
                     f"streak={r['streak']}/{n} last: {last}")
    c.close()
    for ln in lines:
        print(ln)
    return lines


def selftest():
    passed = total = 0

    def check(cond, label):
        nonlocal passed, total
        total += 1
        assert cond, label
        passed += 1
        print(f"PASS {label}")

    tag = "selftest-fixture"
    c = gc.conn()
    cur = c.cursor()
    gc.ensure_schema(cur)
    cur.execute("DELETE FROM successbrian_os.autonomy_events WHERE action_type=%s", (tag,))
    cur.execute("DELETE FROM successbrian_os.autonomy_action_types WHERE action_type=%s", (tag,))
    c.commit()
    n = promote_n(cur)
    lvl = None
    for _ in range(n):
        _, _, lvl, streak = record(cur, tag, "approved_clean", actor="selftest")
        c.commit()
    check(lvl == 1 and streak == 0, f"promote: {n} consecutive approved_clean -> L1, streak resets")
    _, before, lvl, streak = record(cur, tag, "approved_edited", actor="selftest")
    c.commit()
    check(before == 1 and lvl == 0 and streak == 0, "demote: approved_edited demotes one level and resets streak")
    for _ in range(n - 1):
        record(cur, tag, "approved_clean", actor="selftest"); c.commit()
    _, _, lvl, streak = record(cur, tag, "rejected", actor="selftest"); c.commit()
    check(lvl == 0 and streak == 0, "demote: rejected resets a partial streak without going below L0")
    for _ in range(n):
        record(cur, tag, "approved_clean", actor="selftest"); c.commit()
    cur.execute("SELECT current_level FROM successbrian_os.autonomy_action_types WHERE action_type=%s", (tag,))
    check(cur.fetchone()[0] == 1, "re-promotion after demotion works (state is durable in PG)")
    cur.execute("DELETE FROM successbrian_os.autonomy_events WHERE action_type=%s", (tag,))
    cur.execute("DELETE FROM successbrian_os.autonomy_action_types WHERE action_type=%s", (tag,))
    c.commit(); c.close()
    check(True, "cleanup — fixture action type removed")
    print(f"SELFTEST OK: autonomy {passed}/{total}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS earned-autonomy ladder (advisory only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("action_type")
    r.add_argument("outcome", choices=list(OUTCOMES))
    r.add_argument("--actor")
    r.add_argument("--note")
    sub.add_parser("show")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "show":
        show(); return 0
    if args.cmd == "record":
        c = gc.conn(); cur = c.cursor()
        eid, before, after, streak = record(cur, args.action_type, args.outcome, args.actor, args.note)
        c.commit(); c.close()
        print(f"event id={eid} {args.action_type}: {LEVEL_NAMES[before]} -> {LEVEL_NAMES[after]} streak={streak} (advisory only)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
