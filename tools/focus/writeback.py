#!/usr/bin/env python3
"""SuccessBrian OS: writeback — every evaluation strengthens the ecosystem.

PURPOSE:
    Converts a completed candidate dossier + evaluation into ecosystem
    intel: a research_digest item (what was found, with sources) and a
    second_brain learning (what it means). Prints both as JSON to stdout.
    The operator's agent loads them into the real stores — that is the
    thin contract, because only the agent holds the database credentials.

WHY:
    Brian 2026-10-04: "going through this exercise should make the
    ecosystem stronger with more intel either way." Research that
    evaporates after the decision is wasted work. Writeback closes the
    loop: evaluate -> record -> the next evaluation starts smarter.

CALLED BY:
    - Humans/agents after focus.py evaluate --intel:
        python3 writeback.py --candidate candidates/x.json --score 44 --band shelve-or-reshape
      then load the emitted JSON via the ecosystem writers
      (e.g. tools/second_brain.py, altair.research_digest inserts).

NOTES:
    - Print-only by design: no credentials, no direct DB writes. The agent
      that ran the research performs the load — it already has the access.
    - The digest item carries item_id/topic/title/summary/url/source/signal;
      the second_brain entry carries topic/content/confidence/tags.
"""

import argparse
import datetime
import json
import sys


def build(cand, score, band):
    name = cand.get("name", "candidate")
    today = datetime.date.today().isoformat()
    ident = cand.get("identity", {})
    comp = cand.get("comp_plan", {})
    veh = cand.get("vehicle", {})
    mkt = cand.get("market", {})

    def val(node, default=""):
        if isinstance(node, dict):
            return node.get("value", default)
        return node if node is not None else default

    def src(node):
        return node.get("source", "") if isinstance(node, dict) else ""

    sources = sorted({src(n) for group in
                      (ident, comp, veh, mkt) for n in group.values()
                      if isinstance(n, dict) and src(n)})
    gotchas = val(comp.get("gotchas"), []) or []
    gotcha_txt = "; ".join(
        f"{g.get('pattern')} [{g.get('severity')}]" for g in gotchas) or "none confirmed"
    prods = val(cand.get("offer", {}).get("products"))
    prod_txt = ", ".join(prods) if isinstance(prods, list) else (prods or "?")
    auto_req = val(comp.get("autoship_required"))
    auto_usd = val(comp.get("autoship_monthly_usd"))
    auto_txt = ("required" if auto_req else "not required") if auto_req is not None else "unknown"
    auto_usd_txt = f"${auto_usd}/mo" if auto_usd is not None else "unknown $/mo"

    digest = {
        "digest_date": today,
        "item_id": f"focus-eval-{name.lower().replace(' ', '-')}-{today}",
        "topic": "focus-eval",
        "title": f"Focus evaluation: {name} scored {score}/100 ({band})",
        "summary": (
            f"Evaluated {name} ({val(ident.get('website'))}) via the focus coach v2. "
            f"Score {score}/100, band {band}. "
            f"Lane: {val(ident.get('lane'))}. "
            f"Products: {prod_txt}. "
            f"Comp: startup ${val(comp.get('startup_cost_usd'), '?')}, "
            f"autoship {auto_txt} ({auto_usd_txt}). "
            f"Gotchas: {gotcha_txt}. "
            f"Momentum: {val(veh.get('momentum'), '?')}/2. "
            f"Regulatory flags: {val(veh.get('regulatory_flags'), []) or 'none'}. "
            f"Perception risk: {val(mkt.get('perception_risk'), '?')}/2."
        ),
        "url": val(ident.get("website")),
        "source": "focus coach intel pipeline; sources: " + "; ".join(sources[:5]),
        "signal": "high" if band == "shelve-or-reshape" else "medium",
    }
    brain = {
        "topic": f"Focus evaluation: {name} ({band}, {score}/100)",
        "content": (
            f"Candidate {name} evaluated {today}: {score}/100 → {band}. "
            f"Key determinants: {gotcha_txt}; "
            f"lane '{val(ident.get('lane'))}'; "
            f"momentum {val(veh.get('momentum'), '?')}/2; "
            f"perception risk {val(mkt.get('perception_risk'), '?')}/2. "
            f"Full dossier: candidates/{name.lower().replace(' ', '-')}.json."
        ),
        "category": "learning",
        "confidence": "medium",
        "source": "focus-eval",
        "tags": ["focus-coach", "evaluation", name.lower().replace(" ", "-")],
    }
    return {"research_digest_item": digest, "second_brain_entry": brain}


def main():
    p = argparse.ArgumentParser(description="Emit ecosystem intel from a focus evaluation.")
    p.add_argument("--candidate", required=True, help="Candidate JSON from intel.py")
    p.add_argument("--score", required=True, type=int)
    p.add_argument("--band", required=True)
    a = p.parse_args()
    with open(a.candidate) as f:
        cand = json.load(f)
    out = build(cand, a.score, a.band)
    print(json.dumps(out, indent=2))
    print("\nLoad the above via your ecosystem writers "
          "(research_digest insert, second_brain.py).", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
