#!/usr/bin/env python3
"""SuccessBrian OS: intel pipeline for the focus coach — knowns vs unknowns.

PURPOSE:
    The focus coach must not score analyst-supplied guesses as if they were
    facts. This module defines WHAT intel an evaluation needs (the checklist),
    tracks what is KNOWN vs UNKNOWN per candidate, and catalogs comp-plan
    gotcha patterns to check. The operator's AI agent does the digging —
    research is the agent's job; scoring stays deterministic in focus.py.

WHY:
    Brian 2026-10-04: the v1 scorer accepted inputs with no record of what
    was verified versus assumed — and the LifeWise inputs were the analyst's,
    not the founder's. A coach that can't say "I don't know this yet" will
    confidently score hype. This module makes ignorance explicit and
    actionable, and every completed checklist strengthens the ecosystem
    (see writeback.py).

CALLED BY:
    - Humans/agents: intel.py new|audit|show --candidate ...
    - focus.py --intel <candidate.json> (v2 evaluate path)
    - writeback.py (exports the completed dossier to the ecosystem)

NOTES:
    - Agent loop (the thin contract): new -> research each UNKNOWN with
      real-world sources -> fill value+source -> audit until unknowns are
      empty or explicitly marked unfindable -> evaluate -> writeback.
    - Candidate files live in tools/focus/candidates/ (gitignored working
      data). candidates/example.json is the committed fictional template.
    - A "verified" field means: a real-world source was checked and cited.
      "Assumed" means: default, guess, or analyst inference. The scorer
      treats them differently — see focus.py.
"""

import argparse
import copy
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAND_DIR = os.path.join(HERE, "candidates")

# The checklist: every field an evaluation needs, grouped. None means unknown.
CHECKLIST = {
    "identity": ["name", "lane", "competing_lanes", "website"],
    "offer": ["products", "prices"],
    "comp_plan": ["startup_cost_usd", "autoship_required", "autoship_monthly_usd",
                  "payout_structure", "gotchas"],
    "vehicle": ["momentum", "momentum_source", "regulatory_flags"],
    "market": ["target_audiences", "sentiment", "perception_risk", "perception_notes"],
    "founder_fit": ["personally_tested", "personal_benefit", "attention_cost"],
}

# Comp-plan gotcha patterns. Severity drives deterministic penalties in focus.py.
# warn = -2 future_fit, severe = -4. Checked against the real plan, not marketing.
GOTCHA_CATALOG = {
    "autoship-required-to-earn": {
        "severity": "severe",
        "what": "Must maintain monthly autoship to earn any commission."},
    "autoship-creep": {
        "severity": "warn",
        "what": "Autoship/PV threshold rises with rank; costs scale with ambition."},
    "rank-requalification": {
        "severity": "warn",
        "what": "Ranks (and bonuses) must be re-earned monthly/quarterly; nothing is permanent."},
    "enrollment-fee-no-product": {
        "severity": "severe",
        "what": "Join fee buys no product — pay-to-play signal."},
    "binary-weak-leg": {
        "severity": "warn",
        "what": "Binary plan: commissions gated on the weaker leg; most volume never pays."},
    "commission-lapse": {
        "severity": "warn",
        "what": "Commissions lapse after N days of inactivity; dormant builders earn zero."},
    "tool-system-upsell": {
        "severity": "warn",
        "what": "Required/expected spend on marketing tools, events, or training packs."},
    "fifty-percent-rule": {
        "severity": "info",
        "what": "Max 50% of rank volume from one leg — standard anti-gaming rule, neutral."},
}


def field(value=None, verified=False, source=""):
    return {"value": value, "verified": bool(verified), "source": source}


def blank_candidate(name):
    return {
        "name": name,
        "updated": datetime.date.today().isoformat(),
        "identity": {
            "name": field(name, True, "founder"),
            "lane": field(),
            "competing_lanes": field([]),
            "website": field(),
        },
        "offer": {
            "products": field(),
            "prices": field(),
        },
        "comp_plan": {
            "startup_cost_usd": field(),
            "autoship_required": field(),
            "autoship_monthly_usd": field(),
            "payout_structure": field(),
            "gotchas": field([]),
        },
        "vehicle": {
            "momentum": field(),  # 0 declining/unknown, 1 stable, 2 growing
            "momentum_source": field(),
            "regulatory_flags": field([]),
        },
        "market": {
            "target_audiences": field([]),
            "sentiment": field(),
            "perception_risk": field(),  # 0 clean, 1 needs explaining, 2 fails the smell test
            "perception_notes": field(),
        },
        "founder_fit": {
            "personally_tested": field(False, True, "founder"),
            "personal_benefit": field(0, True, "founder"),  # 0-2, founder's own call
            "attention_cost": field(1, True, "founder"),    # 0-2, founder's own call
        },
    }


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "candidate"


def audit(candidate):
    """Returns (knowns, unknowns): 'group.field' paths with verification state."""
    known, unknown = [], []
    for group, fields in CHECKLIST.items():
        for f in fields:
            node = candidate.get(group, {}).get(f, {})
            v = node.get("value") if isinstance(node, dict) else node
            ver = node.get("verified", False) if isinstance(node, dict) else False
            # Verified + empty list/dict means "checked, none found" — that is known.
            # Verified + None/"" means contradictory data — treat as unknown.
            empty = v in (None, "", {})
            empty_list = isinstance(v, list) and len(v) == 0
            known_now = ver and (not empty or empty_list)
            (known if known_now else unknown).append(
                f"{group}.{f}" + ("" if known_now else " (unverified value)" if not empty or empty_list else ""))
    return known, unknown


def cmd_new(a):
    os.makedirs(CAND_DIR, exist_ok=True)
    path = os.path.join(CAND_DIR, slug(a.name) + ".json")
    if os.path.exists(path) and not a.force:
        print(f"Candidate exists: {path} (use --force to overwrite)")
        return 1
    with open(path, "w") as f:
        json.dump(blank_candidate(a.name), f, indent=2)
    print(f"Created {path}")
    print("Next: research each UNKNOWN (see audit), fill value+source, then re-audit.")
    return 0


def cmd_audit(a):
    with open(a.candidate) as f:
        cand = json.load(f)
    known, unknown = audit(cand)
    print(f"=== {cand.get('name', '?')} — intel audit ===")
    print(f"KNOWN ({len(known)}):")
    for k in known:
        print(f"  + {k}")
    print(f"UNKNOWN ({len(unknown)}):")
    for k in unknown:
        print(f"  ? {k}")
    if unknown:
        print("\nNext intel to find: " + ", ".join(unknown[:3]))
    else:
        print("\nChecklist complete. Ready for: focus.py evaluate --intel " + a.candidate)
    return 0


def cmd_show(a):
    with open(a.candidate) as f:
        cand = json.load(f)
    print(json.dumps(cand, indent=2))
    return 0


def cmd_gotchas(_a):
    print("Comp-plan gotcha catalog (check each against the real plan):")
    for key, g in GOTCHA_CATALOG.items():
        print(f"  [{g['severity']:>6}] {key}: {g['what']}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Focus coach intel pipeline: knowns vs unknowns.")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="Start a candidate checklist.")
    n.add_argument("--name", required=True)
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)
    au = sub.add_parser("audit", help="Report KNOWN vs UNKNOWN for a candidate.")
    au.add_argument("--candidate", required=True)
    au.set_defaults(func=cmd_audit)
    s = sub.add_parser("show", help="Print a candidate file.")
    s.add_argument("--candidate", required=True)
    s.set_defaults(func=cmd_show)
    g = sub.add_parser("gotchas", help="List the comp-plan gotcha catalog.")
    g.set_defaults(func=cmd_gotchas)
    a = p.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    sys.exit(main())
