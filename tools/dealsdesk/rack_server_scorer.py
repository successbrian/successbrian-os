#!/usr/bin/env python3
"""rack_server_scorer.py — rank rack-server candidates for the Colibri/DB expansion.

PURPOSE: Score and rank rack-server listings against Brian's 2026-10-08
         sourcing directive: high-RAM (64GB+) rack servers for (1) Colibri
         DeepSeek-150B inference and (2) PostgreSQL database serving.

WHY:     Brian wants DealsDesk to *seriously* source these boxes, which means
         the ranking logic must be code, not a chat message. The score encodes
         his hardware reasoning: Colibri is a 3-tier (VRAM/RAM/NVMe) MoE
         streaming stack for an ~85GB model, so inference speed scales with
         how much of the model stays resident in RAM; PostgreSQL wants RAM as
         buffer pool. A candidate that can't hold the model resident is a
         streaming box (~1 tok/s, which Brian is happy with); one that can is
         a resident box (several tok/s). Without this module every evaluation
         re-derives the math by hand and drifts.

CALLED BY: DealsDesk agent (directive arrived via knowledge_bridge row 23926,
           urgency high); manually for one-off listing checks; future systemd
           timer once candidate ingestion exists.

NOTES:   - Speed figures are estimates from the k11-alpha Colibri deployment
           (0.66 tok/s streaming, Sep 2026) and DDR3/DDR4 bandwidth math, NOT
           benchmarks of the candidates. Mark them as such downstream.
         - Model size ~85GB is the measured Sep 2026 Colibri INT4 build
           (DeepSeek-V4-Flash-reap-150b, 17 safetensors shards on k11-alpha).
         - This module never writes dealsdesk.ecosystem_needs — DealsDesk owns
           that table; needs enter via the knowledge_bridge feed. It also never
           purchases anything; it ranks only.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/rack_server_scorer.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/rack_server_scorer.py (k11-alpha; when wired to a timer).

"""

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [rack_scorer] %(message)s")
LOG = logging.getLogger("rack_scorer")

# --- Directive constants (Brian 2026-10-08) -----------------------------------
MIN_RAM_GB = 64          # hard floor per the directive
MODEL_GB = 85            # measured Colibri 150B INT4 build, Sep 2026
RESIDENT_HEADROOM_GB = 11  # OS + KV headroom for full residency
RESIDENT_MIN_GB = MODEL_GB + RESIDENT_HEADROOM_GB  # 96

# Reference bar: Garland Computers DL380 Gen9, 2026-10-08 listing.
REFERENCE_BAR = {
    "name": "Garland DL380 Gen9 (reference bar)",
    "price": 384.99,
    "ram_gb": 64,
    "ram_gen": "DDR4",
    "cores": 24,
    "threads": 48,
    "nvme": True,      # Gen9 is NVMe-capable (may need enablement kit)
    "generation": 9,
    "psu_w": 750,
    "notes": "2x E5-2680 v3, P440ar, 2x300GB SAS, no rails/cords/OS",
}

RAM_GEN_RANK = {"DDR3": 0, "DDR4": 1, "DDR5": 2}


def residency_tier(ram_gb):
    """How the 150B model sits on this box. Returns (tier, note)."""
    if ram_gb < MIN_RAM_GB:
        return ("reject", "below %dGB directive floor" % MIN_RAM_GB)
    if ram_gb >= RESIDENT_MIN_GB:
        return ("resident",
                "full 85GB model resident + headroom (est. several tok/s)")
    return ("streaming",
            "model streams from SSD/NVMe tier (est. ~1 tok/s; acceptable)")


def score_candidate(c):
    """Score one candidate dict. Returns the dict with scoring fields added."""
    price = float(c.get("price", 0) or 0)
    ram_gb = int(c.get("ram_gb", 0) or 0)
    cores = int(c.get("cores", 0) or 0)
    ram_gen = str(c.get("ram_gen", "DDR3")).upper()
    nvme = bool(c.get("nvme", False))
    gen = int(c.get("generation", 0) or 0)

    tier, tier_note = residency_tier(ram_gb)
    c["tier"] = tier
    c["tier_note"] = tier_note
    c["dollar_per_gb_ram"] = round(price / ram_gb, 2) if ram_gb else None
    c["dollar_per_core"] = round(price / cores, 2) if cores else None

    if tier == "reject":
        c["score"] = -1.0
        c["verdict"] = "REJECT"
        return c

    # Rank score: residency first, then economics, then platform quality.
    # Weights are Brian's priorities: resident-150B capability outranks price.
    score = 0.0
    score += 100.0 if tier == "resident" else 40.0
    score += 20.0 * RAM_GEN_RANK.get(ram_gen, 0)   # DDR4 +20, DDR5 +40
    score += 15.0 if nvme else 0.0                  # Colibri's stream tier
    score += 10.0 if gen >= 9 else 0.0              # Gen9+: NVMe, AVX2, DDR4
    # Cheaper per-GB RAM wins among equals (normalized against the bar).
    bar_dpg = REFERENCE_BAR["price"] / REFERENCE_BAR["ram_gb"]
    if c["dollar_per_gb_ram"]:
        score += max(0.0, 30.0 * (bar_dpg - c["dollar_per_gb_ram"]) / bar_dpg)
    c["score"] = round(score, 1)
    c["verdict"] = "RESIDENT-150B" if tier == "resident" else "STREAMING-150B"
    return c


def rank(candidates):
    scored = [score_candidate(dict(c)) for c in candidates]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rank rack-server candidates.")
    ap.add_argument("--json", help="JSON file with a list of candidate dicts")
    ap.add_argument("--bar", action="store_true",
                    help="Score the reference-bar listing and exit")
    args = ap.parse_args(argv)

    if args.bar:
        print(json.dumps(score_candidate(dict(REFERENCE_BAR)), indent=2))
        return 0

    if not args.json:
        ap.error("--json <file> or --bar is required")

    with open(args.json) as f:
        candidates = json.load(f)
    for c in rank(candidates):
        LOG.info("%-42s score=%6.1f tier=%-9s $/GB=%s $/core=%s verdict=%s",
                 c.get("name", "?")[:42], c["score"], c["tier"],
                 c["dollar_per_gb_ram"], c["dollar_per_core"], c["verdict"])
    print(json.dumps(rank(candidates), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
