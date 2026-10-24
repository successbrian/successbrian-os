#!/usr/bin/env python3
"""notice.py — the provenance checker.

Brian's rule (2026-10-23): "you need to notice these things" / "the
ecosystem needs to be coded to notice these things." A Muse suggestion
must never harden into the record as if Brian ruled it. This tool is the
machinery: a register of design elements, each with a provenance status
(ruled by Brian / proposal / open), and a checker that scans canonical
docs for proposal-or-open elements stated WITHOUT a proposal label.

A match is clean only if a label marker appears on the matched line or
the line directly before/after it. Unlabeled matches are FLAGS for the
morning brief: "proposal wearing a ruling's clothes — Brian to confirm
or strike."

Deterministic, stdlib only, per the architecture law (code, not winging
it). Usage:
  notice.py check <doc> [doc...] [--register PATH]
  notice.py show [--register PATH]
  notice.py add --id X --status ruled|proposal|open --owner brian|Muse \
      --patterns "a;b;c" --source "..." [--register PATH]
  notice.py selftest
"""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

DEFAULT_REGISTER = Path(__file__).with_name("provenance_register.jsonl")

LABEL_MARKERS = [
    "proposal",
    "not ruled",
    "not brian-ruled",
    "Muse's",
    "Muse recommendation",
    "recommendation only",
    "open",
    "not chosen",
    "never chosen",
    "not a hard choice",
    "not locked",
    "unruled",
]


def load_register(path):
    rows = []
    if not Path(path).exists():
        return rows
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def has_label(lines, idx):
    lo = max(0, idx - 1)
    hi = min(len(lines), idx + 2)
    window = "\n".join(lines[lo:hi]).lower()
    if any(m in window for m in LABEL_MARKERS):
        return True
    # A section heading above (within 6 lines) carrying a marker labels
    # its whole section — e.g. "## Still open (Brian to rule)".
    for j in range(idx - 1, max(-1, idx - 7), -1):
        line = lines[j]
        if line.lstrip().startswith("#"):
            head = line.lower()
            return any(m in head for m in LABEL_MARKERS)
        if line.strip() == "" and j < idx - 2:
            continue
    return False


def check_doc(doc_path, register):
    text = Path(doc_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    flags = []
    seen_flags = set()
    found_ruled = []
    found_labeled = []
    for el in register:
        status = el["status"]
        for pat in el["patterns"]:
            rx = re.compile(re.escape(pat), re.IGNORECASE)
            for i, line in enumerate(lines):
                if rx.search(line):
                    if status == "ruled":
                        if el["id"] not in found_ruled:
                            found_ruled.append(el["id"])
                    else:
                        if has_label(lines, i):
                            if el["id"] not in found_labeled:
                                found_labeled.append(el["id"])
                        else:
                            key = (i, el["id"])
                            if key not in seen_flags:
                                seen_flags.add(key)
                                flags.append(
                                    {
                                        "doc": str(doc_path),
                                        "line": i + 1,
                                        "element": el["id"],
                                        "status": status,
                                        "text": line.strip()[:160],
                                    }
                                )
    return flags, found_ruled, found_labeled


def cmd_check(args):
    register = load_register(args.register)
    all_flags = []
    for doc in args.docs:
        flags, ruled, labeled = check_doc(doc, register)
        all_flags.extend(flags)
        print(f"{doc}: ruled elements present={len(ruled)} "
              f"proposals labeled={len(labeled)} flags={len(flags)}")
    for f in all_flags:
        print(f"FLAG {f['doc']}:{f['line']} [{f['element']} status={f['status']}] "
              f"stated without a proposal label: {f['text']}")
    if all_flags:
        print(f"NOTICE: {len(all_flags)} unlabeled proposal/open element(s) "
              f"— Brian to confirm or strike.")
        return 1
    print("NOTICE: clean — every proposal/open element found is labeled.")
    return 0


def cmd_show(args):
    for el in load_register(args.register):
        print(f"{el['id']:<28} {el['status']:<9} owner={el['owner']:<7} "
              f"patterns={el['patterns']} source={el.get('source','')}")
    return 0


def cmd_add(args):
    row = {
        "id": args.id,
        "status": args.status,
        "owner": args.owner,
        "patterns": [p.strip() for p in args.patterns.split(";") if p.strip()],
        "source": args.source,
    }
    path = Path(args.register)
    existing = load_register(path)
    existing = [e for e in existing if e["id"] != args.id]
    existing.append(row)
    with path.open("w", encoding="utf-8") as fh:
        for e in existing:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"registered {args.id} [{args.status}]")
    return 0


def cmd_selftest(_args):
    reg = [
        {"id": "benching", "status": "proposal", "owner": "Muse",
         "patterns": ["benched for the night"], "source": "test"},
        {"id": "decomp", "status": "ruled", "owner": "brian",
         "patterns": ["many easy ones"], "source": "test"},
        {"id": "gpu", "status": "open", "owner": "brian",
         "patterns": ["P40"], "source": "test"},
    ]
    cases = [
        ("(PROPOSAL — Muse's, not ruled by Brian: a stalled seat is "
         "benched for the night.) The clerk breaks it into many easy "
         "ones.", []),
        ("A stalled seat is benched for the night. The clerk breaks it "
         "into many easy ones.", ["benching"]),
        ("The seats run the P40 card.", ["gpu"]),
        ("The card is OPEN — never chosen: a P40 was Muse's "
         "recommendation only.", []),
    ]
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "reg.jsonl"
        rp.write_text("\n".join(json.dumps(r) for r in reg) + "\n",
                      encoding="utf-8")
        register = load_register(rp)
        ok = True
        for n, (body, expect) in enumerate(cases, 1):
            dp = Path(td) / f"doc{n}.md"
            dp.write_text(body + "\n", encoding="utf-8")
            flags, _r, _l = check_doc(dp, register)
            got = sorted({f["element"] for f in flags})
            want = sorted(expect)
            verdict = "PASS" if got == want else "FAIL"
            if got != want:
                ok = False
            print(f"case {n}: {verdict} (flags={got}, expected={want})")
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default=str(DEFAULT_REGISTER))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("docs", nargs="+")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("show")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("add")
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True,
                   choices=["ruled", "proposal", "open"])
    p.add_argument("--owner", required=True, choices=["brian", "Muse"])
    p.add_argument("--patterns", required=True)
    p.add_argument("--source", default="")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
