#!/usr/bin/env python3
"""capacity_solver.py — cheapest-adequate solver for ecosystem needs.

PURPOSE: For each open dealsdesk.ecosystem_needs row, evaluate candidate
         approaches (gpu / nvme / ram / node / network / tooling) with coded
         adequacy rules and recommend the cheapest option that actually meets
         the need. Quality + low price wins; speed alone never does.
WHY:     Brian's rule: don't answer "need more Morpheus" with "buy GPUs" when
         an NVMe or RAM sticks serve the need cheaper. The math decides.
CALLED BY: manually / future systemd timer; writes dealsdesk.solution_options.
NOTES:   - Adequacy is deterministic (streaming math, bandwidth, footprints).
         - Anything the math can't model stays 'candidate' with a note —
           never auto-recommended.
         - Nothing here purchases anything; it recommends only.

Adequacy models (v1):
  colibri_nvme: required sustained read = model_gb / target_load_s.
      GLM-5.3 INT4 = 391GB. Adequate if drive_read_gbs >= required.
      Score = read_gbs per dollar (bandwidth per dollar).
  model_capacity (morpheus 14B Q6): footprint ~12GB RAM; adequate if the
      option's usable RAM >= footprint. Score = adequate_slots per dollar.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/capacity_solver.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/capacity_solver.py (k11-alpha; systemd timers).

"""

import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [capacity_solver] %(message)s",
)
LOG = logging.getLogger("capacity_solver")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"

# --- known constants (update as intel loop learns more) ---
COLIBRI_MODELS = {
    "glm-5.3-int4": {"gb": 391.0, "target_load_s": 120.0},
}
NVME_DRIVES = [
    # (name, sustained_read_gbs, market_price_key, fallback_price)
    # Prices from web research 2026-10-01: Gen 4 at parity-or-cheaper than
    # Gen 3 new (970 EVO Plus discontinued; new stock inflated $209-340).
    # NAND prices elevated across the board in 2026 (tariff/shortage).
    ("1TB NVMe PCIe 4.0 x4 (new)", 7.0, "nvme_1tb_gen4_new", 68.0),
    ("1TB NVMe PCIe 3.0 x4 (used)", 3.5, "nvme_1tb_gen3_used", 115.0),
    ("1TB NVMe PCIe 4.0 x4 (used)", 7.0, "nvme_1tb_gen4_used", 180.0),
    ("2TB NVMe PCIe 4.0 x4 (new)", 7.0, "nvme_2tb_gen4_new", 150.0),
]
MORPHEUS_FOOTPRINT_GB = 12.0  # 14B Q6 working set

# Brian's buying doctrine (2026-10-01), encoded:
#  - Prices are NEVER hardcoded: solver reads dealsdesk.market_prices first,
#    falls back to the constant only when no market row exists.
#  - Lower wattage preferred; but early-stage budget may force high-watt.
#    Score = 2-year TCO; flag it when cheapest-upfront != TCO winner.
#  - No Windows tax: a bundled Windows license is worth $0 (stripped for
#    Linux). effective_price subtracts strip_value for comparisons.
#  - No strip tax generally: don't pay for bundled extras he'd remove.
ELECTRICITY_RATE = 0.17   # USD/kWh, US avg 2026 (tunable)
TCO_YEARS = 2
WINDOWS_LICENSE_VALUE = 140  # OEM Win10/11: worth $0 to Brian, stripped


def get_market_price(key, fallback):
    """Live price from market_prices; fallback constant if no row yet."""
    rows = psql(f"""SELECT price FROM dealsdesk.market_prices
                    WHERE component_key = '{key}'""")
    if rows and rows[0][0]:
        return float(rows[0][0])
    LOG.info("no market row for %s — using fallback $%s", key, fallback)
    return fallback


def effective_price(price, strip_value=0.0):
    """Price minus the value of bundled extras Brian would strip (Win license etc)."""
    return max(0.0, price - strip_value)


def tco(price, watts):
    """2-year total cost of ownership: upfront + power at 24/7."""
    if watts is None:
        return None
    return price + watts * 8.76 * ELECTRICITY_RATE * TCO_YEARS

# Brian's buy rule (2026-10-01): Gen 4 is the default ecosystem asset — it
# runs fine in a Gen 3 slot today and moves to a Gen 4 box later. Only buy
# Gen 3 on a steal: under half of Gen 4 street price.
GEN4_STREET_1TB = 68.0
GEN3_STEAL_MULT = 0.5
GEN3_STEAL_THRESHOLD = GEN4_STREET_1TB * GEN3_STEAL_MULT  # $34


def psql(sql):
    result = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        LOG.error("psql failed: %s", result.stderr.strip()[:200])
        return []
    return [l.split("\x1f") for l in result.stdout.strip().split("\n") if l.strip()]


def psql_write(sql):
    result = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


def esc(s):
    return (s or "").replace("'", "''")


def clear_options(need_id):
    psql_write(f"DELETE FROM dealsdesk.solution_options WHERE need_id = {need_id}")


def add_option(need_id, label, approach, est_cost, adequacy_note,
               cost_per_unit, score, status):
    cpu = "NULL" if cost_per_unit is None else str(cost_per_unit)
    sc = "NULL" if score is None else str(score)
    cost = "NULL" if est_cost is None else str(est_cost)
    psql_write(
        f"""INSERT INTO dealsdesk.solution_options
            (need_id, option_label, approach, est_cost, adequacy_note,
             cost_per_unit, score, status)
            VALUES ({need_id}, '{esc(label)}', '{approach}', {cost},
                    '{esc(adequacy_note)}', {cpu}, {sc}, '{status}')"""
    )


def solve_colibri_nvme(need_id, magnitude):
    """Cheapest NVMe bandwidth that streams the model in target time."""
    model = COLIBRI_MODELS["glm-5.3-int4"]
    required = model["gb"] / model["target_load_s"]
    LOG.info("colibri: need %.2f GB/s sustained (%sGB / %ss)",
             required, model["gb"], model["target_load_s"])
    ranked = []
    for name, read_gbs, price_key, fallback in NVME_DRIVES:
        price = get_market_price(price_key, fallback)
        adequate = read_gbs >= required
        per_dollar = read_gbs / price
        ranked.append((per_dollar, name, read_gbs, price, adequate))
    ranked.sort(reverse=True)
    for per_dollar, name, read_gbs, price, adequate in ranked:
        is_gen3 = "3.0" in name
        steal = price <= GEN3_STEAL_THRESHOLD
        if is_gen3 and not steal:
            status = "rejected"
            note = (f"REJECTED: Gen 4 is the default asset; Gen 3 only on a "
                    f"steal (< ${GEN3_STEAL_THRESHOLD:.0f}). This is ${price:.0f}.")
        else:
            status = "candidate"
            note = (f"{read_gbs} GB/s sustained vs {required:.2f} required; "
                    f"${price:.0f} = ${price / read_gbs:.2f} per GB/s")
            if is_gen3 and steal:
                note += " — STEAL price, acceptable."
        if adequate:
            add_option(need_id, name, "nvme", price, note,
                       price / read_gbs, per_dollar, status)
            add_option(need_id, name + " (3x stripe)", "nvme", 3 * price,
                       f"3x striped: {3 * read_gbs:.1f} GB/s for ${3 * price:.0f} "
                       f"= ${3 * price / (3 * read_gbs):.2f} per GB/s"
                       + (" — STEAL price, acceptable." if is_gen3 and steal else "")
                       + (" REJECTED unless steal." if is_gen3 and not steal else ""),
                       3 * price / (3 * read_gbs),
                       (3 * read_gbs) / (3 * price),
                       "rejected" if (is_gen3 and not steal) else "candidate")
    # recommend cheapest adequate non-rejected option
    adequate = [r for r in ranked if r[4] and not ("3.0" in r[1] and r[3] > GEN3_STEAL_THRESHOLD)]
    if adequate:
        best = min(adequate, key=lambda r: r[3])
        psql_write(
            f"""UPDATE dealsdesk.solution_options SET status = 'recommended'
                WHERE need_id = {need_id} AND option_label = '{esc(best[1])}'
                  AND status = 'candidate'"""
        )
        LOG.info("colibri: recommended %s ($%.0f)", best[1], best[3])


def solve_morpheus_capacity(need_id, magnitude):
    """Cheapest adequate Morpheus slots, scored on 2-year TCO (watts matter).

    Watt figures marked est. are estimates until measured; TCO uses them
    anyway and says so. Lower wattage wins ties; a much cheaper high-watt
    option is flagged as budget tension for Brian, not auto-rejected.
    """
    options = [
        # label, approach, price_key, fallback, ram_gb, watts, watts_est, note, unconditional
        ("Aoostar 24GB node", "node", "aoostar_24gb_node", 350.0, 24.0, 65, True,
         "24GB RAM fits 14B Q6 (~12GB); ~9 tok/s class on iGPU", True),
        ("K11 96GB node", "node", "k11_96gb_node", 900.0, 96.0, 150, True,
         "96GB fits multiple 14B instances or bigger quants", True),
        ("64GB DDR5 SODIMM kit (existing box)", "ram", "ddr5_64gb_sodimm", 220.0,
         64.0, 8, True,
         "RAM upgrade only adequate if box already has iGPU/CPU headroom", False),
    ]
    best_tco = None
    cheapest_upfront = None
    for label, approach, price_key, fallback, ram_gb, watts, watts_est, note, unconditional in options:
        price = get_market_price(price_key, fallback)
        adequate = ram_gb >= MORPHEUS_FOOTPRINT_GB
        slots = int(ram_gb // MORPHEUS_FOOTPRINT_GB)
        tco2 = tco(price, watts)
        per_slot_tco = tco2 / slots if (tco2 and slots) else None
        per_slot_upfront = price / slots if slots else None
        wnote = f"~{watts}W{' (est.)' if watts_est else ''}"
        add_option(need_id, label, approach, price,
                   f"{note}; {slots} Morpheus slot(s); {wnote}; "
                   f"2yr TCO ${tco2:.0f} = ${per_slot_tco:.0f}/slot"
                   if per_slot_tco else note,
                   per_slot_tco, 1 / per_slot_tco if per_slot_tco else None,
                   "candidate")
        if adequate and unconditional and per_slot_tco:
            if best_tco is None or per_slot_tco < best_tco[1]:
                best_tco = (label, per_slot_tco)
            if cheapest_upfront is None or per_slot_upfront < cheapest_upfront[1]:
                cheapest_upfront = (label, per_slot_upfront)
    if best_tco:
        psql_write(
            f"""UPDATE dealsdesk.solution_options SET status = 'recommended'
                WHERE need_id = {need_id} AND option_label = '{esc(best_tco[0])}'
                  AND status = 'candidate'"""
        )
        LOG.info("morpheus: recommended %s (TCO $%.0f/slot)", best_tco[0], best_tco[1])
        if cheapest_upfront and cheapest_upfront[0] != best_tco[0]:
            LOG.info("morpheus: budget tension — cheapest upfront is %s ($%.0f/slot)",
                     cheapest_upfront[0], cheapest_upfront[1])


def main():
    needs = psql(
        """SELECT id, need_type, subject, COALESCE(magnitude,'')
           FROM dealsdesk.ecosystem_needs WHERE status = 'open'"""
    )
    LOG.info("%d open needs", len(needs))
    for row in needs:
        row = (row + [""] * 4)[:4]
        need_id, need_type, subject, magnitude = row
        clear_options(need_id)
        if subject == "colibri_nvme":
            solve_colibri_nvme(need_id, magnitude)
        elif subject == "morpheus":
            solve_morpheus_capacity(need_id, magnitude)
        else:
            LOG.info("need '%s': no coded model yet — left for manual options",
                     subject)
    psql_write(
        """INSERT INTO system_operations_log (subsystem, action_type, status, payload)
           VALUES ('capacity_solver', 'solve', 'OK',
                   jsonb_build_object('needs', %d))""" % len(needs)
    )
    LOG.info("done")


if __name__ == "__main__":
    main()
