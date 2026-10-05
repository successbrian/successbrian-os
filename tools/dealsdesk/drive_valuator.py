#!/usr/bin/env python3
"""drive_valuator.py — sliding-scale used-drive pricing based on health.

PURPOSE: Value a used hard drive / SSD from its SMART health. Returns a
         health score (0-100), the max sane price as a fraction of new, and
         a BUY / OVERPRICED / REJECT verdict.
WHY:     Brian's rule: drive price must slide with drive health. A 98%-health
         drive is worth close to new; a 75%-health drive is steal-only.
CALLED BY: manually when vetting a used drive listing; future: DealsDesk vet.
NOTES:   Tier boundaries live in dealsdesk.drive_price_tiers (tunable data,
         not hardcoded). The health rubric below is v1 — penalties are
         documented and adjustable.

Health rubric (v1):
  start 100
  SMART overall FAIL                -> 0 (reject outright)
  reallocated sectors 1-10          -> -15
  reallocated sectors > 10          -> -35
  pending sectors > 0               -> -15
  power-on hours                    -> -1 per 2000h, capped at -25
  clamp to 0..100
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/drive_valuator.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/drive_valuator.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [drive_valuator] %(message)s")
LOG = logging.getLogger("drive_valuator")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql):
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A",
                        "-F\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return []
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def health_score(hours, reallocated, pending, smart_pass):
    """0-100 health score from SMART readings. v1 rubric, see module docstring."""
    if not smart_pass:
        return 0
    score = 100
    if reallocated > 10:
        score -= 35
    elif reallocated > 0:
        score -= 15
    if pending > 0:
        score -= 15
    score -= min(25, hours / 2000)
    return max(0, min(100, int(round(score))))


def tier_for(health):
    rows = psql("""SELECT min_health, max_health, max_pct_new, label
                   FROM dealsdesk.drive_price_tiers ORDER BY min_health DESC""")
    for r in rows:
        r = (r + [""] * 4)[:4]
        if int(r[0]) <= health <= int(r[1]):
            return {"min": int(r[0]), "max": int(r[1]),
                    "pct": float(r[2]), "label": r[3]}
    return {"min": 0, "max": 0, "pct": 0.0, "label": "reject"}


def evaluate(new_price, ask_price, hours, reallocated, pending, smart_pass,
             unknown_health=False):
    if unknown_health:
        return {"health": None, "tier": "unknown", "max_price": 0.0,
                "verdict": "REJECT",
                "reason": "health unknown — never buy a drive blind"}
    health = health_score(hours, reallocated, pending, smart_pass)
    tier = tier_for(health)
    max_price = round(new_price * tier["pct"] / 100, 2)
    if health <= 0 or tier["pct"] <= 0:
        verdict = "REJECT"
        reason = "health too low — not worth any price"
    elif ask_price <= max_price:
        verdict = "BUY"
        reason = f"ask ${ask_price:.0f} <= max ${max_price:.0f} for {health}% health"
    else:
        verdict = "OVERPRICED"
        reason = f"ask ${ask_price:.0f} > max ${max_price:.0f} for {health}% health"
    return {"health": health, "tier": tier["label"], "max_price": max_price,
            "verdict": verdict, "reason": reason}


def main():
    ap = argparse.ArgumentParser(description="Value a used drive by SMART health")
    ap.add_argument("--new-price", type=float, required=True)
    ap.add_argument("--ask-price", type=float, required=True)
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--reallocated", type=int, default=0)
    ap.add_argument("--pending", type=int, default=0)
    ap.add_argument("--smart-pass", dest="smart_pass", action="store_true", default=True)
    ap.add_argument("--smart-fail", dest="smart_pass", action="store_false")
    ap.add_argument("--unknown-health", action="store_true",
                    help="no SMART/health data available: reject outright")
    a = ap.parse_args()
    r = evaluate(a.new_price, a.ask_price, a.hours, a.reallocated,
                 a.pending, a.smart_pass, a.unknown_health)
    h = f"{r['health']}%" if r["health"] is not None else "unknown"
    print(f"health: {h} ({r['tier']})")
    print(f"max sane price: ${r['max_price']:.2f}")
    print(f"verdict: {r['verdict']} — {r['reason']}")


if __name__ == "__main__":
    main()
