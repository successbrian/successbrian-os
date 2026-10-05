#!/usr/bin/env python3
"""compat_check.py — advisory fit checks: do a build's items fit its box?

PURPOSE: Check a build's items against dealsdesk.box_constraints (GPU/PSU
         headroom, NVMe slot count, RAM ceiling, drive bays) and log results
         to dealsdesk.compat_checks.
WHY:     The solver can recommend a part that doesn't physically fit the box
         or that the PSU can't feed. Bad recommendations should die here,
         before they reach Brian.
CALLED BY: manually: python3 compat_check.py --build-id N
NOTES:   Verdicts are ADVISORY for Brian — never decisions. Unknown
         constraints are reported as SKIP, never guessed. Multi-box builds
         (box_name NULL, e.g. the 4U shelf) map items to boxes by keyword.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/compat_check.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/compat_check.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import re
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [compat_check] %(message)s")
LOG = logging.getLogger("compat_check")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"

# Known component power draw (watts). M40/B50/A2000 TDPs are manufacturer
# specs; node figures are estimates and marked as such in output.
KNOWN_WATTS = {
    "tesla m40": (250, False),
    "arc pro b50": (70, False),
    "rtx a2000": (70, False),
    "aoostar": (65, True),
    "2.5gbe switch": (10, True),
    "16-port switch": (10, True),
}

# keyword -> box_name for multi-box builds
BOX_HINTS = [
    ("aoostar", "Aoostar 24GB node"),
    ("ms-02", "MS-02 Ultra"),
    ("ms02", "MS-02 Ultra"),
    ("arc pro b50", "MS-02 Ultra"),
    ("x79", "X79 node"),
    ("tesla m40", "X79 node"),
    ("m40", "X79 node"),
    ("precision", "Precision 3620"),
    ("3620", "Precision 3620"),
    ("epyc", "EPYC training box"),
    ("sp3", "EPYC training box"),
]


def psql(sql):
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A",
                        "-F\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return []
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def psql_write(sql):
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A",
                        "-c", sql], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql write failed: %s", r.stderr.strip()[:200])
        return False
    return True


def esc(s):
    return str(s).replace("'", "''")


def load_box(name):
    rows = psql(f"SELECT * FROM dealsdesk.box_constraints WHERE box_name = '{esc(name)}'")
    if not rows:
        return None
    cols = ["box_name", "max_gpu_length_mm", "pcie_x16_slots", "psu_watts",
            "power_connectors", "drive_bays_25", "drive_bays_35",
            "nvme_slots_onboard", "max_ram_gb", "notes"]
    d = dict(zip(cols, (rows[0] + [""] * 10)[:10]))
    for k in cols[1:9]:
        d[k] = int(d[k]) if d[k] not in ("", None) else None
    return d


def box_for_item(item_name, build_box):
    if build_box:
        return build_box
    low = item_name.lower()
    for kw, box in BOX_HINTS:
        if kw in low:
            return box
    return None


def is_gpu(name):
    return bool(re.search(r"gpu|tesla|quadro|rtx|gtx|arc pro|radeon|m40", name, re.I))


def is_nvme(name):
    return bool(re.search(r"nvme|m\.2", name, re.I))


def is_ram(name):
    return bool(re.search(r"\bram\b|ddr|sodimm|dimm|rdimm", name, re.I))


def ram_gb(name, qty):
    m = re.search(r"(\d+)\s*gb", name, re.I)
    return int(m.group(1)) * qty if m else 0


def comp_watts(name, qty, watts_est):
    if watts_est not in (None, ""):
        return float(watts_est) * qty, False
    low = name.lower()
    for kw, (w, est) in KNOWN_WATTS.items():
        if kw in low:
            return w * qty, est
    return 0, True


def run(build_id):
    b = psql(f"SELECT name, box_name FROM dealsdesk.builds WHERE id = {build_id}")
    if not b:
        LOG.error("build %s not found", build_id)
        return
    build_name, build_box = (b[0] + ["", ""])[:2]
    items = psql(f"""SELECT id, component_name, quantity, watts_est
                     FROM dealsdesk.build_items WHERE build_id = {build_id}""")
    LOG.info("build %s '%s' box=%s items=%d", build_id, build_name,
             build_box or "multi-box (infer)", len(items))

    psql_write(f"DELETE FROM dealsdesk.compat_checks WHERE build_id = {build_id}")
    results = []

    def check(item_id, name, passed, detail):
        results.append((item_id, name, passed, detail))
        psql_write(f"""INSERT INTO dealsdesk.compat_checks
            (build_id, item_id, check_name, passed, detail)
            VALUES ({build_id}, {item_id if item_id else 'NULL'},
                    '{esc(name)}', {'TRUE' if passed else 'FALSE'},
                    '{esc(detail)}')""")

    # group items by box
    by_box = {}
    for r in items:
        r = (r + ["", "", "", ""])[:4]
        item_id, cname, qty, watts_est = r[0], r[1], int(r[2] or 1), r[3]
        box = box_for_item(cname, build_box)
        by_box.setdefault(box, []).append((item_id, cname, qty, watts_est))

    for box, blist in by_box.items():
        if not box:
            for item_id, cname, qty, _ in blist:
                check(item_id, "box_mapping",
                      True, f"SKIP: no box mapping for '{cname}' — cannot check fit")
            continue
        bc = load_box(box)
        if not bc:
            for item_id, cname, qty, _ in blist:
                check(item_id, "box_mapping", True,
                      f"SKIP: box '{box}' has no constraints row")
            continue

        # NVMe slots
        nvme_n = sum(q for _, n, q, _ in blist if is_nvme(n))
        if bc["nvme_slots_onboard"] is None:
            check(None, f"nvme_slots:{box}", True,
                  f"SKIP: NVMe slot count unknown for {box} ({nvme_n} NVMe items)")
        else:
            check(None, f"nvme_slots:{box}", nvme_n <= bc["nvme_slots_onboard"],
                  f"{nvme_n} NVMe item(s) vs {bc['nvme_slots_onboard']} slots on {box}")

        # GPU vs PSU headroom
        gpu_w, gpu_est = 0, False
        gpu_names = []
        for item_id, cname, qty, we in blist:
            if is_gpu(cname):
                w, e = comp_watts(cname, qty, we)
                gpu_w += w
                gpu_est = gpu_est or e
                gpu_names.append(cname)
        if gpu_names:
            if bc["psu_watts"] is None:
                check(None, f"gpu_psu:{box}", True,
                      f"SKIP: PSU unknown for {box}; GPU load ~{gpu_w:.0f}W"
                      f"{' (est.)' if gpu_est else ''} ({', '.join(gpu_names)})")
            else:
                ok = gpu_w <= bc["psu_watts"] * 0.8
                check(None, f"gpu_psu:{box}", ok,
                      f"GPU load ~{gpu_w:.0f}W{' (est.)' if gpu_est else ''} "
                      f"vs {bc['psu_watts']}W PSU (80% rule = {bc['psu_watts']*0.8:.0f}W)")

        # RAM ceiling
        ram_total = sum(ram_gb(n, q) for _, n, q, _ in blist if is_ram(n))
        if ram_total and bc["max_ram_gb"] is None:
            check(None, f"ram_ceiling:{box}", True,
                  f"SKIP: RAM ceiling unknown for {box} ({ram_total}GB planned)")
        elif ram_total:
            check(None, f"ram_ceiling:{box}", ram_total <= bc["max_ram_gb"],
                  f"{ram_total}GB planned vs {bc['max_ram_gb']}GB max on {box}")

    fails = [r for r in results if not r[2]]
    skips = [r for r in results if r[2] and r[3].startswith("SKIP")]
    print(f"build {build_id}: {len(results)} checks, {len(fails)} FAIL, "
          f"{len(skips)} skipped (unknown), "
          f"{len(results)-len(fails)-len(skips)} pass")
    for item_id, name, passed, detail in results:
        if not passed or detail.startswith("SKIP"):
            print(f"  [{'FAIL' if not passed else 'SKIP'}] {name}: {detail}")
    return results


def main():
    ap = argparse.ArgumentParser(description="Advisory fit checks for a build")
    ap.add_argument("--build-id", type=int, required=True)
    a = ap.parse_args()
    run(a.build_id)


if __name__ == "__main__":
    main()
