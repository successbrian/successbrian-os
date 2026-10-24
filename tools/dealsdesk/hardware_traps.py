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


def selftest():
    failures = 0
    for text, want in _SELFTEST:
        hit = check_item(text)
        got = hit["id"] if hit else None
        ok = got == want
        failures += 0 if ok else 1
        print("%s %-38r -> %s" % ("OK  " if ok else "FAIL", text, got))
    print("selftest: %d/%d passed" % (len(_SELFTEST) - failures, len(_SELFTEST)))
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
