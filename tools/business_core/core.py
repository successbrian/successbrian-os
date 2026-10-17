#!/usr/bin/env python3
"""
business_core — the business brain as a system.

The schema + this code ship with successbrian-os for every user.
The DATA is per-tenant (tenant_id on every table): Brian's business
is tenant 'brian'; another user's install holds their own business.

Agent orientation:
    from core import get_brief
    brief = get_brief('brian')   # dict of everything

Rendered doc (single source of truth = the DB):
    python3 core.py --tenant brian --render > BUSINESS_CORE.md

stdlib + psql CLI only.
"""
import argparse
import json
import os
import subprocess

TABLES = [
    "tenants", "products", "product_links", "income_streams",
    "capital_flows", "rules", "tool_stack", "people", "roadmap",
]


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


def lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def get_brief(tenant_id):
    """Return the full business brief for a tenant as a dict."""
    t = lit(tenant_id)
    brief = {}
    cols = {
        "tenants": ["id", "display_name", "tagline"],
        "products": ["name", "layer", "one_liner", "repo", "status",
                     "pricing"],
        "product_links": ["from_product", "rel", "to_product", "note"],
        "income_streams": ["name", "kind", "status", "note"],
        "capital_flows": ["from_stream", "to_stream", "rule"],
        "rules": ["category", "rule", "severity"],
        "tool_stack": ["tool", "role", "cost_basis", "note"],
        "people": ["name", "kind", "role", "note"],
        "roadmap": ["item", "horizon", "status"],
    }
    for table, columns in cols.items():
        key = "id" if table == "tenants" else "tenant_id"
        rows = pg_query(
            f"SELECT {', '.join(columns)} FROM business_core.{table} "
            f"WHERE {key}={t} ORDER BY 1;")
        brief[table] = [dict(zip(columns, r)) for r in rows]
    return brief


def render_markdown(tenant_id):
    """Render the BUSINESS_CORE doc from the database."""
    b = get_brief(tenant_id)
    if not b["tenants"]:
        return f"# No business core for tenant '{tenant_id}'\n"
    t = b["tenants"][0]
    L = [f"# BUSINESS CORE — {t['display_name']}",
         f"*{t['tagline'] or ''}*",
         "_Generated from the business_core database — the DB is the source "
         "of truth, this doc is a rendered view._",
         ""]
    L += ["## Products",
          "| Product | Layer | Status | Pricing |",
          "|---|---|---|---|"]
    for p in b["products"]:
        L.append(f"| {p['name']} | {p['layer']} | {p['status']} | "
                 f"{p['pricing'] or ''} |")
        if p["one_liner"]:
            L.append(f"  _{p['one_liner']}_")
    L += ["", "## How they fit together"]
    for l in b["product_links"]:
        L.append(f"- **{l['from_product']}** {l['rel'].replace('_', ' ')} "
                 f"**{l['to_product']}**"
                 + (f" — {l['note']}" if l["note"] else ""))
    L += ["", "## Money"]
    for s in b["income_streams"]:
        L.append(f"- **{s['name']}** ({s['kind'] or '?'}) — {s['status'] or ''}"
                 + (f" — {s['note']}" if s["note"] else ""))
    if b["capital_flows"]:
        L += ["", "### Capital flows"]
        for f in b["capital_flows"]:
            L.append(f"- {f['from_stream']} → {f['to_stream']}: {f['rule']}")
    L += ["", "## Rules (non-negotiable)"]
    for r in b["rules"]:
        L.append(f"- **[{r['category']}/{r['severity']}]** {r['rule']}")
    L += ["", "## Tool stack"]
    for tl in b["tool_stack"]:
        L.append(f"- **{tl['tool']}** — {tl['role']}"
                 + (f" ({tl['cost_basis']})" if tl["cost_basis"] else "")
                 + (f" — {tl['note']}" if tl["note"] else ""))
    L += ["", "## Who's who"]
    for p in b["people"]:
        L.append(f"- **{p['name']}** ({p['kind']}) — {p['role']}"
                 + (f" — {p['note']}" if p["note"] else ""))
    L += ["", "## Roadmap"]
    for r in b["roadmap"]:
        if r["status"] == "open":
            L.append(f"- **[{r['horizon']}]** {r['item']}")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--brief", action="store_true",
                    help="print brief as JSON")
    ap.add_argument("--render", action="store_true",
                    help="render BUSINESS_CORE markdown")
    args = ap.parse_args()
    if args.brief:
        print(json.dumps(get_brief(args.tenant), indent=2))
    elif args.render:
        print(render_markdown(args.tenant))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
