#!/usr/bin/env python3
"""
interview — Altair and Muse interview the user to map the business.

The system notices when the map has gaps and sends an agent to ask.
"Each time that is necessary" (per Brian):
  1. New tenant with empty/sparse business_core -> full onboarding interview.
  2. Existing tenant with gaps (no products, no streams, no rules...) ->
     targeted interview for just the gaps.
  3. Staleness -> roadmap all done / nothing updated in a while ->
     "has anything changed?" check-in.

This module is the DRIVER, not the interviewer. It tells the agent:
  - coverage(tenant): what's mapped, what's missing
  - questions(tenant): the exact questions to ask for the gaps
The agent (Altair/Muse) conducts the conversation, then writes answers
back with record_* below (or plain SQL).

CLI:
    python3 interview.py --tenant brian --coverage
    python3 interview.py --tenant brian --questions
    python3 interview.py --tenant brian --needs-interview  # exit 0/1

stdlib + psql CLI only.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


# table -> (label, ask_if_empty)
COVERAGE_AREAS = [
    ("tenants", "business identity",
     "What does your business do, in one sentence?"),
    ("products", "products",
     "What are your products? For each: name, what layer it's on "
     "(core product, shared platform, skin/branding, the OS itself), "
     "status (live/building/planned), and pricing."),
    ("product_links", "how products fit",
     "How do your products fit together? Which ones build on which, "
     "which compete, which integrate?"),
    ("income_streams", "money",
     "How do you make money? List every income stream and what kind it "
     "is (product sales, affiliate, content, trading, investing)."),
    ("capital_flows", "money movement",
     "How does money move between your income streams? Which funds which?"),
    ("rules", "hard rules",
     "What are the inviolable rules every agent must respect? "
     "(If unsure, I'll propose defaults from how you operate.)"),
    ("tool_stack", "tools",
     "What tools do you use? For each: what it's for and what it costs "
     "(free, monthly, lifetime deal, owned)."),
    ("people", "who's who",
     "Who's who — the key humans and the agents, and what each one does."),
    ("roadmap", "future",
     "Where's the business going? What's now, what's next, what's the "
     "far horizon?"),
]


def coverage(tenant_id):
    """What's mapped vs missing for a tenant."""
    t = lit(tenant_id)
    result = {}
    for table, label, _ in COVERAGE_AREAS:
        key = "id" if table == "tenants" else "tenant_id"
        rows = pg_query(f"SELECT COUNT(*) FROM business_core.{table} "
                        f"WHERE {key}={t};")
        n = int(rows[0][0]) if rows else 0
        result[table] = {"label": label, "count": n, "mapped": n > 0}
    # staleness: newest write across the core tables
    rows = pg_query(
        "SELECT MAX(ts) FROM ("
        " SELECT MAX(created_at) AS ts FROM business_core.tenants "
        f"WHERE id={t}"
        " UNION ALL SELECT MAX(built_at) FROM "
        "business_core.context_packets "
        f"WHERE tenant_id={t}) s;")
    result["_freshness"] = (rows[0][0] if rows and rows[0][0] else "unknown")
    return result


def questions(tenant_id):
    """The exact questions to ask for this tenant's gaps."""
    cov = coverage(tenant_id)
    qs = []
    for table, label, question in COVERAGE_AREAS:
        if not cov[table]["mapped"]:
            qs.append({"area": label, "question": question})
    return qs


def needs_interview(tenant_id):
    """True when an interview is necessary right now."""
    qs = questions(tenant_id)
    if qs:
        return True, f"{len(qs)} unmapped areas: " + \
            ", ".join(q["area"] for q in qs)
    return False, "business core fully mapped"


# --- write-back helpers (agents call these with interview answers) ---

def record_product(tenant_id, name, layer, one_liner=None, repo=None,
                   status="planned", pricing=None):
    pg_exec(f"INSERT INTO business_core.products "
            f"(tenant_id, name, layer, one_liner, repo, status, pricing) "
            f"VALUES ({lit(tenant_id)}, {lit(name)}, {lit(layer)}, "
            f"{lit(one_liner)}, {lit(repo)}, {lit(status)}, {lit(pricing)}) "
            f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
            f"layer=EXCLUDED.layer, one_liner=EXCLUDED.one_liner, "
            f"repo=EXCLUDED.repo, status=EXCLUDED.status, "
            f"pricing=EXCLUDED.pricing;")


def record_income_stream(tenant_id, name, kind=None, status=None, note=None):
    pg_exec(f"INSERT INTO business_core.income_streams "
            f"(tenant_id, name, kind, status, note) "
            f"VALUES ({lit(tenant_id)}, {lit(name)}, {lit(kind)}, "
            f"{lit(status)}, {lit(note)}) "
            f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
            f"kind=EXCLUDED.kind, status=EXCLUDED.status, note=EXCLUDED.note;")


def record_rule(tenant_id, category, rule, severity="hard", triggers=None):
    trig = ("ARRAY[" + ",".join(lit(t) for t in triggers) + "]"
            if triggers else "NULL")
    pg_exec(f"INSERT INTO business_core.rules "
            f"(tenant_id, category, rule, severity, triggers) "
            f"VALUES ({lit(tenant_id)}, {lit(category)}, {lit(rule)}, "
            f"{lit(severity)}, {trig});")


def record_tool(tenant_id, tool, role, cost_basis=None, note=None):
    pg_exec(f"INSERT INTO business_core.tool_stack "
            f"(tenant_id, tool, role, cost_basis, note) "
            f"VALUES ({lit(tenant_id)}, {lit(tool)}, {lit(role)}, "
            f"{lit(cost_basis)}, {lit(note)}) "
            f"ON CONFLICT (tenant_id, tool) DO UPDATE SET "
            f"role=EXCLUDED.role, cost_basis=EXCLUDED.cost_basis, "
            f"note=EXCLUDED.note;")


def record_person(tenant_id, name, kind, role, note=None):
    pg_exec(f"INSERT INTO business_core.people "
            f"(tenant_id, name, kind, role, note) "
            f"VALUES ({lit(tenant_id)}, {lit(name)}, {lit(kind)}, "
            f"{lit(role)}, {lit(note)}) "
            f"ON CONFLICT (tenant_id, name) DO UPDATE SET "
            f"kind=EXCLUDED.kind, role=EXCLUDED.role, note=EXCLUDED.note;")


def record_roadmap_item(tenant_id, item, horizon="future"):
    pg_exec(f"INSERT INTO business_core.roadmap (tenant_id, item, horizon) "
            f"VALUES ({lit(tenant_id)}, {lit(item)}, {lit(horizon)});")


def main():
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--questions", action="store_true")
    ap.add_argument("--needs-interview", action="store_true")
    args = ap.parse_args()
    if args.coverage:
        print(json.dumps(coverage(args.tenant), indent=2))
    elif args.questions:
        print(json.dumps(questions(args.tenant), indent=2))
    elif args.needs_interview:
        need, why = needs_interview(args.tenant)
        print(why)
        raise SystemExit(0 if need else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
