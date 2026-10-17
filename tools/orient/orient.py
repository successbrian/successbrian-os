#!/usr/bin/env python3
"""
orient — the one call every agent makes when it starts work.

Instead of reading docs, querying five systems, and hoping nothing was
missed, an agent calls:

    from orient import orient, check_rules
    ctx = orient('brian', task_hint='deploy a webhook')
    # ctx['context']  — business packet (products, money, roadmap)
    # ctx['intel']    — relevant facts/howtos/gotchas
    # ctx['rules']    — hard rules, always included
    # ctx['roadmap']  — open roadmap items

And before acting on anything consequential:

    hits = check_rules('brian', 'I will delete the old leads table')
    # -> [{'rule': ..., 'why': 'matched: delete', ...}]

check_rules is a checklist generator, not a judge: it surfaces the hard
rules a proposal might violate so the agent can't claim ignorance. The
agent still decides; the system makes sure it decided informed.

stdlib + psql CLI only.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "business_core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "ecosystem_intel"))
from core import get_brief  # noqa: E402
from intel import get_digest, find  # noqa: E402


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


def lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


# task_hint -> intel categories worth pulling
HINT_CATEGORIES = {
    "deploy": ["network", "systemd", "nginx"],
    "webhook": ["network", "marketing"],
    "marketing": ["marketing", "systeme.io", "flexifunnels"],
    "funnel": ["marketing", "systeme.io", "flexifunnels"],
    "crm": ["people"],
    "people": ["people"],
    "database": ["database"],
    "github": ["github"],
    "repo": ["github"],
}


def _categories_for(hint):
    if not hint:
        return None
    cats = set()
    for word, wcats in HINT_CATEGORIES.items():
        if word in hint.lower():
            cats.update(wcats)
    return sorted(cats) if cats else None


def get_hard_rules(tenant_id):
    rows = pg_query(
        "SELECT category, rule, triggers FROM business_core.rules "
        f"WHERE tenant_id={lit(tenant_id)} AND severity='hard' "
        f"ORDER BY category;")
    out = []
    for r in rows:
        trig = r[2] if len(r) > 2 else ""
        triggers = [t.strip() for t in trig.strip("{}").split(",")
                    if t.strip()] if trig else []
        out.append({"category": r[0], "rule": r[1], "triggers": triggers})
    return out


def orient(tenant_id, task_hint=None):
    """One call: business packet + relevant intel + hard rules + roadmap."""
    brief = get_brief(tenant_id)
    cats = _categories_for(task_hint)
    if cats:
        intel = {"facts": [], "howtos": [], "gotchas": []}
        d = get_digest(tenant_id)
        for f in d["facts"]:
            if f["category"] in cats:
                intel["facts"].append(f)
        intel["howtos"] = d["howtos"]
        intel["gotchas"] = d["gotchas"]
    else:
        intel = get_digest(tenant_id)
    return {
        "tenant": tenant_id,
        "task_hint": task_hint,
        "context": {
            "tagline": (brief["tenants"][0]["tagline"]
                        if brief["tenants"] else ""),
            "products": brief["products"],
            "product_links": brief["product_links"],
            "income_streams": brief["income_streams"],
            "capital_flows": brief["capital_flows"],
        },
        "intel": intel,
        "rules": get_hard_rules(tenant_id),
        "roadmap": [r for r in brief["roadmap"]
                    if r["status"] == "open"],
    }


def check_rules(tenant_id, proposal_text, task_hint=None):
    """Flag hard rules a proposal might violate.

    Returns a list of {'category', 'rule', 'matched'} — the agent reviews
    each hit before acting. Empty list = no obvious conflict (not a clean
    bill of health, just no keyword hit).
    """
    text = proposal_text.lower()
    hits = []
    for r in get_hard_rules(tenant_id):
        matched = [t for t in r["triggers"] if t.lower() in text]
        if matched:
            hits.append({"category": r["category"], "rule": r["rule"],
                         "matched": matched})
    return hits


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--check", default=None,
                    help="proposal text to check against hard rules")
    args = ap.parse_args()
    if args.check:
        print(json.dumps(check_rules(args.tenant, args.check,
                                     args.task), indent=2))
    else:
        print(json.dumps(orient(args.tenant, args.task), indent=2))


if __name__ == "__main__":
    main()
