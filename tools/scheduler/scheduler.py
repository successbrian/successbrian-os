#!/usr/bin/env python3
"""
scheduler — successbrian-os's schedule governor.

The crontab grew to 77 jobs with no map of what feeds what. This is the map.

  register(name, schedule, ...)  — add/update a job in the registry
  audit()                        — collisions, unregistered jobs, broken
                                   sequences, load map (from the LIVE crontab)
  plan_slot(frequency, ...)      — where should a NEW cron go? Picks the
                                   least-loaded valid minute honoring
                                   upstream dependencies + min gaps.

CLI:
    python3 scheduler.py --audit
    python3 scheduler.py --plan --frequency hourly --weight light \
        --upstream derive_needs.py --purpose "claim new screams"

stdlib + psql CLI only.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "business_core"))
from core import lit  # noqa: E402


def _pg_env():
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
    })
    return env


def pg_query(sql):
    p = subprocess.run(["psql", "-t", "-A", "-F", "\t", "-c", sql],
                       capture_output=True, text=True,
                       env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_query failed: {p.stderr.strip()[:300]}")
    return [l.split("\t") for l in p.stdout.strip().split("\n") if l.strip()]


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")


# ---------- cron parsing ----------

def expand_field(field, lo, hi):
    """Expand one cron field to a set of ints."""
    out = set()
    for chunk in field.split(","):
        chunk = chunk.strip()
        if chunk == "*":
            return set(range(lo, hi + 1))
        step = 1
        if "/" in chunk:
            chunk, step = chunk.split("/")
            step = int(step)
        if chunk == "*":
            out.update(range(lo, hi + 1, step))
        elif "-" in chunk:
            a, b = chunk.split("-")
            out.update(range(int(a), int(b) + 1, step))
        elif chunk:
            out.add(int(chunk))
    return out


def minutes_in_hour(schedule):
    """Set of minutes (0-59) a cron schedule fires within an hour.

    Only meaningful for schedules that repeat within the hour; for daily+
    jobs this is the minute-of-hour they fire.
    """
    return expand_field(schedule.split()[0], 0, 59)


def live_crontab():
    """Parse the live crontab: [(schedule, job_name)]."""
    p = subprocess.run(["crontab", "-l"], capture_output=True, text=True,
                       env=_pg_env(), timeout=30)
    jobs = []
    for line in p.stdout.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        sched, cmd = " ".join(parts[:5]), parts[5]
        core = cmd.split(">>")[0]
        m = re.search(r"([\w\-.]+?\.(?:py|sh))\b", core)
        if m:
            name = m.group(1)
        else:
            # fall back: first meaningful token (skip env assigns, [, cd)
            toks = [t for t in re.findall(r"[\w\-.]+", core)
                    if t not in ("export", "cd") and "=" not in t]
            name = toks[0] if toks else core[:40]
        jobs.append((sched, name, cmd))
    return jobs


# ---------- registry ----------

def register(job_name, schedule, purpose="", weight="unknown", upstream=None,
             downstream=None, min_gap=10, area="", command="",
             enriched=False):
    up = ("ARRAY[" + ",".join(lit(u) for u in (upstream or [])) + "]"
          if upstream else "'{}'")
    down = ("ARRAY[" + ",".join(lit(d) for d in (downstream or [])) + "]"
            if downstream else "'{}'")
    pg_exec(
        "INSERT INTO successbrian_os.cron_registry "
        "(job_name, schedule, purpose, weight, upstream, downstream, "
        " min_gap_minutes, area, command, enriched, updated_at) VALUES "
        f"({lit(job_name)}, {lit(schedule)}, {lit(purpose)}, {lit(weight)}, "
        f"{up}, {down}, {min_gap}, {lit(area)}, {lit(command)}, "
        f"{'TRUE' if enriched else 'FALSE'}, now()) "
        "ON CONFLICT (job_name) DO UPDATE SET "
        "schedule=EXCLUDED.schedule, purpose=EXCLUDED.purpose, "
        "weight=EXCLUDED.weight, upstream=EXCLUDED.upstream, "
        "downstream=EXCLUDED.downstream, "
        "min_gap_minutes=EXCLUDED.min_gap_minutes, area=EXCLUDED.area, "
        "command=EXCLUDED.command, enriched=EXCLUDED.enriched, "
        "updated_at=now();")


def registry():
    rows = pg_query(
        "SELECT job_name, schedule, purpose, weight, upstream, downstream, "
        "min_gap_minutes, area, enriched FROM "
        "successbrian_os.cron_registry ORDER BY job_name;")
    out = {}
    for r in rows:
        out[r[0]] = {
            "schedule": r[1], "purpose": r[2], "weight": r[3],
            "upstream": [u for u in r[4].strip("{}").split(",") if u],
            "downstream": [d for d in r[5].strip("{}").split(",") if d],
            "min_gap": int(r[6]), "area": r[7], "enriched": r[8] == "t",
        }
    return out


WEIGHT_LOAD = {"light": 1, "unknown": 2, "heavy": 3}


# ---------- audit ----------

def audit():
    """Audit the live crontab against the registry."""
    live = live_crontab()
    reg = registry()

    # load per minute-of-hour
    load = {}
    by_minute = {}
    for sched, name, _ in live:
        try:
            mins = minutes_in_hour(sched)
        except Exception:
            continue
        w = WEIGHT_LOAD.get(reg.get(name, {}).get("weight", "unknown"), 2)
        for m in mins:
            load[m] = load.get(m, 0) + w
            by_minute.setdefault(m, []).append(name)

    collisions = [{"minute": m, "load": load[m],
                   "jobs": sorted(set(by_minute[m]))}
                  for m in sorted(by_minute)
                  if len(set(by_minute[m])) >= 3]

    live_names = {n for _, n, _ in live}
    unregistered = sorted(n for n in live_names if n not in reg)

    # sequence check: downstream must run >= min_gap after upstream
    violations = []
    sched_of = {}
    for sched, name, _ in live:
        try:
            sched_of.setdefault(name, minutes_in_hour(sched))
        except Exception:
            pass
    for name, info in reg.items():
        if name not in sched_of:
            continue
        for up in info["upstream"]:
            if up not in sched_of:
                continue
            gap = info["min_gap"]
            ok = False
            for m in sched_of[name]:
                # minutes since most recent upstream run
                since = min((m - u) % 60 for u in sched_of[up])
                if since >= gap:
                    ok = True
                    break
            if not ok:
                violations.append({
                    "job": name, "upstream": up,
                    "issue": f"no run >= {gap}min after {up}",
                })

    return {
        "total_jobs": len(live),
        "registered": len(reg),
        "enriched": sum(1 for v in reg.values() if v["enriched"]),
        "collisions": collisions,
        "unregistered": unregistered,
        "sequence_violations": violations,
        "peak_load": max(load.values()) if load else 0,
        "peak_minute": max(load, key=load.get) if load else None,
    }


# ---------- planner ----------

FREQUENCIES = {
    "4/hour": "*/15", "2/hour": "*/30", "hourly": "*",
    "daily": None, "weekly": None, "monthly": None,
}


def plan_slot(frequency, weight="light", upstream=None, min_gap=10,
              purpose=""):
    """Find the best cron slot for a NEW job.

    Returns {schedule, minute, reason}. Honors upstream deps + min gap,
    picks the least-loaded valid minute.
    """
    live = live_crontab()
    reg = registry()
    load = {}
    for sched, name, _ in live:
        try:
            mins = minutes_in_hour(sched)
        except Exception:
            continue
        w = WEIGHT_LOAD.get(reg.get(name, {}).get("weight", "unknown"), 2)
        for m in mins:
            load[m] = load.get(m, 0) + w
    for m in range(60):
        load.setdefault(m, 0)

    # upstream constraint: candidate minute must be >= min_gap after the
    # most recent upstream run (mod 60)
    up_minutes = []
    sched_of = {}
    for sched, name, _ in live:
        try:
            sched_of.setdefault(name, minutes_in_hour(sched))
        except Exception:
            pass
    for up in (upstream or []):
        if up in sched_of:
            up_minutes.extend(sched_of[up])

    def valid(m):
        if not up_minutes:
            return True
        return min((m - u) % 60 for u in up_minutes) >= min_gap

    cands = [(load[m], m) for m in range(60) if valid(m)]
    if not cands:
        return {"error": "no valid minute honors upstream gaps"}
    cands.sort()
    best_load, best_m = cands[0]

    step = FREQUENCIES.get(frequency)
    if step == "*":
        sched = f"{best_m} * * * *"
    elif step:
        # align stepped schedules to the chosen minute offset
        base = {"*/15": 15, "*/30": 30}[step]
        sched = f"{best_m % base}-59/{base} * * * *" if False else \
            f"{best_m},{(best_m+base)%60} * * * *" if base == 30 else \
            f"{best_m},{(best_m+15)%60},{(best_m+30)%60},{(best_m+45)%60} * * * *"
    elif frequency == "daily":
        sched = f"{best_m} 4 * * *"
    elif frequency == "weekly":
        sched = f"{best_m} 4 * * 0"
    elif frequency == "monthly":
        sched = f"{best_m} 4 1 * *"
    else:
        return {"error": f"unknown frequency: {frequency}"}

    why = (f"minute :{best_m:02d} has the lowest load ({best_load})")
    if up_minutes:
        why += f" and runs >= {min_gap}min after {', '.join(upstream)}"
    return {"schedule": sched, "minute": best_m, "load": best_load,
            "reason": why, "frequency": frequency, "weight": weight,
            "upstream": upstream or [], "purpose": purpose}


def watch():
    """Self-running audit: file a question only when the schedule degrades.
    Silent when clean. Deduped like gap_watch."""
    a = audit()
    problems = []
    bad = [c for c in a["collisions"] if c["load"] >= 12]
    if bad:
        worst = sorted(bad, key=lambda c: -c["load"])[:3]
        desc = ", ".join(f":{c['minute']:02d} ({c['load']} load)" for c in worst)
        problems.append(f"{len(bad)} overloaded minutes, worst: {desc}")
    if a["sequence_violations"]:
        problems.append(f"{len(a['sequence_violations'])} sequence violations")
    if a["unregistered"]:
        problems.append(f"{len(a['unregistered'])} unregistered jobs")
    if not problems:
        return "clean"
    question = ("Schedule audit found problems: " + "; ".join(problems) +
                ". Want me to propose a rebalance?")
    ctx = "scheduler-watch " + "; ".join(problems)
    rows = pg_query(
        "SELECT 1 FROM successbrian_os.pending_questions "
        f"WHERE asked_by='scheduler-watch' AND status='open' LIMIT 1;")
    if rows:
        return "already filed"
    pg_exec(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, priority) VALUES "
        f"('scheduler-watch', {lit(question)}, {lit(ctx)}, 3);")
    return "filed: " + "; ".join(problems)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--frequency", default="hourly")
    ap.add_argument("--weight", default="light")
    ap.add_argument("--upstream", nargs="*", default=[])
    ap.add_argument("--min-gap", type=int, default=10)
    ap.add_argument("--purpose", default="")
    args = ap.parse_args()
    if args.audit:
        print(json.dumps(audit(), indent=2))
    elif args.watch:
        print(watch())
    elif args.plan:
        print(json.dumps(plan_slot(args.frequency, args.weight,
                                   args.upstream, args.min_gap,
                                   args.purpose), indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
