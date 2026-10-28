#!/usr/bin/env python3
"""
PURPOSE:
    The common repeated routines of SuccessBrian OS, defined ONCE.

WHY:
    Audit 2026-10-27 (Brian: "code common repeated routines"): across
    ~/bin + tools/ the same small routines were hand-copied over and over —
      * SQL quote escaping `esc()`            — 35 separate definitions
      * Postgres helpers (psql/pg/q/db/...)   — 100+ separate definitions
        (30x `def psql`, 13x `def pg`, 12x pg_exec, 11x q, 9x pg_query,
         8x db, 8x _psql, 6x kssh_psql); 50 files psycopg2.connect,
         22 files shell out to psql themselves
      * LLM chat/completions callers          — 29 files
      * `log()`                               — 9 definitions
      * `slugify()`                           — 5 definitions
    Every copy is a place a fix has to be made 35 times — and wasn't:
    the qwen_task_queue duplicate flood (2026-10-27) lived in one copy of
    the queue-add routine while its correct pattern sat in another.
    New code imports from here. Existing files migrate in vetted batches.

CONTENTS:
    esc(s)                  — the 35-copy SQL string escape, verbatim semantics
    slugify(s)              — the 5-copy slug routine
    log(msg)                — timestamped stdout line (the 9-copy logger)
    pg_rows(sql, params)    — query -> list of row tuples (psycopg2)
    pg_one(sql, params)     — first row / first value
    pg_exec(sql, params)    — write, committed
    llm_chat(prompt, ...)   — chat/completions -> (text, usage dict)
    SONIC / MORPHEUS / PENNY— local model endpoint presets (env-overridable)
    pulse(source, message, metrics) — one Lyra-table (clerk_checkins) row
    add_queue_task(...)     — qwen_task_queue add WITH the 2026-10-27
                              dedupe fix (title+description, any status
                              except 'cancelled')

NOTES:
    DB access uses psycopg2 with a fresh connection per call — the same
    shape the existing helpers use, so migration changes call sites, not
    behavior. Parameterized queries (%s params) are supported so new code
    can stop hand-escaping; esc() remains for legacy-shaped call sites.
    Selftest: python3 sbos_common.py --selftest
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

DB_NAME = os.environ.get("SBOS_DB", "ecosystem_central")

# Local model endpoints (llama.cpp servers on k11-alpha).
SONIC_URL = os.environ.get("SONIC_URL", "http://127.0.0.1:11439/v1/chat/completions")
SONIC_MODEL = os.environ.get("SONIC_MODEL", "qwen3.6")
MORPHEUS_URL = os.environ.get("MORPHEUS_URL", "http://127.0.0.1:11437/v1/chat/completions")
PENNY_URL = os.environ.get("PENNY_URL", "http://127.0.0.1:11438/v1/chat/completions")


# ---------------------------------------------------------------- basics

def esc(s) -> str:
    """SQL string escape — identical to the 35 hand-copied versions."""
    return str(s or "").replace("'", "''")


def slugify(s: str) -> str:
    """Lowercase hyphen slug — the shape the 5 copies converge on."""
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------------------------------------------------------------- postgres

def connect(user: str = None, dbname: str = None):
    """The one connection factory. Batch B (2026-10-27): the Atlas
    family's pg() returned a raw psycopg2 connection as user 'postgres';
    callers that need the connection itself (cursor-style work) get it
    here, with the same host/db/role they always used."""
    import psycopg2
    kw = {"dbname": dbname or DB_NAME, "host": "localhost"}
    if user:
        kw["user"] = user
    return psycopg2.connect(**kw)


def _connect(user: str = None, dbname: str = None):
    return connect(user=user, dbname=dbname)


def pg_rows(sql: str, params=None, user: str = None, dbname: str = None):
    """Run a query, return all rows as a list of tuples."""
    conn = _connect(user=user, dbname=dbname)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if cur.description is None:
            # Write statement with no RETURNING (INSERT/UPDATE/DELETE):
            # psycopg2 produces no result set, and fetchall() raises
            # ProgrammingError no results to fetch (root cause of the
            # 2026-10-27 atlas add-node break / clerk freeze, fixed
            # 2026-10-28). Commit the write and report zero rows.
            conn.commit()
            return []
        rows = cur.fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def pg_one(sql: str, params=None, user: str = None, dbname: str = None):
    """First row of a query (or its single value), None when empty."""
    rows = pg_rows(sql, params, user=user, dbname=dbname)
    if not rows:
        return None
    row = rows[0]
    return row[0] if len(row) == 1 else row


def pg_exec(sql: str, params=None, user: str = None,
            dbname: str = None) -> int:
    """Run a write, commit, return affected row count."""
    conn = _connect(user=user, dbname=dbname)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


# ------------------------------------------------- psql-text compatibility
# The legacy helpers (heartbeat/harness query(), qwen db_query()) return
# psql's TEXT output and their callers split/strip/parse those strings.
# These wrappers reproduce psql -A -t formatting from psycopg2 values so
# a migrated file's call sites behave byte-for-byte as before.

def _fmt_psql(v) -> str:
    """Format one value the way psql -A prints it."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "t" if v else "f"
    from datetime import datetime as _dt, date as _date
    if isinstance(v, _dt):
        base = v.strftime("%Y-%m-%d %H:%M:%S")
        if v.microsecond:
            base += "." + ("%06d" % v.microsecond).rstrip("0")
        if v.tzinfo is not None:
            off = v.utcoffset()
            if off is not None:
                total = int(off.total_seconds())
                sign = "+" if total >= 0 else "-"
                total = abs(total)
                hh, rem = divmod(total, 3600)
                mm = rem // 60
                base += f"{sign}{hh:02d}" + (f":{mm:02d}" if mm else "")
        return base
    if isinstance(v, _date):
        return v.isoformat()
    from datetime import timedelta as _tdlt
    if isinstance(v, _tdlt):
        # Postgres interval style: '1 day 02:00:00' / '02:00:00',
        # zero-padded, fractional seconds trailing-zero trimmed.
        total = v.total_seconds()
        sign = "-" if total < 0 else ""
        a = abs(total)
        days = int(a // 86400)
        rem = a - days * 86400
        hh = int(rem // 3600)
        mm = int((rem % 3600) // 60)
        ss = rem % 60
        ss_str = ("%05.6f" % ss).rstrip("0").rstrip(".") if ss % 1 else "%02d" % int(ss)
        out = f"{hh:02d}:{mm:02d}:{ss_str}"
        if days:
            out = f"{days} day{'s' if days != 1 else ''} " + out
        return sign + out
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return format(v, "f")
    except Exception:
        pass
    return str(v)


def pg_text(sql: str, sep: str = "\t", user: str = None,
            dbname: str = None, strict: bool = False) -> str:
    """Raw-SQL query -> psql-style text (rows joined by newline, values
    by sep). Returns '' on error — the legacy query() semantics — unless
    strict=True, where the error raises (discovery.psql semantics).
    The SQL is sent with NO parameter interpolation (like psql -c), so
    literal % signs in the SQL are safe."""
    try:
        rows = pg_rows(sql, user=user, dbname=dbname)
    except Exception:
        if strict:
            raise
        return ""
    return "\n".join(sep.join(_fmt_psql(v) for v in row) for row in rows)


def pg_lines(sql: str, sep: str = "|", user: str = None,
             dbname: str = None, strict: bool = False):
    """Raw-SQL query -> list of psql-style text lines ([] on error, or
    raise when strict=True) — the legacy qwen db_query() semantics."""
    try:
        rows = pg_rows(sql, user=user, dbname=dbname)
    except Exception:
        if strict:
            raise
        return []
    out = []
    for row in rows:
        line = sep.join(_fmt_psql(v) for v in row)
        if line.strip():
            out.append(line)
    return out


def pg_exec_bool(sql: str, user: str = None, dbname: str = None) -> bool:
    """Raw-SQL write -> True/False — the legacy exec_sql()/db_exec()
    semantics, except honest: psql without ON_ERROR_STOP reports
    success on failed SQL; psycopg2 raises, so False means it failed."""
    try:
        pg_exec(sql, user=user, dbname=dbname)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- llm

def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def normalize_usage(body: dict, fallback_model: str = "") -> dict:
    """The usage-normalizer copied into qwen_task_worker and
    harness_worker: ints or None, total derived from parts when the
    server omits it, model from the response or the fallback."""
    raw = (body or {}).get("usage") or {}
    usage = {
        "prompt_tokens": _int_or_none(raw.get("prompt_tokens")),
        "completion_tokens": _int_or_none(raw.get("completion_tokens")),
        "total_tokens": _int_or_none(raw.get("total_tokens")),
        "model": (body or {}).get("model") or fallback_model,
    }
    if (usage["total_tokens"] is None and usage["prompt_tokens"] is not None
            and usage["completion_tokens"] is not None):
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage


def llm_chat(prompt: str = None, messages=None, url: str = SONIC_URL,
             model: str = SONIC_MODEL, max_tokens: int = 800,
             temperature: float = 0.3, timeout: int = 300,
             headers: dict = None):
    """One chat/completions call. Returns (text, usage-dict normalized).

    The 29 hand-copied callers all build this same urllib request and
    then throw the usage field away; here usage comes back with the text
    so per-task time/token reporting (Lyra table) is free.
    Pass prompt= for the common single-user-message shape, or
    messages=[...] for system+user shapes. model=None omits the model
    field entirely (llama-server default), max_tokens=None omits it.
    Raises on transport/HTTP error — callers keep their own error shape.
    """
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    payload = {"messages": messages, "temperature": temperature}
    if model is not None:
        payload["model"] = model
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode())
    text = body["choices"][0]["message"]["content"]
    return text, normalize_usage(body, fallback_model=model or "")


def http_ok(url: str, timeout: int = 10) -> bool:
    """GET a health URL, True iff HTTP 200 — the sonic_available()
    pattern copied into both the heartbeat and the harness worker."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------- lyra pulse

def pulse(source: str, message: str, metrics: dict = None) -> bool:
    """File one row in the Lyra table (successbrian_os.clerk_checkins).

    Brian's 2026-10-26 ruling: workers report there — performance from
    the stats each row carries, silence is Lyra's investigation case.
    The clerk flow counters are NOT NULL and are not the worker's, so
    they are filed as 0, exactly as qwen_task_worker does today.
    Returns True when the row landed.
    """
    try:
        pg_exec(
            """INSERT INTO successbrian_os.clerk_checkins
                 (source, message, tasks_created, queue_depth, metrics,
                  captures_in, board_filed, sent_altair, bounced, filed_kept,
                  rechecks_sent)
               VALUES (%s, %s, NULL, NULL, %s, 0, 0, 0, 0, 0, 0)""",
            (source, message, json.dumps(metrics or {})))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- task queue

def add_queue_task(title: str, description: str, source: str = "discovery",
                   priority: int = 3):
    """Add a task to successbrian_os.qwen_task_queue, deduped.

    Carries the 2026-10-27 SBOS dedupe fix: a job is the same job when
    title AND description match, at ANY status except 'cancelled'
    (the old copies checked 'pending' only and re-created the same
    bridge/outbox jobs every 600s — 1,434 duplicate rows).
    Returns the existing task id when the job is already queued.
    """
    import uuid
    rows = pg_rows(
        """SELECT id FROM successbrian_os.qwen_task_queue
            WHERE title = %s AND description = %s AND status <> 'cancelled'
            LIMIT 1""",
        (title, description))
    if rows:
        return rows[0][0]
    task_id = f"qtw-{uuid.uuid4().hex[:8]}"
    pg_exec(
        """INSERT INTO successbrian_os.qwen_task_queue
             (id, title, description, source, priority)
           VALUES (%s, %s, %s, %s, %s)""",
        (task_id, title, description, source, priority))
    return task_id


# ------------------------------------------------------- v4pro handoffs
# The handoff lifecycle (enqueue / claim / get / mark / release) lived
# in v4pro_handoff_worker.py, v4pro_router.py and podcast_friday_kickoff
# as separate hand-built SQL. One definition now (Batch C, 2026-10-27).

def handoff_enqueue(requested_by: str, task_kind: str, task_summary: str,
                    context: str = "", sonic_draft: str = "",
                    ask: str = "", constraints: str = "") -> int:
    """Queue one DeepSeek V4 Pro handoff; returns its id."""
    return pg_one(
        """INSERT INTO successbrian_os.v4pro_handoffs
             (requested_by, task_kind, task_summary, context, sonic_draft,
              ask, constraints, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') RETURNING id""",
        (requested_by, task_kind, task_summary, context, sonic_draft,
         ask, constraints))


def handoff_claim(limit: int = 3):
    """Atomically claim up to `limit` queued handoffs (FOR UPDATE SKIP
    LOCKED — parallel workers never get the same row). Returns ids."""
    rows = pg_rows(
        """UPDATE successbrian_os.v4pro_handoffs SET status = 'working'
            WHERE id IN (SELECT id FROM successbrian_os.v4pro_handoffs
                          WHERE status = 'queued' ORDER BY created_at
                          LIMIT %s FOR UPDATE SKIP LOCKED)
            RETURNING id""",
        (int(limit),))
    return [int(r[0]) for r in rows]


def handoff_get(hid: int) -> dict:
    """The worker's view of one handoff (text fields, None -> '')."""
    row = pg_one(
        """SELECT task_kind, task_summary, context, sonic_draft, ask,
                  constraints
             FROM successbrian_os.v4pro_handoffs WHERE id = %s""",
        (int(hid),))
    keys = ["kind", "summary", "context", "draft", "ask", "constraints"]
    if row is None:
        return dict(zip(keys, [""] * 6))
    return dict(zip(keys, [("" if v is None else str(v)) for v in row]))


def handoff_mark(hid: int, status: str, result: str = "",
                 error: str = "") -> None:
    """Finish a handoff: status + result/error + completed_at.
    Truncation matches the worker's historical caps."""
    pg_exec(
        """UPDATE successbrian_os.v4pro_handoffs
              SET status = %s, v4pro_result = %s, error = %s,
                  completed_at = now()
            WHERE id = %s""",
        (status, (result or "")[:20000], (error or "")[:1000], int(hid)))


def handoff_release(hid: int) -> None:
    """Put a claimed handoff back to queued (checker unavailable)."""
    pg_exec(
        "UPDATE successbrian_os.v4pro_handoffs SET status = 'queued' "
        "WHERE id = %s",
        (int(hid),))


# ------------------------------------------------------- knowledge bridge
# altair.knowledge_bridge is the agents' message bus (Brian 2026-10-24:
# sender, target, subject, body, urgency, read_at). 25 files read/write
# it by hand; these are the shared accessors (Batch C, 2026-10-27).
# Sending is always parameterized now — no more $$-quoting workarounds.

def bridge_send(sender: str, target: str, subject: str, body: str,
                urgency: str = "routine") -> int:
    """Post one message on the bus; returns its id.
    urgency is TEXT by table constraint: routine | important | critical."""
    return pg_one(
        """INSERT INTO altair.knowledge_bridge
             (sender, target, subject, body, urgency)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (sender, target, subject, body, urgency))


def bridge_unread(target: str, limit: int = 50):
    """Unread messages for a target, newest first: list of dicts."""
    rows = pg_rows(
        """SELECT id, sender, subject, body, urgency, created_at
             FROM altair.knowledge_bridge
            WHERE target = %s AND read_at IS NULL
            ORDER BY id DESC LIMIT %s""",
        (target, int(limit)))
    return [{"id": r[0], "sender": r[1], "subject": r[2], "body": r[3],
             "urgency": r[4], "created_at": r[5]} for r in rows]


def bridge_mark_read(ids) -> int:
    """Mark messages read (sets read_at). Returns rows updated."""
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    return pg_exec(
        "UPDATE altair.knowledge_bridge SET read_at = now() "
        "WHERE id = ANY(%s) AND read_at IS NULL",
        (ids,))


# ---------------------------------------------------------------- selftest

def selftest() -> int:
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    check("esc doubles quotes", esc("a'b") == "a''b")
    check("esc handles None", esc(None) == "")
    check("slugify basic", slugify("Hello, World! 2026") == "hello-world-2026")
    check("slugify collapses", slugify("a -- b__c") == "a-b-c")
    check("pg read works", pg_one("SELECT 1") == 1)

    # psql-text formatting (the Batch A migration layer)
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from decimal import Decimal as _Dec
    check("fmt bool/null", _fmt_psql(True) == "t" and _fmt_psql(False) == "f"
          and _fmt_psql(None) == "")
    check("fmt decimal", _fmt_psql(_Dec("36.62")) == "36.62")
    check("fmt timestamptz",
          _fmt_psql(_dt(2026, 10, 27, 9, 15, 27, 895170,
                        tzinfo=_tz(_td(hours=-5))))
          == "2026-10-27 09:15:27.89517-05")
    check("fmt timestamptz no fraction",
          _fmt_psql(_dt(2026, 10, 27, 9, 15, 27,
                        tzinfo=_tz(_td(hours=-5))))
          == "2026-10-27 09:15:27-05")
    check("pg literal % is safe (no interpolation)",
          pg_one("SELECT 'x' WHERE 'a%b' LIKE 'a%b'") == "x")
    check("usage total derived",
          normalize_usage({"usage": {"prompt_tokens": 3,
                                     "completion_tokens": 4},
                           "model": "m"})["total_tokens"] == 7)

    # Queue dedupe: add a unique test job twice inside the live table,
    # second call must return the SAME id and add no row; then clean up.
    import uuid
    tag = f"sbos-common-selftest-{uuid.uuid4().hex[:8]}"
    try:
        first = add_queue_task(tag, "selftest body", source="selftest", priority=1)
        second = add_queue_task(tag, "selftest body", source="selftest", priority=1)
        n = pg_one(
            "SELECT count(*) FROM successbrian_os.qwen_task_queue WHERE title = %s",
            (tag,))
        check("queue dedupe: same id, one row", first == second and n == 1)
    finally:
        pg_exec("DELETE FROM successbrian_os.qwen_task_queue WHERE title = %s",
                (tag,))

    # Handoff + bridge round-trips (selftest rows, cleaned up after).
    try:
        hid = handoff_enqueue("sbos-common-selftest", "selftest",
                              "sbos_common handoff round-trip",
                              ask="ignore")
        got = handoff_get(hid)
        handoff_mark(hid, "cancelled", result="selftest")
        st = pg_one(
            "SELECT status FROM successbrian_os.v4pro_handoffs WHERE id = %s",
            (hid,))
        check("handoff enqueue/get/mark", got["summary"].startswith(
            "sbos_common handoff") and st == "cancelled")
        pg_exec("DELETE FROM successbrian_os.v4pro_handoffs WHERE id = %s",
                (hid,))
    except Exception as e:
        check(f"handoff round-trip raised {e}", False)
    try:
        bid = bridge_send("sbos-selftest", "sbos-selftest",
                          "sbos_common bridge round-trip", "ignore")
        un = bridge_unread("sbos-selftest", limit=5)
        n = bridge_mark_read([bid])
        check("bridge send/unread/mark_read",
              any(m["id"] == bid for m in un) and n == 1)
        pg_exec("DELETE FROM altair.knowledge_bridge WHERE id = %s", (bid,))
    except Exception as e:
        check(f"bridge round-trip raised {e}", False)

    print("SELFTEST " + ("GREEN" if not fails else f"FAILED: {fails}"))
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
