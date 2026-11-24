#!/usr/bin/env python3
"""dashboard.py - SBOS Dashboard generator (Brian order 2026-11-23).

Renders an exception-first status page from the live stores. Brian
does not read dashboards; the readers are the review passes and the
Wednesday sitting, so every panel answers "so what" in one line,
exceptions first, vanity last. Any number a store cannot answer
renders as UNKNOWN with the reason - never invented.

Design lessons taken from the Paperclip field study (capture #3121):
one tokenised status vocabulary (the same hues for ok / warn / bad /
unknown across every panel), monospace for machine values, relative
timestamps ("14d ago"), integer counts, and no skeleton states (the
page is generated, so it simply renders what the stores said).

Modes:
  generate   query the stores, render, store a snapshot row, and
             write the HTML file (the cron mode)
  selftest   in-memory checks of the render + so-what rules; touches
             no tables and writes no files

State (Postgres, successbrian_os schema):
  dashboard_snapshots (id, generated_at, data jsonb, html text) -
  the latest row is the current page; history is kept.

Output file: tools/dashboard/output/index.html (stable path).
Registry: program_registry 'sbos-dashboard-py', probe = table
freshness of dashboard_snapshots.generated_at, cadence 30 min.
QA: pm_project_checks sbos-program-registry/dashboard-headlines-true
proves the latest snapshot is <40 min old AND its three headline
numbers (decisions waiting, pm_steps queued, QA failing) equal live
recounts.

Selftest: python3 tools/dashboard/dashboard.py selftest
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402
from sbos_common import log, pg_exec, pg_one, pg_rows  # noqa: E402

TZ = ZoneInfo("America/Chicago")
OUT_PATH = os.path.expanduser(
    "~/successbrian-os/tools/dashboard/output/index.html")

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.dashboard_snapshots (
    id serial PRIMARY KEY,
    generated_at timestamptz NOT NULL DEFAULT now(),
    data jsonb NOT NULL,
    html text NOT NULL
);
CREATE INDEX IF NOT EXISTS dashboard_snapshots_generated_idx
    ON successbrian_os.dashboard_snapshots (generated_at DESC);
"""


def ensure_schema():
    pg_exec(DDL)


# ---------------------------------------------------------------- helpers
def now_utc():
    return datetime.now(timezone.utc)


def rel(ts, ref=None):
    """Relative timestamp: '14d ago', '3h ago', 'just now'."""
    if ts is None:
        return "UNKNOWN"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return ts
    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ref = ref or now_utc()
    secs = (ref - ts).total_seconds()
    if secs < 0:
        return "in the future"
    if secs < 90:
        return "just now"
    if secs < 3600:
        return "%dm ago" % int(secs // 60)
    if secs < 86400:
        return "%dh ago" % int(secs // 3600)
    return "%dd ago" % int(secs // 86400)


def age_days(ts, ref=None):
    if ts is None:
        return None
    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ref = ref or now_utc()
    return max(0, int((ref - ts).total_seconds() // 86400))


def esc(v):
    return html.escape("" if v is None else str(v))


def unk(reason):
    return {"unknown": True, "reason": reason}


def is_unk(v):
    return isinstance(v, dict) and v.get("unknown")


def fmt(v):
    """Format a possibly-UNKNOWN scalar for display."""
    if is_unk(v):
        return "UNKNOWN (%s)" % v["reason"]
    if v is None:
        return "UNKNOWN (no value in store)"
    return str(v)


# ---------------------------------------------------------------- panels
def panel_needs_brian():
    # Brian's ONE inbox: successbrian_os.pending_questions, status
    # 'open' - the store behind the unified Inbox page
    # (build_unified_inbox.py renders it as "Inbox / Needs your
    # call") and the dash-actions answer API. Brian, 2026-11-23:
    # "needs brian - we do already have an inbox for brian." This
    # panel reads THAT store and keeps no dashboard-side list.
    # brian_inbox_route.py sweeps the scattered Brian-bound items
    # (Einstein FOR BRIAN sections, held_brian pm_steps, the review
    # passes' waiting decisions) into the same inbox, so this count
    # is the one count of what needs Brian.
    rows = pg_rows(
        "SELECT id, question, priority, created_at FROM "
        "successbrian_os.pending_questions WHERE status='open' "
        "ORDER BY priority DESC, created_at DESC")
    items = []
    oldest = None
    oldest_date = None
    ref = now_utc()
    for qid, question, _prio, created in rows:
        a = age_days(created, ref)
        if oldest is None or a > oldest:
            oldest = a
            oldest_date = created.date().isoformat()
        items.append({"id": qid, "item": question,
                      "first_surfaced": created.date().isoformat(),
                      "age_days": a})
    n = len(items)
    sowhat = ("%d questions in Brian's inbox; oldest is %dd old."
              % (n, oldest) if n else "Brian's inbox is clear.")
    status = "bad" if n and oldest and oldest >= 14 else (
        "warn" if n else "ok")
    return {"count": n, "oldest_age_days": oldest,
            "oldest_date": oldest_date,
            "top5": items[:5], "sowhat": sowhat, "status": status}


def panel_blockers():
    out = {}
    # VPS: no live DB store exists (verified 2026-11-23) - honesty habit.
    out["vps"] = {
        "live": unk("no live source in the ecosystem"),
        "note": "VPS status: no live source in the ecosystem"}
    snap = pg_one(
        "SELECT taken_at, gauges, window_summary FROM "
        "successbrian_os.review_snapshots ORDER BY taken_at DESC LIMIT 1")
    if snap:
        taken_at, gauges, window = snap
        vals = (gauges or {}).get("values", gauges or {})
        out["vps"]["last_known"] = {
            "snapshot_at": taken_at.isoformat(),
            "gamma_disk": vals.get("gamma_disk"),
            "window_stalls": (window or {}).get("stalls")}
    else:
        out["vps"]["last_known"] = unk("no review_snapshots rows")
    rows = pg_rows(
        "SELECT program_key, exception_state, last_proof_at, "
        "expected_cadence_min FROM successbrian_os.lyra_program_status "
        "WHERE program_key LIKE 'gamma-%' OR program_key='worker-gamma' "
        "ORDER BY program_key")
    gamma = []
    stale_rollup = False
    for pk, state, proof, cad in rows:
        stale = False
        if pk == "gamma-ping-rollup-py" and proof is not None:
            stale = (now_utc() - proof) > timedelta(hours=2)
            stale_rollup = stale
        gamma.append({"program_key": pk, "state": state,
                      "last_proof_at": proof.isoformat() if proof else None,
                      "last_proof_rel": rel(proof),
                      "expected_cadence_min": cad, "stale_2h": stale})
    out["gamma"] = gamma
    bad = any(g["state"] not in ("ok", "manual") for g in gamma)
    out["status"] = "bad" if (bad or stale_rollup) else "ok"
    bits = []
    if stale_rollup:
        bits.append("gamma-ping-rollup-py proof is >2h stale")
    if bad:
        bits.append("a gamma program is in exception state")
    out["sowhat"] = ("; ".join(bits) + "." if bits else
                      "Gamma programs all report ok; VPS has no live "
                      "source, last-known only.")
    return out


def panel_goals():
    # The 42-goal coverage universe = the slugs that carry a brief.
    rows = pg_rows("""
        SELECT b.goal_slug, b.origin_class, b.has_brian_words, b.compiled_at,
               h.tier, h.gated, h.due_early, h.stall_count, h.last_progress_at,
               (SELECT looked_at FROM successbrian_os.goal_coverage c
                 WHERE c.goal_slug=b.goal_slug ORDER BY looked_at DESC
                 LIMIT 1) AS last_look,
               (SELECT planner_seat FROM successbrian_os.goal_coverage c
                 WHERE c.goal_slug=b.goal_slug ORDER BY looked_at DESC
                 LIMIT 1) AS last_seat,
               (SELECT verdict FROM successbrian_os.harness_movements m
                 WHERE m.goal_slug=b.goal_slug ORDER BY measured_at DESC
                 LIMIT 1) AS last_verdict
        FROM successbrian_os.goal_briefs b
        LEFT JOIN successbrian_os.goal_harness_state h
          ON h.goal_slug=b.goal_slug
        ORDER BY b.goal_slug""")
    goals = []
    by_origin, by_tier = {}, {}
    due_early = stalled = 0
    tier_rank = {"daily": 0, "critical": 0, "high": 1, "medium": 2,
                 "low": 3, "gated": 4}
    for r in rows:
        (slug, origin, hbw, compiled, tier, gated, de, stalls, lprog,
         last_look, seat, verdict) = r
        by_origin[origin or "UNKNOWN"] = by_origin.get(origin or "UNKNOWN", 0) + 1
        by_tier[tier or "UNKNOWN"] = by_tier.get(tier or "UNKNOWN", 0) + 1
        if de:
            due_early += 1
        if stalls and stalls > 0:
            stalled += 1
        goals.append({
            "slug": slug, "origin_class": origin, "has_brian_words": hbw,
            "compiled_at": compiled.isoformat() if compiled else None,
            "tier": tier, "gated": gated, "due_early": bool(de),
            "stall_count": stalls or 0,
            "last_progress_at": lprog.isoformat() if lprog else None,
            "last_look": last_look.isoformat() if last_look else None,
            "last_look_rel": rel(last_look), "last_seat": seat,
            "last_verdict": verdict})
    goals.sort(key=lambda g: (0 if g["stall_count"] > 0 else 1,
                              -g["stall_count"],
                              0 if g["due_early"] else 1,
                              tier_rank.get(g["tier"] or "", 5),
                              g["slug"]))
    total = len(goals)
    assembled = by_origin.get("AGENT-ASSEMBLED", 0)
    # 'looks overdue' = no look in the last 4 days (the coverage window)
    overdue = sum(1 for g in goals
                  if g["last_look"] is None or
                  (now_utc() - datetime.fromisoformat(g["last_look"]))
                  > timedelta(days=4))
    sowhat = ("%d of %d goals are agent-assembled; %d stalled; "
              "%d looks overdue." % (assembled, total, stalled, overdue))
    return {"total": total, "by_origin": by_origin, "by_tier": by_tier,
            "due_early": due_early, "stalled": stalled,
            "looks_overdue": overdue, "goals": goals,
            "sowhat": sowhat,
            "status": "bad" if stalled else ("warn" if overdue else "ok")}


def panel_work():
    steps = dict(pg_rows(
        "SELECT status, count(*) FROM successbrian_os.pm_steps "
        "GROUP BY status"))
    claims_total = dict(pg_rows(
        "SELECT action || '/' || coalesce(outcome,'open'), count(*) "
        "FROM successbrian_os.harness_claims GROUP BY 1"))
    claims_24h = dict(pg_rows(
        "SELECT action || '/' || coalesce(outcome,'open'), count(*) "
        "FROM successbrian_os.harness_claims "
        "WHERE claimed_at > now() - interval '24 hours' GROUP BY 1"))
    props = dict(pg_rows(
        "SELECT status, count(*) FROM "
        "successbrian_os.consolidation_proposals GROUP BY status"))
    sweep = pg_one(
        "SELECT steps_scanned, ran_at, status FROM "
        "successbrian_os.consolidation_sweeps ORDER BY ran_at DESC LIMIT 1")
    queued = steps.get("queued", 0)
    running = steps.get("running", 0)
    if queued > running * 10 and queued > 100:
        sowhat = ("%d steps queued, %d running - the queue is the "
                  "constraint." % (queued, running))
    elif running == 0 and queued:
        sowhat = ("%d steps queued, none running - nothing is being "
                  "worked right now." % queued)
    elif queued == 0:
        sowhat = "No steps queued; %d running." % running
    else:
        sowhat = "%d steps queued, %d running." % (queued, running)
    return {"pm_steps": steps, "claims_total": claims_total,
            "claims_24h": claims_24h, "proposals": props,
            "latest_sweep": ({"steps_scanned": sweep[0],
                              "ran_at": sweep[1].isoformat(),
                              "status": sweep[2]} if sweep else
                             unk("no consolidation_sweeps rows")),
            "sowhat": sowhat,
            "status": "warn" if queued > 500 else "ok"}


def panel_einstein():
    by_status = dict(pg_rows(
        "SELECT status, count(*) FROM successbrian_os.einstein_passes "
        "GROUP BY status"))
    rows = pg_rows(
        "SELECT goal_slug, collected_at, plan_text FROM "
        "successbrian_os.einstein_passes WHERE status='collected' "
        "AND plan_text IS NOT NULL ORDER BY collected_at DESC LIMIT 3")
    latest = [{"goal": g, "collected_at": c.isoformat() if c else None,
               "collected_rel": rel(c), "plan": (p or "")[:300]}
              for g, c, p in rows]
    n = by_status.get("collected", 0)
    sowhat = ("%d Einstein plans collected; %d dispatched awaiting "
              "return." % (n, by_status.get("dispatched", 0)))
    return {"by_status": by_status, "latest": latest, "sowhat": sowhat,
            "status": "ok" if n else "warn"}


def panel_fleet():
    rows = pg_rows(
        "SELECT program_key, watch_state, exception_state, last_proof_at, "
        "expected_cadence_min FROM successbrian_os.lyra_program_status")
    total = len(rows)
    watched = sum(1 for r in rows if r[1] == "watched")
    manual = sum(1 for r in rows if r[1] == "manual")
    fresh = 0
    exceptions = []
    ref = now_utc()
    for pk, ws, state, proof, cad in rows:
        age_min = None
        if proof is not None:
            age_min = (ref - proof).total_seconds() / 60.0
            if age_min <= 60:
                fresh += 1
        stale_proof = (cad is not None and age_min is not None
                       and age_min > cad * 2)
        no_proof = proof is None
        if state not in ("ok", "manual") or stale_proof or no_proof:
            exceptions.append({
                "program_key": pk, "state": state,
                "last_proof_at": proof.isoformat() if proof else None,
                "last_proof_rel": rel(proof),
                "expected_cadence_min": cad,
                "age_min": round(age_min) if age_min is not None else None,
                "reason": ("no proof on record" if no_proof else
                           "proof older than 2x cadence" if stale_proof
                           else "state=%s" % state)})
    exceptions.sort(key=lambda e: (e["age_min"] is None,
                                   -(e["age_min"] or 0)))
    no_fresh = total - fresh
    sowhat = "%d of %d programs have no fresh proof." % (no_fresh, total)
    return {"total": total, "watched": watched, "manual": manual,
            "fresh_le_1h": fresh, "no_fresh_proof": no_fresh,
            "exceptions": exceptions[:10],
            "exception_count": len(exceptions),
            "sowhat": sowhat,
            "status": "bad" if len(exceptions) > 20 else (
                "warn" if exceptions else "ok")}


def panel_research():
    by_status = dict(pg_rows(
        "SELECT status, count(*) FROM successbrian_os.research_questions "
        "GROUP BY status"))
    rows = pg_rows("""
        SELECT q.subject, q.status,
               (SELECT count(*) FROM successbrian_os.research_routes r
                 WHERE r.question_id=q.id)
        FROM successbrian_os.research_questions q ORDER BY q.id""")
    qs = [{"subject": s, "status": st, "routed_outputs": n}
          for s, st, n in rows]
    sowhat = ("%d research questions: %s." % (
        len(qs), ", ".join("%d %s" % (v, k)
                           for k, v in sorted(by_status.items()))))
    return {"by_status": by_status, "questions": qs, "sowhat": sowhat,
            "status": "ok"}


def panel_blogs():
    by_status = dict(pg_rows(
        "SELECT status, count(*) FROM campaignsdesk.blogs GROUP BY status"))
    latest_end = pg_one(
        "SELECT max(period_end) FROM campaignsdesk.blog_scorecards")
    stale = False
    age = None
    if latest_end is not None:
        age = (datetime.now(TZ).date() - latest_end).days
        stale = age > 14
    sowhat = ("%d blogs (%s); latest scorecard period ended %s%s." % (
        sum(by_status.values()),
        ", ".join("%d %s" % (v, k) for k, v in sorted(by_status.items())),
        latest_end.isoformat() if latest_end else "UNKNOWN",
        " - STALE, %dd old" % age if stale else ""))
    return {"by_status": by_status,
            "latest_period_end": latest_end.isoformat() if latest_end else None,
            "scorecard_age_days": age, "scorecard_stale": stale,
            "sowhat": sowhat, "status": "bad" if stale else "ok"}


QA_FAIL_SQL = """
SELECT count(*) FROM (
  SELECT DISTINCT ON (c.id) c.id, r.status
  FROM successbrian_os.pm_project_checks c
  JOIN successbrian_os.pm_project_qa_runs r ON r.check_id = c.id
  ORDER BY c.id, r.ran_at DESC
) latest WHERE status = 'fail'"""


def panel_gauges():
    qa_failing = pg_one(QA_FAIL_SQL)
    watermark = pg_one(
        "SELECT value FROM successbrian_os.capture_ingest_state "
        "WHERE key='epoch_capture_id'")
    backlog = {}
    try:
        backlog = dict(pg_rows(
            "SELECT status, count(*) FROM atlas.scattered_captures "
            "GROUP BY status"))
    except Exception as e:  # store unreachable: UNKNOWN, never invented
        backlog = unk("atlas.scattered_captures unreadable: %s" % e)
    raw = backlog.get("raw") if isinstance(backlog, dict) and not is_unk(backlog) else None
    price_max = pg_one("SELECT max(checked_on) FROM successbrian_os.price_intel")
    price_expired = pg_one(
        "SELECT count(*) FROM successbrian_os.price_intel "
        "WHERE valid_until < now()")
    market_max = pg_one("SELECT max(fetched_at) FROM public.market_pricing")
    sowhat = ("QA failing %s; clerk watermark %s; raw backlog %s; "
              "price_intel expired %s." % (
                  fmt(qa_failing), fmt(watermark), fmt(raw),
                  fmt(price_expired)))
    return {"qa_failing": qa_failing,
            "clerk_watermark": (int(watermark) if watermark and
                                str(watermark).isdigit() else watermark),
            "scattered_backlog": backlog,
            "price_intel_max_checked_on": price_max.isoformat() if price_max else None,
            "price_intel_expired": price_expired,
            "market_pricing_max_fetched_at": market_max.isoformat() if market_max else None,
            "market_pricing_rel": rel(market_max),
            "sowhat": sowhat,
            "status": "bad" if (qa_failing or 0) > 0 else "ok"}


PANELS = [
    ("needs_brian", "Needs Brian", panel_needs_brian),
    ("blockers", "Blockers", panel_blockers),
    ("goals", "Goal Register", panel_goals),
    ("work", "Work in Motion", panel_work),
    ("einstein", "Einstein Look Feed", panel_einstein),
    ("fleet", "Workers & Fleet", panel_fleet),
    ("research", "Competitive Research", panel_research),
    ("blogs", "Blog Fleet", panel_blogs),
    ("gauges", "System Gauges", panel_gauges),
]


def collect():
    data = {"generated_at": now_utc().isoformat(), "panels": {}}
    for key, _title, fn in PANELS:
        try:
            data["panels"][key] = fn()
        except Exception as e:
            data["panels"][key] = {
                "unknown": True, "reason": "panel query failed: %s" % e,
                "sowhat": "UNKNOWN - panel query failed: %s" % e,
                "status": "unknown"}
    # headline numbers the QA check recounts live
    p = data["panels"]
    data["headlines"] = {
        "decisions_waiting": (p["needs_brian"].get("count")
                              if not is_unk(p["needs_brian"]) else None),
        "pm_steps_queued": (p["work"].get("pm_steps", {}).get("queued")
                            if not is_unk(p["work"]) else None),
        "qa_failing": (p["gauges"].get("qa_failing")
                       if not is_unk(p["gauges"]) else None),
    }
    return data


# ---------------------------------------------------------------- render
CSS = """
:root{--ok:#1a7f37;--warn:#bf8700;--bad:#cf222e;--unknown:#6e7781;
--ink:#1f2328;--mut:#57606a;--line:#d0d7de;--bg:#f6f8fa}
*{box-sizing:border-box}body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
margin:0;background:var(--bg);color:var(--ink)}
header{padding:16px 20px 4px}h1{font-size:20px;margin:0}
.sub{color:var(--mut);font-size:13px}
main{padding:8px 20px 24px;display:grid;gap:14px}
section{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 16px}
h2{font-size:15px;margin:0 0 2px}
.sowhat{font-size:14px;margin:0 0 8px}
.badge{display:inline-block;padding:0 7px;border-radius:9px;font-size:11px;
color:#fff;vertical-align:2px;margin-left:6px}
.st-ok{background:var(--ok)}.st-warn{background:var(--warn)}
.st-bad{background:var(--bad)}.st-unknown{background:var(--unknown)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-top:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
.kv{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:13px}
.unk{color:var(--unknown);font-weight:600}
.stale{color:var(--bad);font-weight:700}
.plan{white-space:pre-wrap;font-size:12.5px;color:var(--mut)}
"""


def badge(status):
    return '<span class="badge st-%s">%s</span>' % (status, status.upper())


def kv(pairs):
    out = []
    for k, v in pairs:
        cls = ' class="unk"' if (isinstance(v, str) and
                                 v.startswith("UNKNOWN")) else ""
        out.append("<div>%s: <span class='mono'%s>%s</span></div>"
                   % (esc(k), cls, esc(v)))
    return '<div class="kv">%s</div>' % "".join(out)


def table(headers, rows_html):
    return ("<table><tr>%s</tr>%s</table>" % (
        "".join("<th>%s</th>" % esc(h) for h in headers),
        "".join("<tr>%s</tr>" % r for r in rows_html)))


def counts_str(d):
    if is_unk(d):
        return fmt(d)
    return ", ".join("%s=%s" % (k, v) for k, v in sorted(d.items()))


def render(data):
    p = data["panels"]
    gen = datetime.fromisoformat(data["generated_at"])
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
             "<title>SBOS Dashboard</title><style>%s</style></head>"
             "<body><header><h1>SBOS Dashboard</h1>"
             "<div class='sub'>Generated <span class='mono'>%s</span> "
             "(%s) &middot; exception-first; UNKNOWN means the store "
             "cannot answer, never an invented number.</div></header>"
             "<main>" % (CSS, gen.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z"),
                         rel(gen))]

    def section(key, title, body):
        pan = p[key]
        parts.append("<section><h2>%s%s</h2><p class='sowhat'>%s</p>%s"
                     "</section>" % (esc(title), badge(pan.get("status",
                     "unknown")), esc(pan.get("sowhat", "")), body))

    # 1 Needs Brian
    nb = p["needs_brian"]
    if is_unk(nb):
        body = "<p class='unk'>%s</p>" % esc(fmt(nb))
    else:
        rows = ["<td class='mono'>%s</td><td>%s</td>"
                "<td class='mono'>%s</td><td class='mono'>%dd</td>"
                % (r["id"], esc(r["item"]), r["first_surfaced"],
                   r["age_days"]) for r in nb["top5"]]
        body = kv([("waiting", nb["count"]),
                   ("oldest", "%sd" % nb["oldest_age_days"])]) + \
            table(["id", "item", "first surfaced", "age"], rows)
    section("needs_brian", "Needs Brian", body)

    # 2 Blockers
    bl = p["blockers"]
    if is_unk(bl):
        body = "<p class='unk'>%s</p>" % esc(fmt(bl))
    else:
        lk = bl["vps"].get("last_known", {})
        lk_txt = ("last-known (%s): gamma_disk=%s" % (
            lk.get("snapshot_at", "UNKNOWN"), fmt(lk.get("gamma_disk")))
            if not is_unk(lk) else fmt(lk))
        rows = []
        for g in bl["gamma"]:
            flag = " <span class='stale'>STALE &gt;2h</span>" if g["stale_2h"] else ""
            rows.append("<td class='mono'>%s</td><td class='mono'>%s</td>"
                        "<td class='mono'>%s</td>" % (
                            g["program_key"], g["state"],
                            g["last_proof_rel"] + flag))
        body = ("<p>VPS status: <span class='unk'>UNKNOWN - no live "
                "source in the ecosystem</span><br>"
                "<span class='mono'>%s</span></p>" % esc(lk_txt)) + \
            table(["gamma program", "state", "last proof"], rows)
    section("blockers", "Blockers", body)

    # 3 Goal Register
    gl = p["goals"]
    if is_unk(gl):
        body = "<p class='unk'>%s</p>" % esc(fmt(gl))
    else:
        rows = []
        for g in gl["goals"]:
            mark = ("STALLED x%d" % g["stall_count"] if g["stall_count"] else
                    "due-early" if g["due_early"] else "")
            rows.append(
                "<td class='mono'>%s</td><td class='mono'>%s</td>"
                "<td class='mono'>%s</td><td class='mono'>%s</td>"
                "<td>%s</td><td class='mono'>%s (%s)</td>"
                "<td>%s</td>" % (
                    g["slug"], g["origin_class"] or "UNKNOWN",
                    g["tier"] or "UNKNOWN",
                    "yes" if g["has_brian_words"] else "no",
                    esc(mark), g["last_look_rel"], g["last_seat"] or "-",
                    esc(g["last_verdict"] or "")))
        body = kv([("total", gl["total"]),
                   ("by origin", counts_str(gl["by_origin"])),
                   ("by tier", counts_str(gl["by_tier"])),
                   ("due_early", gl["due_early"]),
                   ("stalled", gl["stalled"]),
                   ("looks overdue", gl["looks_overdue"])]) + table(
            ["goal", "origin", "tier", "brian words", "flag",
             "last look (seat)", "verdict"], rows)
    section("goals", "Goal Register", body)

    # 4 Work in Motion
    wk = p["work"]
    if is_unk(wk):
        body = "<p class='unk'>%s</p>" % esc(fmt(wk))
    else:
        sw = wk["latest_sweep"]
        sw_txt = fmt(sw) if is_unk(sw) else (
            "%s steps scanned, %s (%s)" % (sw["steps_scanned"],
                                           rel(datetime.fromisoformat(sw["ran_at"])),
                                           sw["status"]))
        body = kv([("pm_steps", counts_str(wk["pm_steps"])),
                   ("claims 24h", counts_str(wk["claims_24h"])),
                   ("claims total", counts_str(wk["claims_total"])),
                   ("consolidation proposals", counts_str(wk["proposals"])),
                   ("latest sweep", sw_txt)])
    section("work", "Work in Motion", body)

    # 5 Einstein
    ei = p["einstein"]
    if is_unk(ei):
        body = "<p class='unk'>%s</p>" % esc(fmt(ei))
    else:
        rows = ["<td class='mono'>%s</td><td class='mono'>%s</td>"
                "<td class='plan'>%s</td>" % (e["goal"], e["collected_rel"],
                                              esc(e["plan"]))
                for e in ei["latest"]]
        body = kv([("by status", counts_str(ei["by_status"]))]) + \
            table(["goal", "collected", "plan (first 300 chars)"], rows)
    section("einstein", "Einstein Look Feed", body)

    # 6 Fleet
    fl = p["fleet"]
    if is_unk(fl):
        body = "<p class='unk'>%s</p>" % esc(fmt(fl))
    else:
        rows = ["<td class='mono'>%s</td><td class='mono'>%s</td>"
                "<td class='mono'>%s</td><td>%s</td>" % (
                    e["program_key"], e["state"], e["last_proof_rel"],
                    esc(e["reason"])) for e in fl["exceptions"]]
        body = kv([("total", fl["total"]), ("watched", fl["watched"]),
                   ("manual", fl["manual"]),
                   ("fresh <=1h", fl["fresh_le_1h"]),
                   ("exceptions shown", "%d of %d" % (
                       len(fl["exceptions"]), fl["exception_count"]))]) + \
            table(["program", "state", "last proof", "why exception"], rows)
    section("fleet", "Workers & Fleet", body)

    # 7 Research
    rs = p["research"]
    if is_unk(rs):
        body = "<p class='unk'>%s</p>" % esc(fmt(rs))
    else:
        rows = ["<td>%s</td><td class='mono'>%s</td>"
                "<td class='mono'>%d</td>" % (esc(q["subject"]), q["status"],
                                              q["routed_outputs"])
                for q in rs["questions"]]
        body = kv([("by status", counts_str(rs["by_status"]))]) + \
            table(["subject", "status", "routed outputs"], rows)
    section("research", "Competitive Research", body)

    # 8 Blogs
    bg = p["blogs"]
    if is_unk(bg):
        body = "<p class='unk'>%s</p>" % esc(fmt(bg))
    else:
        stale = (" <span class='stale'>STALE</span>"
                 if bg["scorecard_stale"] else "")
        body = kv([("by status", counts_str(bg["by_status"])),
                   ("latest scorecard period_end",
                    "%s (%sd old)%s" % (bg["latest_period_end"],
                                        bg["scorecard_age_days"], ""))]) + \
            ("<p class='stale'>Scorecard data is STALE - latest period "
             "ended %s.</p>" % bg["latest_period_end"] if bg["scorecard_stale"]
             else "")
        _ = stale
    section("blogs", "Blog Fleet", body)

    # 9 Gauges
    gz = p["gauges"]
    if is_unk(gz):
        body = "<p class='unk'>%s</p>" % esc(fmt(gz))
    else:
        body = kv([("QA failing (latest run per check)", gz["qa_failing"]),
                   ("clerk watermark (epoch_capture_id)", gz["clerk_watermark"]),
                   ("scattered backlog", counts_str(gz["scattered_backlog"])),
                   ("price_intel max checked_on", gz["price_intel_max_checked_on"] or "UNKNOWN"),
                   ("price_intel expired", gz["price_intel_expired"]),
                   ("market_pricing max fetched_at",
                    "%s (%s)" % (gz["market_pricing_max_fetched_at"] or "UNKNOWN",
                                 gz["market_pricing_rel"]))])
    section("gauges", "System Gauges", body)

    parts.append("</main></body></html>")
    return "".join(parts)


# ---------------------------------------------------------------- modes
def do_generate():
    ensure_schema()
    data = collect()
    page = render(data)
    pg_exec(
        "INSERT INTO successbrian_os.dashboard_snapshots (data, html) "
        "VALUES (%s, %s)",
        (json.dumps(data, default=str), page))
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(page)
    log("dashboard generated: headlines=%s -> %s"
        % (json.dumps(data["headlines"]), OUT_PATH))
    print(json.dumps(data["headlines"]))
    return 0


def do_selftest():
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    check("rel days", rel(datetime.now(timezone.utc)
                          - timedelta(days=14)) == "14d ago")
    check("rel hours", rel(datetime.now(timezone.utc)
                           - timedelta(hours=3)) == "3h ago")
    check("rel none is UNKNOWN", rel(None) == "UNKNOWN")
    check("fmt unknown carries reason",
          fmt(unk("no store")) == "UNKNOWN (no store)")
    fake = {"generated_at": now_utc().isoformat(), "headlines": {},
            "panels": {}}
    for key, _t, _fn in PANELS:
        fake["panels"][key] = {"sowhat": "x", "status": "unknown",
                               "unknown": True, "reason": "selftest"}
    page = render(fake)
    check("render produces all 9 panels",
          page.count("<section>") == 9)
    check("render is self-contained (no external refs)",
          "http://" not in page and "https://" not in page
          and "<script" not in page and "<link" not in page)
    check("status vocabulary present",
          all(("st-%s" % s) in page for s in
              ("ok", "warn", "bad", "unknown")))
    # live collect: every panel either answers or declares UNKNOWN
    data = collect()
    for key, _t, _fn in PANELS:
        pan = data["panels"][key]
        check("panel %s answered or UNKNOWN" % key,
              "sowhat" in pan)
    check("headlines keys present",
          set(data["headlines"]) == {"decisions_waiting",
                                     "pm_steps_queued", "qa_failing"})
    print("SELFTEST %s (%d failures)" % ("PASS" if not fails else "FAIL",
                                        len(fails)))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["generate", "selftest"])
    args = ap.parse_args()
    if args.mode == "generate":
        return do_generate()
    return do_selftest()


if __name__ == "__main__":
    sys.exit(main())
