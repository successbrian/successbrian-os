#!/usr/bin/env python3
"""cron_time_tracker.py — SBOS time tracking for ALL daily crons.

Brian (2026-11-05): "all daily crons should be tracked through an SBOS
time tracking system."

Before this tool, successbrian_os.cron_jobs / cron_runs existed as a
skeleton that nothing wrote to (cron_runs had 0 rows), and the
mini-PC price watch ran degraded on 2026-11-03 (6 of ~59 specs
priced) with nobody noticing. This tracker is the live system:

  sync   — register EVERY line of the successbrian crontab and
           /etc/cron.d/dealsdesk-* as a job in cron_jobs, plus the
           Muse-side daily jobs (source='muse-cron', run history
           lives in the Muse scheduler — no run rows fabricated).
  audit  — for each active job DUE on a date, write one cron_runs
           row (scheduled-vs-actual). Evidence is the job's log
           file mtime/size that day. A job with no log evidence past
           its grace window is 'missed' ONLY if it has a log_path;
           otherwise 'unknown' — not knowing is not the same as not
           (Brian's law). exit_code / duration stay NULL: they are
           not knowable from log evidence and are never invented.
           Files a daily summary into successbrian_os.reports
           (report_type='cron-time-tracking').

Deterministic, stdlib + psycopg2 only, zero AI tokens, idempotent
(sync and audit can re-run safely; cron_runs upserts on
(job_id, date, scheduled_time)). Never deletes history rows.
Credential-looking values in crontab commands are redacted before
storage and before any printing.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

TZ = ZoneInfo("America/Chicago")
REPO_TOOLS = os.path.dirname(os.path.abspath(__file__))
SELF_COMMAND = ("/usr/bin/python3 /home/successbrian/successbrian-os/"
                "tools/cron_time_tracker.py audit")
SELF_LOG = "/home/successbrian/logs/cron-time-tracker.log"
SELF_SLUG_SCHEDULE = "48 * * * *"
GRACE_MIN = 90

CLAUDE_JOBS = [
    # slug, name, schedule, cadence, primary_time HH:MM
    ("daily-flow-capture", "Daily Flow Capture (Muse)",
     "41 23 * * *", "daily", "23:41"),
    ("friend-vetting-daily-10", "Friend Vetting Daily 10 (Muse)",
     "41 9 * * *", "daily", "09:41"),
    ("amd-stock-daily-watch", "AMD Stock Daily Watch (Muse)",
     "41 15 * * 1-5", "weekday", "15:41"),
    ("duol-bottom-watch-2026", "DUOL Bottom Watch 2026 (Muse)",
     "41 15 * * 1-5", "weekday", "15:41"),
    ("intc-stock-daily-watch", "INTC Stock Daily Watch (Muse)",
     "41 15 * * 1-5", "weekday", "15:41"),
]

MONTH_NAMES = {n: i + 1 for i, n in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
DOW_NAMES = {n: i for i, n in enumerate(
    ["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}
CRON_D_USERS = {"root", "successbrian", "dealsdesk", "agents", "postgres"}

SECRET_RE = re.compile(
    r"((?:PASSWORD|PASSWD|PASS|TOKEN|SECRET|API[_-]?KEY|AUTH)"
    r"\s*=\s*)[^\s'\"]+"
    r"|(--(?:password|token|api[-_]?key)[=\s])[^\s'\"]+"
    r"|(\bmysql\b[^|;]*?\s-p)[^\s]+"
    r"|(https?://[^:\s/]+:)[^@\s]+@", re.IGNORECASE)


def redact(text):
    if not text:
        return text
    return SECRET_RE.sub(lambda m: (m.group(1) or m.group(2)
                                     or m.group(3) or m.group(4)
                                     or "") + "REDACTED", text)


def db():
    return psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)


# ---------- cron schedule machinery ----------

def _atom(tok, names=None):
    tok = tok.strip().lower()
    if names and tok in names:
        return names[tok]
    return int(tok)


def field_values(field, lo, hi, names=None):
    """Expand one cron field to a sorted set of ints (within lo..hi)."""
    vals = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a_s, b_s = part.split("-", 1)
            a, b = _atom(a_s, names), _atom(b_s, names)
        else:
            a = _atom(part, names)
            b = hi if "/" in field and False else a
            if step != 1 and part != "*":
                b = hi
        v = a
        while v <= b:
            vals.add(v)
            v += step
    return sorted(v for v in vals if lo <= v <= hi)


def field_matches(field, value, lo, hi, names=None):
    if field.strip() == "*":
        return True
    return value in field_values(field, lo, hi, names)


def is_due(schedule, d):
    """Cron due-date test. dom/dow follow standard cron OR semantics
    when both are restricted."""
    f = schedule.split()
    if len(f) != 5:
        return False
    minute, hour, dom, month, dow = f
    if not field_matches(month, d.month, 1, 12, MONTH_NAMES):
        return False
    dom_star = dom.strip() == "*"
    dow_star = dow.strip() == "*"
    cron_dow = (d.weekday() + 1) % 7  # Mon=1 .. Sat=6, Sun=0
    dow_hit = field_matches(dow, cron_dow, 0, 7, DOW_NAMES) or (
        cron_dow == 0 and field_matches(dow, 7, 0, 7, DOW_NAMES))
    dom_hit = field_matches(dom, d.day, 1, 31)
    if dom_star and dow_star:
        return True
    if dom_star:
        return dow_hit
    if dow_star:
        return dom_hit
    return dom_hit or dow_hit


def cadence_of(schedule):
    f = schedule.split()
    if len(f) != 5:
        return "daily"
    minute, hour, dom, month, dow = f
    if dom.strip() != "*" or month.strip() != "*":
        return "monthly"
    _mins = field_values(minute, 0, 59)
    _hours = field_values(hour, 0, 23)
    if len(_mins) * len(_hours) > 1:
        return "subdaily"
    if dow.strip() != "*":
        dow_vals = field_values(dow, 0, 7, DOW_NAMES)
        dow_vals = sorted({0 if v == 7 else v for v in dow_vals})
        return "weekday" if dow_vals == [1, 2, 3, 4, 5] else "weekly"
    mins = field_values(minute, 0, 59)
    hours = field_values(hour, 0, 23)
    if len(mins) * len(hours) > 1:
        return "subdaily"
    return "daily"


def first_time_of(schedule):
    f = schedule.split()
    mins = field_values(f[0], 0, 59)
    hours = field_values(f[1], 0, 23)
    return time(min(hours), min(mins))


def scheduled_time_of(schedule, cadence):
    if cadence == "subdaily":
        return schedule
    t = first_time_of(schedule)
    return f"{t.hour:02d}:{t.minute:02d}"


# ---------- crontab parsing ----------

ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")
REDIRECT_RE = re.compile(r">>\s*([^\s]+)")
AT_MAP = {"@hourly": "0 * * * *", "@daily": "0 0 * * *",
          "@midnight": "0 0 * * *", "@weekly": "0 0 * * 0",
          "@monthly": "0 0 1 * *", "@yearly": "0 0 1 1 *",
          "@annually": "0 0 1 1 *"}


def sanitize(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "job"


INTERPRETERS = {"python3", "python", "bash", "sh", "env", "node",
                "perl", "ruby", "php"}

def script_basename(command):
    toks = [t.strip("'\"") for t in command.split()]
    for tok in toks:  # the real script file, if any token names one
        if re.search(r"\.(py|sh|pl|rb|js)$", tok):
            return os.path.basename(tok)
    for tok in toks:  # else first path that is not an interpreter
        if "/" in tok and not tok.startswith("--"):
            base = os.path.basename(tok)
            if base and base not in INTERPRETERS:
                return base
    parts = command.split()
    return parts[0] if parts else "job"


def slug_for(schedule, command):
    base = script_basename(command)
    base = re.sub(r"\.(py|sh|pl|rb)$", "", base)
    h = hashlib.md5(f"{schedule} {command}".encode()).hexdigest()[:6]
    return f"{sanitize(base)}-{h}"


def parse_cron_line(line, cron_d=False):
    """Return dict(schedule, command, log_path) or None."""
    line = line.strip()
    if not line or line.startswith("#") or ENV_RE.match(line):
        return None
    if line.startswith("@"):
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[0] not in AT_MAP:
            return None
        schedule, rest = AT_MAP[parts[0]], parts[1]
    else:
        parts = line.split(None, 5)
        if len(parts) < 6:
            return None
        schedule = " ".join(parts[:5])
        rest = parts[5]
        if cron_d:
            first = rest.split(None, 1)
            if len(first) == 2 and first[0] in CRON_D_USERS:
                rest = first[1]
    m = REDIRECT_RE.search(rest)
    log_path = m.group(1) if m else None
    command = REDIRECT_RE.sub("", rest)
    command = re.sub(r"\s*2>&1\s*$", "", command).strip()
    command = redact(command)
    if log_path:
        log_path = log_path.strip("'\"")
    return {"schedule": schedule, "command": command,
            "log_path": log_path}


def read_alpha_lines():
    out = []
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True,
                           text=True, timeout=30)
        text = r.stdout if r.returncode == 0 else ""
    except Exception:
        text = ""
    if not text:
        try:
            with open("/var/spool/cron/crontabs/successbrian") as fh:
                text = fh.read()
        except Exception:
            text = ""
    for ln in text.splitlines():
        p = parse_cron_line(ln, cron_d=False)
        if p:
            p["source"] = "alpha-crontab"
            out.append(p)
    for path in sorted(glob.glob("/etc/cron.d/dealsdesk-*")):
        try:
            with open(path) as fh:
                lines = fh.read().splitlines()
        except Exception:
            continue
        for ln in lines:
            p = parse_cron_line(ln, cron_d=True)
            if p:
                p["source"] = "cron.d"
                out.append(p)
    return out


# ---------- sync ----------

def upsert_job(cur, slug, name, command, schedule, source, log_path,
               cad, goal_cluster=None):
    cur.execute(
        """INSERT INTO successbrian_os.cron_jobs
             (job_slug, name, command, primary_time, status, source,
              log_path, cadence, goal_cluster)
           VALUES (%s,%s,%s,%s,'active',%s,%s,%s,%s)
           ON CONFLICT (job_slug) DO UPDATE
             SET name=EXCLUDED.name, command=EXCLUDED.command,
                 primary_time=EXCLUDED.primary_time, source=EXCLUDED.source,
                 log_path=EXCLUDED.log_path, cadence=EXCLUDED.cadence,
                 status=CASE WHEN successbrian_os.cron_jobs.status='retired'
                             THEN 'active'
                             ELSE successbrian_os.cron_jobs.status END
           RETURNING id""",
        (slug, name, command, schedule, source, log_path, cad,
         goal_cluster))
    return cur.fetchone()["id"]


def do_sync(cur):
    lines = read_alpha_lines()
    seen = set()
    counts = {}
    for p in lines:
        slug = slug_for(p["schedule"], p["command"])
        seen.add(slug)
        cad = cadence_of(p["schedule"])
        name = re.sub(r"\.(py|sh)$", "",
                      script_basename(p["command"])).replace("_", " ")
        upsert_job(cur, slug, name.title() if name else slug,
                   p["command"], p["schedule"], p["source"],
                   p["log_path"], cad)
        counts[p["source"]] = counts.get(p["source"], 0) + 1
    # self job (matches the installed line exactly once installed)
    slug = slug_for(SELF_SLUG_SCHEDULE, SELF_COMMAND)
    seen.add(slug)
    upsert_job(cur, slug, "Cron Time Tracker", SELF_COMMAND,
               SELF_SLUG_SCHEDULE, "alpha-crontab", SELF_LOG,
               cadence_of(SELF_SLUG_SCHEDULE))
    # Muse-side jobs
    for slug, name, sched, cad, _hhmm in CLAUDE_JOBS:
        upsert_job(cur, slug, name,
                   f"Muse scheduler job: {slug}", sched, "muse-cron",
                   None, cad,
                   goal_cluster="muse-cron: run history lives in the "
                                "Muse scheduler")
    # backfill cadence for curated rows from their primary_time
    cur.execute("SELECT id, primary_time FROM successbrian_os.cron_jobs "
                "WHERE cadence IS NULL AND primary_time IS NOT NULL")
    for row in cur.fetchall():
        cur.execute("UPDATE successbrian_os.cron_jobs SET cadence=%s "
                    "WHERE id=%s",
                    (cadence_of(row["primary_time"]), row["id"]))
    # retire vanished alpha lines
    cur.execute(
        """UPDATE successbrian_os.cron_jobs SET status='retired'
           WHERE source IN ('alpha-crontab','cron.d')
             AND NOT (job_slug = ANY(%s))""", (list(seen),))
    retired = cur.rowcount
    return counts, retired


# ---------- audit ----------

def log_evidence(log_path, d):
    """(actual_time, size) if the log file's mtime falls on date d."""
    if not log_path:
        return None
    try:
        st = os.stat(log_path)
    except Exception:
        return None
    mtime = datetime.fromtimestamp(st.st_mtime, TZ)
    if mtime.date() == d:
        return mtime, st.st_size
    return None


def do_audit(cur, d, now=None):
    now = now or datetime.now(TZ)
    cur.execute("SELECT * FROM successbrian_os.cron_jobs "
                "WHERE status='active' ORDER BY job_slug")
    jobs = cur.fetchall()
    stats = {"due": 0, "ran": 0, "missed": 0, "unknown": 0}
    missed_names = []
    self_slug = slug_for(SELF_SLUG_SCHEDULE, SELF_COMMAND)
    for job in jobs:
        sched = job["primary_time"]
        if not sched or not is_due(sched, d):
            continue
        cad = job["cadence"] or cadence_of(sched)
        stime = scheduled_time_of(sched, cad)
        stats["due"] += 1
        status, actual, metric = "unknown", None, {}
        if job["job_slug"] == self_slug and d == now.date():
            status, actual = "ran", now
            metric = {"evidence": "self_run"}
        elif job["source"] == "muse-cron":
            status = "unknown"
            metric = {"evidence": "none_on_alpha",
                      "note": "run history lives in the Muse scheduler"}
        else:
            ev = log_evidence(job["log_path"], d)
            if ev:
                status, actual = "ran", ev[0]
                metric = {"evidence": "log_mtime",
                          "log_path": job["log_path"], "log_size": ev[1]}
            elif cad == "subdaily":
                if d < now.date():
                    status = "missed" if job["log_path"] else "unknown"
                else:
                    status = "unknown"
            else:
                t = first_time_of(sched)
                deadline = datetime.combine(d, t, TZ) + timedelta(
                    minutes=GRACE_MIN)
                if now > deadline:
                    status = "missed" if job["log_path"] else "unknown"
                else:
                    status = "unknown"
                if not job["log_path"]:
                    metric = {"evidence": "none", "note": "no log_path; "
                              "cannot prove a miss"}
                elif status == "missed":
                    metric = {"evidence": "log_mtime_absent",
                              "log_path": job["log_path"]}
        stats[status] = stats.get(status, 0) + 1
        if status == "missed":
            missed_names.append(job["name"])
        cur.execute(
            """INSERT INTO successbrian_os.cron_runs
                 (job_id, date, scheduled_time, actual_time, status,
                  produced_metric)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT (job_id, date, scheduled_time) DO UPDATE
                 SET actual_time=CASE
                       WHEN successbrian_os.cron_runs.status='ran'
                            AND EXCLUDED.status<>'ran'
                       THEN successbrian_os.cron_runs.actual_time
                       ELSE EXCLUDED.actual_time END,
                     status=CASE
                       WHEN successbrian_os.cron_runs.status='ran'
                            AND EXCLUDED.status<>'ran'
                       THEN 'ran' ELSE EXCLUDED.status END,
                     produced_metric=CASE
                       WHEN successbrian_os.cron_runs.status='ran'
                            AND EXCLUDED.status<>'ran'
                       THEN successbrian_os.cron_runs.produced_metric
                       ELSE EXCLUDED.produced_metric END""",
            (job["id"], d, stime, actual, status,
             json.dumps(metric)))
        if status == "ran" and actual is not None:
            cur.execute(
                """UPDATE successbrian_os.cron_jobs
                     SET last_run_at=%s,
                         run_count_today=CASE WHEN %s::date=CURRENT_DATE
                                              THEN run_count_today
                                              ELSE run_count_today END
                   WHERE id=%s""", (actual, d, job["id"]))
    return stats, missed_names


def file_report(cur, d, stats, missed_names):
    lines = [
        f"Due: {stats['due']} | Ran: {stats.get('ran', 0)} | "
        f"Missed: {stats.get('missed', 0)} | "
        f"Unknown: {stats.get('unknown', 0)}",
        "",
        "## Missed jobs",
    ]
    if missed_names:
        lines += [f"- {n}" for n in missed_names]
    else:
        lines.append("- none proven missed")
    lines += [
        "",
        "## Coverage limits",
        "- Evidence is log-file mtime/size on alpha. Jobs without a "
        "log redirect cannot be proven missed - they are 'unknown', "
        "never 'missed' (not knowing is not the same as not).",
        "- exit_code and duration_sec stay NULL: they cannot be "
        "known from log evidence and are never invented.",
        "- Jobs sharing one log file share its evidence.",
        "- Muse-side jobs (source=muse-cron) are registered here; "
        "their run history lives in the Muse scheduler and their "
        "rows stay 'unknown' on alpha - no run rows are fabricated.",
        "- Subdaily jobs get one summary row per day.",
    ]
    body = "\n".join(lines)
    title = f"Cron time tracking — {d.isoformat()}"
    cur.execute("SELECT id FROM successbrian_os.reports "
                "WHERE report_type='cron-time-tracking' AND title=%s",
                (title,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE successbrian_os.reports SET body=%s "
                    "WHERE id=%s", (body, row["id"]))
    else:
        cur.execute("INSERT INTO successbrian_os.reports "
                    "(report_type, title, body, source) "
                    "VALUES ('cron-time-tracking', %s, %s, "
                    "'cron-time-tracker')", (title, body))
    return title


# ---------- selftest ----------

def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL'}: {name}")
        ok = ok and cond

    check("cadence daily", cadence_of("15 5 * * *") == "daily")
    check("cadence subdaily */5", cadence_of("*/5 * * * *") == "subdaily")
    check("cadence subdaily */6h", cadence_of("0 */6 * * *") == "subdaily")
    check("cadence subdaily multi-hour",
          cadence_of("0 5,9,13 * * *") == "subdaily")
    check("cadence weekday", cadence_of("30 8 * * 1-5") == "weekday")
    check("cadence weekly", cadence_of("30 10 * * 3") == "weekly")
    check("cadence monthly", cadence_of("0 15 1 * *") == "monthly")
    thu = date(2026, 11, 5)   # Thursday
    wed = date(2026, 11, 4)   # Wednesday
    check("due daily on Thu", is_due("15 5 * * *", thu))
    check("due weekday on Thu", is_due("30 8 * * 1-5", thu))
    check("not due weekly(3) on Thu", not is_due("30 10 * * 3", thu))
    check("due weekly(3) on Wed", is_due("30 10 * * 3", wed))
    check("due monthly dom=5", is_due("0 15 5 * *", thu))
    check("not due monthly dom=1", not is_due("0 15 1 * *", thu))
    check("scheduled_time daily",
          scheduled_time_of("15 5 * * *", "daily") == "05:15")
    check("scheduled_time subdaily is schedule",
          scheduled_time_of("*/5 * * * *", "subdaily") == "*/5 * * * *")
    p = parse_cron_line("15 5 * * * /usr/bin/python3 /home/x/watch.py "
                        ">> /home/x/logs/watch.log 2>&1")
    check("parse log_path", p and p["log_path"] == "/home/x/logs/watch.log")
    check("parse command clean",
          p and p["command"] == "/usr/bin/python3 /home/x/watch.py")
    p2 = parse_cron_line("30 10 * * 3 successbrian /usr/bin/python3 "
                         "/home/y/hw.py >> /var/log/hw.log 2>&1",
                         cron_d=True)
    check("parse cron.d user stripped",
          p2 and p2["command"] == "/usr/bin/python3 /home/y/hw.py")
    check("env line skipped", parse_cron_line("PATH=/usr/bin") is None)
    check("comment skipped", parse_cron_line("# 15 5 * * * x") is None)
    check("redact password",
          "REDACTED" in redact("run PASSWORD=hunter2 now")
          and "hunter2" not in redact("run PASSWORD=hunter2 now"))
    check("slug deterministic",
          slug_for("15 5 * * *", "/a/b/c.py") ==
          slug_for("15 5 * * *", "/a/b/c.py"))
    check("slug differs by schedule",
          slug_for("15 5 * * *", "/a/b/c.py") !=
          slug_for("16 5 * * *", "/a/b/c.py"))
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="SBOS cron time tracker")
    ap.add_argument("cmd", choices=["sync", "audit", "selftest"])
    ap.add_argument("--date", default=None,
                    help="audit date YYYY-MM-DD (default today, Chicago)")
    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    conn = db()
    cur = conn.cursor()
    if args.cmd == "sync":
        counts, retired = do_sync(cur)
        conn.commit()
        print(f"sync: registered {counts} retired={retired}")
    elif args.cmd == "audit":
        do_sync(cur)
        d = (date.fromisoformat(args.date) if args.date
             else datetime.now(TZ).date())
        if not args.date:
            yday = d - timedelta(days=1)
            cur.execute("SELECT count(*) AS n FROM "
                        "successbrian_os.cron_runs WHERE date=%s",
                        (yday,))
            if cur.fetchone()["n"]:
                # tracker was live yesterday: finalize its rows
                # (proven 'ran' rows are never downgraded). Dates
                # before tracking started (2026-11-05) are NOT
                # backfilled - log mtimes cannot prove them.
                do_audit(cur, yday)
        stats, missed = do_audit(cur, d)
        title = file_report(cur, d, stats, missed)
        conn.commit()
        print(f"audit {d}: due={stats['due']} ran={stats.get('ran',0)} "
              f"missed={stats.get('missed',0)} "
              f"unknown={stats.get('unknown',0)} report='{title}'")
        for n in missed:
            print(f"  MISSED: {n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
