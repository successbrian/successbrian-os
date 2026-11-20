#!/usr/bin/env python3
"""program_registry_seed.py — seed successbrian_os.program_registry
from the sources that already exist (Brian 2026-11-19 design):

- the successbrian user crontab and /etc/cron.d (every scheduled
  program gets a row; its stated job comes from the cron comment or
  the curated KNOWN_JOBS map — otherwise UNKNOWN, which is itself a
  finding);
- systemd timers + the ecosystem's long-running services;
- Lyra's worker_heartbeats rows not already covered by a cron row.

Idempotent: INSERT ... ON CONFLICT (program_key) DO NOTHING, so
re-running never clobbers sweep state. The seven areas under the
concurrent 2026-11-19 seven-fix run are seeded as watch_state=
'manual' — registered, not probed by this sweep, until that run
lands and binds its own probes.
"""
import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

KNOWN_JOBS = {
    "pm_runner.py": "Runs due PM steps (the repair/build queue), a few at a time",
    "repair_ladder.py": "Works the repair ladder — turns failing checks into repair work",
    "chat_brief.py": "Builds the chat briefing snapshot for the review passes",
    "desk_worker.py": "Runs the desks' work cycles",
    "dashboard.py": "Rebuilds the PM dashboard data",
    "morpheus_worker.py": "Runs Morpheus-engine PM steps from the queue",
    "closure_audit.py": "Audits closed work for real closure evidence",
    "project_qa.py": "Runs due project QA checks and records pass/fail",
    "ruling_census_sweep.py": "Sweeps rulings-census probes; files exception captures; heartbeats into Lyra",
    "coverage_watch.py": "Daily coverage sweep: unclassified folders, registry drift, thin definitions, unread dossiers",
    "weekly_planning.py": "Prepares the weekly deep-planning session (Wed 10:00 America/Chicago)",
    "verdict_applier.py": "Applies REAP verdicts to decision-queue items",
    "rulings_bridge.py": "Promotes captures carrying Brian's verbatim words into decisions and learnings",
    "sbos_ingest_router.py": "Routes ingest items into the clerk pipeline",
    "lyra_watchdog.py": "Watches Lyra worker heartbeats for staleness",
    "harness_worker.py": "Runs Intel Harness queue work on the fleet engines",
    "altair_heartbeat_v4pro.py": "Altair heartbeat cycle — advances board work through the queue",
    "carry_forward.py": "Calendar carry-forward: reschedules missed items, never drops them",
    "sprawl_census.py": "Atlas sprawl census watch",
    "fleet_dash_poller.py": "Polls fleet node state for the dashboard",
    "altair_state_cache.py": "Refreshes the Altair state cache",
    "jive.py": "Jive cycle run",
    "meme_idea_box.py": "Generates meme ideas through Brian's audience-desk themes",
    "repo_hygiene_checker.py": "Checks repo hygiene across the ecosystem repos",
    "demand_meter.py": "Meters model demand for capacity planning",
    "capacity_reconciler.py": "Reconciles capacity signals",
    "janitor.py": "Janitor pass over ecosystem state",
    "derive_needs.py": "Derives ecosystem needs from signals",
    "collect_watchdog.py": "Collects watchdog signals",
    "collect_infra.py": "Collects infrastructure signals",
    "daily_director.py": "Daily director pass",
    "pipeline_healthcheck.py": "Pipeline health check",
    "dedup.py": "AnythingLLM dedup cleanup",
    "hygiene.py": "AnythingLLM hygiene cleanup",
    "build_unified_inbox.py": "Builds the unified inbox fragment",
    "build_pm_master_fragment.py": "Builds the PM master dashboard fragment",
    "altair_briefing.py": "Writes Altair briefings (standup/sync/Sunday)",
    "spencer_checkin.py": "Spencer check-in for the Altair profile",
    "core.py": "Business-core packet builder (per-tenant)",
    "gap_watch.py": "Business-core gap and staleness watch",
    "epyc_watch_daily.py": "Daily EPYC price watch (DealsDesk)",
    "need_reader.py": "DealsDesk need reader",
    "replan_deals.py": "DealsDesk deal replanning",
    "score_builds.py": "DealsDesk build scoring",
    "need_from_task.py": "DealsDesk: turns tasks into needs",
    "needs_intake.py": "DealsDesk needs intake",
    "need_status_sync.py": "DealsDesk need status sync",
    "intel_scraper.py": "DealsDesk daily intel scrape",
    "cl_full_scrape.py": "Craigslist full scrape (Brian 2026-10-11: full coverage 7d/wk)",
    "travel_intel_monitor.py": "Travel intel monitor",
    "ecosystem_cleanup_marathon.py": "Ingests cleanup-marathon items",
    "map_income_streams.py": "Maps income streams",
    "glm_usage_telemetry.py": "GLM usage telemetry",
    "model_token_telemetry.py": "Model token telemetry",
    "model_capacity.py": "Model capacity snapshot writer",
    "model_demand_curve.py": "Model demand curve signal",
    "model_learning_review.py": "Model learning review",
    "health.py": "Flags stuck work older than 48h",
    "digest.py": "Sends the hourly digest",
    "email_reply.py": "Polls for email replies",
    "archive_stale.py": "Archives stale items",
    "auto_repair_worker.py": "Auto-repair worker",
    "v4pro_handoff_worker.py": "V4Pro handoff worker",
    "cycle_improve.py": "DealsDesk cycle improvement pass",
    "daily_knowledge_sync.py": "DealsDesk daily knowledge sync",
    "cron_watchdog.py": "DealsDesk cron watchdog",
    "collaboration_monitor.py": "SearXNG collaboration monitor",
    "carry_forward.py": "Calendar carry-forward: reschedules missed items, never drops them",
}

# Areas under the concurrent seven-fix run (2026-11-19): register
# only, do not probe.
SEVEN_FIX = {
    "sbos_backup.py": "seven-fix run 2026-11-19: pg retention being applied",
    "planner_rotation.py": "seven-fix run 2026-11-19: being scheduled",
    "gpu_watch_daily.py": "seven-fix run 2026-11-19: feed being repaired",
    "ruling_audit.py": "seven-fix run 2026-11-19: ruling-audit-collect being rescheduled + staleness alarm",
    "component_scout.py": "seven-fix run 2026-11-19: SXM form-factor gate being added",
    "hardware_traps.py": "seven-fix run 2026-11-19: SXM form-factor gate being added",
}

SERVICES = [
    "a2a-hub.service", "a2a-agent-bridge.service",
    "altair-a2a-bridge.service", "altair-api.service",
    "dashboard-api.service", "dashboard-tunnel.service",
    "deals-api.service", "dealsdesk-agent.service",
    "anythingllm.service", "anythingllm-collector.service",
    "email-tracking.service", "health-api.service",
    "heartbeat-monitor.service", "autonomous-huddle-executor.service",
    "android-fleet.service",
    "hermes-gateway-altair.service", "hermes-gateway-lyra.service",
    "hermes-gateway-mavity.service",
    "hermes-gateway-oliabo-atlanta.service",
    "hermes-gateway-oliabo-denver.service",
    "hermes-gateway-oliabo-drjerry-zoom.service",
    "hermes-gateway-oliabo-duluth.service",
    "hermes-gateway-oliabo-edina.service",
    "hermes-gateway-oliabo-followup.service",
    "hermes-gateway-oliabo-fresno.service",
]

SERVICE_JOBS = {
    "a2a-hub.service": "Agent-to-agent messaging hub",
    "altair-api.service": "Altair API suite + gateway (SuccessBrian OS)",
    "dashboard-api.service": "Altair dashboard API (FastAPI :8089)",
    "deals-api.service": "DealsDesk API server",
    "dealsdesk-agent.service": "DealsDesk Hermes agent — hardware deal hunter",
    "anythingllm.service": "AnythingLLM server (the second brain's shelves)",
    "email-tracking.service": "Oliabo outreach tracking service",
    "health-api.service": "People enricher health API",
    "heartbeat-monitor.service": "Cross-agent heartbeat monitor — detects dead/stale agents",
    "autonomous-huddle-executor.service": "Runs cross-VP huddles every 60s",
    "android-fleet.service": "Mavity Android fleet controller",
}


def cadence_min(fields):
    mi, hh, dom, dow = fields[0], fields[1], fields[2], fields[4]
    base = 1440
    m = re.fullmatch(r"\*/(\d+)", mi)
    h = re.fullmatch(r"\*/(\d+)", hh)
    if m and hh == "*":
        base = int(m.group(1))
    elif h:
        base = int(h.group(1)) * 60
    elif dom != "*":
        base = 43200
    elif dow != "*":
        base = 10080 if re.fullmatch(r"\d", dow) else 4320
    return base * 2 + 360


def owner_of(path):
    if "successbrian-os" in path:
        return "successbrian-os"
    if "dealsdesk" in path:
        return "dealsdesk"
    if "vera-repo" in path:
        return "vera-relationship-intel"
    m = re.search(r"\.hermes/profiles/([^/]+)", path)
    if m:
        return "hermes:" + m.group(1)
    if "/agents/workspace" in path:
        return "agents-workspace"
    if "/home/dealsdesk" in path:
        return "dealsdesk"
    return "scripts"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


rows = []
used_keys = set()


def add(key, name, job, owner, source, schedule, code_path, probe_kind,
        probe_ref, cadence, watch, notes):
    k = key
    n = 2
    while k in used_keys:
        k = f"{key}-{n}"
        n += 1
    used_keys.add(k)
    rows.append((k, name, job, owner, source, schedule, code_path,
                 probe_kind, probe_ref, cadence, watch, notes))


CRON_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)$")


def parse_cron_lines(lines, source, has_user_field):
    comment = None
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            c = line.lstrip("# ").strip()
            comment = c if c and not c.startswith(("SHELL", "PATH")) else comment
            continue
        if re.match(r"^[A-Z_]+=", line):
            continue
        m = CRON_RE.match(line)
        if not m:
            continue
        fields = list(m.groups()[:5])
        rest = m.group(6)
        if has_user_field:
            parts = rest.split(None, 1)
            if len(parts) < 2:
                continue
            rest = parts[1]
        script = None
        sm = re.search(r"([\w./~-]+\.(?:py|sh))\b", rest)
        if sm:
            script = os.path.expanduser(sm.group(1))
        base = os.path.basename(script) if script else None
        name = base or rest.split()[0]
        logm = re.search(r">>\s*(\S+\.log)", rest)
        log = os.path.expanduser(logm.group(1)) if logm else None
        job = KNOWN_JOBS.get(base) or (comment if comment and base else None)
        cadence = cadence_min(fields)
        sched = " ".join(fields)
        if base in SEVEN_FIX:
            add(slugify(name), name, KNOWN_JOBS.get(base), owner_of(rest),
                source, sched, script, "none", None, cadence, "manual",
                SEVEN_FIX[base])
        elif log:
            add(slugify(name), name, job, owner_of(rest), source, sched,
                script, "log_mtime", log, cadence, "watched", None)
        else:
            add(slugify(name), name, job, owner_of(rest), source, sched,
                script, "none", None, cadence, "manual",
                "no observable output wired — probe UNKNOWN")
        comment = None


def main():
    out = subprocess.run(["crontab", "-l"], capture_output=True,
                         text=True).stdout.splitlines()
    parse_cron_lines(out, "user-crontab", has_user_field=False)
    for path in sorted(glob.glob("/etc/cron.d/*")):
        if ".bak" in path or ".disabled" in path:
            continue
        try:
            lines = open(path).read().splitlines()
        except OSError:
            continue
        parse_cron_lines(lines, f"cron.d:{os.path.basename(path)}",
                         has_user_field=True)
    # systemd timers -> their services (probe = last exit stamp;
    # oneshot units are inactive between runs by design). Pure-OS
    # timers (apt, man-db, logrotate...) are not Brian's software.
    OS_TIMERS = {"anacron", "fwupd-refresh", "logrotate",
                 "dpkg-db-backup", "apt-daily", "apt-daily-upgrade",
                 "man-db", "motd-news", "e2scrub_all", "fstrim",
                 "systemd-tmpfiles-clean", "update-notifier-download",
                 "update-notifier-motd", "apport-autoreport",
                 "snapd.snap-repair", "ua-timer"}
    timers = subprocess.run(["systemctl", "list-timers", "--all",
                             "--no-legend", "--no-pager"],
                            capture_output=True, text=True).stdout
    for line in timers.splitlines():
        parts = line.split()
        if not parts:
            continue
        unit = [p for p in parts if p.endswith(".timer")]
        if not unit:
            continue
        stem = unit[0].replace(".timer", "")
        if stem in OS_TIMERS:
            continue
        svc = stem + ".service"
        add(slugify(svc), svc, SERVICE_JOBS.get(svc), "systemd",
            "systemd-timer", "timer", None, "service_exit", svc, 2880,
            "watched", None)
    for svc in SERVICES:
        add(slugify(svc), svc, SERVICE_JOBS.get(svc), "systemd",
            "systemd-service", "always-on", None, "service", svc, 120,
            "watched", None)
    # Lyra workers not covered above
    workers = sbos_common.pg_rows(
        "SELECT worker_name FROM successbrian_os.worker_heartbeats")
    covered = {"ingest_router", "lyra_watchdog", "gamma-queue-keeper",
               "coverage-watch", "ruling-census-sweep"}
    for (w,) in workers:
        if w in covered:
            continue
        if w == "ruling-audit-collect":
            add("worker-ruling-audit-collect", w, None, "lyra",
                "lyra-heartbeat", None, None, "heartbeat", w, 2880,
                "manual",
                "seven-fix run 2026-11-19: being rescheduled + alarm")
        elif w == "gamma":
            add("worker-gamma", w,
                "Gamma node heartbeat (Meghan CEO reports)", "lyra",
                "lyra-heartbeat", None, None, "heartbeat", w, 180,
                "watched", None)
        elif w == "sbos-public-push":
            add("worker-sbos-public-push", w, None, "lyra",
                "lyra-heartbeat", None, None, "heartbeat", w, 2880,
                "watched", None)
        else:
            add(slugify("worker-" + w), w, None, "lyra", "lyra-heartbeat",
                None, None, "heartbeat", w, 2880, "watched", None)
    ins = 0
    for r in rows:
        done = sbos_common.pg_exec(
            "INSERT INTO successbrian_os.program_registry "
            "(program_key, name, stated_job, owner, source, "
            "schedule_text, code_path, probe_kind, probe_ref, "
            "expected_cadence_min, watch_state, notes) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (program_key) DO NOTHING",
            r)
        if done:
            ins += 1
    total = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.program_registry")
    unknown = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.program_registry "
        "WHERE stated_job IS NULL")
    print(f"seeded {ins} new rows; registry total {total}; "
          f"stated_job UNKNOWN on {unknown}")


if __name__ == "__main__":
    main()
