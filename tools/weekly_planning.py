#!/usr/bin/env python3
"""Weekly Deep-Planning Session - Brian's order (2026-11-18 04:04 CST):

  "build robust tools inside successbrian os; that allow the user to
  pick a time each week where the entire system works together (with a
  muse agent if the user has one) to come up with a once a week deep
  planning session where the ecosystem asks simple questions one at a
  time to deep plan the future"

Design, grounded in Brian's standing rulings:

  * THE USER PICKS THE TIME. planning_session_config holds one weekly
    slot (weekday + local time + timezone) that Brian sets and only
    Brian changes. Until he sets it the tool still works manually;
    the tick simply has nothing to prepare for.

  * THE SYSTEM WORKS FIRST (Brian, 2026-11-15: "submit your questions
    into the system to work them out; only surface to me the things
    that you and the system together cannot figure out"). PREPARE is
    the pre-work: it syncs the decision queue (the residue stream -
    held_brian PM steps, unruled brian_decision captures, compile
    residue), snapshots the pending residue WITH its context, and
    adds forward-looking goal questions from Atlas (goals carrying a
    blocker, goals overdue for their planner look). What the record
    already settles never reaches the session: the decision queue
    only holds what is genuinely Brian's to rule on.

  * ONE AT A TIME, SIMPLE, CONTEXT INSIDE (Brian, 2026-10-23:
    ask with context, one question at a time; he is forgetful and a
    bare question is a memory test). --next serves exactly ONE
    question with its context attached. No lists, no batches.

  * ANSWERS LAND IN THE OWNING TABLE THE SAME PASS (the B8 rule).
    A ruling on a residue question goes through decision_queue.rule
    (write-back to pm_steps / scattered_captures / knowledge_index,
    verified both sides by that tool). An answer to a goal question
    is filed as a capture into the Intel Bridge (atlas.scattered_
    captures via scattered_brain.capture) in the same pass, so the
    clerk and the planner rotation pick it up.

  * CARRY-FORWARD, NEVER DROP (the calendar law, 2026-10-27).
    --skip records an explicit carry on the owning stream; anything
    unreached stays pending in the decision queue and reappears in
    next week's snapshot. A session closing never deletes a question.

  * WITH A MUSE AGENT IF THE USER HAS ONE. The session is driven
    through this CLI: any Muse agent (or Brian himself) runs
    --next / --answer / --skip. The config flag with_muse records
    that a Muse agent participates; the prepared session + its
    snapshot are the handoff surface between the ecosystem and the
    agent. Nothing here sends, buys, publishes, or contacts anyone.

Scheduling: an alpha crontab tick every 30 min (the ruling-census
pattern) calls --tick. When the configured slot's lead window opens
and no session exists for that week, the tick prepares one; at the
slot itself the session is marked due. Sessions are keyed by the
ISO week of their scheduled slot, so a tick can never double-prepare.

State home: PostgreSQL, successbrian_os.planning_session_* in
ecosystem_central. Logic home: this file, in the repo.
Idempotent schema: run --init any number of times.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decision_queue as dq  # noqa: E402

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

DB = "ecosystem_central"
SCHEMA = "successbrian_os"
DEFAULT_TZ = "America/Chicago"
WEEKDAYS = {"mon": 0, "monday": 0, "tue": 1, "tuesday": 1,
            "wed": 2, "wednesday": 2, "thu": 3, "thursday": 3,
            "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
            "sun": 6, "sunday": 6}

DDL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.planning_session_config (
    id          int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    weekday     int CHECK (weekday BETWEEN 0 AND 6),
    local_time  time,
    tz          text NOT NULL DEFAULT '{DEFAULT_TZ}',
    lead_minutes int NOT NULL DEFAULT 240,
    enabled     boolean NOT NULL DEFAULT false,
    with_muse   boolean NOT NULL DEFAULT true,
    set_by      text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.planning_sessions (
    id           bigserial PRIMARY KEY,
    week_key     text UNIQUE NOT NULL,
    scheduled_at timestamptz,
    status       text NOT NULL DEFAULT 'prepared'
                 CHECK (status IN ('prepared','due','in_session','closed')),
    prepared_at  timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    closed_at    timestamptz,
    summary      jsonb NOT NULL DEFAULT '{{}}'::jsonb
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.planning_session_questions (
    id          bigserial PRIMARY KEY,
    session_id  bigint NOT NULL REFERENCES {SCHEMA}.planning_sessions(id)
                ON DELETE CASCADE,
    position    int NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('residue','goal')),
    source_ref  text,
    title       text NOT NULL,
    context     jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    status      text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','asked','answered','carried')),
    answer      text,
    answered_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, source_ref)
);
"""


def conn():
    return psycopg2.connect(dbname=DB, host="localhost",
                            cursor_factory=psycopg2.extras.RealDictCursor)


def init():
    c = conn()
    cur = c.cursor()
    cur.execute(DDL)
    cur.execute(f"INSERT INTO {SCHEMA}.planning_session_config (id) "
                "VALUES (1) ON CONFLICT (id) DO NOTHING")
    c.commit()
    c.close()
    return 0


def get_config(cur):
    cur.execute(f"SELECT * FROM {SCHEMA}.planning_session_config WHERE id=1")
    return cur.fetchone()


def occurrence_for_week(cfg, ref=None):
    """The configured slot's datetime in the week containing ref
    (default now), in the configured timezone."""
    tz = ZoneInfo(cfg["tz"] or DEFAULT_TZ)
    ref = ref or datetime.now(tz)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=tz)
    ref = ref.astimezone(tz)
    monday = ref.date() - timedelta(days=ref.weekday())
    day = monday + timedelta(days=cfg["weekday"])
    return datetime.combine(day, cfg["local_time"], tzinfo=tz)


def week_key_of(dt):
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def next_occurrence(cfg, ref=None):
    tz = ZoneInfo(cfg["tz"] or DEFAULT_TZ)
    ref = ref or datetime.now(tz)
    occ = occurrence_for_week(cfg, ref)
    if occ <= ref:
        occ = occ + timedelta(days=7)
    return occ


def goal_questions(cur):
    """Forward-looking questions from Atlas: active goals carrying a
    blocker, or overdue for their planner look. The question carries
    its context (Brian's ask-with-context rule)."""
    cur.execute(
        """SELECT goal_slug, name, priority, blocker, days_since_look,
                  last_looked_at
             FROM atlas.goal_nodes
            WHERE status IN ('active','planned','blocked')
              AND (blocker IS NOT NULL OR look_overdue IS TRUE)
            ORDER BY priority DESC NULLS LAST, days_since_look DESC NULLS LAST
            LIMIT 10""")
    out = []
    for g in cur.fetchall():
        if g["blocker"]:
            title = (f"Goal '{g['name']}': the record shows a blocker - "
                     f"{g['blocker']}. What should happen with it?")
        else:
            days = g["days_since_look"]
            days_txt = f"{float(days):.0f}" if days is not None else "many"
            title = (f"Goal '{g['name']}' has not had a planning look in "
                     f"{days_txt} days. What matters most about it now?")
        out.append({
            "kind": "goal",
            "source_ref": f"goal:{g['goal_slug']}",
            "title": title,
            "context": {
                "goal_slug": g["goal_slug"], "priority": g["priority"],
                "blocker": g["blocker"],
                "days_since_look": (float(g["days_since_look"])
                                    if g["days_since_look"] is not None
                                    else None),
                "last_looked_at": (g["last_looked_at"].isoformat()
                                   if g["last_looked_at"] else None)},
        })
    return out


def prepare(week_key=None, scheduled_at=None, quiet=False):
    """The system's pre-work: sync the residue stream, snapshot it
    with context, add goal questions, one session per week."""
    init()
    dq.init()
    dq.sync()
    c = conn()
    cur = c.cursor()
    cfg = get_config(cur)
    if week_key is None:
        if cfg and cfg["weekday"] is not None and cfg["local_time"]:
            occ = occurrence_for_week(cfg)
            week_key = week_key_of(occ)
            scheduled_at = occ
        else:
            now = datetime.now(ZoneInfo(DEFAULT_TZ))
            week_key = week_key_of(now)
            scheduled_at = None
    cur.execute(f"SELECT * FROM {SCHEMA}.planning_sessions WHERE week_key=%s",
                (week_key,))
    session = cur.fetchone()
    if session is None:
        cur.execute(
            f"""INSERT INTO {SCHEMA}.planning_sessions
                   (week_key, scheduled_at) VALUES (%s, %s)
                RETURNING *""", (week_key, scheduled_at))
        session = cur.fetchone()
        c.commit()
    sid = session["id"]
    cur.execute(f"SELECT COALESCE(MAX(position),0) AS p FROM {SCHEMA}."
                "planning_session_questions WHERE session_id=%s", (sid,))
    pos = cur.fetchone()["p"]
    added = 0
    for r in dq.fetch_pending():
        pos += 1
        cur.execute(
            f"""INSERT INTO {SCHEMA}.planning_session_questions
                   (session_id, position, kind, source_ref, title, context)
                VALUES (%s,%s,'residue',%s,%s,%s::jsonb)
                ON CONFLICT (session_id, source_ref) DO NOTHING""",
            (sid, pos, r["ref"], r["title"],
             json.dumps(r["context"] if isinstance(r["context"], dict)
                        else json.loads(r["context"] or "{}"))))
        added += cur.rowcount
    for q in goal_questions(cur):
        pos += 1
        cur.execute(
            f"""INSERT INTO {SCHEMA}.planning_session_questions
                   (session_id, position, kind, source_ref, title, context)
                VALUES (%s,%s,'goal',%s,%s,%s::jsonb)
                ON CONFLICT (session_id, source_ref) DO NOTHING""",
            (sid, pos, q["source_ref"], q["title"],
             json.dumps(q["context"])))
        added += cur.rowcount
    c.commit()
    cur.execute(
        f"""SELECT kind, status, COUNT(*) AS n FROM {SCHEMA}.
            planning_session_questions WHERE session_id=%s
            GROUP BY kind, status ORDER BY kind, status""", (sid,))
    counts = [dict(r) for r in cur.fetchall()]
    c.close()
    if not quiet:
        print(f"session {week_key} (id {sid}): +{added} new questions")
        for row in counts:
            print(f"  {row['kind']}/{row['status']}: {row['n']}")
    return sid


def open_session(cur):
    cur.execute(
        f"""SELECT * FROM {SCHEMA}.planning_sessions
             WHERE status IN ('prepared','due','in_session')
             ORDER BY prepared_at DESC LIMIT 1""")
    return cur.fetchone()


def show_config():
    init()
    c = conn()
    cur = c.cursor()
    cfg = get_config(cur)
    c.close()
    if not cfg or cfg["weekday"] is None:
        print("weekly slot: NOT SET - Brian picks the day and time "
              "(--set-time \"wed 10:00\")")
        return 0
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]
    nxt = next_occurrence(cfg)
    print(f"weekly slot: {names[cfg['weekday']]} "
          f"{cfg['local_time']} {cfg['tz']} "
          f"(enabled={cfg['enabled']}, with_muse={cfg['with_muse']}, "
          f"lead={cfg['lead_minutes']}m, set_by={cfg['set_by']})")
    print(f"next session: {nxt.isoformat()} ({week_key_of(nxt)})")
    return 0


def set_time(day, hhmm, tz=DEFAULT_TZ, lead=240, by="brian",
             enable=True, with_muse=True):
    init()
    wd = WEEKDAYS.get(day.strip().lower())
    if wd is None:
        print(f"unknown weekday: {day}")
        return 2
    hh, mm = hhmm.split(":")
    c = conn()
    cur = c.cursor()
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_session_config
               SET weekday=%s, local_time=%s, tz=%s, lead_minutes=%s,
                   enabled=%s, with_muse=%s, set_by=%s, updated_at=now()
             WHERE id=1""",
        (wd, f"{int(hh):02d}:{int(mm):02d}", tz, lead, enable,
         with_muse, by))
    c.commit()
    c.close()
    print(f"weekly slot set: weekday={wd} time={hhmm} tz={tz} "
          f"lead={lead}m enabled={enable} by={by}")
    return show_config()


def tick():
    """Crontab heartbeat: prepare when the lead window opens, mark
    due at the slot. Never double-prepares (week_key UNIQUE)."""
    init()
    c = conn()
    cur = c.cursor()
    cfg = get_config(cur)
    c.close()
    if not cfg or not cfg["enabled"] or cfg["weekday"] is None:
        print("tick: no enabled weekly slot; nothing to do")
        return 0
    tz = ZoneInfo(cfg["tz"] or DEFAULT_TZ)
    now = datetime.now(tz)
    occ = occurrence_for_week(cfg, now)
    wk = week_key_of(occ)
    lead_open = occ - timedelta(minutes=cfg["lead_minutes"])
    if now < lead_open:
        print(f"tick: slot {occ.isoformat()} not in lead window yet")
        return 0
    sid = prepare(week_key=wk, scheduled_at=occ, quiet=True)
    c = conn()
    cur = c.cursor()
    if now >= occ:
        cur.execute(
            f"""UPDATE {SCHEMA}.planning_sessions SET status='due'
                 WHERE id=%s AND status='prepared'""", (sid,))
    c.commit()
    cur.execute(f"SELECT status FROM {SCHEMA}.planning_sessions WHERE id=%s",
                (sid,))
    st = cur.fetchone()["status"]
    c.close()
    print(f"tick: session {wk} ready (status={st})")
    return 0


def fmt_context(ctx):
    if not ctx:
        return ""
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            return ctx
    lines = []
    for k, v in ctx.items():
        if v in (None, "", [], {}):
            continue
        lines.append(f"    {k}: {v}")
    return "\n".join(lines)


def show_next():
    init()
    c = conn()
    cur = c.cursor()
    s = open_session(cur)
    if not s:
        print("no open session - run --prepare (or wait for the tick)")
        c.close()
        return 0
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_sessions SET status='in_session',
               started_at=COALESCE(started_at, now())
             WHERE id=%s AND status IN ('prepared','due')""", (s["id"],))
    cur.execute(
        f"""SELECT * FROM {SCHEMA}.planning_session_questions
             WHERE session_id=%s AND status IN ('pending','asked')
             ORDER BY position ASC LIMIT 1""", (s["id"],))
    q = cur.fetchone()
    if not q:
        c.commit()
        c.close()
        print(f"session {s['week_key']}: no questions left - "
              "everything answered or carried")
        return 0
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_session_questions SET status='asked'
             WHERE id=%s AND status='pending'""", (q["id"],))
    cur.execute(
        f"""SELECT COUNT(*) AS n FROM {SCHEMA}.planning_session_questions
             WHERE session_id=%s AND status IN ('pending','asked')""",
        (s["id"],))
    remaining = cur.fetchone()["n"]
    c.commit()
    c.close()
    print(f"[{s['week_key']}] question ({remaining} remaining, "
          f"{q['kind']}, ref {q['source_ref']})")
    print(f"  {q['title']}")
    ctx = fmt_context(q["context"])
    if ctx:
        print(ctx)
    return 0


def current_question(cur, session_id):
    cur.execute(
        f"""SELECT * FROM {SCHEMA}.planning_session_questions
             WHERE session_id=%s AND status='asked'
             ORDER BY position ASC LIMIT 1""", (session_id,))
    q = cur.fetchone()
    if q:
        return q
    cur.execute(
        f"""SELECT * FROM {SCHEMA}.planning_session_questions
             WHERE session_id=%s AND status='pending'
             ORDER BY position ASC LIMIT 1""", (session_id,))
    return cur.fetchone()


def file_goal_answer(q, answer, by):
    """Goal answers land in the Intel Bridge the same pass, so the
    clerk + planner rotation work from them."""
    sys.path.insert(0, os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "atlas"))
    import scattered_brain as sb
    c = conn()
    try:
        sb.capture(c, f"Planning answer - {q['title']}",
                   f"Weekly deep-planning session answer by {by}. "
                   f"Question: {q['title']}",
                   answer)
    finally:
        c.close()


def answer(text, by="brian"):
    init()
    c = conn()
    cur = c.cursor()
    s = open_session(cur)
    if not s:
        print("no open session")
        c.close()
        return 2
    q = current_question(cur, s["id"])
    if not q:
        print("no unanswered question in the open session")
        c.close()
        return 2
    c.close()
    if q["kind"] == "residue":
        rc = dq.rule(q["source_ref"], text, by=by)
        if rc not in (0, None):
            print(f"decision_queue write-back returned {rc}; "
                  "question NOT marked answered")
            return 3
    else:
        file_goal_answer(q, text, by)
    c = conn()
    cur = c.cursor()
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_session_questions
               SET status='answered', answer=%s, answered_at=now()
             WHERE id=%s""", (text, q["id"]))
    c.commit()
    c.close()
    print(f"answered + filed: {q['source_ref']}")
    return 0


def skip(note="", by="spencer"):
    init()
    c = conn()
    cur = c.cursor()
    s = open_session(cur)
    if not s:
        print("no open session")
        c.close()
        return 2
    q = current_question(cur, s["id"])
    if not q:
        print("no unanswered question in the open session")
        c.close()
        return 2
    c.close()
    if q["kind"] == "residue":
        dq.carry(q["source_ref"], note=note or "carried from weekly "
                 "planning session", by=by)
    c = conn()
    cur = c.cursor()
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_session_questions
               SET status='carried' WHERE id=%s""", (q["id"],))
    c.commit()
    c.close()
    print(f"carried forward: {q['source_ref']} "
          "(stays on the stream; returns next week)")
    return 0


def show_status():
    init()
    show_config()
    c = conn()
    cur = c.cursor()
    s = open_session(cur)
    if not s:
        print("open session: none")
    else:
        cur.execute(
            f"""SELECT status, COUNT(*) AS n FROM {SCHEMA}.
                planning_session_questions WHERE session_id=%s
                GROUP BY status ORDER BY status""", (s["id"],))
        counts = ", ".join(f"{r['status']}={r['n']}"
                           for r in cur.fetchall())
        print(f"open session: {s['week_key']} ({s['status']}) - {counts}")
    cur.execute(
        f"""SELECT week_key, status, prepared_at FROM {SCHEMA}.
            planning_sessions ORDER BY prepared_at DESC LIMIT 5""")
    for r in cur.fetchall():
        print(f"  past: {r['week_key']} {r['status']} "
              f"prepared {r['prepared_at']}")
    c.close()
    return 0


def close_session():
    init()
    c = conn()
    cur = c.cursor()
    s = open_session(cur)
    if not s:
        print("no open session to close")
        c.close()
        return 0
    cur.execute(
        f"""SELECT status, COUNT(*) AS n FROM {SCHEMA}.
            planning_session_questions WHERE session_id=%s
            GROUP BY status""", (s["id"],))
    summary = {r["status"]: r["n"] for r in cur.fetchall()}
    cur.execute(
        f"""UPDATE {SCHEMA}.planning_sessions SET status='closed',
               closed_at=now(), summary=%s::jsonb WHERE id=%s""",
        (json.dumps(summary), s["id"]))
    c.commit()
    c.close()
    print(f"session {s['week_key']} closed: {summary}. Unanswered "
          "residue stays pending on the decision queue and returns "
          "next week - nothing was dropped.")
    return 0


def selftest():
    """Disposable probes: a held_brian PM step goes through prepare ->
    answer/skip for real (exercising decision_queue's verified
    write-back); goal questions are probed with one synthetic question
    (atlas.nodes grants no DELETE, so no probe goal is inserted) with
    the Intel Bridge filing stubbed to a recorder, while the real
    goal-question SQL is exercised read-only against live Atlas.
    All probe rows are removed."""
    init()
    dq.init()
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")

    # occurrence math (pure)
    cfg = {"weekday": 2, "local_time": dtime(10, 0), "tz": DEFAULT_TZ}
    occ = occurrence_for_week(
        cfg, datetime(2026, 12, 2, 9, 0, tzinfo=ZoneInfo(DEFAULT_TZ)))
    check("occurrence: Wed 2026-12-02 10:00 CT slot resolves",
          occ.date().isoformat() == "2026-12-02"
          and occ.hour == 10 and week_key_of(occ) == "2026-W49")
    nxt = next_occurrence(
        cfg, datetime(2026, 12, 2, 11, 0, tzinfo=ZoneInfo(DEFAULT_TZ)))
    check("next_occurrence rolls to the following week after the slot",
          nxt.date().isoformat() == "2026-12-09")

    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    step_key = f"SELFTEST-weekly-planning-{stamp}"
    slug = f"selftest-weekly-planning-{stamp}"
    c = conn()
    cur = c.cursor()
    cur.execute(
        f"""INSERT INTO {SCHEMA}.pm_steps (step_key, title, kind,
               origin, status)
            VALUES (%s, 'SELFTEST weekly planning probe step', 'task',
                    'system', 'held_brian') RETURNING id""", (step_key,))
    step_id = cur.fetchone()["id"]
    c.commit()
    c.close()
    ref = f"pm_steps:{step_id}"
    gref = f"goal:{slug}"
    # the real goal-question SQL runs read-only against live Atlas
    c = conn()
    cur = c.cursor()
    live_goals = goal_questions(cur)
    c.close()
    check("goal_questions SQL runs on live Atlas, shape holds",
          isinstance(live_goals, list) and all(
              "title" in g and "source_ref" in g for g in live_goals))
    # session mechanics use one synthetic goal question (atlas.nodes
    # grants this user no DELETE, so no probe goal is ever inserted)
    synthetic = {"kind": "goal", "source_ref": gref,
                 "title": "Goal 'SELFTEST': probe blocker question",
                 "context": {"goal_slug": slug, "blocker": "probe"}}
    filed = []
    orig_filer = file_goal_answer
    orig_gq = goal_questions
    globals()["file_goal_answer"] = (
        lambda q, a, by: filed.append((q["source_ref"], a)))
    globals()["goal_questions"] = lambda cur: [synthetic]
    try:
        sid = prepare(week_key="SELFTEST", quiet=True)
        c = conn()
        cur = c.cursor()
        cur.execute(
            f"""SELECT source_ref, kind FROM {SCHEMA}.
                planning_session_questions WHERE session_id=%s
                AND source_ref IN (%s, %s)""", (sid, ref, gref))
        got = {r["source_ref"]: r["kind"] for r in cur.fetchall()}
        check("prepare snapshots the residue probe", got.get(ref)
              == "residue")
        check("prepare snapshots the blocked-goal question",
              got.get(gref) == "goal")
        # session-local only: park every other question so the probes
        # are the ones served (the real queue is untouched by this)
        cur.execute(
            f"""UPDATE {SCHEMA}.planning_session_questions
                   SET status='carried' WHERE session_id=%s
                   AND source_ref NOT IN (%s, %s)""", (sid, ref, gref))
        c.commit()
        c.close()
        check("answer residue probe via write-back",
              answer("selftest ruling - probe approved") == 0)
        c = conn()
        cur = c.cursor()
        cur.execute(f"SELECT status FROM {SCHEMA}.pm_steps WHERE id=%s",
                    (step_id,))
        check("owning pm_step left held_brian (ruled)",
              cur.fetchone()["status"] == "done")
        c.close()
        check("answer goal probe (filing stubbed)",
              answer("selftest goal answer") == 0)
        check("goal answer reached the filer", len(filed) == 1
              and filed[0][0] == gref)
        # skip/carry on a fresh probe step
        c = conn()
        cur = c.cursor()
        cur.execute(
            f"""INSERT INTO {SCHEMA}.pm_steps (step_key, title, kind,
                   origin, status)
                VALUES (%s, 'SELFTEST weekly planning carry probe',
                        'task', 'system', 'held_brian')
                RETURNING id""", (step_key + "-carry",))
        step2 = cur.fetchone()["id"]
        c.commit()
        c.close()
        prepare(week_key="SELFTEST", quiet=True)
        c = conn()
        cur = c.cursor()
        cur.execute(
            f"""UPDATE {SCHEMA}.planning_session_questions
                   SET status='carried' WHERE session_id=%s
                   AND source_ref <> %s""", (sid, f"pm_steps:{step2}"))
        c.commit()
        c.close()
        check("skip carries the probe", skip("selftest carry") == 0)
        c = conn()
        cur = c.cursor()
        cur.execute(f"SELECT status FROM {SCHEMA}.pm_steps WHERE id=%s",
                    (step2,))
        check("carried step stays held_brian (never dropped)",
              cur.fetchone()["status"] == "held_brian")
        c.close()
    finally:
        globals()["file_goal_answer"] = orig_filer
        globals()["goal_questions"] = orig_gq
        c = conn()
        cur = c.cursor()
        cur.execute(f"DELETE FROM {SCHEMA}.planning_sessions "
                    "WHERE week_key='SELFTEST'")
        cur.execute(f"DELETE FROM {SCHEMA}.pm_steps WHERE step_key "
                    "LIKE %s", (f"SELFTEST-weekly-planning-{stamp}%",))
        cur.execute(
            f"DELETE FROM {dq.SCHEMA}.{dq.TABLE} WHERE source_ref "
            "LIKE 'pm_steps:%' AND title LIKE 'SELFTEST weekly "
            "planning%'")
        c.commit()
        c.close()
    failed = [n for n, ok in checks if not ok]
    print(f"SELFTEST {'OK' if not failed else 'FAILED'} "
          f"({len(checks)} checks)")
    return 0 if not failed else 1


from datetime import time as dtime, timezone  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description="Weekly deep-planning session (SBOS)")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--config", action="store_true")
    ap.add_argument("--set-time", metavar='"wed 10:00"')
    ap.add_argument("--tz", default=DEFAULT_TZ)
    ap.add_argument("--lead", type=int, default=240)
    ap.add_argument("--by", default="brian")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--tick", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--answer", metavar="TEXT")
    ap.add_argument("--skip", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--close", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.init:
        return init()
    if a.set_time:
        day, hhmm = a.set_time.split()
        return set_time(day, hhmm, tz=a.tz, lead=a.lead, by=a.by)
    if a.disable:
        init()
        c = conn()
        cur = c.cursor()
        cur.execute(f"UPDATE {SCHEMA}.planning_session_config "
                    "SET enabled=false, updated_at=now() WHERE id=1")
        c.commit()
        c.close()
        print("weekly slot disabled (config kept)")
        return 0
    if a.config:
        return show_config()
    if a.prepare:
        prepare()
        return 0
    if a.tick:
        return tick()
    if a.next:
        return show_next()
    if a.answer:
        return answer(a.answer, by=a.by)
    if a.skip:
        return skip(note=a.note, by=a.by)
    if a.status:
        return show_status()
    if a.close:
        return close_session()
    if a.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
