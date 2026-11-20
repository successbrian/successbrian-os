#!/usr/bin/env python3
"""hardware_traps.py — the hardware trap registry, in code.

THE CONCEPT (Brian 2026-10-20): some hardware is a trap — the spec sheet
promises value the silicon cannot deliver for our workloads, so it won't
help us no matter the price. The Tesla K80's fake 24 GB and Raptor Lake's
self-degrading cores are the same trap wearing different clothes. Traps
are banned outright, not discounted: never recommend, never buy, never
let a deal scan surface one as a win.

UNIVERSAL SCOPE (Brian 2026-10-20): a trap fails in EVERY machine
class — inference, web hosting, database, scrapers, code runners, any
class invented later — at any price, including free, in any channel.
Class-fit is relative; traps are not. This registry sits ABOVE the
machine-class system (machine_classes.py): no class scorer may pass
what this registry bans, and the only way off this list is Brian
removing an entry on new evidence.

This module is the registry. Anything that sources, scores, or vets
hardware imports from here instead of re-deriving the list — because
Brian will forget, and the code must not.

SCOPE PRINCIPLE: bans track documented failure mechanisms, not brands
or generation vibes. A trap enters this registry only with its mechanism
written next to it, and a ban widens only on evidence. Deliberately NOT
traps, do not add without new evidence:
  - Tesla V100 / P40 / M40 — EOL (R580) but run modern stacks with pins;
    see docs/HARDWARE-TRAPS.md. Old is not a trap.
  - Intel Core Ultra / Arrow Lake — different design, no degradation
    finding. Newer is not a trap either.
  - AMD Ryzen anything — no entry, no evidence.

CALLED BY: tools/dealsdesk/mini_node_scorer.py (fleet-node gate) and
         dealsdesk/src/validation_gates.py (listing pipeline reject).
         Manually: `python3 hardware_traps.py "listing title"` or
         `--list` / `--selftest`.

NOTES:   - Prose rationale lives in docs/HARDWARE-TRAPS.md; this file is
           the enforceable source of truth and wins on conflict.
         - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/hardware_traps.py
         - DEPLOYED COPY: ~/dealsdesk/src/hardware_traps.py (keep in sync).
"""

import argparse
import json
import re
import sys

# --- The registry -------------------------------------------------------------
# Each trap: id, display name, kind of part, match patterns (applied to a
# listing title or part name, case-insensitive), the failure mechanism in
# one line, and the owner directive that banned it. Patterns are kept in
# sync with the gates that predated this module.
TRAPS = [
    {
        "id": "tesla_k80",
        "name": "NVIDIA Tesla K80",
        "kind": "gpu",
        "patterns": [r"tesla\s*k80", r"\bk80\b"],
        "mechanism": ("Dual GK210 12GB GPUs sold as one 24GB card; Kepler — "
                      "R470 final driver, CUDA 11.x ceiling, no tensor "
                      "cores. The VRAM number is the lie."),
        "directive": "Owner directive 2026-10-12; agent contract rule 11.",
    },
    {
        "id": "raptor_lake_burnout",
        "name": "Intel 13th/14th gen (Raptor Lake) desktop CPU",
        "kind": "cpu",
        "patterns": [r"\b1[34]\d{3}[a-z]*\b", r"raptor\s*lake"],
        "mechanism": ("Vmin-shift degradation: the silicon permanently "
                      "loses stability under its own voltage curve. A "
                      "used chip can test fine today and be dying."),
        "directive": ("Owner directive 2026-10-20: not looking for Intel "
                      "CPUs that potentially burn themselves out; agent "
                      "contract rule 12."),
    },
]

_COMPILED = [
    (trap, [re.compile(p, re.IGNORECASE) for p in trap["patterns"]])
    for trap in TRAPS
]


def check_item(text, kind=None):
    """Return the trap dict (plus 'matched' pattern) if text names a
    banned part, else None. kind optionally restricts to one part kind
    ('cpu', 'gpu') so a CPU field is not judged by GPU patterns."""
    if not text:
        return None
    text = str(text)
    for trap, patterns in _COMPILED:
        if kind and trap["kind"] != kind:
            continue
        for pat in patterns:
            if pat.search(text):
                hit = dict(trap)
                hit["matched"] = pat.pattern
                return hit
    return None


# --- CPU class rules (sourcing classes - NOT traps) ----------------------------
# The traps above ban parts for documented failure mechanisms. This section
# is different: Brian's CPU CLASS rules say which silicon classes DealsDesk
# sources at all. A class reject is not a defect claim - the part works; it
# is simply not the class Brian buys. Class rules live in this module
# because it is the one every sourcing/scoring path already consults, but
# a class reject is never reported as a trap.
#
# XEON GOLD RULE (Brian 2026-10-21: "not gold 61** only gold 62**"; full
# form Brian 2026-10-27: "we don't want 51** or 52** ; we want 62** and
# 63**"): when text names a Xeon Gold CPU, ONLY the 62xx (2nd-gen
# Scalable, Cascade Lake) and 63xx (3rd-gen Scalable, Ice Lake) series
# pass. 61xx excluded 2026-10-21; 51xx/52xx excluded 2026-10-27. Reasons
# on record: DDR4-2933 vs 2666, two AVX-512 FMA units per core vs one,
# AVX-512 VNNI (62xx vs 61xx), higher clocks at the same core counts.

GOLD_SERIES_ACCEPTED = (62, 63)
GOLD_SERIES_REJECTED = (51, 52, 61)

_GOLD_RE = re.compile(r"gold\D{0,4}?(\d{4})", re.IGNORECASE)


def gold_series(text):
    """The Xeon Gold series in text (62 for a 6230, 52 for a 5218R), or
    None when no Gold CPU is named."""
    if not text:
        return None
    m = _GOLD_RE.search(str(text))
    if not m:
        return None
    return int(m.group(1)[:2])


def check_cpu_class(text):
    """Brian's CPU class verdict for text naming a Xeon Gold CPU.
    Returns None when no Gold CPU is named or the series is outside the
    rule (the rule does not judge), else a dict with 'series', 'verdict'
    ('accept' or 'reject'), 'rule' and 'reason'."""
    series = gold_series(text)
    if series is None:
        return None
    if series in GOLD_SERIES_REJECTED:
        return {"series": series, "verdict": "reject",
                "rule": "xeon_gold_class",
                "reason": ("Xeon Gold %dxx is not sourced - Brian's Gold "
                           "rule: 62xx and 63xx only (2026-10-21; full "
                           "form 2026-10-27)" % series)}
    if series in GOLD_SERIES_ACCEPTED:
        return {"series": series, "verdict": "accept",
                "rule": "xeon_gold_class",
                "reason": "Xeon Gold %dxx - Brian's Gold class" % series}
    return None


# --- Do-not-track GPU models (tracking class rule - NOT traps) ---------------
# Brian 2026-11-17: "we should ban those models from all tracking -- they
# are under spec for what we need." These cards WORK; nothing here claims
# a defect. They sit below the fleet's inference floor (8 GB and under),
# so DealsDesk does not track them at all: no price watches, no sightings,
# no captures, no surfacing as candidates. This is a tracking class rule
# like the Xeon Gold rule above -- it is never reported as a trap, and it
# does not judge a machine that merely contains one of these as a display
# card; it governs what the desk TRACKS.
# Named by Brian 2026-11-17, one by one, off the SFF 70-75 W class map:
# RTX A1000, RTX A400, T1000, T600, T400.
# Pattern care: \ba400\b must not catch the RTX A4000 (16 GB, a different
# card) -- the trailing \b sees the extra 0 as a word char, so it cannot.
# \bt400\b does not catch the Tesla T4 (16 GB, tracked) -- different token.
# Accepted collision: \bt400\b also matches a ThinkPad T400 laptop title;
# the desk tracks no T400 laptops, so the match costs nothing.

DO_NOT_TRACK = [
    {"id": "rtx_a1000", "name": "NVIDIA RTX A1000 (8GB)",
     "patterns": [r"\ba1000\b"]},
    {"id": "rtx_a400", "name": "NVIDIA RTX A400 (4GB)",
     "patterns": [r"\ba400\b"]},
    {"id": "quadro_t1000", "name": "NVIDIA T1000 (4/8GB)",
     "patterns": [r"\bt1000\b"]},
    {"id": "quadro_t600", "name": "NVIDIA T600 (4GB)",
     "patterns": [r"\bt600\b"]},
    {"id": "quadro_t400", "name": "NVIDIA T400 (4GB)",
     "patterns": [r"\bt400\b"]},
]

_DNT_COMPILED = [
    (entry, [re.compile(p, re.IGNORECASE) for p in entry["patterns"]])
    for entry in DO_NOT_TRACK
]

_DNT_REASON = ("under spec for the fleet's inference work -- Brian "
               "2026-11-17: banned from all tracking")


def check_do_not_track(text):
    """Return the do-not-track entry (plus 'matched' and 'reason') if
    text names a model Brian has banned from tracking, else None.
    A tracking class rule -- NOT a hardware trap verdict."""
    if not text:
        return None
    text = str(text)
    for entry, patterns in _DNT_COMPILED:
        for pat in patterns:
            if pat.search(text):
                hit = dict(entry)
                hit["matched"] = pat.pattern
                hit["reason"] = _DNT_REASON
                return hit
    return None


def is_do_not_track(text):
    """True if text names a do-not-track model."""
    return check_do_not_track(text) is not None


# --- Form-factor gate (PCIe card needs vs SXM modules) ---------------------
# Friction #51 (2026-11-19, capture 2569): a "Tesla V100 32GB" at
# $61.73 was filed UNDER TARGET for the PCIe card need, but the
# listing was an SXM2 module + water block + SXM2-to-PCIe adapter
# combo. An SXM module is not a PCIe card: it mounts on an SXM
# baseboard, and a carrier conversion is a different product than
# the native card a PCIe need names. This is a FORM rule — not a
# trap (the module is fine hardware in its own class) and not a
# tracking ban (the desk may still record module sightings, labeled
# as modules). It only says a module can never satisfy a PCIe-card
# need: never crowned best, never filed under-target for one. Same
# pattern as the A2000 model-token gate in component_scout: the
# listing is judged against what the NEED actually is.
# Pattern care: the SXM token may be written SXM2, SXM 2, SXM-2 or
# SXM2+... — the pattern tolerates the separators. A genuine PCIe
# listing never carries an SXM token. The gate fires only when the
# NEED names PCIe; a need that wants modules (an SXM baseboard
# build) is not judged by it.

_SXM_RE = re.compile(r"\bsxm(?:\s?-?\s?[2-5])?\b", re.IGNORECASE)
_PCIE_RE = re.compile(r"\bpci[\s\-]?e\b|\bpci[\s\-]?express\b",
                      re.IGNORECASE)


def is_sxm_module_title(title):
    """True when a listing title marks the part as an SXM module
    (SXM, SXM2..SXM5 — including 'SXM2 to PCIe' carrier/conversion
    combos, whose titles carry the SXM token)."""
    if not title:
        return False
    return bool(_SXM_RE.search(str(title)))


def check_form_factor(title, need_text):
    """Form-factor verdict for one listing against one need.
    Returns a reject dict when the need names a PCIe card and the
    listing is an SXM module; None when the gate does not judge
    (the need is not a PCIe need, or the listing is not an SXM
    module). A form rule — never reported as a trap."""
    if not title or not need_text:
        return None
    if not _PCIE_RE.search(str(need_text)):
        return None
    if not is_sxm_module_title(title):
        return None
    return {"form": "sxm-module", "verdict": "reject",
            "rule": "form_factor_pcie_vs_sxm",
            "reason": ("SXM module (or SXM-to-PCIe carrier combo) — "
                       "not the native PCIe card this need names; "
                       "modules mount on an SXM baseboard "
                       "(friction #51, 2026-11-19)")}


def is_trapped(text, kind=None):
    """True if text names any banned part."""
    return check_item(text, kind=kind) is not None


def explain(text, kind=None):
    """One-line human verdict for logs and rejections."""
    hit = check_item(text, kind=kind)
    if hit is None:
        return "clean"
    return "TRAP %s: %s (%s)" % (hit["id"], hit["mechanism"], hit["directive"])


_SELFTEST = [
    ("NVIDIA Tesla K80 24GB GPU", "tesla_k80"),
    ("Dell server with Tesla K80", "tesla_k80"),
    ("Intel Core i7-14700K", "raptor_lake_burnout"),
    ("Mini PC i5-13400T 32GB", "raptor_lake_burnout"),
    ("Raptor Lake build, cheap", "raptor_lake_burnout"),
    ("Lenovo M920q i5-8500T", None),
    ("HP EliteDesk 800 G4 i7-8700T", None),
    ("Tesla V100 32GB", None),          # EOL but usable — NOT a trap
    ("Tesla P40 24GB", None),           # EOL but usable — NOT a trap
    ("Core Ultra 5 235HX mini PC", None),  # different design — NOT banned
    ("Ryzen 9 8945HS", None),
    ("ASUS RTX 3060 12GB", None),
]


_CLASS_SELFTEST = [
    ("Dell R740 2x Xeon Gold 6230 32GB", "accept"),
    ("Dell R750 2x Gold 6330 32GB", "accept"),
    ("Dell R740 1x Gold 5218R 32GB", "reject"),
    ("Dell R640 2x Gold 5218", "reject"),
    ("Dell R740 2x Gold 6138", "reject"),
    ("Dell R740 2x Gold 5120", "reject"),
    ("Dell R730 2x E5-2680 v4", None),      # no Gold named - rule silent
    ("Lenovo M920q i5-8500T", None),
]


_FORM_SELFTEST = [
    # (listing title, need text, want verdict)
    ("Tesla V100 32GB GPU SXM2+water cooler block+SXM2 To PCIE "
     "Card option combo US",
     "Tesla V100 32GB PCIe GPU (dual-unit builds)", "reject"),
    ("NVIDIA Tesla V100 SXM2 32GB GPU 699-2G503-0203-200",
     "Tesla V100 32GB PCIe GPU (dual-unit builds)", "reject"),
    ("NVIDIA Tesla V100 32GB PCIe GPU Accelerator",
     "Tesla V100 32GB PCIe GPU (dual-unit builds)", None),
    ("NVIDIA Tesla V100 SXM2 32GB GPU",
     "Tesla V100 SXM2 baseboard build", None),   # need wants modules
    ("NVIDIA TESLA M40 24GB GDDR5 PCI-E 3.0 X16 GPU CARD CUDA PG600",
     "Tesla M40 24GB PG600 GPU (second card)", None),
    ("Intel Arc Pro B70 32GB PCIe 5.0 Graphics Card",
     "Intel Arc Pro B70 32GB GPU (dual, Xeon/AMD servers)", None),
]


_DNT_SELFTEST = [
    ("NVIDIA RTX A1000 8GB Low Profile", "rtx_a1000"),
    ("PNY RTX A400 4GB", "rtx_a400"),
    ("Quadro T1000 8GB GDDR6", "quadro_t1000"),
    ("NVIDIA T600 4GB", "quadro_t600"),
    ("PNY T400 4GB Low Profile", "quadro_t400"),
    ("RTX 4000 SFF Ada 20GB", None),     # different card -- NOT banned
    ("NVIDIA RTX A4000 16GB", None),     # A4000 is not the A400
    ("Tesla T4 16GB", None),             # T4 is tracked -- not T400
    ("RTX A2000 12GB", None),            # not ruled -- rule stays silent
    ("Intel Arc Pro B50 16GB", None),
]


def selftest():
    failures = 0
    for text, want in _CLASS_SELFTEST:
        hit = check_cpu_class(text)
        got = hit["verdict"] if hit else None
        ok = got == want
        failures += 0 if ok else 1
        print("%s %-38r -> class %s" % ("OK  " if ok else "FAIL", text, got))
    for text, want in _SELFTEST:
        hit = check_item(text)
        got = hit["id"] if hit else None
        ok = got == want
        failures += 0 if ok else 1
        print("%s %-38r -> %s" % ("OK  " if ok else "FAIL", text, got))
    for text, want in _DNT_SELFTEST:
        hit = check_do_not_track(text)
        got = hit["id"] if hit else None
        ok = got == want
        failures += 0 if ok else 1
        print("%s %-38r -> do-not-track %s" % ("OK  " if ok else "FAIL", text, got))
    for title, need, want in _FORM_SELFTEST:
        hit = check_form_factor(title, need)
        got = hit["verdict"] if hit else None
        ok = got == want
        failures += 0 if ok else 1
        print("%s %-38r -> form-factor %s" % ("OK  " if ok else "FAIL", title[:38], got))
    total = (len(_SELFTEST) + len(_CLASS_SELFTEST) + len(_DNT_SELFTEST)
             + len(_FORM_SELFTEST))
    print("selftest: %d/%d passed" % (total - failures, total))
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check text against the hardware trap registry.")
    ap.add_argument("text", nargs="?", help="listing title or part name")
    ap.add_argument("--kind", choices=["cpu", "gpu"], default=None)
    ap.add_argument("--list", action="store_true", help="dump the registry")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.list:
        print(json.dumps(TRAPS, indent=2))
        return 0
    if not args.text:
        ap.error("text, --list, or --selftest is required")
    print(explain(args.text, kind=args.kind))
    return 0 if check_item(args.text, kind=args.kind) is None else 2


if __name__ == "__main__":
    sys.exit(main())
