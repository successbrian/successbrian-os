#!/usr/bin/env python3
"""
Horizon layer of the Spencer Review Toolkit — the weekly companion to
tools/review/review.py (same CLI surface; review.py exposes these verbs).

Brian's order (2026-11-09 23:29 CST): "build tools/systems/code into
successbrian os that allow you to more easily and efficiently do these
things" — the things being the Saturday 04:00 WEEKEND HORIZON CHECK's
work (charter set 2026-11-09 23:18-23:27 CST): goals/pace, money
horizon, systems trend, content chain, health trend, aged waiting
list, set the week's agenda. Plus the 23:30 CST charter addition:
"Saturday 4am should QA check other builds/improvements that happened
and make sure they really improved things" — the build-verification
instrument below.

Doctrine position is identical to the daily toolkit (spec:
docs/spencer-review-toolkit-spec.md): bookkeeping and arithmetic for
the Intel Harness flow's management surface. These instruments render
no verdicts of their own about Brian's life; the one verdict-shaped
output (build verification) is a machine verdict over QA/gauge
evidence, with its evidence lines attached and an explicit reason
whenever it cannot verify.

Honesty rules (inherited, non-negotiable):
  * a source that cannot be read is a printed coverage gap, never a
    silent zero or an invented figure;
  * prices are Postgres state only;
  * the health instrument emits DATA ONLY — no targets, no advice,
    no evaluative health language (selftest-enforced);
  * goal actuals that are not machine-readable are coverage gaps.

Verbs (via review.py): pace, trend, aging, money, health-week,
content-chain, build-verify, agenda-set, agenda-list, agenda-mark,
week-briefing, horizon-selftest.

State added (Postgres, successbrian_os schema):
  review_agenda          — the week's priorities, as data
  review_build_verdicts  — persisted build-verification verdicts

Pace-data repair (2026-11-09, capture #1148): pace also reads the
goal-driver stores as DATA — successbrian_os.monthly_goals (Brian-ruled
monthly targets) + successbrian_os.goal_month_scores (actuals entered
from program back offices ONLY, via tools/goal_driver.py score; an
unreported month is NOT REPORTED, never estimated) +
successbrian_os.goal_income_ladder (Brian's fixed dollar ladders,
entered as data by tools/goal_pace_data_migration_2026-11-09.sql —
amounts are Brian's data, never hardcoded here).
"""

import calendar as _cal
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
for _p in (_TOOLS, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402
import review as R  # noqa: E402  (the daily toolkit: gauges, snapshots)

TZ = R.TZ


def _num(x):
    """Decimal/date-safe float or None."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _attempt(cov, name, fn):
    try:
        out = fn()
        cov.append({"source": name, "ok": True})
        return out
    except Exception as e:  # noqa: BLE001
        cov.append({"source": name, "ok": False,
                    "note": f"{type(e).__name__}: {str(e)[:160]}"})
        return None


def ensure_horizon_tables():
    pg_exec("""
    CREATE TABLE IF NOT EXISTS successbrian_os.review_agenda (
        id serial PRIMARY KEY,
        week_of date NOT NULL,
        slot int NOT NULL,
        priority text NOT NULL,
        source text,
        why text,
        state text NOT NULL DEFAULT 'open',
        state_note text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (week_of, slot)
    )""")
    pg_exec("""
    CREATE TABLE IF NOT EXISTS successbrian_os.review_build_verdicts (
        id serial PRIMARY KEY,
        verified_at timestamptz NOT NULL DEFAULT now(),
        window_start timestamptz,
        window_end timestamptz,
        build_ref text NOT NULL,
        project_key text,
        claim text,
        verdict text NOT NULL,
        evidence jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""")


# ---------------------------------------------------------------------------
# 1. PACE — required pace vs recorded actuals, per tracked goal.
# Sources: alpha stores only. A goal whose actuals are not machine-
# readable is a coverage-gap line, never an invented figure.
# ---------------------------------------------------------------------------
def monthly_scorecard(today):
    """Brian-ruled monthly goals (monthly_goals) vs the counts entered
    from program back offices (goal_month_scores). An unreported month
    is NOT REPORTED — never estimated (goal-driver doctrine)."""
    first = date(today.year, today.month, 1)
    dim = _cal.monthrange(today.year, today.month)[1]
    rows = pg_rows("""
        SELECT g.goal_key, g.product, g.target, g.unit, g.kind,
               cur.achieved, cur.source, last.month, last.achieved
        FROM successbrian_os.monthly_goals g
        LEFT JOIN successbrian_os.goal_month_scores cur
          ON cur.goal_key = g.goal_key AND cur.month = %s
        LEFT JOIN LATERAL (
            SELECT month, achieved
            FROM successbrian_os.goal_month_scores s
            WHERE s.goal_key = g.goal_key
            ORDER BY month DESC LIMIT 1) last ON true
        ORDER BY g.target DESC""", (first,))
    out = []
    for key, product, target, unit, kind, achieved, src, lm, la in rows:
        fast = (kind == "fast_track")
        if achieved is None:
            verdict, state, rec = "no-data", "NOT REPORTED", None
            required = None if fast else round(
                float(target) * today.day / dim, 1)
            rate = None
        else:
            state, rec = "reported", float(achieved)
            if fast:
                verdict = ("ahead" if rec >= float(target)
                           else "holding")
                required, rate = None, None
            else:
                required = float(target) * today.day / dim
                ratio = rec / required if required > 0 else None
                verdict = ("no-data" if ratio is None else
                           "ahead" if ratio >= 1.1 else
                           "slipping" if ratio < 0.7 else "holding")
                required = round(required, 1)
                rate = (round((float(target) - rec)
                              / max(dim - today.day, 1), 2)
                        if float(target) > rec else 0)
        note = None
        if state == "NOT REPORTED":
            note = ("current month NOT REPORTED — counts enter from "
                    "the program back office only "
                    "(tools/goal_driver.py score); unreported months "
                    "are never estimated.")
            if lm is None:
                note += (" No month has ever been reported for this "
                         "goal.")
        if fast:
            note = ((note + " ") if note else "") + (
                "Product pick still OPEN (Brian's ruling pending); "
                "0 evidenced sales recorded — nothing fabricated.")
        out.append({
            "goal": product, "goal_key": key,
            "store": "successbrian_os.monthly_goals + "
                     "goal_month_scores",
            "method": "monthly target (monthly_goals, Brian-ruled) "
                      "vs entered back-office counts "
                      "(goal_month_scores)",
            "kind": kind, "target_per_month": float(target),
            "target_unit": unit,
            "actual_recorded_this_month": rec,
            "actuals_state": state,
            "actuals_source": src,
            "required_by_today": required,
            "rate_needed_rest_of_month": rate,
            "last_reported": ({"month": lm.isoformat(),
                               "achieved": float(la)}
                              if lm is not None else None),
            "verdict": verdict, "note": note})
    return out


def ladder_report(today):
    """Brian's fixed dollar ladder for GotBackup, read from
    successbrian_os.goal_income_ladder (data, entered 2026-11-09 by
    tools/goal_pace_data_migration_2026-11-09.sql from Brian's
    2026-10-29 ruling). The ladder never moves."""
    rows = pg_rows("""
        SELECT rung_month, target_monthly_usd
        FROM successbrian_os.goal_income_ladder
        WHERE goal_key = 'gotbackup-40' ORDER BY rung_month""")
    if not rows:
        return None
    rungs = [{"month": r[0].isoformat(),
              "target_monthly_usd": float(r[1])} for r in rows]
    nxt = next((r for r in rows if r[0] >= date(today.year,
                                                today.month, 1)), None)
    months_to = None
    if nxt is not None:
        months_to = ((nxt[0].year - today.year) * 12
                     + (nxt[0].month - today.month))
    actual = _num(pg_one(
        "SELECT actual_monthly_usd FROM successbrian_os.income_streams "
        "WHERE name = 'GotBackup'"))
    if actual is None:
        verdict = "no-data"
    elif nxt is not None and actual >= float(nxt[1]):
        verdict = "ahead"
    else:
        verdict = "no-data"
    return {
        "goal": "GotBackup fixed dollar ladder",
        "goal_key": "gotbackup-40",
        "store": "successbrian_os.goal_income_ladder",
        "method": "rungs as data vs the recorded GotBackup run-rate "
                  "(income_streams.actual_monthly_usd)",
        "rungs": rungs,
        "next_rung": ({"month": nxt[0].isoformat(),
                       "target_monthly_usd": float(nxt[1])}
                      if nxt is not None else None),
        "months_to_next_rung": months_to,
        "recorded_run_rate_usd": actual,
        "run_rate_state": ("NOT REPORTED" if actual is None
                           else "recorded"),
        "verdict": verdict,
        "note": ("recorded run-rate: none on record — "
                 "income_streams.actual_monthly_usd is unset for "
                 "GotBackup, so ladder position is no-data, stated "
                 "plainly; the rungs themselves are now data."
                 if actual is None else
                 "run-rate recorded; the instrument reports ladder "
                 "position only against the next rung (no growth "
                 "model is encoded)."),
        "rule": "the ladder never moves; if the 40/mo pace is being "
                "hit the PACE may be raised — the dollar rungs stay "
                "(Brian, 2026-10-29)"}


def pace_report():
    today = R.now_ct().date()
    cov, goals, gaps = [], [], []

    def sbos_metric_goals():
        rows = pg_rows("""
            SELECT id, goal_name, goal_slug, target_date, progress_pct,
                   success_metrics, current_month_deals, current_revenue,
                   last_revenue_update, created_at
            FROM successbrian_os.sbos_goals
            WHERE status = 'active' AND success_metrics IS NOT NULL
              AND success_metrics::text NOT IN ('{}', 'null')
            ORDER BY id""")
        out = []
        for r in rows:
            sm = r[5] if isinstance(r[5], dict) else {}
            mt = _num(sm.get("monthly_target"))
            if mt:
                dim = _cal.monthrange(today.year, today.month)[1]
                required = mt * today.day / dim
                actual = _num(r[6]) or 0.0
                # A counter that has NEVER been updated is not a
                # measurement (pace-data repair, 2026-11-09): verdict
                # off it would be fiction. The maintained actuals home
                # is goal_month_scores — see the monthly scorecard.
                counter_live = r[8] is not None
                ratio = ((actual / required)
                         if (counter_live and required > 0) else None)
                verdict = ("no-data" if ratio is None else
                           "ahead" if ratio >= 1.1 else
                           "slipping" if ratio < 0.7 else "holding")
                out.append({
                    "goal": r[1], "store": "successbrian_os.sbos_goals",
                    "goal_id": r[0], "method": "monthly target vs "
                    "current_month_deals, pro-rated to today",
                    "counter_state": ("live" if counter_live else
                                      "never updated — not a "
                                      "measurement"),
                    "note": (None if counter_live else
                             "this store's actuals counter "
                             "(current_month_deals) has never been "
                             "updated — it is not a measurement. "
                             "Monthly actuals live in "
                             "successbrian_os.goal_month_scores "
                             "(program back-office counts only); see "
                             "the monthly scorecard entries below."),
                    "target_per_month": mt,
                    "weekly_target": _num(sm.get("weekly_target")),
                    "daily_target": _num(sm.get("daily_target")),
                    "actual_recorded_this_month": (actual if counter_live
                    else None),
                    "required_by_today": round(required, 1),
                    "ratio": round(ratio, 2) if ratio is not None else None,
                    "days_left_in_month": dim - today.day,
                    "rate_needed_rest_of_month": (round(
                        (mt - actual) / max(dim - today.day, 1), 2)
                    if mt > actual else 0) if counter_live else None,
                    "actuals_last_updated": r[8].isoformat() if r[8]
                    else None,
                    "verdict": verdict})
            elif r[3]:  # target_date but no numeric metric target
                out.append({
                    "goal": r[1], "store": "successbrian_os.sbos_goals",
                    "goal_id": r[0], "method": "target date only",
                    "target_date": r[3].isoformat(),
                    "days_remaining": (r[3] - today).days,
                    "progress_pct": _num(r[4]), "verdict": "no-data",
                    "note": "date is machine-readable; no numeric "
                            "actuals counter in this store"})
        return out

    def brian_goal_dates():
        rows = pg_rows("""
            SELECT id, goal_name, target_date, start_date, created_at,
                   progress_pct, status
            FROM public.brian_goals
            WHERE target_date IS NOT NULL
              AND status NOT IN ('completed', 'done', 'cancelled')
            ORDER BY target_date""")
        out = []
        for r in rows:
            start = r[3] or (r[4].date() if r[4] else None)
            if not start or r[2] <= start:
                continue
            total = (r[2] - start).days
            elapsed = min(max((today - start).days, 0), total)
            expected = round(100.0 * elapsed / total, 1) if total else None
            prog = _num(r[5])
            diff = (prog - expected) if (prog is not None
                                         and expected is not None) else None
            verdict = ("no-data" if diff is None else
                       "ahead" if diff >= 10 else
                       "slipping" if diff <= -10 else "holding")
            if r[2] < today and (prog or 0) < 100:
                verdict = "slipping"
            out.append({
                "goal": r[1], "store": "public.brian_goals",
                "goal_id": r[0], "method": "progress_pct vs elapsed "
                "share of start->target window",
                "target_date": r[2].isoformat(),
                "days_remaining": (r[2] - today).days,
                "progress_pct": prog, "expected_pct_by_now": expected,
                "verdict": verdict})
        return out

    def mindell_deadline():
        found = []

        def probe(label, fn):
            try:
                hit = fn()
            except Exception:  # noqa: BLE001
                hit = None
            if hit:
                found.append((label, hit))

        def from_node():
            rows = pg_rows(
                "SELECT details::text FROM atlas.nodes "
                "WHERE node_key = 'launch:mindell-olive-oil-bible'")
            if rows:
                m = re.search(r"2027-05-18|May 18,? 2027", rows[0][0] or "")
                if m:
                    return "atlas node launch:mindell-olive-oil-bible " \
                           "details"

        def from_calendar():
            rows = pg_rows(
                "SELECT title FROM successbrian_os.life_calendar "
                "WHERE title ILIKE '%mindell%' OR title ILIKE '%olive%'")
            for r in rows:
                if r[0] and ("2027" in r[0] or "Olive" in r[0]):
                    return f"life_calendar: {r[0]}"

        def from_captures():
            rows = pg_rows(
                "SELECT id, raw_text FROM atlas.scattered_captures "
                "WHERE id IN (464, 468)")
            for cid, raw in rows:
                if raw and re.search(r"2027-05-18|May 18,? 2027", raw):
                    return f"Intel Bridge capture #{cid} (publicly " \
                           f"listed publication date in the dig text)"

        probe("node", from_node)
        probe("calendar", from_calendar)
        probe("captures", from_captures)
        checks = pg_rows(
            "SELECT last_status, count(*) FROM "
            "successbrian_os.pm_project_checks "
            "WHERE project_key = 'mindell-launch-readiness' "
            "GROUP BY last_status")
        qa = {r[0] or "never-run": r[1] for r in checks}
        if found:
            return {"goal": "Mindell Olive Oil Bible launch readiness",
                    "store": found[0][1],
                    "method": "fixed deadline vs calendar; readiness "
                              "actuals = the PM project's check states "
                              "(proxy, labeled)",
                    "deadline": "2027-05-18",
                    "days_remaining": (date(2027, 5, 18) - today).days,
                    "readiness_qa_states": qa, "verdict": "no-data",
                    "note": "no machine-readable readiness metric "
                            "(percent ready, warm-up counts) exists in "
                            "the alpha stores; the deadline and the QA "
                            "proxy are what the record holds"}
        return None

    def ladder_probe():
        n = pg_one("SELECT count(*) FROM "
                   "successbrian_os.goal_month_scores")
        return n

    a = _attempt(cov, "pace:sbos_goals", sbos_metric_goals)
    if a:
        goals.extend(a)
    b = _attempt(cov, "pace:brian_goals", brian_goal_dates)
    if b:
        goals.extend(b)
    m = _attempt(cov, "pace:mindell_deadline", mindell_deadline)
    if m:
        goals.append(m)
    scores = _attempt(cov, "pace:goal_month_scores", ladder_probe)
    sc = _attempt(cov, "pace:monthly_scorecard",
                  lambda: monthly_scorecard(today))
    if sc:
        goals.extend(sc)
    lad = _attempt(cov, "pace:goal_income_ladder",
                   lambda: ladder_report(today))
    unreported = [g["goal_key"] for g in (sc or [])
                  if g.get("actuals_state") == "NOT REPORTED"]
    if unreported:
        gaps.append(
            "Monthly-goal actuals feeding duty: counts enter "
            "successbrian_os.goal_month_scores ONLY from program "
            "back offices via tools/goal_driver.py score — never "
            "estimated; unreported months print NOT REPORTED. "
            f"goal_month_scores holds {scores} rows total; currently "
            "unreported for this month: " + ", ".join(unreported)
            + ". The review passes nag until a count is reported.")
    if not lad:
        gaps.append(
            "GotBackup fixed dollar ladder: "
            "successbrian_os.goal_income_ladder holds no rungs — "
            "ladder pace cannot be computed until the rungs are "
            "entered as data (tools/goal_pace_data_migration_"
            "2026-11-09.sql).")
    gaps.append(
        "Muse-side tracked goals (user_action_required / "
        "new_information flags) are not readable from alpha; pace "
        "covers alpha-store goals only.")
    if b:
        gaps.append(
            "public.brian_goals mixes Brian's own goals with synced "
            "task items (brian_todo sync); the date/progress rows are "
            "reported as recorded, store quality noted.")
    return {"taken_at": datetime.now(timezone.utc).isoformat(),
            "goals": goals, "ladder": lad,
            "coverage_gaps": gaps, "coverage": cov}


def pace_text(rep):
    L = ["PACE — required pace vs recorded actuals (alpha stores)"]
    shown = 0
    for g in rep["goals"]:
        if g.get("store") == "public.brian_goals":
            shown += 1
            if shown > 12:
                continue
        bits = [f"{g['goal']} [{g['verdict']}]"]
        if "target_per_month" in g:
            unit = g.get("target_unit")
            bits.append(f"target {g['target_per_month']}/mo"
                        + (f" ({unit})" if unit else ""))
            rec = g.get("actual_recorded_this_month")
            bits.append("recorded this month NOT REPORTED"
                        if rec is None else
                        f"recorded this month {rec}")
            if g.get("required_by_today") is not None:
                bits.append(f"required by today "
                            f"{g['required_by_today']}")
            if g.get("rate_needed_rest_of_month") is not None:
                bits.append(f"rate needed rest of month "
                            f"{g['rate_needed_rest_of_month']}/day")
            lr = g.get("last_reported")
            if lr:
                bits.append(f"last reported {lr['month']}: "
                            f"{lr['achieved']}")
            if ("actuals_last_updated" in g
                    and not g.get("actuals_last_updated")):
                bits.append("actuals counter never updated in this "
                            "store (staleness noted)")
        elif "deadline" in g:
            bits.append(f"deadline {g['deadline']}; "
                        f"{g['days_remaining']} days remaining; "
                        f"readiness QA states {g['readiness_qa_states']}")
        elif "target_date" in g:
            bits.append(f"target {g['target_date']}; "
                        f"{g['days_remaining']} days remaining; "
                        f"progress {g.get('progress_pct')}%"
                        + (f" vs {g['expected_pct_by_now']}% expected "
                           f"by now" if g.get("expected_pct_by_now")
                           is not None else ""))
        L.append("  - " + "; ".join(bits))
        L.append(f"    method: {g.get('method', '')} "
                 f"({g.get('store', '')})")
        if g.get("note"):
            L.append(f"    note: {g['note']}")
    lad = rep.get("ladder")
    if lad:
        L.append(f"  LADDER — {lad['goal']} [{lad['verdict']}] "
                 f"(data: {lad['store']})")
        for r in lad["rungs"]:
            L.append(f"    rung {r['month']}: "
                     f"${r['target_monthly_usd']:,.0f}/mo")
        nr = lad.get("next_rung")
        if nr:
            rr = lad.get("recorded_run_rate_usd")
            L.append(f"    next rung {nr['month']}: "
                     f"${nr['target_monthly_usd']:,.0f}/mo in "
                     f"{lad['months_to_next_rung']} months; recorded "
                     f"GotBackup run-rate: "
                     + ("NOT REPORTED" if rr is None else f"${rr:,.2f}"))
        L.append(f"    rule: {lad['rule']}")
        if lad.get("note"):
            L.append(f"    note: {lad['note']}")
    nb = sum(1 for g in rep["goals"]
             if g.get("store") == "public.brian_goals")
    if nb > 12:
        L.append(f"  ... +{nb - 12} more public.brian_goals rows in "
                 f"the JSON output (store mixes goals with synced "
                 f"task items — see gaps)")
    for gap in rep["coverage_gaps"]:
        L.append(f"  GAP: {gap}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 2. TREND — week-over-week movement. History starts 2026-11-09; the
# thin-history case is reported as "accumulating", never faked.
# ---------------------------------------------------------------------------
_SCALAR_GAUGES = ["qa_failing_count", "raw_backlog", "raw_oldest_age_h",
                  "unsorted_docs", "unindexed_docs", "github_stars",
                  "github_forks", "afbn_fans", "authorship_reserve",
                  "authorship_days_since_publish", "gamma_disk_pct",
                  "price_intel_expired", "decisions_waiting",
                  "frictions_open", "issues_blocked_brian",
                  "clerk_watermark", "market_pricing_age_h"]


def trend_report():
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "coverage": cov}

    def snaps():
        rows = pg_rows(
            "SELECT id, taken_at, pass_kind, gauges FROM "
            "successbrian_os.review_snapshots ORDER BY taken_at")
        out = {"count": len(rows),
               "first_taken_at": rows[0][1].isoformat() if rows else None,
               "latest_taken_at": rows[-1][1].isoformat() if rows
               else None}
        if rows:
            span_d = (rows[-1][1] - rows[0][1]).total_seconds() / 86400.0
            out["span_days"] = round(span_d, 2)
            out["week_over_week"] = (
                "computable" if span_d >= 7 else "accumulating")
            if span_d < 7:
                out["week_over_week_note"] = (
                    f"snapshot history began {out['first_taken_at']}; "
                    f"a full week of history exists from "
                    f"{(rows[0][1] + timedelta(days=7)).date().isoformat()}. "
                    "Until then this section reports first-vs-latest "
                    "movement and labels it accumulating.")
            series = {}
            for key in _SCALAR_GAUGES:
                vals = []
                for r in rows:
                    g = r[3] if isinstance(r[3], dict) else \
                        json.loads(r[3])
                    v = (g.get("values") or {}).get(key)
                    if isinstance(v, (int, float)):
                        vals.append(v)
                if len(vals) >= 2 and vals[0] != vals[-1]:
                    if key in R.LOWER_BETTER:
                        word = "improved" if vals[-1] < vals[0] \
                            else "worsened"
                    elif key in R.HIGHER_BETTER:
                        word = "improved" if vals[-1] > vals[0] \
                            else "worsened"
                    else:
                        word = "changed"
                    series[key] = {"first": vals[0], "latest": vals[-1],
                                   "direction": word,
                                   "points": len(vals)}
                elif vals:
                    series[key] = {"first": vals[0], "latest": vals[-1],
                                   "direction": "unchanged",
                                   "points": len(vals)}
            out["gauge_series"] = series
        return out

    def qa_recurring():
        rows = pg_rows("""
            SELECT r.check_id, c.project_key, c.check_key, r.status,
                   r.ran_at
            FROM successbrian_os.pm_project_qa_runs r
            JOIN successbrian_os.pm_project_checks c ON c.id = r.check_id
            WHERE r.ran_at > now() - interval '14 days'
            ORDER BY r.check_id, r.ran_at""")
        by = {}
        for cid, proj, chk, status, ran_at in rows:
            by.setdefault(cid, {"project": proj, "check": chk,
                                "runs": []})
            by[cid]["runs"].append((status, ran_at))
        out = []
        for cid, d in by.items():
            runs = d["runs"]
            fails = sum(1 for s, _ in runs if s == "fail")
            streak = 0
            for s, _ in reversed(runs):
                if s == "fail":
                    streak += 1
                else:
                    break
            if streak >= 2 or (len(runs) >= 3 and fails * 2 >= len(runs)):
                out.append({"project": d["project"], "check": d["check"],
                            "runs_14d": len(runs), "fails_14d": fails,
                            "current_fail_streak": streak,
                            "last_run_at": runs[-1][1].isoformat()})
        out.sort(key=lambda x: (-x["current_fail_streak"],
                                -x["fails_14d"]))
        return out[:20]

    def authorship():
        rows = pg_rows(
            "SELECT ran_at, verdict, reserve_count, days_since_publish "
            "FROM campaignsdesk.authorship_runs ORDER BY ran_at")
        if not rows:
            return {"runs": 0}
        return {"runs": len(rows),
                "first": {"ran_at": rows[0][0].isoformat(),
                          "verdict": rows[0][1],
                          "reserve": rows[0][2],
                          "days_since_publish": rows[0][3]},
                "latest": {"ran_at": rows[-1][0].isoformat(),
                           "verdict": rows[-1][1],
                           "reserve": rows[-1][2],
                           "days_since_publish": rows[-1][3]},
                "reserve_min": min(r[2] for r in rows),
                "reserve_max": max(r[2] for r in rows),
                "verdicts_seen": sorted({r[1] for r in rows})}

    rep["snapshots"] = _attempt(cov, "trend:snapshots", snaps)
    rep["qa_recurring_failures"] = _attempt(cov, "trend:qa_runs",
                                            qa_recurring)
    rep["authorship"] = _attempt(cov, "trend:authorship", authorship)
    rep["fan_star_note"] = (
        "fan-evidence and GitHub stars trends ride the snapshot "
        "series above (afbn_fans / github_stars); with history "
        "accumulating they are first-vs-latest only.")
    return rep


def trend_text(rep):
    L = ["TREND — week-over-week movement"]
    s = rep.get("snapshots") or {}
    L.append(f"  snapshots: {s.get('count')} stored, span "
             f"{s.get('span_days')}d, week-over-week: "
             f"{s.get('week_over_week')}")
    if s.get("week_over_week_note"):
        L.append(f"  note: {s['week_over_week_note']}")
    for k, v in (s.get("gauge_series") or {}).items():
        L.append(f"  - {k}: {v['direction']} {v['first']} -> "
                 f"{v['latest']} ({v['points']} points)")
    q = rep.get("qa_recurring_failures") or []
    L.append(f"  recurring QA failures (14d): {len(q)}")
    for r in q[:10]:
        L.append(f"  - {r['project']}/{r['check']}: streak "
                 f"{r['current_fail_streak']}, {r['fails_14d']} fails "
                 f"in {r['runs_14d']} runs")
    a = rep.get("authorship") or {}
    if a.get("runs"):
        L.append(f"  authorship: {a['runs']} runs; latest verdict "
                 f"{a['latest']['verdict']}, reserve "
                 f"{a['latest']['reserve']} (range {a['reserve_min']}-"
                 f"{a['reserve_max']}), {a['latest']['days_since_publish']}"
                 f"d since publish")
    L.append(f"  note: {rep.get('fan_star_note', '')}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 3. AGING — the slow-debt report.
# ---------------------------------------------------------------------------
PARKED_REGISTRY = [
    {"item": "Repo Phase 2: scrub former DB passwords from the 14 "
             "tracked files (pg_password() migration); the "
             "price_historian_sweep hardcoded credentials join the "
             "same scrub class",
     "parked_since": "2026-10-28",
     "source": "Greg-ready audit capture #508; Phase 1 completion "
               "capture #511; price_historian find recorded in the "
               "2026-11-09 Intel Harness build record"},
    {"item": "Core DDL + bootstrap so a fresh SBOS install can "
             "create its database (gate G-C)",
     "parked_since": "2026-10-28",
     "source": "captures #508 (audit) + #509 (Asked-For-By-Name "
               "stage data)"},
    {"item": "Push the doctrine commits + sanitized reference-desk "
             "skeleton + composition CLI + clean-clone proof (gate "
             "G-D)",
     "parked_since": "2026-10-28",
     "source": "captures #508 + #509"},
    {"item": "Mirror the entry-point article off free Wix before "
             "any traffic spike (gate G-E)",
     "parked_since": "2026-10-28",
     "source": "capture #509; AFBN judgment check 295"},
    {"item": "Rotate the 4 private-desk credentials (Apify / "
             "Scrapfly / DeepSeek / Telegram)",
     "parked_since": "2026-10-28",
     "source": "capture #508"},
    {"item": "Git-history purge decision for the rotated AnythingLLM "
             "key (the dead key remains in pushed history)",
     "parked_since": "2026-10-28",
     "source": "capture #511 (rotation verified; purge is a "
               "separate later gate)"},
    {"item": "Board launcher: restore an automatic 02:30 Mon-Fri "
             "sitting or keep hand-started — decision pending",
     "parked_since": "2026-10-28",
     "source": "asked in chat 2026-10-28 16:20 CDT, unanswered; "
               "board record in captures #484/#489"},
    {"item": "Gamma disk at 100%: the space consumer is "
             "unidentified; blocks the link-tracking deploy and "
             "threatens click logging",
     "parked_since": "2026-11-09",
     "source": "capture #1096; review friction ledger (gamma disk "
               "row)"},
]


def _age_buckets(rows_dates, today):
    b = {"0_6d": 0, "7_13d": 0, "14d_plus": 0}
    for d in rows_dates:
        age = (today - d).days
        if age >= 14:
            b["14d_plus"] += 1
        elif age >= 7:
            b["7_13d"] += 1
        else:
            b["0_6d"] += 1
    return b


def aging_report():
    today = R.now_ct().date()
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "coverage": cov}

    def decisions():
        rows = pg_rows(
            "SELECT id, item, first_surfaced FROM "
            "successbrian_os.review_decisions WHERE state='waiting' "
            "ORDER BY first_surfaced, id")
        return {"count": len(rows),
                "buckets": _age_buckets([r[2] for r in rows], today),
                "oldest": [{"id": r[0], "item": r[1],
                            "since": r[2].isoformat(),
                            "age_d": (today - r[2]).days}
                           for r in rows[:10]]}

    def captures():
        raw = pg_rows(
            "SELECT id, created_at FROM atlas.scattered_captures "
            "WHERE status='raw' ORDER BY created_at")
        unruled = pg_one(
            "SELECT count(*) FROM atlas.scattered_captures "
            "WHERE ruled_at IS NULL AND triaged_at IS NOT NULL "
            "AND triaged_at < now() - interval '14 days'")
        return {"raw_count": len(raw),
                "raw_oldest_age_d": round(
                    (datetime.now(timezone.utc) - raw[0][1])
                    .total_seconds() / 86400.0, 1) if raw else None,
                "triaged_unruled_over_14d": unruled,
                "note": "captures carry no Brian-flag column; the "
                        "Brian-facing proxy is altair.issues "
                        "blocked_brian (below) plus this queue's own "
                        "decisions"}

    def blocked():
        n = pg_one("SELECT count(*) FROM altair.issues "
                   "WHERE status='blocked_brian'")
        oldest = pg_one("SELECT min(created_at) FROM altair.issues "
                        "WHERE status='blocked_brian'")
        return {"count": n,
                "oldest_age_d": round(
                    (datetime.now(timezone.utc) - oldest)
                    .total_seconds() / 86400.0, 1) if oldest else None}

    def steps():
        rows = pg_rows(
            "SELECT id, title, status, created_at FROM "
            "successbrian_os.pm_steps WHERE kind='repair' "
            "AND status NOT IN ('done','cancelled') ORDER BY created_at")
        dates = [r[3].date() for r in rows]
        total_open = pg_one(
            "SELECT count(*) FROM successbrian_os.pm_steps "
            "WHERE status IN ('queued','failed','running','held_brian')")
        return {"repair_open": len(rows),
                "repair_buckets": _age_buckets(dates, today),
                "repair_oldest": [
                    {"id": r[0], "title": (r[1] or "")[:90],
                     "status": r[2],
                     "age_d": (today - r[3].date()).days}
                    for r in rows[:8]],
                "all_open_steps": total_open,
                "note": "per Brian's lifecycle law a 'failed' step is "
                        "an attempt record, not a resting state; "
                        "repair steps not done/cancelled are the "
                        "aging set"}

    rep["decisions_waiting"] = _attempt(cov, "aging:decisions",
                                         decisions)
    rep["captures"] = _attempt(cov, "aging:captures", captures)
    rep["issues_blocked_brian"] = _attempt(cov, "aging:blocked",
                                            blocked)
    rep["pm_steps"] = _attempt(cov, "aging:pm_steps", steps)
    parked = []
    for p in PARKED_REGISTRY:
        since = p.get("parked_since")
        age = (today - date.fromisoformat(since)).days if since else None
        parked.append({**p, "age_d": age})
    rep["parked_registry"] = parked
    return rep


def aging_text(rep):
    L = ["AGING — the slow-debt report"]
    d = rep.get("decisions_waiting") or {}
    L.append(f"  decisions waiting on Brian: {d.get('count')} "
             f"(buckets {d.get('buckets')})")
    for o in d.get("oldest") or []:
        L.append(f"  - decision #{o['id']} age {o['age_d']}d: {o['item']}")
    c = rep.get("captures") or {}
    L.append(f"  captures: raw {c.get('raw_count')} (oldest "
             f"{c.get('raw_oldest_age_d')}d); triaged-unruled >14d: "
             f"{c.get('triaged_unruled_over_14d')}")
    b = rep.get("issues_blocked_brian") or {}
    L.append(f"  issues blocked on Brian (altair): {b.get('count')} "
             f"(oldest {b.get('oldest_age_d')}d)")
    s = rep.get("pm_steps") or {}
    L.append(f"  PM repair steps open: {s.get('repair_open')} "
             f"(buckets {s.get('repair_buckets')}); all open steps: "
             f"{s.get('all_open_steps')}")
    for o in s.get("repair_oldest") or []:
        L.append(f"  - repair step #{o['id']} age {o['age_d']}d "
                 f"[{o['status']}]: {o['title']}")
    L.append("  parked registry (hand-seeded, each row source-cited):")
    for p in rep["parked_registry"]:
        L.append(f"  - [{p['age_d']}d] {p['item']}")
        L.append(f"    source: {p['source']}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 4. MONEY — budgets vs the build table. Prices are Postgres state.
# A need with no matching cap reads "no cap set" — never "no limit".
# ---------------------------------------------------------------------------
def money_report():
    today = R.now_ct().date()
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "coverage": cov}

    def budgets():
        out = {"project_budgets": [], "dealsdesk_budgets": []}
        for r in pg_rows(
                "SELECT project_ref, budget_name, allocated, spent, "
                "period_start, period_end, status FROM "
                "successbrian_os.project_budgets ORDER BY id"):
            alloc, spent = _num(r[2]) or 0.0, _num(r[3]) or 0.0
            out["project_budgets"].append({
                "project": r[0], "name": r[1], "allocated": alloc,
                "spent": spent, "remaining": round(alloc - spent, 2),
                "period": f"{r[4]}..{r[5]}",
                "period_state": "lapsed" if r[5] and r[5] < today
                else "current", "status": r[6]})
        for r in pg_rows(
                "SELECT name, amount, period_start, period_end, "
                "category FROM dealsdesk.budgets ORDER BY id"):
            out["dealsdesk_budgets"].append({
                "name": r[0], "amount": _num(r[1]),
                "period": f"{r[2]}..{r[3]}",
                "period_state": "lapsed" if r[3] and r[3] < today
                else "current", "category": r[4]})
        return out

    def builds():
        rows = pg_rows(
            "SELECT status, count(*), sum(estimated_cost), sum(spent) "
            "FROM dealsdesk.builds GROUP BY status ORDER BY status")
        recent = pg_rows(
            "SELECT id, name, spent, updated_at FROM dealsdesk.builds "
            "WHERE spent > 0 AND updated_at > now() - interval '7 days' "
            "ORDER BY updated_at DESC LIMIT 10")
        return {"by_status": [
                    {"status": r[0], "builds": r[1],
                     "estimated_total": _num(r[2]),
                     "spent_total": _num(r[3])} for r in rows],
                "dated_activity_last_7d": [
                    {"build": r[1], "spent": _num(r[2]),
                     "updated_at": r[3].isoformat()} for r in recent],
                "dated_activity_note": "build rows carry no spend-date "
                "column; last-7d activity is builds with spent > 0 "
                "whose record was updated in the last 7 days (dated "
                "by record update, labeled as such)"}

    def items():
        rows = pg_rows(
            "SELECT item_status, count(*), sum(price_ea * quantity) "
            "FROM dealsdesk.build_items GROUP BY item_status")
        bought = {"in_hand"}
        queued, inhand = [], []
        for r in rows:
            entry = {"status": r[0], "items": r[1], "total": _num(r[2])}
            (inhand if r[0] in bought else queued).append(entry)
        needs = pg_rows(
            "SELECT id, subject, target_buy_price, qty_needed, "
            "qty_filled, status FROM dealsdesk.ecosystem_needs "
            "WHERE status = 'open' ORDER BY id")
        return {"queued_by_status": queued, "in_hand": inhand,
                "queued_total": round(sum(e["total"] or 0
                                           for e in queued), 2),
                "open_needs": [
                    {"id": r[0], "subject": r[1],
                     "cap_price_each": _num(r[2]),
                     "cap_label": (f"cap ${ _num(r[2]) }" if r[2]
                                   else "no cap set"),
                     "qty_needed": r[3], "qty_filled": r[4]}
                    for r in needs],
                "cap_note": "queued build items are covered by "
                "project budgets only where a budget's period is "
                "current; every budget period on record has lapsed "
                "(see budgets), so the queued total currently stands "
                "against no live cap. Open needs carry their own "
                "per-item caps where set; a need without one reads "
                "'no cap set'."}

    rep["budgets"] = _attempt(cov, "money:budgets", budgets)
    rep["builds"] = _attempt(cov, "money:builds", builds)
    rep["items"] = _attempt(cov, "money:items", items)
    rep["coverage_gaps"] = [
        "quick-$1,000 track: data home exists on alpha "
        "(successbrian_os.monthly_goals 'quick-1000', ruled "
        "2026-10-29; actuals home goal_month_scores) but no spend "
        "or revenue actuals are recorded yet (see pace) — money "
        "state = no-data."]
    return rep


def money_text(rep):
    L = ["MONEY — budgets vs the build table (Postgres state)"]
    b = rep.get("budgets") or {}
    for x in b.get("project_budgets") or []:
        L.append(f"  budget [{x['period_state']}] {x['name']} "
                 f"({x['project']}): allocated ${x['allocated']}, "
                 f"spent ${x['spent']}, remaining ${x['remaining']}, "
                 f"period {x['period']}")
    for x in b.get("dealsdesk_budgets") or []:
        L.append(f"  budget [{x['period_state']}] {x['name']}: "
                 f"${x['amount']}, period {x['period']}")
    bd = rep.get("builds") or {}
    for x in bd.get("by_status") or []:
        L.append(f"  builds [{x['status']}]: {x['builds']} builds, "
                 f"estimated ${x['estimated_total']}, spent "
                 f"${x['spent_total']}")
    for x in bd.get("dated_activity_last_7d") or []:
        L.append(f"  - spend-carrying build updated last 7d: "
                 f"{x['build']} (spent ${x['spent']}, {x['updated_at']})")
    it = rep.get("items") or {}
    for x in it.get("queued_by_status") or []:
        tot = f"${x['total']}" if x["total"] is not None else \
            "not priced"
        L.append(f"  build items [{x['status']}]: {x['items']} items, "
                 f"{tot}")
    L.append(f"  queued items total: ${it.get('queued_total')}")
    for n in it.get("open_needs") or []:
        qn = n["qty_needed"] if n["qty_needed"] is not None else \
            "not recorded"
        L.append(f"  open need #{n['id']}: {n['subject']} — "
                 f"{n['cap_label']} each, qty {n['qty_filled']}/"
                 f"{qn} filled")
    if it.get("cap_note"):
        L.append(f"  note: {it['cap_note']}")
    for gap in rep.get("coverage_gaps") or []:
        L.append(f"  GAP: {gap}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 5. HEALTH WEEK — health_log aggregation, DATA ONLY.
# This instrument emits recorded facts and counts. It carries no
# evaluative language about the data (selftest scans for it).
# ---------------------------------------------------------------------------
HEALTH_BANNED = ["should", "recommend", "target", "aim for", "advice",
                 "try to", "ought to", "need to", "must "]


def health_week():
    today = R.now_ct().date()
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "coverage": cov}

    def last7():
        rows = pg_rows(
            "SELECT metric, value, unit, reading_date, reported_date, "
            "source FROM successbrian_os.health_log "
            "WHERE reported_date > CURRENT_DATE - 7 "
            "OR reading_date > CURRENT_DATE - 7 ORDER BY metric, "
            "reported_date")
        by = {}
        for r in rows:
            by.setdefault(r[0], []).append({
                "value": _num(r[1]), "unit": r[2],
                "reading_date": r[3].isoformat() if r[3] else None,
                "reported_date": r[4].isoformat() if r[4] else None,
                "source": r[5]})
        return {"window_days": 7, "entries_by_metric": by,
                "entry_count": len(rows)}

    def a1c():
        rows = pg_rows(
            "SELECT value, unit, reading_date, reported_date, source "
            "FROM successbrian_os.health_log WHERE metric = 'a1c' "
            "ORDER BY reported_date, id")
        return [{"value": _num(r[0]), "unit": r[1],
                 "reading_date": r[2].isoformat() if r[2]
                 else "not recorded",
                 "reported_date": r[3].isoformat() if r[3] else None,
                 "source": r[4]} for r in rows]

    def zepbound():
        rows = pg_rows(
            "SELECT value, unit, reading_date, reported_date "
            "FROM successbrian_os.health_log "
            "WHERE metric ILIKE '%zepbound%' ORDER BY reported_date, id")
        hist = {}
        dated = 0
        for r in rows:
            if r[2]:
                dated += 1
                wd = r[2].strftime("%A")
                hist[wd] = hist.get(wd, 0) + 1
        return {"dose_rows": [{"value": _num(r[0]), "unit": r[1],
                               "reading_date": r[2].isoformat()
                               if r[2] else None,
                               "reported_date": r[3].isoformat()
                               if r[3] else None} for r in rows],
                "dated_entries_by_weekday": hist,
                "dated_entry_count": dated,
                "coverage_note": "weekday pattern is computed from "
                "dated entries only; rows without a reading date "
                "cannot be placed on a weekday"}

    def movement():
        n = pg_one(
            "SELECT count(*) FROM successbrian_os.health_log WHERE "
            "metric ILIKE '%walk%' OR metric ILIKE '%step%' OR "
            "metric ILIKE '%movement%' OR metric ILIKE '%exercise%'")
        return {"movement_entries_total": n,
                "coverage_note": "count is over all health_log rows "
                "ever recorded with a movement-shaped metric name"}

    rep["last_7_days"] = _attempt(cov, "health:last7", last7)
    rep["a1c_series"] = _attempt(cov, "health:a1c", a1c)
    rep["zepbound"] = _attempt(cov, "health:zepbound", zepbound)
    rep["movement"] = _attempt(cov, "health:movement", movement)
    return rep


def health_text(rep):
    L = ["HEALTH WEEK — recorded entries from health_log (data only)"]
    l7 = rep.get("last_7_days") or {}
    L.append(f"  entries in the last 7 days: {l7.get('entry_count')}")
    for metric, entries in (l7.get("entries_by_metric") or {}).items():
        for e in entries:
            L.append(f"  - {metric}: {e['value']} {e['unit']} "
                     f"(reading {e['reading_date'] or 'not recorded'}"
                     f", reported {e['reported_date']}, source "
                     f"{e['source']})")
    L.append("  A1C series (all recorded rows):")
    for e in rep.get("a1c_series") or []:
        L.append(f"  - {e['value']} {e['unit']} (reading date: "
                 f"{e['reading_date']}, reported {e['reported_date']}, "
                 f"source {e['source']})")
    z = rep.get("zepbound") or {}
    for e in z.get("dose_rows") or []:
        L.append(f"  dose row: {e['value']} {e['unit']} (reading date: "
                 f"{e['reading_date'] or 'not recorded'}, reported "
                 f"{e['reported_date']})")
    L.append(f"  dated dose entries by weekday: "
             f"{z.get('dated_entries_by_weekday')} "
             f"({z.get('dated_entry_count')} dated entries)")
    L.append(f"  note: {z.get('coverage_note', '')}")
    mv = rep.get("movement") or {}
    L.append(f"  movement-shaped entries in health_log (all time): "
             f"{mv.get('movement_entries_total')}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


def health_language_clean(text):
    low = " " + text.lower() + " "
    return [w for w in HEALTH_BANNED if w in low]


# ---------------------------------------------------------------------------
# 6. CONTENT CHAIN — weekly movement visits -> contacts -> revenue.
# Dry tributaries are reported dry (known gaps, named).
# ---------------------------------------------------------------------------
def content_chain():
    today = R.now_ct().date()
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "coverage": cov}

    def scorecards():
        rows = pg_rows(
            "SELECT blog_slug, period_start, period_end, "
            "unique_visits, pageviews, contacts_captured, "
            "revenue_cents FROM campaignsdesk.blog_scorecards "
            "ORDER BY blog_slug")
        out = []
        for r in rows:
            out.append({
                "blog": r[0], "period": f"{r[1]}..{r[2]}",
                "visits": r[3] if r[3] is not None else "dry — not "
                          "recorded",
                "pageviews": r[4],
                "contacts": r[5] if r[5] is not None else "dry — not "
                            "recorded",
                "revenue_cents": r[6] if r[6] is not None else
                "dry — not recorded"})
        return {"scorecards": out,
                "note": "scorecard fields left empty in the record "
                        "are reported dry; no new scorecard has been "
                        "written since 2026-10-29"}

    def reach():
        def sums(lo, hi):
            rows = pg_rows(
                "SELECT platform, metric, sum(value) FROM "
                "successbrian_os.reach_daily_activity "
                "WHERE day_date > %s AND day_date <= %s "
                "AND is_measured AND value IS NOT NULL "
                "AND metric <> 'post_views_total' "
                "GROUP BY platform, metric ORDER BY 1, 2", (lo, hi))
            out = {f"{r[0]}/{r[1]}": _num(r[2]) for r in rows}
            tot = pg_one(
                "SELECT value FROM "
                "successbrian_os.reach_daily_activity "
                "WHERE platform='blog' AND metric='post_views_total' "
                "AND day_date > %s AND day_date <= %s "
                "ORDER BY day_date DESC LIMIT 1", (lo, hi))
            if tot is not None:
                out["blog/post_views_total (latest in window)"] = \
                    _num(tot)
            return out
        dark = pg_one(
            "SELECT count(*) FROM successbrian_os.reach_daily_activity "
            "WHERE day_date > %s AND day_date <= %s "
            "AND NOT is_measured", (today - timedelta(days=7), today))
        latest_views = pg_one(
            "SELECT value FROM successbrian_os.reach_daily_activity "
            "WHERE platform='blog' AND metric='post_views_total' "
            "ORDER BY day_date DESC LIMIT 1")
        return {"this_week": sums(today - timedelta(days=7), today),
                "last_week": sums(today - timedelta(days=14),
                                  today - timedelta(days=7)),
                "unmeasured_rows_this_week": dark,
                "blog_post_views_total_latest": _num(latest_views),
                "note": "unmeasured rows are dark-with-reason rows "
                        "(sources the fleet cannot read yet), counted "
                        "not hidden"}

    def clicks():
        if not pg_one("SELECT to_regclass('campaignsdesk."
                      "outbound_clicks')"):
            raise RuntimeError("outbound_clicks table not present")
        tw = pg_one(
            "SELECT count(*) FROM campaignsdesk.outbound_clicks "
            "WHERE clicked_at > now() - interval '7 days'")
        lw = pg_one(
            "SELECT count(*) FROM campaignsdesk.outbound_clicks "
            "WHERE clicked_at > now() - interval '14 days' "
            "AND clicked_at <= now() - interval '7 days'")
        return {"tracked_link_clicks_this_week": tw,
                "tracked_link_clicks_last_week": lw}

    def stages():
        rows = pg_rows(
            "SELECT ramp_stage, status, count(*) FROM "
            "campaignsdesk.blogs GROUP BY 1, 2 ORDER BY 1, 2")
        live = pg_rows(
            "SELECT slug, ramp_stage FROM campaignsdesk.blogs "
            "WHERE status = 'live' ORDER BY slug")
        return {"distribution": [
                    {"ramp_stage": r[0], "status": r[1], "blogs": r[2]}
                    for r in rows],
                "live_blogs": [{"slug": r[0], "ramp_stage": r[1]}
                               for r in live]}

    rep["scorecards"] = _attempt(cov, "content:scorecards", scorecards)
    rep["reach"] = _attempt(cov, "content:reach", reach)
    rep["clicks"] = _attempt(cov, "content:clicks", clicks)
    rep["ramp_stages"] = _attempt(cov, "content:stages", stages)
    return rep


def content_text(rep):
    L = ["CONTENT CHAIN — visits -> contacts -> revenue, weekly"]
    sc = rep.get("scorecards") or {}
    for s in sc.get("scorecards") or []:
        L.append(f"  {s['blog']} ({s['period']}): visits {s['visits']}, "
                 f"pageviews {s['pageviews']}, contacts {s['contacts']}, "
                 f"revenue_cents {s['revenue_cents']}")
    L.append(f"  note: {sc.get('note', '')}")
    rc = rep.get("reach") or {}
    L.append(f"  reach this week (measured): {rc.get('this_week')}")
    L.append(f"  reach last week (measured): {rc.get('last_week')}")
    L.append(f"  blog post views total (latest daily row): "
             f"{rc.get('blog_post_views_total_latest')}; unmeasured "
             f"rows this week: {rc.get('unmeasured_rows_this_week')}")
    ck = rep.get("clicks") or {}
    L.append(f"  tracked-link clicks: this week "
             f"{ck.get('tracked_link_clicks_this_week')}, last week "
             f"{ck.get('tracked_link_clicks_last_week')}")
    st = rep.get("ramp_stages") or {}
    L.append(f"  ramp stages: {st.get('distribution')}")
    L.append(f"  live blogs: {st.get('live_blogs')}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 7. AGENDA — the week's priorities as data. Seeded EMPTY by design:
# the first real agenda is set by the first Saturday run.
# ---------------------------------------------------------------------------
def agenda_set(week_of, items):
    """items: list of (priority, source, why), 1..3 entries."""
    ensure_horizon_tables()
    if not (1 <= len(items) <= 3):
        raise ValueError("an agenda holds 1 to 3 priorities")
    pg_exec("DELETE FROM successbrian_os.review_agenda "
            "WHERE week_of = %s", (week_of,))
    ids = []
    for i, (prio, source, why) in enumerate(items, start=1):
        row = pg_rows(
            "INSERT INTO successbrian_os.review_agenda "
            "(week_of, slot, priority, source, why) VALUES "
            "(%s, %s, %s, %s, %s) RETURNING id",
            (week_of, i, prio, source, why))
        ids.append(row[0][0])
    return ids


def agenda_list():
    ensure_horizon_tables()
    weeks = pg_rows(
        "SELECT DISTINCT week_of FROM successbrian_os.review_agenda "
        "ORDER BY week_of DESC LIMIT 2")
    out = {"weeks": []}
    for (wk,) in weeks:
        rows = pg_rows(
            "SELECT id, slot, priority, source, why, state, "
            "state_note FROM successbrian_os.review_agenda "
            "WHERE week_of = %s ORDER BY slot", (wk,))
        out["weeks"].append({
            "week_of": wk.isoformat(),
            "priorities": [
                {"id": r[0], "slot": r[1], "priority": r[2],
                 "source": r[3], "why": r[4], "state": r[5],
                 "state_note": r[6]} for r in rows]})
    if not weeks:
        out["note"] = ("agenda table is empty — the first agenda is "
                       "set by the first Saturday horizon run")
    return out


def agenda_mark(agenda_id, state, note=None):
    ensure_horizon_tables()
    pg_exec("UPDATE successbrian_os.review_agenda SET state = %s, "
            "state_note = %s, updated_at = now() WHERE id = %s",
            (state, note, agenda_id))


def agenda_text(rep):
    L = ["AGENDA — the week's priorities (data for the daily passes)"]
    if rep.get("note"):
        L.append(f"  {rep['note']}")
    for w in rep.get("weeks") or []:
        L.append(f"  week of {w['week_of']}:")
        for p in w["priorities"]:
            L.append(f"  - #{p['id']} [{p['state']}] {p['priority']}")
            L.append(f"    source: {p['source']}; why: {p['why']}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 8. BUILD VERIFICATION — did the week's builds really improve things?
# (Brian's charter addition, 2026-11-09 23:30 CST.) Machine verdict per
# build over evidence: improved / unchanged / regressed / unverifiable.
# ---------------------------------------------------------------------------
BUILD_GAUGE_MAP = {
    "clerk-filing-flow-repair": ["unsorted_docs", "unindexed_docs",
                                 "raw_backlog"],
    "intel-harness": ["market_pricing_age_h"],
    "scrape-watch-migration": ["market_pricing_age_h"],
}
_BUILD_TITLE_WORDS = ("built", "build", "repair", "complete",
                      "landed", "shipped", "fixed")


def _latest_check_evidence(check_ids):
    """Latest recorded run status per check id (qa_runs), falling back
    to the check row's last_status."""
    ev = {}
    if not check_ids:
        return ev
    rows = pg_rows(
        "SELECT DISTINCT ON (check_id) check_id, status FROM "
        "successbrian_os.pm_project_qa_runs "
        "WHERE check_id = ANY(%s) ORDER BY check_id, ran_at DESC",
        (list(check_ids),))
    for cid, status in rows:
        ev[cid] = status
    return ev


def build_verify(days=7, persist=False, add_frictions=False):
    ensure_horizon_tables()
    cov = []
    rep = {"taken_at": datetime.now(timezone.utc).isoformat(),
           "window_days": days, "coverage": cov, "builds": []}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rep["window_start"] = since.isoformat()

    def enumerate_builds():
        projects = {}
        for r in pg_rows(
                "SELECT project_key, title, description, created_at "
                "FROM successbrian_os.pm_projects "
                "WHERE created_at > %s ORDER BY created_at", (since,)):
            projects[r[0]] = {"project_key": r[0], "title": r[1],
                              "description": (r[2] or "")[:300],
                              "registered_at": r[3].isoformat(),
                              "origin": "project registered in window"}
        for r in pg_rows(
                "SELECT DISTINCT project_key FROM "
                "successbrian_os.pm_project_checks "
                "WHERE created_at > %s", (since,)):
            if r[0] not in projects:
                meta = pg_rows(
                    "SELECT title, description, created_at FROM "
                    "successbrian_os.pm_projects WHERE project_key = %s",
                    (r[0],))
                if meta:
                    projects[r[0]] = {
                        "project_key": r[0], "title": meta[0][0],
                        "description": (meta[0][1] or "")[:300],
                        "registered_at": meta[0][2].isoformat(),
                        "origin": "checks registered in window "
                                  "(project predates window)"}
        return projects

    def captures_for(project_key):
        tokens = [t for t in re.split(r"[-_]", project_key) if len(t) > 3]
        rows = pg_rows(
            "SELECT id, title, created_at FROM "
            "atlas.scattered_captures WHERE created_at > %s "
            "ORDER BY created_at", (since,))
        hits = []
        for cid, title, _ca in rows:
            low = (title or "").lower()
            if any(t in low for t in tokens) and \
                    any(w in low for w in _BUILD_TITLE_WORDS):
                hits.append({"capture_id": cid, "title": title[:110]})
        return hits[:4]

    def git_evidence():
        out = {}
        for name, path in [("successbrian-os",
                            os.path.expanduser("~/successbrian-os")),
                           ("campaignsdesk",
                            os.path.expanduser("~/campaignsdesk")),
                           ("dealsdesk", "/home/dealsdesk")]:
            try:
                r = subprocess.run(
                    ["git", "-C", path, "log",
                     f"--since={days} days ago", "--format=%h %s"],
                    capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or "")[:120])
                lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
                out[name] = {"commits_in_window": len(lines),
                             "subjects": lines[:6]}
            except Exception as e:  # noqa: BLE001
                out[name] = {"commits_in_window": None,
                             "note": f"{type(e).__name__}: "
                                     f"{str(e)[:120]}"}
        return out

    projects = _attempt(cov, "buildverify:enumerate", enumerate_builds)
    rep["git"] = _attempt(cov, "buildverify:git", git_evidence)
    snaps = pg_rows(
        "SELECT taken_at, gauges FROM successbrian_os.review_snapshots "
        "ORDER BY taken_at")
    snap_series = []
    for taken_at, g in snaps:
        gv = g if isinstance(g, dict) else json.loads(g)
        snap_series.append((taken_at, gv.get("values") or {}))
    live = None
    try:
        live = R.collect_gauges()["values"]
    except Exception:  # noqa: BLE001
        live = None

    for key, proj in (projects or {}).items():
        entry = {**proj, "evidence": []}
        checks = pg_rows(
            "SELECT id, check_key, check_type, last_status, created_at "
            "FROM successbrian_os.pm_project_checks "
            "WHERE project_key = %s AND enabled ORDER BY id", (key,))
        entry["checks_total"] = len(checks)
        ev = _latest_check_evidence([c[0] for c in checks])
        failing, passing, norun, judgment_open = [], [], [], []
        for cid, ckey, ctype, last_status, _c in checks:
            status = ev.get(cid, last_status)
            if ctype == "judgment":
                if status != "pass":
                    judgment_open.append(ckey)
                else:
                    passing.append(ckey)
            elif status == "fail":
                failing.append(ckey)
            elif status == "pass":
                passing.append(ckey)
            else:
                norun.append(ckey)
        entry["qa"] = {"passing": passing, "failing": failing,
                       "no_run_yet": norun,
                       "judgment_open": judgment_open}
        entry["evidence"].append(
            f"QA now: {len(passing)} passing, {len(failing)} failing, "
            f"{len(norun)} with no recorded run, {len(judgment_open)} "
            f"judgment checks open")
        if failing:
            entry["evidence"].append(
                "failing checks: " + ", ".join(failing))
        caps = captures_for(key)
        if caps:
            entry["claim_captures"] = caps
            entry["evidence"].append(
                "build captures: " + "; ".join(
                    f"#{c['capture_id']} {c['title']}" for c in caps))
        # gauge bracket
        gauge_moves = []
        mapped = BUILD_GAUGE_MAP.get(key, [])
        build_done = None
        if checks:
            build_done = max(c[4] for c in checks)
        for gname in mapped:
            before = None
            for taken_at, vals in snap_series:
                if build_done and taken_at <= build_done:
                    before = vals.get(gname)
            after = live.get(gname) if live else None
            if before is not None and after is not None \
                    and before != after:
                if gname in R.LOWER_BETTER:
                    word = "improved" if after < before else "worsened"
                elif gname in R.HIGHER_BETTER:
                    word = "improved" if after > before else "worsened"
                else:
                    word = "changed"
                gauge_moves.append({"gauge": gname, "before": before,
                                    "after": after, "direction": word})
                entry["evidence"].append(
                    f"gauge {gname}: {before} -> {after} ({word}; "
                    f"before = last snapshot at/before registration, "
                    f"after = live gauges at verify time)")
        entry["gauge_moves"] = gauge_moves
        # verdict rules, in order
        if failing:
            entry["verdict"] = "regressed"
            entry["verdict_reason"] = (
                "the build's own QA checks are failing now: "
                + ", ".join(failing))
        elif any(m["direction"] == "worsened" for m in gauge_moves):
            entry["verdict"] = "regressed"
            entry["verdict_reason"] = "a mapped gauge moved adversely"
        elif any(m["direction"] == "improved" for m in gauge_moves):
            entry["verdict"] = "improved"
            entry["verdict_reason"] = "mapped gauge(s) moved " \
                                      "favorably over the build"
        elif checks and passing and not norun:
            entry["verdict"] = "improved"
            entry["verdict_reason"] = (
                "verified by its own QA: every check has a recorded "
                "passing run; no gauge bracket exists yet (snapshot "
                "history is thin), so the basis is QA evidence only")
        elif checks and passing:
            entry["verdict"] = "unverifiable"
            entry["verdict_reason"] = (
                "some checks pass on recorded runs but "
                f"{len(norun)} check(s) have no recorded run yet — "
                "the runner has not produced evidence for the whole "
                "build")
        elif checks:
            entry["verdict"] = "unverifiable"
            entry["verdict_reason"] = (
                "QA checks are registered but the runner has not "
                "produced a run for them yet — no evidence either way")
        else:
            entry["verdict"] = "unverifiable"
            entry["verdict_reason"] = "no QA checks registered for " \
                                      "this build"
        if judgment_open:
            entry["evidence"].append(
                "judgment checks open (awaiting ruling or by design): "
                + ", ".join(judgment_open[:6]))
        rep["builds"].append(entry)

    rep["builds"].sort(key=lambda b: b["project_key"])
    counts = {}
    for b in rep["builds"]:
        counts[b["verdict"]] = counts.get(b["verdict"], 0) + 1
    rep["verdict_counts"] = counts

    if persist:
        ids = []
        for b in rep["builds"]:
            row = pg_rows(
                "INSERT INTO successbrian_os.review_build_verdicts "
                "(window_start, build_ref, project_key, claim, "
                "verdict, evidence) VALUES (%s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (rep["window_start"], b["project_key"], b["project_key"],
                 (b.get("title") or "")[:300], b["verdict"],
                 json.dumps(b, default=str)))
            ids.append(row[0][0])
        rep["persisted_verdict_ids"] = ids
    if add_frictions:
        added = []
        R.ensure_tables()
        for b in rep["builds"]:
            if b["verdict"] in ("regressed",):
                row = pg_rows(
                    "INSERT INTO successbrian_os.review_frictions "
                    "(source, description, lane, state) VALUES "
                    "(%s, %s, 2, 'open') RETURNING id",
                    ("build-verify",
                     f"build verification: {b['project_key']} "
                     f"verdict regressed — {b['verdict_reason']}",
                     ))
                added.append(row[0][0])
        rep["frictions_added"] = added
    return rep


def build_verify_text(rep):
    L = [f"BUILD VERIFICATION — builds/fixes of the last "
         f"{rep['window_days']} days, verified against QA + gauges"]
    L.append(f"  verdict counts: {rep.get('verdict_counts')}")
    for name, g in (rep.get("git") or {}).items():
        L.append(f"  git {name}: {g.get('commits_in_window')} commits "
                 f"in window" + (f" ({g['note']})" if g.get("note")
                                  else ""))
    for b in rep["builds"]:
        L.append(f"  [{b['verdict']}] {b['project_key']} — "
                 f"{b.get('title', '')[:80]}")
        L.append(f"    reason: {b['verdict_reason']}")
        for e in b["evidence"]:
            L.append(f"    evidence: {e}")
    if rep.get("persisted_verdict_ids"):
        L.append(f"  persisted verdict rows: "
                 f"{rep['persisted_verdict_ids']}")
    for c in rep["coverage"]:
        if not c["ok"]:
            L.append(f"  GAP source {c['source']}: {c.get('note', '')}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 9. WEEK BRIEFING ASSEMBLER — the Saturday skeleton, numbers filled,
# judgment slots marked. Same discipline as the daily assembler.
# ---------------------------------------------------------------------------
def render_week_briefing():
    pace = pace_report()
    trend = trend_report()
    aging = aging_report()
    money = money_report()
    health = health_week()
    content = content_chain()
    builds = build_verify(days=7)
    agenda = agenda_list()
    waiting = pg_rows(
        "SELECT id, item, first_surfaced FROM "
        "successbrian_os.review_decisions WHERE state='waiting' "
        "ORDER BY first_surfaced, id") if R._table_exists(
            "review_decisions") else []
    L = [f"WEEKEND HORIZON CHECK — {R.now_ct().date().isoformat()} "
         f"(Saturday 04:00 run; briefing waits for Brian)"]
    L.append("\nTHE WEEK ON THE GOALS")
    L.append(pace_text(pace))
    L.append("  [JUDGMENT: did the week's work serve the goals, or "
             "scatter? Say it plainly, in loving words]")
    L.append("\nMONEY")
    L.append(money_text(money))
    L.append("\nSYSTEMS")
    L.append(trend_text(trend))
    L.append(aging_text(aging))
    L.append(build_verify_text(builds))
    L.append("\nCONTENT")
    L.append(content_text(content))
    L.append("\nHEALTH")
    L.append(health_text(health))
    L.append("\nTHE WEEK'S AGENDA")
    L.append(agenda_text(agenda))
    L.append("  [JUDGMENT: set at most three priorities for the "
             "coming week via agenda-set, each with source + why]")
    L.append("\nDONE THIS PASS")
    L.append("  [JUDGMENT: lane-1 actions taken, with QA "
             "registrations]")
    L.append("\nWAITING ON BRIAN")
    if waiting:
        for w in waiting:
            L.append(f"  #{w[0]} {w[1]} (waiting since {w[2]})")
        L.append("  [JUDGMENT: present the single most important "
                 "one, with context + numbers]")
    else:
        L.append("  none waiting.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Selftest — pure logic + live read-only probes + agenda round-trip on
# a throwaway week (cleaned up). Includes the health-language scan.
# ---------------------------------------------------------------------------
def horizon_selftest():
    ok = []

    def check(name, cond):
        ok.append(bool(cond))
        print(f"  {'PASS' if cond else 'FAIL'} {name}")

    print("SELFTEST horizon layer")
    # pace math on the live GotBackup row (read-only)
    try:
        rep = pace_report()
        gb = [g for g in rep["goals"]
              if "GotBackup" in (g.get("goal") or "")]
        check("pace finds GotBackup monthly target",
              bool(gb) and gb[0].get("target_per_month") == 40.0)
        check("pace never verdicts off a never-updated counter",
              bool(gb) and gb[0].get("verdict") != "slipping")
        lad = rep.get("ladder") or {}
        rungs = lad.get("rungs") or []
        check("pace reads the GotBackup dollar ladder as data",
              len(rungs) == 4
              and rungs[0]["target_monthly_usd"] == 1250.0
              and rungs[-1]["target_monthly_usd"] == 3250.0)
        sc_gb = [g for g in rep["goals"]
                 if g.get("goal_key") == "gotbackup-40"]
        check("pace scorecard carries GotBackup from goal_month_scores",
              bool(sc_gb))
        sc_q = [g for g in rep["goals"]
                if g.get("goal_key") == "quick-1000"]
        check("pace carries the quick-$1,000 track from its data home",
              bool(sc_q))
        check("pace reports coverage gaps",
              len(rep["coverage_gaps"]) >= 1)
    except Exception as ex:  # noqa: BLE001
        check(f"pace runs ({ex})", False)
    # trend honesty on thin history
    try:
        rep = trend_report()
        s = rep.get("snapshots") or {}
        check("trend labels thin history honestly",
              s.get("week_over_week") in ("accumulating", "computable"))
    except Exception as ex:  # noqa: BLE001
        check(f"trend runs ({ex})", False)
    # aging buckets math (pure)
    t = date(2026, 11, 9)
    b = _age_buckets([date(2026, 11, 9), date(2026, 11, 1),
                      date(2026, 10, 1)], t)
    check("age buckets", b == {"0_6d": 1, "7_13d": 1, "14d_plus": 1})
    # health language scan — the instrument's own output must be clean
    try:
        rep = health_week()
        txt = health_text(rep) + json.dumps(rep, default=str)
        bad = health_language_clean(txt)
        check(f"health output carries no advice/target phrasing "
              f"(found: {bad})", not bad)
        check("health emits the A1C series",
              len(rep.get("a1c_series") or []) >= 3)
    except Exception as ex:  # noqa: BLE001
        check(f"health runs ({ex})", False)
    # agenda round-trip on a throwaway week, cleaned up
    try:
        ensure_horizon_tables()
        wk = date(2099, 1, 2)
        ids = agenda_set(wk, [("selftest priority", "selftest",
                               "round-trip probe")])
        lst = agenda_list()
        mine = [w for w in lst["weeks"]
                if w["week_of"] == wk.isoformat()]
        agenda_mark(ids[0], "done", "selftest cleanup")
        row = pg_one("SELECT state FROM successbrian_os.review_agenda "
                     "WHERE id = %s", (ids[0],))
        pg_exec("DELETE FROM successbrian_os.review_agenda "
                "WHERE week_of = %s", (wk,))
        check("agenda round-trip",
              bool(mine) and row == "done")
    except Exception as ex:  # noqa: BLE001
        check(f"agenda round-trip ({ex})", False)
    # build verification runs and every verdict carries a reason
    try:
        rep = build_verify(days=7)
        check("build-verify enumerates builds",
              len(rep["builds"]) >= 5)
        check("every verdict has evidence + reason",
              all(b.get("evidence") and b.get("verdict_reason")
                  for b in rep["builds"]))
    except Exception as ex:  # noqa: BLE001
        check(f"build-verify runs ({ex})", False)
    # week briefing renders all charter groups
    try:
        txt = render_week_briefing()
        check("week briefing renders charter groups",
              all(h in txt for h in
                  ["THE WEEK ON THE GOALS", "MONEY", "SYSTEMS",
                   "CONTENT", "HEALTH", "THE WEEK'S AGENDA",
                   "DONE THIS PASS", "WAITING ON BRIAN"]))
    except Exception as ex:  # noqa: BLE001
        check(f"week briefing renders ({ex})", False)
    print(f"selftest horizon: {sum(ok)}/{len(ok)}")
    return 0 if all(ok) else 1


# ---------------------------------------------------------------------------
# 10. ATLAS / GOAL-COHERENCE AUDIT (the Deep Look, Brian 2026-11-09 23:29 +
#     23:37 + 23:38 CST) — is Atlas driving the goals, is the system
#     working together on them, and is it working the highest priorities
#     first, efficiently, week to week and day to day?
#     (a) goal linkage census (b) Atlas flow (c) orphan machinery census
#     (d) handoff stalls (e) priority discipline: agenda completion,
#     queue-age vs priority inversions (CANDIDATES, never verdicts),
#     week's motion by goal. Census persists to review_coherence.
# ---------------------------------------------------------------------------

# Goal -> Atlas linkage map. Sources: sbos_goals rows (goal_slug) for the
# goal side; the anchor node keys were read live from atlas.nodes on
# 2026-11-09 (plan:gotbackup-40-monthly, launch:mindell-olive-oil-bible,
# launch:trafficstreemz-30, proj:oliabo, launch:contactflowcrm-saas all
# exist). Tokens are matched against node_key and name (lowercased).
GOAL_LINKS = [
    {"goal": "GotBackup: 40 signups/month",
     "source": "sbos_goals goal_slug gotbackup-40-per-month",
     "tokens": ["gotbackup", "gb40"],
     "anchors": ["plan:gotbackup-40-monthly", "plan:gb40-cycle-2026-11"]},
    {"goal": "TrafficStreemz Revenue",
     "source": "sbos_goals (target_date 2027-03-01)",
     "tokens": ["trafficstreemz"],
     "anchors": ["launch:trafficstreemz-30"]},
    {"goal": "Oliabo MLM to $5k/mo",
     "source": "sbos_goals (target_date 2026-12-01)",
     "tokens": ["oliabo"], "anchors": ["proj:oliabo"]},
    {"goal": "Mindell Olive Oil Bible launch",
     "source": "sbos_goals/Atlas launch node; deadline 2027-05-18",
     "tokens": ["mindell"],
     "anchors": ["launch:mindell-olive-oil-bible",
                 "proj:mindell-launch-readiness"]},
    {"goal": "ContactFlowCRM SaaS",
     "source": "Atlas launch node; SBOS split ruling 2026-10-29",
     "tokens": ["contactflowcrm"],
     "anchors": ["launch:contactflowcrm-saas"]},
]

# Core substrate: serves every goal indirectly (Brian's own caveat in the
# Deep Look brief). A no-path finding on one of these reads "indirect
# path plausible", never "orphan".
SUBSTRATE_KEYS = {
    "sys:postgresql", "sys:atlas", "sys:altair-second-brain",
    "sys:scattered-second-brain", "sys:anythingllm",
    "sys:tailscale-fabric", "sys:a2a-bus", "sys:clerk", "sys:desks",
    "sys:successbrian-os", "sys:altair", "sys:agent-knowledge-gateway",
    "sys:knowledge-bridge", "sys:identity-resolution",
    "sys:comm-ingestion", "proj:atlas",
}

OPEN_TASK_STATES = ("queued", "open")


def ensure_coherence_table():
    pg_exec(
        "CREATE TABLE IF NOT EXISTS successbrian_os.review_coherence ("
        "id bigserial PRIMARY KEY, taken_at timestamptz DEFAULT now(), "
        "window_days int, payload jsonb)")
    pg_exec("COMMENT ON TABLE successbrian_os.review_coherence IS "
            "'Weekly Atlas/goal-coherence census snapshots (horizon "
            "layer, tools/review/horizon.py)'")


def _atlas_graph():
    nodes = {}
    for r in pg_rows("SELECT node_key, node_type, name, status, "
                     "created_at, updated_at FROM atlas.nodes"):
        nodes[r[0]] = {"key": r[0], "type": r[1], "name": r[2],
                       "status": r[3], "created_at": r[4],
                       "updated_at": r[5]}
    adj = {}
    edge_count = 0
    for r in pg_rows("SELECT from_node, to_node FROM atlas.edges"):
        edge_count += 1
        adj.setdefault(r[0], set()).add(r[1])
        adj.setdefault(r[1], set()).add(r[0])
    return nodes, adj, edge_count


def _token_hit(text, tokens):
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def _goal_of_text(text):
    for g in GOAL_LINKS:
        if _token_hit(text, g["tokens"]):
            return g["goal"]
    return None


def goal_linkage(nodes, adj):
    out, gaps = [], []
    tasks = [n for n in nodes.values() if n["type"] == "atlas_task"]
    for g in GOAL_LINKS:
        anchor_keys = [a for a in g["anchors"] if a in nodes]
        extra = [n["key"] for n in nodes.values()
                 if n["type"] in ("plan", "project")
                 and n["key"] not in anchor_keys
                 and _token_hit(n["key"] + " " + (n["name"] or ""),
                                g["tokens"])]
        anchors = anchor_keys + extra
        if not anchors:
            gaps.append(f"goal '{g['goal']}': NO Atlas presence found "
                        f"(no anchor node, no token-matched plan/project "
                        f"node) — named gap class: unrepresented goal")
            out.append({"goal": g["goal"], "source": g["source"],
                        "anchors": [], "verdict": "no-atlas-presence"})
            continue
        linked = set()
        for t in tasks:
            if _token_hit(t["key"] + " " + (t["name"] or ""),
                          g["tokens"]):
                linked.add(t["key"])
        for a in anchors:
            for nb in adj.get(a, ()):
                if nb in nodes and nodes[nb]["type"] == "atlas_task":
                    linked.add(nb)
        open_t = [nodes[k] for k in linked
                  if nodes[k]["status"] in OPEN_TASK_STATES]
        done_t = [nodes[k] for k in linked
                  if nodes[k]["status"] == "done"]
        oldest = None
        if open_t:
            oc = min(t["created_at"] for t in open_t
                     if t["created_at"])
            oldest = round((R.now_ct() - oc).total_seconds() / 86400, 1) \
                if oc else None
        edges = sum(len(adj.get(a, ())) for a in anchors)
        out.append({
            "goal": g["goal"], "source": g["source"],
            "anchors": [{"key": a, "type": nodes[a]["type"],
                         "status": nodes[a]["status"]}
                        for a in anchors],
            "edges_touching_anchors": edges,
            "linked_tasks_open": len(open_t),
            "linked_tasks_done": len(done_t),
            "oldest_open_task_age_d": oldest,
            "verdict": "linked"})
    return {"goals": out, "gaps": gaps,
            "method": "anchor nodes (seeded from live atlas.nodes "
                      "2026-11-09, cited per goal) + token match on "
                      "task node_key/name + one edge hop from anchors"}


def atlas_flow(nodes, days=7):
    tasks = [n for n in nodes.values() if n["type"] == "atlas_task"]
    cutoff = R.now_ct() - timedelta(days=days)
    cutoff14 = R.now_ct() - timedelta(days=14)
    created = [t for t in tasks if t["created_at"]
               and t["created_at"] > cutoff]
    completed = [t for t in tasks if t["status"] == "done"
                 and t["updated_at"] and t["updated_at"] > cutoff]
    open_t = [t for t in tasks if t["status"] in OPEN_TASK_STATES]
    aged = [t for t in open_t if t["created_at"]
            and t["created_at"] < cutoff14]
    packets = [t for t in tasks if t["key"].startswith("task:ssb-packet-")]
    pk_open = [t for t in packets if t["status"] in OPEN_TASK_STATES]
    by_goal = {}
    for g in GOAL_LINKS:
        by_goal[g["goal"]] = {
            "created": sum(1 for t in created
                           if _token_hit(t["key"] + " "
                                         + (t["name"] or ""),
                                         g["tokens"])),
            "completed": sum(1 for t in completed
                             if _token_hit(t["key"] + " "
                                           + (t["name"] or ""),
                                           g["tokens"]))}
    oldest_pk = None
    if pk_open:
        oc = min(t["created_at"] for t in pk_open if t["created_at"])
        oldest_pk = round((R.now_ct() - oc).total_seconds() / 86400, 1) \
            if oc else None
    return {
        "window_days": days,
        "tasks_total": len(tasks),
        "tasks_open": len(open_t),
        "created_in_window": len(created),
        "completed_in_window": len(completed),
        "open_aged_over_14d": len(aged),
        "board_packets": {
            "total": len(packets), "open": len(pk_open),
            "oldest_open_age_d": oldest_pk,
            "note": "board packets are atlas_task nodes keyed "
                    "task:ssb-packet-* (WF1 output); the board's "
                    "consumption of them is the known boundary stall"},
        "by_goal": by_goal}


def orphan_census(nodes, adj, max_hops=3):
    anchors = set()
    for g in GOAL_LINKS:
        anchors.update(a for a in g["anchors"] if a in nodes)
        # same token-matched plan/project extras the linkage census
        # counts as anchors, so the two sections agree
        anchors.update(
            n["key"] for n in nodes.values()
            if n["type"] in ("plan", "project")
            and _token_hit(n["key"] + " " + (n["name"] or ""),
                           g["tokens"]))
    subjects = [n for n in nodes.values()
                if n["type"] in ("system", "project")]
    linked, no_path = [], []
    for n in subjects:
        # BFS undirected, up to max_hops, looking for any goal anchor
        seen = {n["key"]}
        frontier = {n["key"]}
        hops = 0
        found = n["key"] in anchors
        while frontier and hops < max_hops and not found:
            hops += 1
            nxt = set()
            for k in frontier:
                for nb in adj.get(k, ()):
                    if nb in anchors:
                        found = True
                    if nb not in seen:
                        seen.add(nb)
                        nxt.add(nb)
            frontier = nxt
        age_d = None
        if n["updated_at"]:
            age_d = round((R.now_ct() - n["updated_at"]).total_seconds()
                          / 86400, 1)
        row = {"key": n["key"], "type": n["type"],
               "status": n["status"], "degree": len(adj.get(n["key"],
                                                             ())),
               "updated_age_d": age_d}
        if found:
            row["hops_to_goal_anchor"] = hops
            linked.append(row)
        else:
            if n["key"] in SUBSTRATE_KEYS:
                row["class"] = "no path within 3 hops — indirect path " \
                               "plausible (core substrate; serves " \
                               "goals indirectly)"
                row["confidence"] = "substrate, per the Deep Look " \
                                    "brief's own caveat"
            else:
                row["class"] = "no path within 3 hops — candidate " \
                               "orphan for the pass's judgment"
                row["confidence"] = "mechanical (edge graph only; a " \
                                    "purpose served outside Atlas " \
                                    "edges would not show here)"
            no_path.append(row)
    return {"subjects": len(subjects), "linked": len(linked),
            "no_path": no_path,
            "method": f"undirected BFS to {max_hops} hops from each "
                      f"system/project node to any goal anchor node"}


def handoff_stalls():
    stalls = []

    def add(queue, fn, note):
        try:
            d, oldest = fn()
            stalls.append({"queue": queue, "depth": d,
                           "oldest_age_d": oldest, "note": note})
        except Exception as e:  # queue unreadable = a stated gap
            stalls.append({"queue": queue, "depth": None,
                           "oldest_age_d": None,
                           "note": f"UNREADABLE: {str(e)[:120]}"})

    def age(ts):
        if not ts:
            return None
        if not hasattr(ts, "hour"):  # DATE column (e.g. first_surfaced)
            import datetime as _dtm
            ts = _dtm.datetime(ts.year, ts.month, ts.day,
                               tzinfo=R.now_ct().tzinfo)
        return round((R.now_ct() - ts).total_seconds() / 86400, 2)

    add("clerk raw captures (atlas.scattered_captures)",
        lambda: (pg_one("SELECT count(*) FROM atlas.scattered_captures "
                        "WHERE status='raw'"),
                 age(pg_one("SELECT min(created_at) FROM "
                            "atlas.scattered_captures WHERE "
                            "status='raw'"))),
        "clerk intake not yet triaged")
    add("board packets (atlas_task task:ssb-packet-*)",
        lambda: (pg_one("SELECT count(*) FROM atlas.nodes WHERE "
                        "node_type='atlas_task' AND starts_with("
                        "node_key, 'task:ssb-packet-') AND status IN "
                        "('queued','open')"),
                 age(pg_one("SELECT min(created_at) FROM atlas.nodes "
                            "WHERE node_type='atlas_task' AND "
                            "starts_with(node_key, 'task:ssb-packet-') "
                            "AND status IN ('queued','open')"))),
        "WF1 packets awaiting the board — the known boundary stall")
    add("atlas tasks open (all)",
        lambda: (pg_one("SELECT count(*) FROM atlas.nodes WHERE "
                        "node_type='atlas_task' AND status IN "
                        "('queued','open')"),
                 age(pg_one("SELECT min(created_at) FROM atlas.nodes "
                            "WHERE node_type='atlas_task' AND status "
                            "IN ('queued','open')"))),
        "the whole Atlas work queue")
    add("v4pro handoffs (successbrian_os.v4pro_handoffs)",
        lambda: (pg_one("SELECT count(*) FROM "
                        "successbrian_os.v4pro_handoffs WHERE status "
                        "NOT IN ('done','complete','completed')"),
                 age(pg_one("SELECT min(created_at) FROM "
                            "successbrian_os.v4pro_handoffs WHERE "
                            "status NOT IN ('done','complete',"
                            "'completed')"))),
        "worker handoff queue (statuses other than done counted, "
        "failed included — read the table for the split)")
    add("PM steps open (successbrian_os.pm_steps)",
        lambda: (pg_one("SELECT count(*) FROM successbrian_os.pm_steps "
                        "WHERE status IN ('queued','running',"
                        "'held_brian')"),
                 age(pg_one("SELECT min(created_at) FROM "
                            "successbrian_os.pm_steps WHERE status IN "
                            "('queued','running','held_brian')"))),
        "includes repair steps; the >14d no-progress subset is in "
        "the aging report")
    add("review decisions waiting (successbrian_os.review_decisions)",
        lambda: (pg_one("SELECT count(*) FROM "
                        "successbrian_os.review_decisions WHERE "
                        "state='waiting'"),
                 age(pg_one("SELECT min(first_surfaced) FROM "
                            "successbrian_os.review_decisions WHERE "
                            "state='waiting'"))),
        "Brian's own queue — surfaced in chat one at a time")
    add("issues blocked on Brian (altair.issues)",
        lambda: (pg_one("SELECT count(*) FROM altair.issues WHERE "
                        "status='blocked_brian'"),
                 age(pg_one("SELECT min(created_at) FROM altair.issues "
                            "WHERE status='blocked_brian'"))),
        "Altair-side blocked queue")
    return {"stalls": stalls,
            "note": "depth + oldest age per cross-system queue, read "
                    "live; an unreadable queue is stated, not skipped"}


def priority_discipline(nodes, days=7):
    out = {}
    # (a) agenda completion — week-to-week efficiency number
    try:
        rows = pg_rows(
            "SELECT week_of, state FROM successbrian_os.review_agenda "
            "WHERE week_of < date_trunc('week', CURRENT_DATE)::date")
        if not rows:
            out["agenda_completion"] = {
                "computable": False,
                "reason": "no completed week exists yet — the agenda "
                          "table begins with the first Saturday-set "
                          "week; the rate starts computing once one "
                          "full set week has passed"}
        else:
            by_week = {}
            for wk, st in rows:
                by_week.setdefault(str(wk), []).append(st)
            detail = {}
            for wk, states in by_week.items():
                total = len(states)
                done = sum(1 for s in states if s == "done")
                moved = sum(1 for s in states if s == "moved")
                detail[wk] = {"items": total, "done": done,
                              "moved": moved,
                              "completion_rate": round(done / total, 3)
                              if total else None}
            out["agenda_completion"] = {"computable": True,
                                        "weeks": detail}
    except Exception as e:
        out["agenda_completion"] = {"computable": False,
                                    "reason": str(e)[:160]}
    # (b) inversion CANDIDATES: old goal-linked open items while newer
    # unlinked items completed in the window
    tasks = [n for n in nodes.values() if n["type"] == "atlas_task"]
    cutoff = R.now_ct() - timedelta(days=days)
    old_linked = []
    for t in tasks:
        if t["status"] not in OPEN_TASK_STATES or not t["created_at"]:
            continue
        age_d = (R.now_ct() - t["created_at"]).total_seconds() / 86400
        if age_d <= 14:
            continue
        goal = _goal_of_text(t["key"] + " " + (t["name"] or ""))
        if goal:
            old_linked.append({"key": t["key"], "name": t["name"],
                               "age_d": round(age_d, 1), "goal": goal,
                               "created_at": t["created_at"]})
    old_linked.sort(key=lambda x: -x["age_d"])
    done_newer_unlinked = 0
    if old_linked:
        oldest_created = max(t["created_at"] for t in old_linked)
        for t in tasks:
            if t["status"] == "done" and t["updated_at"] \
                    and t["updated_at"] > cutoff \
                    and t["created_at"] and t["created_at"] > min(
                        x["created_at"] for x in old_linked) \
                    and not _goal_of_text(t["key"] + " "
                                          + (t["name"] or "")):
                done_newer_unlinked += 1
    out["inversions"] = {
        "label": "CANDIDATES for the pass's judgment — not verdicts",
        "old_goal_linked_open": [
            {k: v for k, v in t.items() if k != "created_at"}
            for t in old_linked[:10]],
        "old_goal_linked_open_total": len(old_linked),
        "newer_unlinked_completed_in_window": done_newer_unlinked,
        "reading": "goal-linked items older than 14d still open, "
                   "counted beside unlinked items created later that "
                   "completed this week — whether any pair is a true "
                   "inversion is the pass's judgment"}
    # (c) week's motion by goal
    motion = {}
    unmapped = 0
    mapped = 0
    for t in tasks:
        if t["status"] == "done" and t["updated_at"] \
                and t["updated_at"] > cutoff:
            goal = _goal_of_text(t["key"] + " " + (t["name"] or ""))
            if goal:
                motion[goal] = motion.get(goal, 0) + 1
                mapped += 1
            else:
                unmapped += 1
    pm_done = None
    try:
        pm_done = pg_one(
            "SELECT count(*) FROM successbrian_os.pm_steps WHERE "
            "status='done' AND updated_at > now() - (%s || ' days')"
            "::interval", (str(days),))
    except Exception:
        pm_done = None
    total_motion = mapped + unmapped
    out["motion_by_goal"] = {
        "window_days": days,
        "atlas_tasks_completed": total_motion,
        "by_goal": motion,
        "goal_mapped": mapped,
        "unmapped": unmapped,
        "goal_mapped_share_pct": round(100 * mapped / total_motion, 1)
        if total_motion else None,
        "pm_steps_done_in_window": pm_done,
        "note": "unmapped = completed Atlas work no goal token claims; "
                "that share is the machinery-for-itself measure. PM "
                "steps carry no goal field — counted separately, not "
                "mapped (a stated limit, not a silent one)"}
    return out


def coherence_report(days=7, persist=False):
    nodes, adj, edge_count = _atlas_graph()
    rep = {"generated_at": R.now_ct().isoformat(), "window_days": days,
           "atlas": {"nodes": len(nodes), "edges": edge_count},
           "linkage": goal_linkage(nodes, adj),
           "flow": atlas_flow(nodes, days=days),
           "orphans": orphan_census(nodes, adj),
           "stalls": handoff_stalls(),
           "priority": priority_discipline(nodes, days=days)}
    if persist:
        ensure_coherence_table()
        pid = pg_one(
            "INSERT INTO successbrian_os.review_coherence "
            "(window_days, payload) VALUES (%s, %s::jsonb) RETURNING id",
            (days, json.dumps(rep, default=str)))
        rep["snapshot_id"] = pid
    return rep


def coherence_text(rep):
    L = ["COHERENCE — Atlas driving the goals (the Deep Look)"]
    lk = rep["linkage"]
    for g in lk["goals"]:
        if g["verdict"] == "no-atlas-presence":
            L.append(f"  - {g['goal']}: NO ATLAS PRESENCE (gap)")
            continue
        L.append(f"  - {g['goal']}: {len(g['anchors'])} anchor node(s), "
                 f"{g['edges_touching_anchors']} edges, "
                 f"{g['linked_tasks_open']} tasks open / "
                 f"{g['linked_tasks_done']} done, oldest open "
                 f"{g['oldest_open_task_age_d']}d")
    for gap in lk["gaps"]:
        L.append(f"  GAP: {gap}")
    f = rep["flow"]
    L.append(f"  flow {f['window_days']}d: {f['created_in_window']} "
             f"tasks created, {f['completed_in_window']} completed, "
             f"{f['tasks_open']} open total, "
             f"{f['open_aged_over_14d']} open aged >14d")
    bp = f["board_packets"]
    L.append(f"  board packets: {bp['open']} open of {bp['total']}, "
             f"oldest open {bp['oldest_open_age_d']}d — the known "
             f"boundary stall")
    o = rep["orphans"]
    cand = [x for x in o["no_path"]
            if x["class"].startswith("no path within 3 hops — candidate")]
    subs = len(o["no_path"]) - len(cand)
    L.append(f"  machinery: {o['linked']} of {o['subjects']} "
             f"systems/projects reach a goal anchor within 3 hops; "
             f"{len(cand)} candidate orphans, {subs} substrate "
             f"no-path (indirect service plausible)")
    for x in cand[:10]:
        L.append(f"    candidate: {x['key']} [{x['type']}/{x['status']}"
                 f", degree {x['degree']}, updated "
                 f"{x['updated_age_d']}d ago]")
    for s in rep["stalls"]["stalls"]:
        if s["depth"] is None:
            L.append(f"  stall: {s['queue']}: {s['note']}")
        else:
            L.append(f"  stall: {s['queue']}: depth {s['depth']}, "
                     f"oldest {s['oldest_age_d']}d")
    p = rep["priority"]
    ac = p["agenda_completion"]
    if ac["computable"]:
        L.append(f"  agenda completion: {ac['weeks']}")
    else:
        L.append(f"  agenda completion: not computable — "
                 f"{ac['reason']}")
    inv = p["inversions"]
    L.append(f"  inversion CANDIDATES: {inv['old_goal_linked_open_total']}"
             f" goal-linked items open >14d; "
             f"{inv['newer_unlinked_completed_in_window']} newer "
             f"unlinked items completed this week (judgment belongs "
             f"to the pass)")
    for t in inv["old_goal_linked_open"][:5]:
        L.append(f"    old+linked: {t['key']} ({t['age_d']}d, "
                 f"{t['goal']})")
    m = p["motion_by_goal"]
    L.append(f"  motion {m['window_days']}d: {m['atlas_tasks_completed']}"
             f" Atlas tasks completed — {m['goal_mapped']} goal-mapped "
             f"({m['goal_mapped_share_pct']}%), {m['unmapped']} "
             f"unmapped; PM steps done: {m['pm_steps_done_in_window']}")
    if rep.get("snapshot_id"):
        L.append(f"  persisted: review_coherence #{rep['snapshot_id']}")
    return "\n".join(L)


# --- week briefing + selftest, extended with the Deep Look ----------------
_render_week_briefing_v1 = render_week_briefing


def render_week_briefing():
    base = _render_week_briefing_v1()
    try:
        coh = coherence_report()
        lines = ["", "DEEP LOOK — ATLAS & GOAL COHERENCE (tenth "
                 "instrument family)"]
        for g in coh["linkage"]["goals"]:
            if g["verdict"] == "no-atlas-presence":
                lines.append(f"- {g['goal']}: NO ATLAS PRESENCE")
            else:
                lines.append(
                    f"- {g['goal']}: {g['linked_tasks_open']} tasks "
                    f"open / {g['linked_tasks_done']} done under "
                    f"{len(g['anchors'])} anchor(s)")
        f = coh["flow"]
        lines.append(f"- flow: {f['created_in_window']} created / "
                     f"{f['completed_in_window']} completed this "
                     f"week; board packets {f['board_packets']['open']}"
                     f" open (oldest "
                     f"{f['board_packets']['oldest_open_age_d']}d)")
        m = coh["priority"]["motion_by_goal"]
        lines.append(f"- motion: {m['goal_mapped_share_pct']}% of "
                     f"completed Atlas work was goal-mapped "
                     f"({m['goal_mapped']}/{m['atlas_tasks_completed']})")
        lines.append("[JUDGMENT: is Atlas driving the goals — are the "
                     "right priorities being worked first, and is the "
                     "week's motion efficient? Full census: review.py "
                     "coherence]")
        block = "\n".join(lines)
    except Exception as e:
        block = ("\nDEEP LOOK — ATLAS & GOAL COHERENCE\n"
                 f"[UNAVAILABLE this run: {str(e)[:140]}]")
    marker = "\nDONE THIS PASS"
    if marker in base:
        return base.replace(marker, "\n" + block + marker, 1)
    return base + "\n" + block


_horizon_selftest_v1 = horizon_selftest


def horizon_selftest():
    rc = _horizon_selftest_v1()
    print("SELFTEST horizon coherence extension")
    ok = True

    def check(label, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'} {label}")
        ok = ok and bool(cond)

    rep = coherence_report()
    gb = [g for g in rep["linkage"]["goals"]
          if g["goal"].startswith("GotBackup")]
    check("coherence linkage finds the GotBackup anchors",
          gb and gb[0].get("anchors"))
    check("coherence stalls table lists the queues",
          len(rep["stalls"]["stalls"]) >= 6)
    check("coherence flow counts board packets",
          rep["flow"]["board_packets"]["total"] > 0)
    check("coherence motion shares computed",
          rep["priority"]["motion_by_goal"]["window_days"] == 7)
    print("selftest horizon: "
          f"{'ALL PASS' if ok and rc == 0 else 'FAILURES PRESENT'}")
    return 0 if (ok and rc == 0) else 1
