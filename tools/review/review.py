#!/usr/bin/env python3
"""
Spencer Review Toolkit — the management surface of the Intel Harness flow.

Brian's order (2026-11-09 23:13 CST): "build actual tools and code INTO
successbrian os, that allow you to manage and guide this process day by
day" — the process being the twice-daily Spencer ecosystem review passes
(charters: Intel Bridge captures #1113 setup, #1114 three-lane authority,
#1130 afternoon owner-absent window charter; Muse crons
spencer-ecosystem-review-am 08:45 Mon-Fri, -pm 15:45 Mon-Fri).

One flow doctrine (captures #1105/#1106): the clerk is part of
SuccessBrian OS; the harness is the name for the FLOW of the whole
system. This toolkit is that flow's management surface — the instruments
the review passes read and write. It is bookkeeping and arithmetic:
recorders, gauges, ledgers, queues, and a briefing assembler that fills
in numbers and leaves judgment slots for the pass agent. It renders no
verdicts of its own.

Verbs:
  window     [--date D] [--start HH:MM] [--end HH:MM] [--json]
             reconstruct the owner-absent window record from live stores
  gauges     [--json]           one structured health snapshot
  snapshot   [--kind am|pm|manual] [--window-verdict TEXT]
             store gauges (+ today's window for pm) as a pass snapshot
  delta      [--json]           latest snapshot vs previous (and 7d ago)
  friction-add   --desc T --lane 1|2|3 [--source S] [--state S]
                 [--capture ID] [--qa ID]
  friction-list  [--state S]
  friction-resolve --id N --state S [--note T]
  decide-add     --item T --context T [--numbers JSON] [--capture ID]
  decide-list
  decide-age                    waiting items with ages, oldest first
  decide-rule    --id N (--ruling T | --dismiss)
  briefing   --kind am|pm       assemble the briefing skeleton
  selftest

State (Postgres, successbrian_os schema):
  review_snapshots / review_frictions / review_decisions

Spec: ~/successbrian-os/docs/spencer-review-toolkit-spec.md
Selftest: python3 tools/review/review.py selftest
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402

TZ = ZoneInfo("America/Chicago")
ALLM_DB = os.path.expanduser("~/anything-llm/server/storage/anythingllm.db")
CLERK_STATE = os.path.expanduser("~/successbrian-os/board/state/scatter_clerk.json")
GITHUB_REPO = "successbrian/successbrian-os"
GAMMA_HOST = "root@100.118.196.66"  # successbrianvps / srv1485029 (TOOLS.md)

# gauges where a LOWER value is better; everything else numeric in the
# delta polarity map is higher-better unless listed here or non-numeric.
LOWER_BETTER = {
    "qa_failing_count", "raw_backlog", "raw_oldest_age_h", "unsorted_docs",
    "unindexed_docs", "price_intel_expired", "gamma_disk_pct",
    "issues_blocked_brian", "market_pricing_age_h", "decisions_waiting",
    "frictions_open",
}
HIGHER_BETTER = {
    "github_stars", "afbn_fans", "authorship_reserve", "clerk_watermark",
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def now_ct():
    return datetime.now(TZ)


def day_bounds(day, start_hhmm, end_hhmm):
    """(start, end) aware datetimes in America/Chicago for a date."""
    sh, sm = (int(x) for x in start_hhmm.split(":"))
    eh, em = (int(x) for x in end_hhmm.split(":"))
    return (datetime.combine(day, time(sh, sm), TZ),
            datetime.combine(day, time(eh, em), TZ))


def age_hours(ts, ref=None):
    if ts is None:
        return None
    ref = ref or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round((ref - ts).total_seconds() / 3600.0, 1)


def ensure_tables():
    pg_exec("""
    CREATE TABLE IF NOT EXISTS successbrian_os.review_snapshots (
        id serial PRIMARY KEY,
        taken_at timestamptz NOT NULL DEFAULT now(),
        pass_kind text NOT NULL DEFAULT 'manual',
        window_date date,
        gauges jsonb NOT NULL,
        window_summary jsonb,
        window_verdict text,
        briefing_hash text
    )""")
    pg_exec("""
    CREATE TABLE IF NOT EXISTS successbrian_os.review_frictions (
        id serial PRIMARY KEY,
        found_on date NOT NULL DEFAULT CURRENT_DATE,
        source text,
        description text NOT NULL,
        lane int,
        state text NOT NULL DEFAULT 'open',
        link_qa_check_id int,
        link_capture_id int,
        resolved_note text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    pg_exec("""
    CREATE TABLE IF NOT EXISTS successbrian_os.review_decisions (
        id serial PRIMARY KEY,
        item text NOT NULL,
        context text,
        numbers jsonb,
        source_capture_id int,
        first_surfaced date NOT NULL DEFAULT CURRENT_DATE,
        state text NOT NULL DEFAULT 'waiting',
        ruling text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")


# --------------------------------------------------------------------------
# GAUGES — one structured snapshot. Every source is attempted inside a
# guard; a source that cannot be read lands in coverage[], never skipped
# silently (the honesty rule for this toolkit).
# --------------------------------------------------------------------------
def collect_gauges():
    g = {}
    cov = []

    def attempt(name, fn):
        try:
            fn()
            cov.append({"gauge": name, "ok": True})
        except Exception as e:  # noqa: BLE001
            g[name] = None
            cov.append({"gauge": name, "ok": False,
                        "note": f"{type(e).__name__}: {str(e)[:160]}"})

    def qa():
        rows = pg_rows("""
            SELECT id, project_key, check_key, last_run_at
            FROM successbrian_os.pm_project_checks
            WHERE enabled AND last_status = 'fail'
            ORDER BY last_run_at NULLS FIRST""")
        g["qa_failing"] = [
            {"id": r[0], "project": r[1], "check": r[2],
             "last_run_at": r[3].isoformat() if r[3] else None,
             "fail_age_h": age_hours(r[3])}
            for r in rows]
        g["qa_failing_count"] = len(rows)

    def clerk():
        wm = None
        try:
            with open(CLERK_STATE) as f:
                wm = json.load(f).get("last_capture_id")
        except Exception:
            wm = None
        g["clerk_watermark"] = wm
        if wm is None:
            g["raw_backlog"] = pg_one(
                "SELECT count(*) FROM atlas.scattered_captures "
                "WHERE status='raw'")
        else:
            g["raw_backlog"] = pg_one(
                "SELECT count(*) FROM atlas.scattered_captures "
                "WHERE status='raw' AND id > %s", (wm,))
        oldest = pg_one(
            "SELECT min(created_at) FROM atlas.scattered_captures "
            "WHERE status='raw'")
        g["raw_oldest_age_h"] = age_hours(oldest)

    def filing():
        if not os.path.exists(ALLM_DB):
            raise FileNotFoundError(f"AnythingLLM db not at {ALLM_DB}")
        con = sqlite3.connect(f"file:{ALLM_DB}?mode=ro", uri=True)
        try:
            g["unsorted_docs"] = con.execute(
                "SELECT count(*) FROM workspace_documents wd "
                "JOIN workspaces w ON w.id = wd.workspaceId "
                "WHERE w.slug = 'unsorted'").fetchone()[0]
            docs = con.execute(
                "SELECT w.slug, wd.filename FROM workspace_documents wd "
                "JOIN workspaces w ON w.id = wd.workspaceId").fetchall()
        finally:
            con.close()
        # Both sides are normalized to stems: AnythingLLM stores
        # filenames as '<name>.md-<uuid>.json' while knowledge_index
        # catalog rows carry the plain stem (sometimes with the source
        # extension). Stem-vs-stem is the honest join.
        def stem(fn):
            fn = re.sub(r"-[0-9a-f]{8}-[0-9a-f-]{27,}\.json$", "", fn or "")
            return re.sub(r"\.(md|txt|json|pdf|html?)$", "", fn)
        indexed = set()
        for slug, fn in pg_rows(
                "SELECT allm_workspace, allm_filename "
                "FROM successbrian_os.knowledge_index "
                "WHERE allm_workspace IS NOT NULL "
                "AND allm_filename IS NOT NULL"):
            indexed.add((slug, stem(fn)))
        g["unindexed_docs"] = sum(
            1 for (slug, fn) in docs if (slug, stem(fn)) not in indexed)
        g["allm_docs_total"] = len(docs)

    def authorship():
        row = pg_rows(
            "SELECT verdict, reserve_count, days_since_publish, ran_at "
            "FROM campaignsdesk.authorship_runs ORDER BY ran_at DESC LIMIT 1")
        if row:
            g["authorship_slo"] = row[0][0]
            g["authorship_reserve"] = row[0][1]
            g["authorship_days_since_publish"] = row[0][2]
            g["authorship_ran_at"] = row[0][3].isoformat() if row[0][3] else None
        g["afbn_fans"] = pg_one(
            "SELECT count(*) FROM campaignsdesk.afbn_fan_evidence")

    def stars():
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}",
            headers={"User-Agent": "sbos-review-toolkit"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        g["github_stars"] = d.get("stargazers_count")
        g["github_forks"] = d.get("forks_count")

    def prices():
        g["price_intel_expired"] = pg_one(
            "SELECT count(*) FROM successbrian_os.price_intel "
            "WHERE valid_until < now()")
        last = pg_one("SELECT max(fetched_at) FROM public.market_pricing")
        g["market_pricing_age_h"] = age_hours(last)

    def gamma():
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", "-o",
             "StrictHostKeyChecking=no", GAMMA_HOST, "df -P / | tail -1"],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"ssh df failed: {(r.stderr or '')[:120]}")
        parts = r.stdout.split()
        g["gamma_disk_pct"] = int(parts[4].rstrip("%"))

    def goals():
        # altair.issues is a firehose log: 'open' is its default state
        # (568k rows), so the raw open count is noise. The Brian-facing
        # number is status='blocked_brian'. open_issues is kept for
        # pulse parity and labeled as the log count.
        g["open_issues"] = pg_one(
            "SELECT count(*) FROM altair.issues "
            "WHERE status NOT IN ('closed','done','resolved')")
        g["issues_blocked_brian"] = pg_one(
            "SELECT count(*) FROM altair.issues "
            "WHERE status = 'blocked_brian'")
        cov.append({"gauge": "goals_flags", "ok": False,
                    "note": "Muse-side goal flags (user_action_required / "
                            "new_information) are not readable from alpha; "
                            "open_issues is the alpha-side proxy (pulse "
                            "parity)."})

    def queues():
        g["decisions_waiting"] = pg_one(
            "SELECT count(*) FROM successbrian_os.review_decisions "
            "WHERE state='waiting'") if _table_exists("review_decisions") else 0
        g["frictions_open"] = pg_one(
            "SELECT count(*) FROM successbrian_os.review_frictions "
            "WHERE state IN ('open','proposed')") \
            if _table_exists("review_frictions") else 0

    for name, fn in [("qa", qa), ("clerk", clerk), ("filing", filing),
                     ("authorship", authorship), ("github_stars", stars),
                     ("prices", prices), ("gamma_disk", gamma),
                     ("goals", goals), ("queues", queues)]:
        attempt(name, fn)
    return {"taken_at": datetime.now(timezone.utc).isoformat(),
            "values": g, "coverage": cov}


def _table_exists(name):
    return pg_one(
        "SELECT to_regclass(%s)", (f"successbrian_os.{name}",)) is not None


# --------------------------------------------------------------------------
# WINDOW RECORDER — reconstruct the owner-absent window from live stores.
# --------------------------------------------------------------------------
def window_record(day, start_hhmm="05:30", end_hhmm="15:30"):
    start, end = day_bounds(day, start_hhmm, end_hhmm)
    rec = {"date": day.isoformat(), "window": f"{start_hhmm}-{end_hhmm}",
           "tz": "America/Chicago", "coverage": []}
    cov = rec["coverage"]

    def attempt(name, fn):
        try:
            fn()
            cov.append({"source": name, "ok": True})
        except Exception as e:  # noqa: BLE001
            rec[name] = None
            cov.append({"source": name, "ok": False,
                        "note": f"{type(e).__name__}: {str(e)[:160]}"})

    def cron_fires():
        # job_id references cron_jobs (the live registry); cron_registry
        # is an older partial table (75 of 760 runs join it). LEFT JOIN
        # both so a run is never dropped for a missing registry row.
        rows = pg_rows("""
            SELECT COALESCE(cj.name, cr.job_name, 'job #' || r.job_id),
                   r.scheduled_time, r.actual_time,
                   r.exit_code, r.status, r.duration_sec
            FROM successbrian_os.cron_runs r
            LEFT JOIN successbrian_os.cron_jobs cj ON cj.id = r.job_id
            LEFT JOIN successbrian_os.cron_registry cr ON cr.id = r.job_id
            WHERE r.actual_time >= %s AND r.actual_time < %s
            ORDER BY r.actual_time""", (start, end))
        rec["cron_fires"] = [
            {"job": r[0], "scheduled": r[1],
             "actual": r[2].isoformat() if r[2] else None,
             "exit_code": r[3], "status": r[4],
             "duration_s": float(r[5]) if r[5] is not None else None}
            for r in rows]
        rec["cron_fires_count"] = len(rows)
        rec["cron_failures"] = sum(
            1 for r in rows if (r[3] not in (0, None)) or
            (r[4] and "fail" in str(r[4]).lower()))

    def captures():
        filed = pg_rows("""
            SELECT id, title, status FROM atlas.scattered_captures
            WHERE created_at >= %s AND created_at < %s ORDER BY id""",
            (start, end))
        rec["captures_filed"] = [
            {"id": r[0], "title": (r[1] or "")[:90], "status": r[2]}
            for r in filed]
        rec["captures_filed_count"] = len(filed)
        rec["captures_triaged_in_window"] = pg_one(
            "SELECT count(*) FROM atlas.scattered_captures "
            "WHERE triaged_at >= %s AND triaged_at < %s", (start, end))
        rec["captures_ruled_in_window"] = pg_one(
            "SELECT count(*) FROM atlas.scattered_captures "
            "WHERE ruled_at >= %s AND ruled_at < %s", (start, end))

    def qa_runs():
        rows = pg_rows("""
            SELECT r.status, count(*) FROM successbrian_os.pm_project_qa_runs r
            WHERE r.ran_at >= %s AND r.ran_at < %s GROUP BY r.status""",
            (start, end))
        rec["qa_runs_by_status"] = {r[0]: r[1] for r in rows}
        fails = pg_rows("""
            SELECT c.project_key, c.check_key
            FROM successbrian_os.pm_project_qa_runs r
            JOIN successbrian_os.pm_project_checks c ON c.id = r.check_id
            WHERE r.ran_at >= %s AND r.ran_at < %s AND r.status = 'fail'
            ORDER BY c.project_key, c.check_key""", (start, end))
        rec["qa_failures_in_window"] = [
            {"project": r[0], "check": r[1]} for r in fails]

    # Desk output tables: (label, table, ts column). Each is attempted
    # independently; a missing table is a coverage note, not a crash.
    OUTPUTS = [
        ("candidate_verdicts", "dealsdesk.candidate_verdicts", "evaluated_at"),
        ("market_pricing_observations", "public.market_pricing_history",
         "observed_at"),
        ("authorship_runs", "campaignsdesk.authorship_runs", "ran_at"),
        ("wf3_filings", "successbrian_os.wf3_filings", "filed_at"),
        ("knowledge_index_rows", "successbrian_os.knowledge_index",
         "created_at"),
    ]

    def outputs():
        out = {}
        for label, table, col in OUTPUTS:
            try:
                n = pg_one(
                    f"SELECT count(*) FROM {table} "
                    f"WHERE {col} >= %s AND {col} < %s", (start, end))
                out[label] = n
            except Exception as e:  # noqa: BLE001
                out[label] = None
                cov.append({"source": f"output:{label}", "ok": False,
                            "note": f"{type(e).__name__}: {str(e)[:120]}"})
        rec["desk_outputs"] = out

    def stalls():
        s = {}
        s["raw_aged_over_24h_at_window_end"] = pg_one(
            "SELECT count(*) FROM atlas.scattered_captures "
            "WHERE status='raw' AND created_at < %s",
            (end - timedelta(hours=24),))
        oldest = pg_one(
            "SELECT min(created_at) FROM atlas.scattered_captures "
            "WHERE status='raw' AND created_at < %s", (end,))
        s["raw_oldest_age_h_at_window_end"] = age_hours(oldest, ref=end)
        s["checks_failing_stale"] = pg_one(
            "SELECT count(*) FROM successbrian_os.pm_project_checks "
            "WHERE enabled AND last_status='fail' AND "
            "(last_run_at IS NULL OR last_run_at < %s)", (start,))
        rec["stalls"] = s

    for name, fn in [("cron_runs", cron_fires), ("captures", captures),
                     ("qa_runs", qa_runs), ("desk_outputs", outputs),
                     ("stalls", stalls)]:
        attempt(name, fn)
    cov.append({"source": "board_packet_files", "ok": False,
                "note": "board packet production is recorded as Atlas "
                        "task nodes, not a timestamped result table this "
                        "recorder reads; covered indirectly via captures "
                        "triaged/ruled counts."})
    return rec


def window_summary_text(rec):
    lines = [f"WINDOW RECORD {rec['date']} {rec['window']} {rec['tz']}"]
    if rec.get("cron_fires_count") is not None:
        lines.append(f"  cron fires: {rec['cron_fires_count']} "
                     f"({rec.get('cron_failures')} failed)")
    if rec.get("captures_filed_count") is not None:
        lines.append(
            f"  captures filed: {rec['captures_filed_count']}; "
            f"triaged in window: {rec.get('captures_triaged_in_window')}; "
            f"ruled in window: {rec.get('captures_ruled_in_window')}")
    if rec.get("qa_runs_by_status") is not None:
        lines.append(f"  qa runs by status: {rec['qa_runs_by_status']}; "
                     f"failures: {len(rec.get('qa_failures_in_window') or [])}")
    if rec.get("desk_outputs"):
        lines.append(f"  desk outputs: {rec['desk_outputs']}")
    if rec.get("stalls"):
        lines.append(f"  stalls: {rec['stalls']}")
    gaps = [c for c in rec["coverage"] if not c["ok"]]
    lines.append(f"  coverage: {len(rec['coverage']) - len(gaps)} ok, "
                 f"{len(gaps)} gap(s)")
    for c in gaps:
        lines.append(f"    GAP {c['source']}: {c.get('note', '')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# PASS MEMORY — snapshots + delta
# --------------------------------------------------------------------------
def take_snapshot(kind, window_verdict=None):
    ensure_tables()
    snap = collect_gauges()
    win = None
    if kind == "pm":
        win = window_record(now_ct().date())
    payload = json.dumps(snap)
    wid = win and json.dumps(win)
    row = pg_rows(
        "INSERT INTO successbrian_os.review_snapshots "
        "(pass_kind, window_date, gauges, window_summary, window_verdict) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (kind, now_ct().date() if win else None, payload, wid,
         window_verdict))
    sid = row[0][0]
    # briefing hash over the skeleton rendered from this snapshot
    text = render_briefing(kind if kind in ("am", "pm") else "am",
                           snap_id=sid)
    h = hashlib.sha256(text.encode()).hexdigest()[:16]
    pg_exec("UPDATE successbrian_os.review_snapshots SET briefing_hash=%s "
            "WHERE id=%s", (h, sid))
    return sid, snap, win, h


def load_snapshot(sid=None, before=None):
    if sid:
        rows = pg_rows(
            "SELECT id, taken_at, pass_kind, gauges, window_summary, "
            "window_verdict FROM successbrian_os.review_snapshots "
            "WHERE id=%s", (sid,))
    elif before:
        rows = pg_rows(
            "SELECT id, taken_at, pass_kind, gauges, window_summary, "
            "window_verdict FROM successbrian_os.review_snapshots "
            "WHERE taken_at < %s ORDER BY taken_at DESC LIMIT 1", (before,))
    else:
        rows = pg_rows(
            "SELECT id, taken_at, pass_kind, gauges, window_summary, "
            "window_verdict FROM successbrian_os.review_snapshots "
            "ORDER BY taken_at DESC LIMIT 1")
    if not rows:
        return None
    r = rows[0]
    return {"id": r[0], "taken_at": r[1], "pass_kind": r[2],
            "gauges": r[3] if isinstance(r[3], dict) else json.loads(r[3]),
            "window_summary": r[4], "window_verdict": r[5]}


def delta_report():
    cur = load_snapshot()
    if not cur:
        return "DELTA: no snapshots stored yet."
    prev = load_snapshot(before=cur["taken_at"])
    lines = [f"DELTA snapshot #{cur['id']} ({cur['pass_kind']}, "
             f"{cur['taken_at']})"]
    if not prev:
        lines.append("  no previous snapshot — this is the baseline.")
        return "\n".join(lines)
    lines.append(f"  vs previous #{prev['id']} ({prev['taken_at']})")
    lines += _delta_lines(cur["gauges"]["values"], prev["gauges"]["values"])
    week = pg_rows(
        "SELECT id, taken_at, gauges FROM successbrian_os.review_snapshots "
        "WHERE taken_at <= %s ORDER BY taken_at DESC LIMIT 1",
        (cur["taken_at"] - timedelta(days=7),))
    if week:
        w = week[0]
        wg = w[2] if isinstance(w[2], dict) else json.loads(w[2])
        lines.append(f"  vs 7 days ago #{w[0]} ({w[1]})")
        lines += _delta_lines(cur["gauges"]["values"], wg["values"],
                              indent="    ")
    return "\n".join(lines)


def _delta_lines(curv, prevv, indent="  "):
    out = []
    keys = sorted(set(curv) | set(prevv))
    for k in keys:
        a, b = curv.get(k), prevv.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a == b:
                out.append(f"{indent}{k}: unchanged at {a}")
            else:
                d = a - b
                if k in LOWER_BETTER:
                    word = "improved" if d < 0 else "worsened"
                elif k in HIGHER_BETTER:
                    word = "improved" if d > 0 else "worsened"
                else:
                    word = "changed"
                out.append(f"{indent}{k}: {word} {b} -> {a} ({d:+})")
        elif a != b:
            out.append(f"{indent}{k}: changed ({b!r} -> {a!r})")
    return out


# --------------------------------------------------------------------------
# BRIEFING ASSEMBLER — arithmetic + layout only. Judgment slots are
# marked placeholders for the pass agent; this code writes no verdicts.
# --------------------------------------------------------------------------
def render_briefing(kind, snap_id=None):
    snap = load_snapshot(snap_id) if snap_id else None
    if snap:
        g = snap["gauges"]["values"]
        win = snap.get("window_summary")
        if isinstance(win, str):
            win = json.loads(win)
    else:
        g = collect_gauges()["values"]
        win = window_record(now_ct().date()) if kind == "pm" else None
    open_fr = pg_rows(
        "SELECT id, description, lane, state FROM "
        "successbrian_os.review_frictions "
        "WHERE state IN ('open','proposed') ORDER BY id") \
        if _table_exists("review_frictions") else []
    waiting = pg_rows(
        "SELECT id, item, first_surfaced FROM "
        "successbrian_os.review_decisions WHERE state='waiting' "
        "ORDER BY first_surfaced, id") \
        if _table_exists("review_decisions") else []
    L = []
    L.append(f"ECOSYSTEM REVIEW — {'AFTERNOON' if kind == 'pm' else 'MORNING'} "
             f"PASS — {now_ct().date().isoformat()}")
    if kind == "pm":
        L.append("\nTHE WINDOW (05:30-15:30, owner at Crew 2)")
        if win:
            L.append(window_summary_text(win))
        L.append("  verdict: [JUDGMENT: one line — did the system earn its "
                 "keep without him?]")
    L.append("\nDOING WELL")
    L.append(f"  [JUDGMENT: name what is healthy, from the numbers below]")
    L.append(f"  gauges: qa failing {g.get('qa_failing_count')}, "
             f"watermark #{g.get('clerk_watermark')}, "
             f"stars {g.get('github_stars')}, fans {g.get('afbn_fans')}")
    L.append("\nNOT DOING WELL")
    for f in (g.get("qa_failing") or [])[:8]:
        L.append(f"  - QA fail: {f['project']}/{f['check']} "
                 f"(last ran {f['last_run_at']})")
    if g.get("gamma_disk_pct") is not None and g["gamma_disk_pct"] >= 95:
        L.append(f"  - gamma disk {g['gamma_disk_pct']}% full")
    if g.get("issues_blocked_brian"):
        L.append(f"  - issues blocked on Brian: "
                 f"{g['issues_blocked_brian']} (altair.issues)")
    if g.get("authorship_slo"):
        L.append(f"  - authorship SLO: {g['authorship_slo']} "
                 f"(reserve {g.get('authorship_reserve')}, "
                 f"{g.get('authorship_days_since_publish')}d since publish)")
    L.append("  [JUDGMENT: anything else the numbers indict]")
    L.append("\nCOULD DO BETTER")
    for fr in open_fr[:8]:
        L.append(f"  - friction #{fr[0]} (lane {fr[2]}, {fr[3]}): {fr[1]}")
    L.append("  [JUDGMENT: the day's single best improvement]")
    L.append("\nDONE THIS PASS")
    L.append("  [JUDGMENT: lane-1 actions taken, with QA registrations]")
    L.append("\nDECISION FOR BRIAN (one only)")
    if waiting:
        w = waiting[0]
        L.append(f"  #{w[0]} {w[1]} (waiting since {w[2]})")
        L.append("  [JUDGMENT: present with context + numbers]")
        if len(waiting) > 1:
            L.append(f"  waiting list: {len(waiting) - 1} more "
                     f"(decide-list shows all)")
    else:
        L.append("  none waiting.")
    return "\n".join(L)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="review.py",
                                 description="Spencer Review Toolkit")
    sub = ap.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("window")
    p.add_argument("--date", default=None)
    p.add_argument("--start", default="05:30")
    p.add_argument("--end", default="15:30")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("gauges")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("snapshot")
    p.add_argument("--kind", default="manual",
                   choices=["am", "pm", "manual"])
    p.add_argument("--window-verdict", default=None)

    sub.add_parser("delta")

    p = sub.add_parser("friction-add")
    p.add_argument("--desc", required=True)
    p.add_argument("--lane", type=int, required=True, choices=[1, 2, 3])
    p.add_argument("--source", default="pass")
    p.add_argument("--state", default="open")
    p.add_argument("--capture", type=int, default=None)
    p.add_argument("--qa", type=int, default=None)

    p = sub.add_parser("friction-list")
    p.add_argument("--state", default=None)

    p = sub.add_parser("friction-resolve")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--note", default=None)

    p = sub.add_parser("decide-add")
    p.add_argument("--item", required=True)
    p.add_argument("--context", default=None)
    p.add_argument("--numbers", default=None)
    p.add_argument("--capture", type=int, default=None)

    sub.add_parser("decide-list")
    sub.add_parser("decide-age")

    p = sub.add_parser("decide-rule")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--ruling", default=None)
    p.add_argument("--dismiss", action="store_true")

    p = sub.add_parser("briefing")
    p.add_argument("--kind", default="pm", choices=["am", "pm"])

    sub.add_parser("selftest")
    args = ap.parse_args(argv)

    if args.verb == "window":
        day = (datetime.strptime(args.date, "%Y-%m-%d").date()
               if args.date else now_ct().date())
        rec = window_record(day, args.start, args.end)
        print(json.dumps(rec, indent=1, default=str) if args.json
              else window_summary_text(rec))
    elif args.verb == "gauges":
        snap = collect_gauges()
        if args.json:
            print(json.dumps(snap, indent=1, default=str))
        else:
            print("GAUGES " + snap["taken_at"])
            for k, v in sorted(snap["values"].items()):
                print(f"  {k}: {v}")
            for c in snap["coverage"]:
                if not c["ok"]:
                    print(f"  GAP {c['gauge']}: {c.get('note', '')}")
    elif args.verb == "snapshot":
        sid, snap, win, h = take_snapshot(args.kind, args.window_verdict)
        print(f"SNAPSHOT #{sid} kind={args.kind} briefing_hash={h}")
        if win:
            print(window_summary_text(win))
    elif args.verb == "delta":
        print(delta_report())
    elif args.verb == "friction-add":
        ensure_tables()
        row = pg_rows(
            "INSERT INTO successbrian_os.review_frictions "
            "(source, description, lane, state, link_capture_id, "
            "link_qa_check_id) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (args.source, args.desc, args.lane, args.state, args.capture,
             args.qa))
        print(f"FRICTION #{row[0][0]} added (lane {args.lane}, "
              f"state {args.state})")
    elif args.verb == "friction-list":
        q = ("SELECT id, found_on, source, lane, state, description "
             "FROM successbrian_os.review_frictions")
        params = ()
        if args.state:
            q += " WHERE state=%s"
            params = (args.state,)
        rows = pg_rows(q + " ORDER BY id", params)
        print(f"FRICTION LEDGER ({len(rows)} rows)")
        for r in rows:
            print(f"  #{r[0]} [{r[4]}] lane {r[3]} found {r[1]} "
                  f"({r[2]}): {r[5]}")
    elif args.verb == "friction-resolve":
        pg_exec(
            "UPDATE successbrian_os.review_frictions SET state=%s, "
            "resolved_note=%s, updated_at=now() WHERE id=%s",
            (args.state, args.note, args.id))
        print(f"FRICTION #{args.id} -> {args.state}")
    elif args.verb == "decide-add":
        ensure_tables()
        row = pg_rows(
            "INSERT INTO successbrian_os.review_decisions "
            "(item, context, numbers, source_capture_id) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (args.item, args.context,
             json.dumps(json.loads(args.numbers)) if args.numbers else None,
             args.capture))
        print(f"DECISION #{row[0][0]} queued (waiting)")
    elif args.verb == "decide-list":
        rows = pg_rows(
            "SELECT id, item, first_surfaced, state, source_capture_id "
            "FROM successbrian_os.review_decisions ORDER BY "
            "CASE state WHEN 'waiting' THEN 0 ELSE 1 END, first_surfaced, id")
        print(f"DECISIONS QUEUE ({len(rows)} rows)")
        for r in rows:
            print(f"  #{r[0]} [{r[3]}] since {r[2]}: {r[1]}"
                  + (f" (capture #{r[4]})" if r[4] else ""))
    elif args.verb == "decide-age":
        rows = pg_rows(
            "SELECT id, item, first_surfaced, "
            "(CURRENT_DATE - first_surfaced) AS age_d FROM "
            "successbrian_os.review_decisions WHERE state='waiting' "
            "ORDER BY first_surfaced, id")
        print(f"DECISIONS WAITING ({len(rows)})")
        for r in rows:
            print(f"  #{r[0]} age {r[3]}d (since {r[2]}): {r[1]}")
    elif args.verb == "decide-rule":
        state = "dismissed" if args.dismiss else "ruled"
        pg_exec(
            "UPDATE successbrian_os.review_decisions SET state=%s, "
            "ruling=%s, updated_at=now() WHERE id=%s",
            (state, args.ruling, args.id))
        print(f"DECISION #{args.id} -> {state}")
    elif args.verb == "briefing":
        ensure_tables()
        print(render_briefing(args.kind))
    elif args.verb == "selftest":
        return selftest()
    return 0


def selftest():
    ok = []

    def check(name, cond):
        ok.append(cond)
        print(f"  {'PASS' if cond else 'FAIL'} {name}")

    print("SELFTEST review toolkit")
    # pure: day bounds land in Chicago time with the right wall clock
    s, e = day_bounds(date(2026, 11, 9), "05:30", "15:30")
    check("window bounds CT", (s.hour, s.minute, e.hour, e.minute)
          == (5, 30, 15, 30) and s.utcoffset() == timedelta(hours=-6))
    # pure: delta polarity words
    lines = _delta_lines({"raw_backlog": 5, "github_stars": 3},
                         {"raw_backlog": 9, "github_stars": 3})
    check("delta polarity", any("improved" in ln and "raw_backlog" in ln
                                for ln in lines)
          and any("unchanged" in ln for ln in lines))
    # pure: age_hours handles naive + aware
    check("age_hours", age_hours(datetime(2026, 1, 1)) is not None)
    # live read-only probes
    try:
        n = pg_one("SELECT count(*) FROM atlas.scattered_captures")
        check("captures readable", isinstance(n, int) and n > 0)
    except Exception as ex:  # noqa: BLE001
        check(f"captures readable ({ex})", False)
    try:
        snap = collect_gauges()
        check("gauges collect", "qa_failing_count" in snap["values"]
              and len(snap["coverage"]) >= 8)
    except Exception as ex:  # noqa: BLE001
        check(f"gauges collect ({ex})", False)
    try:
        rec = window_record(now_ct().date())
        check("window record builds", rec["date"] is not None
              and "coverage" in rec)
    except Exception as ex:  # noqa: BLE001
        check(f"window record builds ({ex})", False)
    try:
        ensure_tables()
        txt = render_briefing("pm")
        check("briefing renders with placeholders",
              "THE WINDOW" in txt and "[JUDGMENT:" in txt)
    except Exception as ex:  # noqa: BLE001
        check(f"briefing renders ({ex})", False)
    print(f"selftest: {sum(ok)}/{len(ok)}")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
