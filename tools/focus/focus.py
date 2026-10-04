#!/usr/bin/env python3
"""SuccessBrian OS: Focus coach — deterministic opportunity evaluator + grounding review.

PURPOSE:
    Two commands. `evaluate` scores any new opportunity (MLM, affiliate
    program, product line, side stream) against the unique-value framework
    before the entrepreneur commits attention to it. `review` produces the
    regular grounding report: every active pursuit reduced to facts —
    what earns, what is promoted, what is tested, what is attention rent.

WHY:
    Brian 2026-10-04: the ADHD-pattern entrepreneur goes in 100 directions
    at once and needs to be ground into facts, regularly, as the business
    grows. Enthusiasm is not evidence ("great, although never tested" scores
    near zero on life value by design). The venture toolkit scores *ideas*;
    this scores *commitments* — the things already eating calendar and
    attention. Deterministic rubric, bands not verdicts: the score proposes,
    the entrepreneur decides. No chat model ever decides (Brian 2026-09-29).

    v2 (Brian 2026-10-04): inputs are tracked as VERIFIED vs ASSUMED. An
    intel file (tools/focus/intel.py checklist) carries real-world findings
    with sources; anything not verified is flagged, not silently scored.
    The v1 flaw: it scored analyst-supplied inputs with no record of what
    was actually checked. New in v2: comp-plan gotcha penalties, audience
    fit axis, lane overlap derived from the registry (not asserted).

CALLED BY:
    - Humans/agents: python3 focus.py evaluate [--intel candidate.json | flags...]
    - Humans: python3 focus.py review [--focus-limit N]
    - Weekly cron (review): the scheduled coaching pass.
    - Importable: evaluate_candidate(dict, active_streams, user_audiences, limit)

NOTES:
    - Product-generic: no user-specific streams are hardcoded. Personal
      registry lives in user_focus.json (gitignored, never committed);
      user_focus.example.json is the committed template.
    - All scores are traceable to input fields; rerunning with the same
      inputs gives the same result. v2 rebalanced the axes to 100 across
      six dimensions (was five); scores from v1 are not comparable.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from intel import GOTCHA_CATALOG
except ImportError:  # pragma: no cover - standalone copy
    GOTCHA_CATALOG = {}

USER_FILE = os.path.join(HERE, "user_focus.json")
EXAMPLE_FILE = os.path.join(HERE, "user_focus.example.json")

BANDS = [(70, "strong"), (45, "consider"), (0, "shelve-or-reshape")]
DEFAULT_FOCUS_LIMIT = 5  # product default; override per user, never hardcoded per person
GOTCHA_PENALTY = {"severe": 4, "warn": 2, "info": 0}


def focus_limit(explicit=None):
    """Resolve the active-stream focus limit: explicit arg > FOCUS_LIMIT env > default."""
    if explicit:
        return int(explicit)
    try:
        return int(os.environ.get("FOCUS_LIMIT", DEFAULT_FOCUS_LIMIT))
    except (TypeError, ValueError):
        return DEFAULT_FOCUS_LIMIT


def _band(total):
    for floor, name in BANDS:
        if total >= floor:
            return name
    return "shelve-or-reshape"


def _val(node, default=None):
    """Extract value from an intel field {'value','verified','source'} or a raw value."""
    if isinstance(node, dict) and "value" in node:
        return node["value"] if node["value"] is not None else default
    return node if node is not None else default


def _ver(node):
    """True only if the intel file marks this field verified with a source."""
    return bool(isinstance(node, dict) and node.get("verified") and node.get("source"))


def evaluate_candidate(cand, active_streams, user_audiences=None, limit=None):
    """Deterministic 0-100 score across six axes. cand may be:

    - an intel-file dict (groups like identity/comp_plan/...) with
      {'value','verified','source'} fields, or
    - a flat dict of raw values (v1 CLI flags) — every input is then
      marked ASSUMED and the report says so loudly.

    Returns {name, total, band, breakdown, flags, verified_inputs,
    assumed_inputs}. Assumed load-bearing inputs are flagged, never hidden.
    """
    from_intel = isinstance(cand.get("identity"), dict)
    bd = {}
    flags = []
    verified_inputs, assumed_inputs = [], []

    def track(label, node, load_bearing=True):
        (verified_inputs if _ver(node) else assumed_inputs).append(label)
        if not _ver(node) and load_bearing:
            flags.append(f"assumed:{label} — not verified against a real-world source")

    if from_intel:
        ident = cand.get("identity", {})
        comp = cand.get("comp_plan", {})
        veh = cand.get("vehicle", {})
        mkt = cand.get("market", {})
        fit = cand.get("founder_fit", {})

        name = _val(ident.get("name"), "candidate")
        lane = _val(ident.get("lane"), "")
        track("lane", ident.get("lane"))
        # Overlap is DERIVED from declared competing lanes matched against the
        # registry — not asserted as a bare number by the analyst.
        declared = [str(x).lower() for x in (_val(ident.get("competing_lanes"), []) or [])]
        track("competing_lanes", ident.get("competing_lanes"))
        registry_lanes = [(s.get("lane") or "").lower() for s in (active_streams or [])]
        overlaps = sum(1 for d in declared if d in registry_lanes)
        if not declared:
            flags.append("no-competing-lanes-declared — researcher did not map this against registry lanes")

        tested = bool(_val(fit.get("personally_tested"), False))
        track("personally_tested", fit.get("personally_tested"), load_bearing=False)
        benefit = max(0, min(2, int(_val(fit.get("personal_benefit"), 0) or 0)))
        track("personal_benefit", fit.get("personal_benefit"), load_bearing=False)

        payout = str(_val(comp.get("payout_structure"), "")).lower()
        recurring = any(k in payout for k in ("unilevel", "binary", "residual", "commission"))
        track("recurring_income", comp.get("payout_structure"))
        momentum = max(0, min(2, int(_val(veh.get("momentum"), 0) or 0)))
        track("momentum", veh.get("momentum"))
        # perception_risk 0-2: the PRIDE test, not a smell test.
        # 0 = product-first: you'd recommend it even with zero comp attached.
        # 1 = needs context: solid, but the story needs telling (default when unknown).
        # 2 = opportunity-only: the pitch only works as income, no standalone
        #     product value for followers.
        risk = max(0, min(2, int(_val(mkt.get("perception_risk"), 1) or 0)))
        track("perception_risk", mkt.get("perception_risk"))
        attention = max(0, min(2, int(_val(fit.get("attention_cost"), 1) or 0)))
        track("attention_cost", fit.get("attention_cost"), load_bearing=False)
        gotchas = _val(comp.get("gotchas"), []) or []
        track("comp_gotchas", comp.get("gotchas"))
        if not gotchas and not _ver(comp.get("autoship_required")):
            flags.append("gotcha-scan-incomplete: autoship terms unknown — "
                         "'autoship-required-to-earn' cannot be ruled out")
        cand_audiences = [a.lower() for a in (_val(mkt.get("target_audiences"), []) or [])]
        track("target_audiences", mkt.get("target_audiences"))
        reg_flags = _val(veh.get("regulatory_flags"), []) or []
        if reg_flags:
            flags.append("regulatory-flags present: " + ", ".join(map(str, reg_flags)))
    else:
        name = cand.get("name", "candidate")
        lane = ""
        overlaps = max(0, int(cand.get("overlaps_active") or 0))
        tested = bool(cand.get("personally_tested"))
        benefit = max(0, min(2, int(cand.get("personal_benefit") or 0)))
        recurring = bool(cand.get("recurring_income"))
        momentum = max(0, min(2, int(cand.get("vehicle_momentum") or 0)))
        risk = max(0, min(2, int(cand.get("perception_risk") or 0)))
        attention = max(0, min(2, int(cand.get("attention_cost") or 0)))
        gotchas = []
        cand_audiences = []
        flags.append("ALL INPUTS ASSUMED — no intel file; build one with intel.py new/audit first")
        assumed_inputs.extend(["lane", "recurring_income", "momentum", "perception_risk",
                               "comp_gotchas", "target_audiences"])

    # 1. Life value (0-20): lived benefit counts; untested enthusiasm is capped.
    if tested:
        bd["life_value"] = min(20, 8 + benefit * 6)
    else:
        bd["life_value"] = benefit * 2  # max 4: enthusiasm is not evidence
        if benefit > 0:
            flags.append("untested-enthusiasm: benefit claimed without personal testing")

    # 2. Ecosystem fit (0-20): a lane nobody owns scores; duplication is taxed.
    bd["ecosystem_fit"] = max(0, min(20, 20 - 7 * overlaps + (4 if overlaps == 0 else 0)))
    if overlaps >= 2:
        flags.append(f"lane-duplication: {overlaps} active streams already cover this lane")

    # 3. Future fit (0-15): recurring income + vehicle momentum, minus gotchas.
    bd["future_fit"] = (6 if recurring else 0) + momentum * 4
    for g in gotchas:
        pat = g.get("pattern", "?") if isinstance(g, dict) else str(g)
        sev = (g.get("severity") if isinstance(g, dict)
               else GOTCHA_CATALOG.get(pat, {}).get("severity", "info"))
        pen = GOTCHA_PENALTY.get(sev, 0)
        if pen:
            flags.append(f"comp-gotcha [{sev}]: {pat} (-{pen})")
        bd["future_fit"] -= pen
    bd["future_fit"] = max(0, min(15, bd["future_fit"]))

    # 4. Focus load (0-15): the ADHD guardrail. Too many active pursuits and
    #    every new candidate pays for it, automatically.
    limit = focus_limit(limit)
    active_count = len(active_streams or [])
    bd["focus_load"] = max(0, 15 - attention * 5 - max(0, active_count - limit) * 2)
    if active_count > limit:
        flags.append(f"over-limit: {active_count} active streams (limit {limit}) — "
                     "new candidates taxed until something exits")

    # 5. Perception (0-15): the pride test. The user chose MLM; this axis does
    # not judge that choice. It asks: can you promote this for the product
    # alone, with pride, to your own followers?
    bd["perception"] = max(0, 15 - risk * 7)
    if risk >= 2:
        flags.append("opportunity-only: the pitch only works as income — "
                     "no standalone product value for followers")

    # 6. Audience fit (0-15): does it match audiences you can actually reach?
    user_auds = [a.lower() for a in (user_audiences or [])]
    if not user_auds or not cand_audiences:
        bd["audience_fit"] = 8
        flags.append("audience-unverified: add audiences to the registry and the intel file")
    else:
        overlap = len(set(user_auds) & set(cand_audiences))
        bd["audience_fit"] = 15 if overlap >= 2 else (10 if overlap == 1 else 3)
        if overlap == 0:
            flags.append(f"no-audience-fit: targets {cand_audiences}, you reach {user_auds}")

    total = sum(bd.values())
    return {"name": name, "total": total, "band": _band(total), "breakdown": bd,
            "flags": flags, "verified_inputs": verified_inputs,
            "assumed_inputs": assumed_inputs}


def load_registry():
    if not os.path.exists(USER_FILE):
        return {"streams": []}
    with open(USER_FILE) as f:
        return json.load(f)


def review_report(registry, limit=None):
    """The grounding pass. Facts only: earn / promote / test status per stream."""
    limit = focus_limit(limit)
    streams = registry.get("streams", [])
    active = [s for s in streams if s.get("status") == "active"]
    lines = [f"ACTIVE PURSUITS: {len(active)} (focus limit {limit})"]
    total_income, income_known = 0, False
    rent, untested, unverified = [], [], []
    for s in active:
        name = s.get("name", "?")
        inc = s.get("monthly_income_usd")
        promoting, tested = bool(s.get("promoting")), bool(s.get("personally_tested"))
        if isinstance(inc, (int, float)):
            income_known = True
            total_income += inc
        else:
            unverified.append(name)
        if isinstance(inc, (int, float)) and inc == 0 and not promoting:
            rent.append(name)  # known-zero only; unverified income is flagged separately
        if promoting and not tested:
            untested.append(name)
        lines.append(f"  - {name} [{s.get('lane', 'no lane')}] "
                     f"income={'$' + str(inc) if isinstance(inc, (int, float)) else 'UNVERIFIED'} "
                     f"promoting={'yes' if promoting else 'no'} "
                     f"tested={'yes' if tested else 'no'}")
    if income_known:
        lines.append(f"COUNTED MONTHLY INCOME: ${total_income:.0f} (streams with numbers only)")
    if unverified:
        lines.append("INCOME UNVERIFIED (ground these in a number): " + ", ".join(unverified))
    if rent:
        lines.append("ATTENTION RENT (active, earns nothing, not promoted): " + ", ".join(rent))
    if untested:
        lines.append("PROMOTING UNTESTED (claims without lived experience): " + ", ".join(untested))
    for status, label in (("dormant", "DORMANT (holding, not building)"),
                          ("testing", "IN TESTING (trial running — needs a deadline)"),
                          ("exiting", "EXITING")):
        names = [s.get("name", "?") for s in streams if s.get("status") == status]
        if names:
            lines.append(f"{label}: " + ", ".join(names))
    if len(active) > limit:
        lines.append(f"COACHING FACT: {len(active)} active pursuits exceeds the {limit}-stream "
                     "focus limit. Something must exit before anything new is added.")
    return "\n".join(lines)


def cmd_evaluate(a):
    registry = load_registry()
    active = [s for s in registry.get("streams", []) if s.get("status") == "active"]
    user_audiences = registry.get("audiences", [])
    if a.intel:
        with open(a.intel) as f:
            cand = json.load(f)
        r = evaluate_candidate(cand, active, user_audiences, a.focus_limit)
    else:
        cand = {
            "name": a.name, "personally_tested": a.tested,
            "personal_benefit": a.benefit, "overlaps_active": a.overlaps,
            "recurring_income": a.recurring, "vehicle_momentum": a.momentum,
            "perception_risk": a.perception_risk, "attention_cost": a.attention_cost,
        }
        r = evaluate_candidate(cand, active, user_audiences, a.focus_limit)
    print(f"{r['name']}: {r['total']}/100 → {r['band']}")
    for k, v in r["breakdown"].items():
        print(f"  {k}: {v}")
    if r["verified_inputs"]:
        print(f"  verified: {', '.join(r['verified_inputs'])}")
    if r["assumed_inputs"]:
        print(f"  ASSUMED (not verified): {', '.join(r['assumed_inputs'])}")
    for f_ in r["flags"]:
        print(f"  FLAG: {f_}")
    print("Score proposes. You decide.")


def cmd_review(a):
    print(review_report(load_registry(), a.focus_limit))
    print("Facts, not feelings. Score proposes. You decide.")


def main():
    p = argparse.ArgumentParser(description="Focus coach: evaluate opportunities, review commitments.")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("evaluate", help="Score a candidate opportunity 0-100.")
    e.add_argument("--intel", default=None,
                   help="Candidate intel file from intel.py (verified inputs). "
                        "Without it, all inputs are marked ASSUMED.")
    e.add_argument("--name", default="candidate")
    e.add_argument("--tested", action="store_true")
    e.add_argument("--benefit", type=int, default=0, choices=[0, 1, 2])
    e.add_argument("--overlaps", type=int, default=0)
    e.add_argument("--recurring", action="store_true")
    e.add_argument("--momentum", type=int, default=0, choices=[0, 1, 2])
    e.add_argument("--perception-risk", type=int, default=1, choices=[0, 1, 2])
    e.add_argument("--attention-cost", type=int, default=1, choices=[0, 1, 2])
    e.add_argument("--focus-limit", type=int, default=None)
    e.set_defaults(func=cmd_evaluate)

    r = sub.add_parser("review", help="Grounding report over your stream registry.")
    r.add_argument("--focus-limit", type=int, default=None)
    r.set_defaults(func=cmd_review)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    sys.exit(main())
