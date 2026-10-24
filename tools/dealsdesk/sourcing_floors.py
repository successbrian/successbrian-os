#!/usr/bin/env python3
"""sourcing_floors.py — minimum sizes for parts DealsDesk may source.

Owner directive 2026-10-20 (Brian): "we want to reject ram 8GB and
smaller, k80, nvme under 256GB, ssd's under 2TB (we want 2TB and up for
these)... hhd's keep only 1TB and up... ideally much larger."

These are floors, not traps (see hardware_traps.py for the trap
concept): an undersized part is not dangerous, it is just not worth
fleet money or a slot. Undersized listings are rejected so they never
surface as wins.

    RAM   reject 8GB and smaller          (parts listings: 8GB sticks are
                                           $0 to us — owner ruling — so
                                           they are never sourced. NOTE:
                                           this floor is for PARTS. Whole
                                           machines shipping 8GB stay in
                                           searches; mini_node_scorer does
                                           not reject them.)
    NVMe  reject under 256GB              (parts listings. Whole machines
                                           shipping a small NVMe are NOT
                                           rejected: the drive is $0 to us
                                           and gets pulled for a 256/512GB
                                           drive — mini_node_scorer.)
    SSD   reject under the 1.92TB class   (SATA/other SSDs: 1.92TB and
                                           up — THE STANDARD, owner
                                           ruling 2026-10-20, promoted
                                           from exception to standard:
                                           enterprise 1.92TB IS the
                                           2TB class; state the floor
                                           in real capacity)
                                           a 2tb")
    HDD   keep 1TB and up                 (floor only — ideally much
                                           larger; see DESIRED_GB)

Classification is by title keywords, NVMe first (an NVMe is judged by
the NVMe floor, never the SSD floor). Capacity is the largest GB/TB
figure in the title, so kit totals ("32GB (2x16GB)") read correctly.

CALLED BY: dealsdesk/src/validation_gates.py (listing reject) and
         tools/dealsdesk/mini_node_scorer.py (RAM gate). Manually:
         `python3 sourcing_floors.py "listing title"` or `--selftest`.

    CANONICAL SOURCE: successbrian-os/tools/dealsdesk/sourcing_floors.py
    DEPLOYED COPY: ~/dealsdesk/src/sourcing_floors.py (keep in sync).
"""

import argparse
import re
import sys

# --- Floors (GB) ---------------------------------------------------------------
RAM_REJECT_AT_OR_BELOW_GB = 8      # 8GB and smaller: rejected
NVME_MIN_GB = 256                  # under 256GB: rejected
SSD_MIN_GB = 1920                  # the standard: 1.92TB and up (owner ruling 2026-10-20)
HDD_MIN_GB = 1000                  # "1TB and up" (marketing TB)
DESIRED_GB = {"hdd": 8192, "ssd": 4096, "nvme": 1024}  # "ideally much larger"

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB)", re.IGNORECASE)
_NVME_KEYS = ("nvme", "m.2", "m2 ")
_HDD_KEYS = ("hdd", "hard drive", "hard disk", "rpm", "spinning")
_SSD_KEYS = ("ssd", "solid state")
_RAM_KEYS = ("ddr3", "ddr4", "ddr5", "so-dimm", "sodimm", "rdimm",
             "udimm", "dimm", "memory")


def capacity_gb(text):
    """Largest capacity figure in the text, normalized to GB, or None."""
    best = None
    for num, unit in _SIZE_RE.findall(str(text or "")):
        gb = float(num) * (1024 if unit.upper() == "TB" else 1)
        best = gb if best is None else max(best, gb)
    return best


def classify(text):
    """Part category from title keywords: nvme | hdd | ssd | ram | None."""
    t = str(text or "").lower()
    if any(k in t for k in _NVME_KEYS):
        return "nvme"
    if any(k in t for k in _HDD_KEYS):
        return "hdd"
    if any(k in t for k in _SSD_KEYS):
        return "ssd"
    if any(k in t for k in _RAM_KEYS):
        return "ram"
    return None


def check_listing(text):
    """Returns (ok, reason). ok=True when the listing meets its floor,
    is not a sized part we police, or states no size (floors judge what
    is stated; unverifiable size is a vetting question, not a floor)."""
    cat = classify(text)
    if cat is None:
        return True, "not a floored category"
    size = capacity_gb(text)
    if size is None:
        return True, "no size stated"
    if cat == "ram" and size <= RAM_REJECT_AT_OR_BELOW_GB:
        return False, ("RAM %gGB rejected: 8GB and smaller are out "
                       "(owner directive 2026-10-20)" % size)
    if cat == "nvme" and size < NVME_MIN_GB:
        return False, ("NVMe %gGB rejected: floor is 256GB "
                       "(owner directive 2026-10-20)" % size)
    if cat == "ssd" and size < SSD_MIN_GB:
        return False, ("SSD %gGB rejected: SSDs are 1.92TB and up only "
                       "(owner directive 2026-10-20)" % size)
    if cat == "hdd" and size < HDD_MIN_GB:
        return False, ("HDD %gGB rejected: HDDs keep 1TB and up only "
                       "(owner directive 2026-10-20)" % size)
    return True, "%s %gGB meets floor" % (cat, size)


_SELFTEST = [
    ("Crucial 8GB DDR4 SO-DIMM", False),
    ("Kingston 4GB DDR3 SODIMM", False),
    ("Samsung 16GB DDR4 3200 SO-DIMM", True),
    ("64GB (2x32GB) DDR4 RDIMM kit", True),
    ("Samsung 970 EVO 250GB NVMe M.2", False),
    ("WD Black SN850X 1TB NVMe", True),
    ("Kingston KC3000 2TB M.2 NVMe", True),
    ("Samsung 870 EVO 1TB SSD", False),
    ("Crucial MX500 500GB SSD", False),
    ("Samsung 990 PRO 2TB SSD", True),       # NVMe keyword wins over ssd
    ("SanDisk 1.92TB Enterprise SSD", True),  # 2TB class
    ("WD Red 1TB HDD 5400RPM", True),
    ("Seagate 500GB Hard Drive", False),
    ("WD Red Pro 12TB HDD", True),
    ("ASUS RTX 3060 12GB", True),             # not a floored category
    ("HP EliteDesk 800 G4 Mini i5-8500T", True),  # no size stated
]


def selftest():
    failures = 0
    for text, want in _SELFTEST:
        ok, reason = check_listing(text)
        good = ok == want
        failures += 0 if good else 1
        print("%s %-42r -> %-5s %s" % ("OK  " if good else "FAIL",
                                       text, ok, reason))
    print("selftest: %d/%d passed" % (len(_SELFTEST) - failures,
                                      len(_SELFTEST)))
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check a listing title against the sourcing floors.")
    ap.add_argument("text", nargs="?", help="listing title")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.text:
        ap.error("text or --selftest is required")
    ok, reason = check_listing(args.text)
    print(("PASS: " if ok else "REJECT: ") + reason)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
