#!/usr/bin/env python3
"""
Decision feedback loop: surface open decisions, record Brian's calls.

PURPOSE:
    `pending` lists every undecided decision from both the briefing_items
    table and pending-decisions.md; `ask` presents one as a choice; `record`
    marks it decided everywhere and logs it to the second brain.

WHY:
    Brian (2026-09-27): Altair must "get my feedback on decisions" as a
    production tool. Before this, decisions surfaced in briefings and then
    evaporated — asked twice, never recorded, never acted on. Recording
    closes the loop: the decision lands in pending-decisions.md (so briefings
    stop re-surfacing it), the briefing_items row is consumed, and the
    second brain keeps the durable record with Brian's actual choice.

CALLED BY:
    routine.py decisions <cmd>; the decisions segment of a briefing session.

NOTES:
    IDs are namespaced: `bi:<rowid>` = briefing_items table, `md:<n>` =
    nth open item in pending-decisions.md. The md parse is best-effort on
    free text — options are extracted from "A or B?" phrasing, else empty
    and the 14B takes free feedback. `record` choices: approve|reject|park.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME, out, fail, today, pg_rows, pg_write, sb_log  # noqa: E402

PENDING_MD = os.path.join(
    HOME, ".hermes/profiles/altair/briefings/context/pending-decisions.md")


def read_md_open():
    """Return [(index, raw_line)] of open items under ## Open."""
    if not os.path.exists(PENDING_MD):
        return []
    with open(PENDING_MD, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^##\s+Open\s*$", text, re.M | re.I)
    if not m:
        return []
    rest = text[m.end():]
    m2 = re.search(r"^##\s+", rest, re.M)
    section = rest[:m2.start()] if m2 else rest
    items = []
    for line in section.splitlines():
        lm = re.match(r"^\s*-\s*\[\s\]\s*(.*)$", line)
        if lm:
            items.append(lm.group(1).strip())
    return list(enumerate(items))


def split_options(text):
    """Best-effort: 'DELETE (x) or KEEP (y)?' -> (title, [opts])."""
    t = text.rstrip("?").strip()
    m = re.match(r"^(.*?):\s*(.*)$", t)
    lead, rest = (m.group(1), m.group(2)) if m else (t, t)
    if " or " in rest:
        parts = [p.strip(" ?") for p in re.split(r"\s+or\s+", rest)]
        if len(parts) == 2 and all(len(p) < 80 for p in parts):
            return lead, parts
    return t, []


def read_bi_decisions():
    """Unconsumed, unexpired briefing_items with category=decision."""
    try:
        rows = pg_rows(
            "SELECT id, title, detail FROM briefing_items "
            "WHERE category='decision' AND consumed_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > now()) ORDER BY id;")
    except Exception as e:
        print(f"[decisions] briefing_items unreadable: {e}", file=sys.stderr)
        return []
    return rows  # [id, title, detail]


def pending_list():
    items = []
    for rid, title, detail in read_bi_decisions():
        items.append({"id": f"bi:{rid}", "title": title,
                      "detail": detail or "", "options": [],
                      "recommendation": "", "source": "briefing-table"})
    for idx, raw in read_md_open():
        title, options = split_options(raw)
        items.append({"id": f"md:{idx}", "title": title,
                      "detail": raw, "options": options,
                      "recommendation": "", "source": "pending-decisions"})
    return items


def cmd_pending(args):
    items = pending_list()
    if not items:
        out({"decisions": [], "count": 0, "done": True,
             "say": "No open decisions — you're all caught up.",
             "expect": "text"})
        return
    out({"decisions": items, "count": len(items), "done": False,
         "say": f"{len(items)} decision{'s' if len(items) != 1 else ''} "
                f"waiting on you.",
         "expect": "text"})


def find_decision(did):
    for d in pending_list():
        if d["id"] == did:
            return d
    return None


def cmd_ask(args):
    d = find_decision(args.id)
    if not d:
        fail(f"Unknown decision id {args.id}.")
    say = d["title"] + "."
    if d["detail"] and d["detail"] != d["title"]:
        say += " " + d["detail"][:300]
    obj = {"say": say, "id": args.id, "done": False}
    if d["options"]:
        obj["expect"] = "choice"
        obj["options"] = d["options"]
    else:
        obj["expect"] = "feedback"
    out(obj)


def md_record(idx, choice, note):
    """Move md item idx from ## Open to ## Recently decided."""
    with open(PENDING_MD, encoding="utf-8") as f:
        text = f.read()
    open_items = read_md_open()
    if idx >= len(open_items):
        raise RuntimeError("md index out of range")
    raw = open_items[idx][1]
    line_re = re.compile(r"^\s*-\s*\[\s\]\s*" + re.escape(raw) + r"\s*$", re.M)
    text, n = line_re.subn("", text, count=1)
    if n == 0:
        raise RuntimeError("could not find open item line to remove")
    entry = f"- [x] {today()}: {raw} → {choice.upper()}"
    if note:
        entry += f" — {note}"
    m = re.search(r"^##\s+Recently decided.*$", text, re.M | re.I)
    if m:
        text = text[:m.end()] + "\n" + entry + text[m.end():]
    else:
        text = text.rstrip() + f"\n\n## Recently decided\n{entry}\n"
    with open(PENDING_MD, "w", encoding="utf-8") as f:
        f.write(text)


def cmd_record(args):
    d = find_decision(args.id)
    if not d:
        fail(f"Unknown decision id {args.id}.")
    choice = args.choice.lower()
    if choice not in ("approve", "reject", "park"):
        fail("choice must be approve, reject, or park.")
    if args.id.startswith("bi:"):
        rid = args.id[3:]
        pg_write(f"UPDATE briefing_items SET consumed_at = now(), "
                 f"briefing_date = '{today()}' WHERE id = {int(rid)};")
    else:
        md_record(int(args.id[3:]), choice, args.note)
    note_txt = f" — {args.note}" if args.note else ""
    past = {"approve": "approved", "reject": "rejected",
            "park": "parked"}[choice]
    sb_log(f"Decision: {d['title']}",
           f"Brian decided: {choice.upper()}{note_txt}\n"
           f"Context: {d['detail'][:500]}",
           category="decision", confidence="high",
           source="brian-direct", tags=("decision", "altair-routines"))
    out({"say": f"Got it — {past}. Logged.",
         "id": args.id, "choice": choice, "done": True,
         "expect": "text"})


def main():
    ap = argparse.ArgumentParser(prog="decisions.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    p = sub.add_parser("ask")
    p.add_argument("--id", required=True)
    p = sub.add_parser("record")
    p.add_argument("--id", required=True)
    p.add_argument("--choice", required=True)
    p.add_argument("--note", default="")
    args = ap.parse_args()
    try:
        {"pending": cmd_pending, "ask": cmd_ask,
         "record": cmd_record}[args.cmd](args)
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))


if __name__ == "__main__":
    main()
