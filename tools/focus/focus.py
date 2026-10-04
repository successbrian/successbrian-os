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

CALLED BY:
    - Humans: python3 focus.py evaluate --name ... / python3 focus.py review
    - Weekly cron (review): the scheduled coaching pass.
    - Importable: evaluate_candidate(dict, active_streams) -> dict.

NOTES:
    - Product-generic: no user-specific streams are hardcoded. Personal
      registry lives in user_focus.json (gitignored, never committed);
      user_focus.example.json is the committed template.
    - All scores are traceable to input fields; rerunning with the same
      inputs gives the same result.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
USER_FILE = os.path.join(HERE, "user_focus.json")
EXAMPLE_FILE = os.path.join(HERE, "user_focus.example.json")

BANDS = [(70, "strong"), (45, "consider"), (0, "shelve-or-reshape")]
DEFAULT_FOCUS_LIMIT = 5  # product default; override per user, never hardcoded per person


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


def evaluate_candidate(cand, active_streams, limit=None):
    """Deterministic 0-100 score. cand fields (all plain facts, no judgment):

    name, personally_tested (bool), personal_benefit (0-2),
    fills_unique_lane (bool), overlaps_active (int: active streams in same lane),
    recurring_income (bool), vehicle_momentum (0-2: 0 declining/unknown,
    1 stable, 2 growing), perception_risk (0-2: 0 clean, 1 needs explaining,
    2 fails the smell test), attention_cost (0-2: 0 runs itself, 1 some
    effort, 2 demands real focus).
    """
    bd = {}
    flags = []

    tested = bool(cand.get("personally_tested"))
    benefit = max(0, min(2, int(cand.get("personal_benefit") or 0)))

    # 1. Life value (0-25): lived benefit counts; untested enthusiasm is capped.
    if tested:
        bd["life_value"] = min(25, 10 + benefit * 7)
    else:
        bd["life_value"] = benefit * 3  # max 6: enthusiasm is not evidence
        if benefit > 0:
            flags.append("untested-enthusiasm: benefit claimed without personal testing")

    # 2. Ecosystem fit (0-25): a lane nobody owns scores; duplication is taxed.
    overlaps = max(0, int(cand.get("overlaps_active") or 0))
    eco = 25 - 8 * overlaps
    if cand.get("fills_unique_lane"):
        eco = min(25, eco + 5)
    bd["ecosystem_fit"] = max(0, eco)
    if overlaps >= 2:
        flags.append(f"lane-duplication: {overlaps} active streams already cover this lane")

    # 3. Future alignment (0-20): recurring income + a vehicle with momentum.
    bd["future_fit"] = (8 if cand.get("recurring_income") else 0) + max(
        0, min(2, int(cand.get("vehicle_momentum") or 0))) * 6

    # 4. Focus load (0-15): the ADHD guardrail. Too many active pursuits and
    #    every new candidate pays for it, automatically.
    limit = focus_limit(limit)
    active_count = len(active_streams or [])
    load = 15 - max(0, min(2, int(cand.get("attention_cost") or 0))) * 5
    load -= max(0, active_count - limit) * 2
    bd["focus_load"] = max(0, load)
    if active_count > limit:
        flags.append(f"over-limit: {active_count} active streams (limit {limit}) — "
                     "new candidates taxed until something exits")

    # 5. Perception test (0-15): would a cold audience buy the story?
    bd["perception"] = max(0, 15 - max(0, min(2, int(cand.get("perception_risk") or 0))) * 7)
    if int(cand.get("perception_risk") or 0) >= 2:
        flags.append("perception-fail: would not survive a cold audience's smell test")

    total = sum(bd.values())
    return {"name": cand.get("name", "candidate"), "total": total,
            "band": _band(total), "breakdown": bd, "flags": flags}


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
    lines = []
    lines.append(f"ACTIVE PURSUITS: {len(active)} (focus limit {limit})")
    total_income = 0
    income_known = False
    rent, untested, unverified = [], [], []
    for s in active:
        name = s.get("name", "?")
        inc = s.get("monthly_income_usd")
        promoting = bool(s.get("promoting"))
        tested = bool(s.get("personally_tested"))
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
    dormant = [s.get("name", "?") for s in streams if s.get("status") == "dormant"]
    if dormant:
        lines.append("DORMANT (holding, not building): " + ", ".join(dormant))
    exiting = [s.get("name", "?") for s in streams if s.get("status") == "exiting"]
    if exiting:
        lines.append("EXITING: " + ", ".join(exiting))
    if len(active) > limit:
        lines.append(f"COACHING FACT: {len(active)} active pursuits exceeds the {limit}-stream "
                     "focus limit. Something must exit before anything new is added.")
    return "\n".join(lines)


def cmd_evaluate(a):
    cand = {
        "name": a.name,
        "personally_tested": a.tested,
        "personal_benefit": a.benefit,
        "fills_unique_lane": a.unique_lane,
        "overlaps_active": a.overlaps,
        "recurring_income": a.recurring,
        "vehicle_momentum": a.momentum,
        "perception_risk": a.perception_risk,
        "attention_cost": a.attention_cost,
    }
    active = [s for s in load_registry().get("streams", []) if s.get("status") == "active"]
    r = evaluate_candidate(cand, active, a.focus_limit)
    print(f"{r['name']}: {r['total']}/100 → {r['band']}")
    for k, v in r["breakdown"].items():
        print(f"  {k}: {v}")
    for f in r["flags"]:
        print(f"  FLAG: {f}")
    print("Score proposes. You decide.")


def cmd_review(a):
    print(review_report(load_registry(), a.focus_limit))
    print("Facts, not feelings. Score proposes. You decide.")


def main():
    p = argparse.ArgumentParser(description="Focus coach: evaluate opportunities, review commitments.")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("evaluate", help="Score a candidate opportunity 0-100.")
    e.add_argument("--name", required=True)
    e.add_argument("--tested", action="store_true", help="You have personally used it.")
    e.add_argument("--benefit", type=int, default=0, choices=[0, 1, 2],
                   help="0 none/unknown, 1 mild, 2 strong lived benefit.")
    e.add_argument("--unique-lane", action="store_true",
                   help="Fills a lane none of your active streams cover.")
    e.add_argument("--overlaps", type=int, default=0,
                   help="How many active streams already cover this lane.")
    e.add_argument("--recurring", action="store_true", help="Pays recurring/residual income.")
    e.add_argument("--momentum", type=int, default=0, choices=[0, 1, 2],
                   help="Vehicle momentum: 0 declining/unknown, 1 stable, 2 growing.")
    e.add_argument("--perception-risk", type=int, default=0, choices=[0, 1, 2],
                   help="0 clean, 1 needs explaining, 2 fails the smell test.")
    e.add_argument("--attention-cost", type=int, default=1, choices=[0, 1, 2],
                   help="0 runs itself, 1 some effort, 2 demands real focus.")
    e.add_argument("--focus-limit", type=int, default=None,
                   help="Override the active-stream focus limit (default 5, or FOCUS_LIMIT env).")
    e.set_defaults(func=cmd_evaluate)

    r = sub.add_parser("review", help="Grounding report over your stream registry.")
    r.add_argument("--focus-limit", type=int, default=None,
                   help="Override the active-stream focus limit (default 5, or FOCUS_LIMIT env).")
    r.set_defaults(func=cmd_review)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    sys.exit(main())
