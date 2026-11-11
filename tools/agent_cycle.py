#!/usr/bin/env python3
"""agent_cycle.py — the shared Agent Cycle runner (SuccessBrian OS).

Brian's rulings: 2026-11-11 03:22 (Spencer 20-min cycle v1), 03:28
(generalize to all personal agents; PostgreSQL + second brain + all
nodes; Wix/systeme.io/FlexiFunnels compatible), 03:29 (fully integrate
Altair and the system's NAMEABLE CEO agent).

ONE loop for every agent: sense -> deduplicate -> file -> act within
authority tier -> report by exception. Spec:
docs/agent-cycle-protocol.md (AGENT-CYCLE-V2-SPEC).

Runs ON alpha (local psql). Usage:
  python3 agent_cycle.py --agent altair [--no-file]

Reads the agent's manifest from successbrian_os.agent_cycle_manifests,
runs the shared check library, upserts findings into
successbrian_os.agent_findings (dedup_key unique), files NEW findings
to the Intel Bridge via tools/atlas/scattered_brain.py, and logs the
run into successbrian_os.agent_cycle_runs. Deterministic sensing only —
no agent thinking happens here, and nothing outward is ever done.
"""
import argparse
import json
import subprocess
import sys

PSQL = ["psql", "ecosystem_central", "-Atc"]
SCATTERED = "/home/successbrian/successbrian-os/tools/atlas/scattered_brain.py"


def q(sql: str) -> str:
    r = subprocess.run(PSQL + [sql], capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {(r.stderr or '')[:200]}")
    return r.stdout.strip()


def sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# ---- shared check library (written ONCE; every agent composes from it) ----
def check_raw_backlog(params):
    n = int(q("select count(*) from atlas.scattered_captures where status='raw'"))
    return n, None  # backlog existing is normal; trend findings live in spencer_cycle


def check_qa_failing(params):
    ids = q("""select coalesce(string_agg(c.id::text, ',' order by c.id), '')
      from successbrian_os.pm_project_checks c
      where (select r.status from successbrian_os.pm_project_qa_runs r
              where r.check_id = c.id order by r.ran_at desc limit 1) = 'fail'""")
    n = 0 if ids == "" else len(ids.split(","))
    finding = None
    if n > 0:
        finding = (f"qa_failing:{ids}", f"{n} QA checks failing",
                   f"failing_check_ids={ids}")
    return n, finding


def check_gamma_liveness(params):
    age = int(q("""select coalesce(round(extract(epoch from
      (now() - max(created_at)))/60)::int, -1)
      from successbrian_os.logs where source_agent = 'gamma'"""))
    finding = None
    if age < 0 or age > 60:
        finding = (f"gamma_silent:{age // 60 if age >= 0 else 'never'}",
                   "gamma road silent",
                   f"gamma_age_min={age} (threshold 60)")
    return age, finding


def check_price_expired(params):
    n = int(q("""select count(*) from successbrian_os.price_intel
      where valid_until is not null and valid_until < current_date"""))
    finding = None
    if n > 0:
        finding = (f"price_expired:{n}", f"{n} price_intel rows past shelf life",
                   f"expired_count={n}")
    return n, finding


def check_issues_open(params):
    n = int(q("""select count(*) from altair.issues
      where status not in ('closed','done','resolved')"""))
    return n, None


CHECKS = {
    "raw_backlog": check_raw_backlog,
    "qa_failing": check_qa_failing,
    "gamma_liveness": check_gamma_liveness,
    "price_expired": check_price_expired,
    "issues_open": check_issues_open,
}


def file_bridge(agent: str, title: str, detail: str) -> str:
    ctx = (f"Filed by agent_cycle.py for agent '{agent}' (SBOS Agent Cycle "
           f"Protocol, Brian's rulings 2026-11-11). Deterministic cycle "
           f"finding; dedup state in successbrian_os.agent_findings.")
    r = subprocess.run([sys.executable, SCATTERED, "capture",
                        f"[agent-cycle:{agent}] {title}",
                        "--context", ctx, "--raw", detail],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or r.stderr or "").strip()[:160]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--no-file", action="store_true")
    args = ap.parse_args()
    agent = args.agent

    reg = q(f"""select display_name || '|' || authority_tier || '|' || enabled
      from successbrian_os.agent_registry where agent_key = {sql_str(agent)}""")
    if not reg:
        print(f"!! agent '{agent}' not in agent_registry")
        return 2
    display, tier, enabled = reg.split("|")
    if enabled not in ("t", "true"):
        print(f"[agent-cycle {agent}] disabled in registry; skipping")
        return 0

    manifest = q(f"""select check_key from successbrian_os.agent_cycle_manifests
      where agent_key = {sql_str(agent)} and enabled order by check_key""")
    check_keys = [c for c in manifest.splitlines() if c]

    results, findings = {}, []
    for ck in check_keys:
        fn = CHECKS.get(ck)
        if fn is None:
            results[ck] = "unknown-check"
            continue
        value, finding = fn({})
        results[ck] = value
        if finding:
            findings.append((ck,) + finding)

    new_count = 0
    for ck, dedup, title, detail in findings:
        full_key = f"{agent}:{dedup}"
        existing = q(f"""select id from successbrian_os.agent_findings
          where dedup_key = {sql_str(full_key)} and status = 'open'""")
        if existing:
            q(f"""update successbrian_os.agent_findings
              set last_seen = now(), times_seen = times_seen + 1,
                  detail = {sql_str(detail)}
              where dedup_key = {sql_str(full_key)}""")
        else:
            q(f"""insert into successbrian_os.agent_findings
              (dedup_key, agent_key, check_key, title, detail)
              values ({sql_str(full_key)}, {sql_str(agent)},
                      {sql_str(ck)}, {sql_str(title)}, {sql_str(detail)})
              on conflict (dedup_key) do update
              set last_seen = now(), times_seen = agent_findings.times_seen + 1,
                  status = 'open', detail = excluded.detail""")
            new_count += 1
            if not args.no_file:
                print(f"  filed: {file_bridge(agent, title, detail)}")

    summary = json.dumps({"agent": agent, "display_name": display,
                          "tier": int(tier), "results": results,
                          "findings_active": len(findings)})
    q(f"""insert into successbrian_os.agent_cycle_runs
      (agent_key, finished_at, checks_run, findings_new, findings_active, summary)
      values ({sql_str(agent)}, now(), {len(check_keys)}, {new_count},
              {len(findings)}, {sql_str(summary)}::jsonb)""")
    print(f"[agent-cycle {agent} ({display}, tier {tier})] "
          f"checks={results} findings_active={len(findings)} new={new_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
