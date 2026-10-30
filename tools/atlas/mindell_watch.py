#!/usr/bin/env python3
"""mindell_watch.py — the daily mapping pass for the Mindell node.

Brian's directive (2026-10-28 15:53 CDT): the Mindell Olive Oil
Bible launch window "is a huge atlas node that the ecosystem needs
to start thinking and mapping daily how we can align with it,
improve it, etc". This script is the daily cadence machinery for
Atlas node launch:mindell-olive-oil-bible, built in the sprawl-
watch shape (sprawl_census.py watch: census -> snapshot ->
evaluate -> file an atlas_task for the board, idempotently).

Cron: 20 2 * * * (daily 02:20 local, ahead of the 02:30 board —
the same board-feeding slot pattern as sprawl-watch at 02:10).

WHAT IS AUTOMATED (every run):
  * node state refresh: days-to-publication countdown, run stamp,
    open-item aging — written back onto the hub node's details.
  * signal checks at the readiness plan's cadence (monthly at T1,
    biweekly at T2, weekly at T3, daily at T4/T5): content-hash +
    keyword watches on the publicly fetchable sources (Square One
    Publishers, drearlmindell.com). Deltas vs the last snapshot are
    detected and recorded. The script FLAGS ladder candidates
    (e.g. a pre-order signal) — it never advances the ladder by
    itself; an agent or Brian confirms stage changes.
  * a dated mapping note: the day's packet appended (dated
    section) to mindell-daily-mapping.md in the longevity-olive-
    blog AnythingLLM workspace (allm_embed, replace-prior-edition).
  * a snapshot row in atlas.mindell_snapshots (audit trail).
  * a board task (task:mindell-mapping, deduped while one is
    open/queued — the sprawl-watch rule) when the day carries a
    signal delta, a ladder candidate, a countdown milestone, or
    open items gone stale (>14 days unworked). An open task IS the
    carry-forward: unmapped items stay on the board's agenda and
    in every day's note until resolved — nothing is dropped.

WHAT STILL NEEDS AN AGENT PASS (stated plainly — no fake
automation): the creative mapping itself. Judging alignment
angles, proposing new edges, checking the sources a script
cannot reliably fetch (BookHype listing, Target product
metadata, Amazon author page, Edelweiss, Mindell's Facebook),
confirming ladder advances, drafting assets — that is agent work
(Altair / the board / Spencer). This script assembles the day's
mapping packet so that pass starts from current facts, and its
task filing is what puts the packet on the board's agenda.

Items close only via:  mindell_watch.py resolve <item-id>
(--cancel exists for Brian's word; the calendar law is that an
item leaves by being worked or by Brian cancelling it — never
by expiry.)

Usage:
  mindell_watch.py run [--force-web] [--dry-run]
  mindell_watch.py resolve <item-id> [--note TEXT]
  mindell_watch.py cancel <item-id> [--note TEXT]
  mindell_watch.py selftest
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # tools/ for sbos_common
sys.path.insert(0, HERE)                   # tools/atlas/ for allm_embed
import sbos_common  # noqa: E402

NODE = "launch:mindell-olive-oil-bible"
TASK_KEY = "task:mindell-mapping"
WS_SLUG = "longevity-olive-blog"
NOTE_NAME = "mindell-daily-mapping.md"
STATE_FILE = os.path.join(HERE, "state", "mindell-daily-mapping.md")
PUB_DATE = dt.date(2027, 5, 18)
MILESTONES = (180, 150, 120, 90, 60, 45, 30, 21, 14, 7, 3, 1, 0)
STALE_DAYS = 14

# Cadence (days between web checks) by ladder stage — readiness plan §2.
CADENCE = {"T0": 25, "T1": 25, "T2": 13, "T3": 6,
           "T4": 0, "T5": 0, "T6": 25}

# Publicly fetchable signal sources. Keyword hits are signals for
# an agent to judge, never proof by themselves. NOTE (build day,
# 2026-10-28): squareonepublishers.com is Cloudflare bot-walled
# from alpha — scripted fetches get HTTP 403 (verified with plain
# and browser-like headers; curl gets a 301 the fetcher cannot
# ride). The check is RETAINED so an un-block registers by itself,
# and every failure is recorded as a delta ("agent to check
# manually") — surfaced, never hidden. In practice Square One is
# an agent-checked source until the wall moves.
SOURCES = [
    {"key": "square-one", "url": "https://squareonepublishers.com/",
     "signals": ["mindell", "olive", "pre-order", "preorder",
                 "coming soon", "new releases"]},
    {"key": "mindell-site", "url": "https://www.drearlmindell.com/",
     "signals": ["olive oil bible", "olive", "new book",
                 "square one", "2027", "tour", "interview"]},
]
# Sources a script cannot reliably fetch — named in every packet
# so the agent pass knows its checklist.
AGENT_ONLY_SOURCES = [
    "BookHype Earl Mindell bibliography (title/date changes)",
    "Target / Walmart / B&N product metadata for the listed title",
    "Amazon Earl Mindell author page (pre-order page appearance)",
    "Edelweiss / publisher catalog listings",
    "Square One press / publicity pages (media kit at T3)",
    "facebook.com/drearlmindell (booking + announcement posts)",
]


def today():
    return dt.date.today()


def pg():
    return sbos_common.connect(user="postgres")


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS atlas.mindell_snapshots ("
            "id SERIAL PRIMARY KEY, run_date DATE NOT NULL, "
            "ran_at TIMESTAMPTZ DEFAULT NOW(), ladder TEXT, "
            "days_to_pub INT, web_checks JSONB, packet JSONB, "
            "task_result TEXT)")
    conn.commit()


def get_node(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT details FROM atlas.nodes WHERE node_key=%s", (NODE,))
        row = cur.fetchone()
    if not row:
        raise SystemExit(
            "node %s missing — run mindell_node_seed.py first" % NODE)
    return row[0] or {}


def last_snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT run_date, ladder, days_to_pub, web_checks FROM "
            "atlas.mindell_snapshots ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if not row:
        return None
    return {"run_date": row[0], "ladder": row[1],
            "days_to_pub": row[2], "web_checks": row[3] or {}}


def fetch_source(src):
    out = {"key": src["key"], "url": src["url"], "ok": False,
           "status": None, "sha": None, "signals_found": [],
           "error": None}
    req = urllib.request.Request(
        src["url"], headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                          "SBOS-mindell-watch"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8", "replace")
            out["status"] = resp.status
        out["ok"] = True
        out["sha"] = hashlib.sha256(body.encode()).hexdigest()[:16]
        low = body.lower()
        out["signals_found"] = [s for s in src["signals"] if s in low]
    except Exception as e:  # unreachable/blocked is data, not death
        out["error"] = "%s: %s" % (type(e).__name__, e)
    return out


def route_model(conn):
    """atlas.py's routing (Brian 2026-10-17): V4 Pro when it has
    API value, else Sonic; an active plan:v4-freeze overrides."""
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM atlas.nodes WHERE "
                    "node_key='plan:v4-freeze'")
        row = cur.fetchone()
        if row and row[0] == "active":
            return "sonic", "frozen"
        cur.execute("SELECT available, usd FROM "
                    "successbrian_os.v4pro_balance_history ORDER BY "
                    "checked_at DESC LIMIT 1")
        row = cur.fetchone()
    if row:
        avail, usd = row[0], row[1] or 0
        if avail and float(usd) > 0:
            return "v4pro", "balance $%.2f" % float(usd)
    return "sonic", "no V4 value"


def file_board_task(conn, headline):
    """File task:mindell-mapping for the board — sprawl-watch
    shape, atlas.py task-add SQL semantics, idempotent while a
    task is open/queued (an open task is the carry-forward)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT node_key FROM atlas.nodes WHERE node_key=%s AND "
            "status IN ('open', 'queued')", (TASK_KEY,))
        if cur.fetchone():
            return "already on the board's agenda (task open)"
    model, reason = route_model(conn)
    title = (
        "MINDELL DAILY MAPPING: %s. Node: %s (trigger ladder + "
        "open items live in its details); dated notes: %s in the "
        "%s workspace; snapshots: atlas.mindell_snapshots. The "
        "board proposes; the chair disposes."
        % (headline, NODE, NOTE_NAME, WS_SLUG))
    det = {"about": NODE, "found_by": "mindell-watch", "model": model}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO atlas.nodes (node_key, node_type, name, "
            "status, details) VALUES (%s, 'atlas_task', %s, "
            "'queued', %s::jsonb) ON CONFLICT (node_key) DO UPDATE "
            "SET name=EXCLUDED.name, status=EXCLUDED.status, "
            "details=EXCLUDED.details, updated_at=NOW()",
            (TASK_KEY, title, json.dumps(det)))
        cur.execute(
            "INSERT INTO atlas.edges (from_node, to_node, edge_type) "
            "VALUES (%s, %s, 'about') ON CONFLICT DO NOTHING",
            (TASK_KEY, NODE))
    conn.commit()
    return "filed as %s (board agenda, model=%s: %s)" % (
        TASK_KEY, model, reason)


def build_packet(conn, details, snap, force_web):
    """Assemble the day's mapping packet from current facts."""
    ladder = (details.get("trigger_ladder") or {}).get("current", "T1")
    days = (PUB_DATE - today()).days
    prev_checks = (snap or {}).get("web_checks") or {}
    last_web = prev_checks.get("_ran_on")
    cadence = CADENCE.get(ladder, 25)
    web_due = force_web or not last_web or cadence == 0 or (
        today() - dt.date.fromisoformat(last_web)).days >= cadence

    checks, deltas, candidates = {}, [], []
    if web_due:
        for src in SOURCES:
            res = fetch_source(src)
            checks[src["key"]] = res
            prev = prev_checks.get(src["key"]) or {}
            if prev.get("sha") and res.get("sha") and \
                    prev["sha"] != res["sha"]:
                deltas.append("%s content changed (hash %s -> %s)"
                              % (src["key"], prev["sha"], res["sha"]))
            new_sigs = [s for s in res.get("signals_found", [])
                        if s not in (prev.get("signals_found") or [])]
            for s in new_sigs:
                deltas.append("new signal '%s' on %s" % (s, src["key"]))
                if "pre-order" in s or "preorder" in s:
                    candidates.append(
                        "POSSIBLE T2 — pre-order signal on %s; agent "
                        "to confirm before any ladder advance"
                        % src["key"])
            if not res["ok"]:
                deltas.append("%s check FAILED (%s) — agent to check "
                              "manually" % (src["key"], res["error"]))
        checks["_ran_on"] = today().isoformat()
    else:
        checks = dict(prev_checks)
        checks["_ran_on"] = last_web
        checks["_skipped"] = ("cadence %dd at %s; last web check %s"
                              % (cadence, ladder, last_web))

    milestones = []
    prev_days = (snap or {}).get("days_to_pub")
    for m in MILESTONES:
        if days == m or (prev_days is not None and prev_days > m >= days):
            milestones.append("%d days to listed publication "
                              "(2027-05-18)" % m)

    items = details.get("open_items") or []
    open_items, stale = [], []
    for it in items:
        if it.get("state") != "open":
            continue
        age = (today() - dt.date.fromisoformat(it["opened"])).days
        entry = dict(it, age_days=age)
        open_items.append(entry)
        if age > STALE_DAYS:
            stale.append("%s (%dd unworked)" % (it["id"], age))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM atlas.edges WHERE from_node=%s OR "
            "to_node=%s", (NODE, NODE))
        edge_count = cur.fetchone()[0]

    packet = {
        "date": today().isoformat(),
        "node": NODE,
        "ladder": ladder,
        "days_to_pub": days,
        "web_due": web_due,
        "signal_deltas": deltas,
        "ladder_candidates": candidates,
        "milestones": milestones,
        "open_items": open_items,
        "stale_items": stale,
        "edge_count": edge_count,
        "agent_only_sources": AGENT_ONLY_SOURCES,
        "agent_pass_needed": [
            "Judge signal deltas; confirm or reject ladder candidates "
            "(script never advances the ladder)",
            "Check the agent-only sources above",
            "Work or re-plan open items; close via resolve",
            "Propose new edges/angles from the node's neighborhood",
        ],
    }
    return packet, checks


def note_section(packet):
    lines = ["## %s — daily mapping" % packet["date"],
             "- Ladder: **%s** · Days to listed publication "
             "(2027-05-18): **%d** · Node edges: %d"
             % (packet["ladder"], packet["days_to_pub"],
                packet["edge_count"])]
    if packet["signal_deltas"]:
        lines.append("- Signal deltas:")
        lines += ["  - %s" % d for d in packet["signal_deltas"]]
    else:
        lines.append("- Signal deltas: none%s" % (
            " (web checks not due this run)" if not packet["web_due"]
            else ""))
    for c in packet["ladder_candidates"]:
        lines.append("- **Ladder candidate:** %s" % c)
    for m in packet["milestones"]:
        lines.append("- **Milestone:** %s" % m)
    lines.append("- Open items carried forward (%d):"
                 % len(packet["open_items"]))
    for it in packet["open_items"]:
        lines.append("  - [%s] %s (%dd open)"
                     % (it["id"], it["title"], it["age_days"]))
    lines.append("- Agent-only sources still to check: %s"
                 % "; ".join(packet["agent_only_sources"]))
    return "\n".join(lines) + "\n"


def write_note(packet):
    section = note_section(packet)
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            old = f.read()
        idx = old.find("\n## ")
        if idx >= 0:
            # newest section goes right before the previous newest
            text = old[:idx + 1] + section + "\n" + old[idx + 1:]
        else:
            text = old.rstrip("\n") + "\n\n" + section
    else:
        text = ("# Mindell daily mapping — longevity-olive-blog\n\n"
                "Dated mapping notes for Atlas node %s, written daily "
                "by mindell_watch.py (dated sections, newest first; "
                "open items carry forward until resolved — never "
                "dropped).\n\n" % NODE) + section
    with open(STATE_FILE, "w") as f:
        f.write(text)
    try:
        import allm_embed
        loc = allm_embed.embed_latest(WS_SLUG, NOTE_NAME, text)
        return "embedded (%s)" % loc
    except Exception as e:
        return ("EMBED FAILED (%s) — local note kept at %s; next run "
                "retries" % (e, STATE_FILE))


def run(force_web=False, dry_run=False):
    conn = pg()
    try:
        ensure_schema(conn)
        details = get_node(conn)
        snap = last_snapshot(conn)
        packet, checks = build_packet(conn, details, snap, force_web)

        headline_bits = []
        if packet["signal_deltas"]:
            headline_bits.append("; ".join(packet["signal_deltas"][:2]))
        if packet["ladder_candidates"]:
            headline_bits.append(packet["ladder_candidates"][0])
        if packet["milestones"]:
            headline_bits.append(packet["milestones"][0])
        if packet["stale_items"]:
            headline_bits.append("stale open items: %s"
                                 % "; ".join(packet["stale_items"][:3]))
        needs_task = bool(headline_bits)
        headline = "; ".join(headline_bits) if headline_bits else \
            "routine day — state refreshed, items carried forward"

        if dry_run:
            print(json.dumps(packet, indent=2, default=str))
            print("DRY RUN — no writes. Task would%s be filed."
                  % ("" if needs_task else " not"))
            return 0

        task_result = "not filed (routine day)"
        if needs_task:
            task_result = file_board_task(conn, headline)

        # Node state refresh — merge, never clobber.
        details["last_daily_run"] = today().isoformat()
        details["days_to_pub"] = packet["days_to_pub"]
        ladder = details.setdefault("trigger_ladder", {})
        ladder["last_checked"] = today().isoformat()
        run_log = details.setdefault("run_log", [])
        run_log.insert(0, {"date": today().isoformat(),
                           "deltas": len(packet["signal_deltas"]),
                           "candidates": len(packet["ladder_candidates"]),
                           "task": task_result})
        details["run_log"] = run_log[:10]
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.nodes SET details=%s::jsonb, "
                "updated_at=NOW() WHERE node_key=%s",
                (json.dumps(details), NODE))
            cur.execute(
                "INSERT INTO atlas.mindell_snapshots (run_date, "
                "ladder, days_to_pub, web_checks, packet, "
                "task_result) VALUES (%s, %s, %s, %s::jsonb, "
                "%s::jsonb, %s)",
                (today(), packet["ladder"], packet["days_to_pub"],
                 json.dumps(checks), json.dumps(packet), task_result))
        conn.commit()

        note_result = write_note(packet)
        print("MINDELL WATCH %s — ladder %s, %d days to pub, "
              "%d open items (%d stale), deltas %d"
              % (packet["date"], packet["ladder"],
                 packet["days_to_pub"], len(packet["open_items"]),
                 len(packet["stale_items"]),
                 len(packet["signal_deltas"])))
        print("  task: %s" % task_result)
        print("  note: %s" % note_result)
        return 0
    finally:
        conn.close()


def set_item_state(item_id, state, note):
    conn = pg()
    try:
        details = get_node(conn)
        items = details.get("open_items") or []
        hit = None
        for it in items:
            if it.get("id") == item_id:
                hit = it
                it["state"] = state
                it["closed_on"] = today().isoformat()
                if note:
                    it["close_note"] = note
        if not hit:
            print("no open item with id %s" % item_id)
            return 1
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.nodes SET details=%s::jsonb, "
                "updated_at=NOW() WHERE node_key=%s",
                (json.dumps(details), NODE))
        conn.commit()
        print("item %s -> %s" % (item_id, state))
        return 0
    finally:
        conn.close()


def selftest():
    ok = True
    conn = pg()
    try:
        details = get_node(conn)
        print("PASS node %s present (ladder %s, %d open items)"
              % (NODE, (details.get("trigger_ladder") or {})
                 .get("current"), len(details.get("open_items") or [])))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM atlas.edges WHERE from_node=%s "
                "OR to_node=%s", (NODE, NODE))
            n = cur.fetchone()[0]
            print("%s hub edges: %d (expect >= 9)"
                  % ("PASS" if n >= 9 else "FAIL", n))
            ok = ok and n >= 9
            cur.execute("SELECT to_regclass('atlas.mindell_snapshots')")
            t = cur.fetchone()[0]
            print("%s snapshots table %s"
                  % ("PASS" if t else "FAIL",
                     "present" if t else "MISSING (run once to create)"))
            ok = ok and bool(t)
    finally:
        conn.close()
    print("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run")
    s.add_argument("--force-web", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    for verb in ("resolve", "cancel"):
        s = sub.add_parser(verb)
        s.add_argument("item_id")
        s.add_argument("--note")
    sub.add_parser("selftest")
    a = p.parse_args()
    if a.cmd == "run":
        return run(force_web=a.force_web, dry_run=a.dry_run)
    if a.cmd == "resolve":
        return set_item_state(a.item_id, "done", a.note)
    if a.cmd == "cancel":
        return set_item_state(a.item_id, "cancelled", a.note)
    if a.cmd == "selftest":
        return selftest()
    return 2


if __name__ == "__main__":
    sys.exit(main())
