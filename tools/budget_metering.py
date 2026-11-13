#!/usr/bin/env python3
"""budget_metering.py - READ-ONLY usage/spend roll-up (B16, step 1 of
improvement-spec Group 3.3: budgets that can fire).

Group 3.3 (builds/sbos-improvements-2026-11-12/spec.md): usage on
subscription/flat paths must be metered, or hard-stops are
decoration. This step is the metering visibility layer only: it
reads what is already on record and rolls it up. It writes nothing,
invents no prices, and enforces nothing. Hard-stop budgets and a
kill switch are later pieces, not this step.

Sources on record (all read-only here):
- successbrian_os.model_token_usage: tokens_in per model/window.
  tokens_out is 0 on every row to date: output metering does not
  exist yet. Flagged, never assumed.
- successbrian_os.project_budgets: allocated vs spent $ per project.
- dealsdesk.daily_api_usage: per-provider daily request counts
  (last row 2026-08-01: the feed is stale. Flagged.)
- public.budget_config: standing monthly $ budget (period July
  2026: stale. Flagged.)
- No per-token $ rate is on record, so none is invented: spend is
  shown in tokens plus the recorded $ budgets.

Usage: budget_metering.py [--summary] [--detail] [--selftest]
"""
import subprocess
import sys
from datetime import date

DB = ["psql", "-d", "ecosystem_central", "-At"]

STALE_DAYS = 30


def run(sql):
    out = subprocess.run(DB + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]


def _int(rows, default=0):
    try:
        return int(rows[0]) if rows else default
    except (ValueError, IndexError):
        return default


def token_windows():
    """tokens_in totals for 24h / 7d / all-time, plus per-model 24h."""
    total_24h = _int(run(
        "select coalesce(sum(tokens_in),0) from "
        "successbrian_os.model_token_usage "
        "where recorded_at >= now() - interval '24 hours'"))
    total_7d = _int(run(
        "select coalesce(sum(tokens_in),0) from "
        "successbrian_os.model_token_usage "
        "where recorded_at >= now() - interval '7 days'"))
    total_all = _int(run(
        "select coalesce(sum(tokens_in),0) from "
        "successbrian_os.model_token_usage"))
    out_all = _int(run(
        "select coalesce(sum(tokens_out),0) from "
        "successbrian_os.model_token_usage"))
    rows = run(
        "select count(*), coalesce(max(recorded_at)::text,'none') from "
        "successbrian_os.model_token_usage")
    count, latest = (rows[0].split("|") + ["", ""])[:2] if rows else ("0", "none")
    per_model_24h = run(
        "select model||'='||coalesce(sum(tokens_in),0) from "
        "successbrian_os.model_token_usage "
        "where recorded_at >= now() - interval '24 hours' "
        "group by model order by sum(tokens_in) desc")
    return {
        "total_24h": total_24h, "total_7d": total_7d,
        "total_all": total_all, "tokens_out_all": out_all,
        "rows": int(count), "latest": latest,
        "per_model_24h": per_model_24h,
    }


def project_budgets():
    rows = run(
        "select budget_name||'|'||allocated||'|'||spent||'|'||status "
        "from successbrian_os.project_budgets order by id")
    out = []
    for r in rows:
        name, allocated, spent, status = r.split("|")
        allocated, spent = float(allocated), float(spent)
        out.append({"name": name, "allocated": allocated,
                    "spent": spent, "status": status,
                    "over": spent - allocated if spent > allocated else 0.0})
    return out


def api_usage_latest():
    rows = run(
        "select date::text||'|'||provider||'|'||requests_used||'|'||"
        "requests_limit from dealsdesk.daily_api_usage "
        "order by date desc limit 1")
    if not rows:
        return None
    d, provider, used, limit = rows[0].split("|")
    return {"date": date.fromisoformat(d), "provider": provider,
            "used": int(used), "limit": int(limit)}


def budget_configs():
    rows = run(
        "select budget_type||'|'||budget_amount||'|'||currency||'|'||"
        "coalesce(period_end::text,'none')||'|'||active "
        "from public.budget_config order by id")
    out = []
    for r in rows:
        btype, amount, currency, period_end, active = r.split("|")
        out.append({"type": btype, "amount": float(amount),
                    "currency": currency,
                    "period_end": (date.fromisoformat(period_end)
                                   if period_end != "none" else None),
                    "active": active == "t"})
    return out


def summary_lines():
    today = date.today()
    tw = token_windows()
    lines = []
    top = tw["per_model_24h"][0] if tw["per_model_24h"] else "none=0"
    lines.append(
        f"budget metering: model tokens in 24h={tw['total_24h']} "
        f"7d={tw['total_7d']} all={tw['total_all']} "
        f"(top 24h: {top}; {tw['rows']} rows, latest {tw['latest']})")
    if tw["tokens_out_all"] == 0:
        lines.append("budget metering: tokens_out UNMETERED "
                     "(0 recorded on all rows — output usage unknown)")
    for b in project_budgets():
        flag = (f"OVER by ${b['over']:.2f}"
                if b["over"] > 0 else "within budget")
        lines.append(
            f"budget metering: project '{b['name']}' "
            f"spent ${b['spent']:.2f} / allocated ${b['allocated']:.2f} "
            f"[{b['status']}] {flag}")
    api = api_usage_latest()
    if api is None:
        lines.append("budget metering: daily_api_usage EMPTY (no rows)")
    else:
        age = (today - api["date"]).days
        stale = "STALE" if age > STALE_DAYS else "fresh"
        lines.append(
            f"budget metering: daily_api_usage latest {api['date']} "
            f"({api['provider']} {api['used']}/{api['limit']}) "
            f"{age}d ago [{stale}]")
    for c in budget_configs():
        if c["period_end"] is None:
            lines.append(
                f"budget metering: budget_config {c['type']} "
                f"{c['currency']} {c['amount']:.2f} "
                f"(no period_end) [{'active' if c['active'] else 'inactive'}]")
        else:
            stale = "STALE" if c["period_end"] < today else "current"
            lines.append(
                f"budget metering: budget_config {c['type']} "
                f"{c['currency']} {c['amount']:.2f} "
                f"period ends {c['period_end']} [{stale}]")
    lines.append("budget metering: no per-token $ rate on record — "
                 "spend shown in tokens + recorded $ budgets only")
    return lines


def detail_lines():
    tw = token_windows()
    lines = ["model tokens, last 24h by model:"]
    for p in tw["per_model_24h"]:
        lines.append(f"  {p}")
    lines.append(f"totals: 24h={tw['total_24h']} 7d={tw['total_7d']} "
                 f"all={tw['total_all']} out_all={tw['tokens_out_all']}")
    return lines


def selftest():
    today = date.today()
    tw = token_windows()
    # windows nest: 24h <= 7d <= all-time
    assert 0 <= tw["total_24h"] <= tw["total_7d"] <= tw["total_all"], \
        f"window totals do not nest: {tw}"
    # per-model 24h sums to the 24h total
    assert sum(int(p.rsplit("=", 1)[1])
               for p in tw["per_model_24h"]) == tw["total_24h"], \
        f"per-model 24h {tw['per_model_24h']} != {tw['total_24h']}"
    # rows exist and the latest row is recent (metering is live)
    assert tw["rows"] > 0, "model_token_usage has no rows"
    assert tw["latest"] != "none", "no latest token row"
    lines = summary_lines()
    assert any(l.startswith("budget metering: model tokens in")
               for l in lines), f"no token line in: {lines}"
    # tokens_out gap is flagged, never silently zero
    assert tw["tokens_out_all"] == 0, "tokens_out is now recorded — " \
        "update the UNMETERED flag wording"
    assert any("tokens_out UNMETERED" in l for l in lines), \
        "unmetered output not flagged"
    # over-budget detection fires on the known lapsed row
    budgets = project_budgets()
    assert budgets, "project_budgets has no rows"
    over = [b for b in budgets if b["over"] > 0]
    assert over, "no over-budget row detected"
    assert any("OVER by $" in l for l in lines), \
        "over-budget row not flagged in summary"
    # staleness flags fire on the known-stale feeds
    api = api_usage_latest()
    assert api is not None, "daily_api_usage unexpectedly empty"
    assert (today - api["date"]).days > STALE_DAYS, \
        "api usage feed is fresh now — update the STALE expectation"
    assert any("daily_api_usage" in l and "STALE" in l for l in lines), \
        "stale api feed not flagged"
    configs = budget_configs()
    assert configs, "budget_config has no rows"
    assert any(c["period_end"] is not None
               and c["period_end"] < today for c in configs), \
        "budget_config period is current now — update STALE expectation"
    assert any("budget_config" in l and "STALE" in l for l in lines), \
        "stale budget_config not flagged"
    # no $ rate invented
    assert any("no per-token $ rate on record" in l for l in lines), \
        "no-rate disclaimer missing"
    print("BUDGET_METERING_OK")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--detail" in sys.argv:
        for line in summary_lines():
            print(line)
        for line in detail_lines():
            print(line)
        return 0
    for line in summary_lines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
