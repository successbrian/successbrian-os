#!/usr/bin/env python3
"""sourcing_worker.py — source open hardware needs via PicClick (DealsDesk side).

PURPOSE: For each open hardware need raised from a project task, scrape PicClick,
         filter blocked sellers, score server candidates, and store results in
         dealsdesk.solution_options. Budget gate decides 'candidate' vs
         'recommended'. Never buys anything.
WHY:     This is the deterministic sourcing leg of the ERP loop:
         task -> need -> sourced options -> budget gate -> human decision.
         No AI inference anywhere: scrape + Python scoring + DB writes.
CALLED BY: DISPATCH FROM A PLANNING SESSION ONLY (--dispatched flag).
         Brian 2026-10-28: no unattended shopping - hunts happen only from
         a planning session; the daily cron was removed the same night.
         --dry-run prints gate decisions WITHOUT searching or writing.
         --top N limits listings per need (default 10).
NOTES:   Server-ish needs use the rack finder + scorer; other hardware uses raw
         listings (score NULL, blocklist applies only when seller is known).
         approach is mapped from need subject keywords to the solution_options
         check constraint (gpu/nvme/ram/node/network/tooling/other).
         Canonical: successbrian-os/tools/dealsdesk/sourcing_worker.py
         Deployed: /home/dealsdesk/scripts/sourcing_worker.py (k11-alpha)
"""

import argparse
import logging
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [sourcing_worker] %(message)s")
LOG = logging.getLogger("sourcing_worker")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"

APPROACH_KEYWORDS = [
    ("gpu", "gpu"), ("nvme", "nvme"), ("ssd", "nvme"), ("ram", "ram"),
    ("memory", "ram"), ("server", "node"), ("switch", "network"), ("nic", "network"),
]


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return None
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.join(_os_c.path.dirname(_os_c.path.abspath(__file__)), ".."))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)


def approach_for(subject):
    s = subject.lower()
    for kw, approach in APPROACH_KEYWORDS:
        if kw in s:
            return approach
    return "other"


def is_server_need(subject):
    return bool(re.search(r"server|gen ?8|gen ?9|dl380|r730|xeon", subject, re.I))


_TRAPS_MOD = "unset"


def trap_or_class_reason(title):
    """Why this listing must never be stored as an option, or None.
    DealsDesk does not seek out traps (Brian 2026-10-28): candidates are
    checked against the hardware trap registry (banned outright - K80,
    Raptor Lake) and Brian's CPU class rules (Gold 62xx/63xx only) at
    INTAKE, before anything reaches dealsdesk.solution_options. The
    registry module loads once; if it is genuinely unavailable the check
    logs loudly instead of failing silently."""
    global _TRAPS_MOD
    if _TRAPS_MOD == "unset":
        try:
            import hardware_traps as _t
            _TRAPS_MOD = _t
        except ImportError:
            import os as _os
            for _p in (_os.path.expanduser("~/dealsdesk/src"),
                       _os.path.expanduser(
                           "~/successbrian-os/tools/dealsdesk")):
                if _p not in sys.path:
                    sys.path.insert(0, _p)
            try:
                import hardware_traps as _t
                _TRAPS_MOD = _t
            except ImportError:
                LOG.warning("hardware_traps unavailable - trap/class "
                            "intake filter NOT applied")
                _TRAPS_MOD = None
    if _TRAPS_MOD is None or not title:
        return None
    hit = _TRAPS_MOD.check_item(title)
    if hit is not None:
        return "TRAP %s: %s" % (hit["id"], hit["name"])
    cls = _TRAPS_MOD.check_cpu_class(title)
    if cls is not None and cls["verdict"] == "reject":
        return cls["reason"]
    return None


def build_plan_for(need_id):
    """The build plan table (dealsdesk.builds) is the plan of record
    (Brian 2026-10-27: planning is Brian + Muse; plans live in the table;
    DealsDesk works from the table). Returns (id, name) or None."""
    rows = psql(
        "SELECT id, name FROM dealsdesk.builds WHERE need_id = %d "
        "AND status NOT IN ('cancelled', 'complete', 'done') "
        "ORDER BY id DESC LIMIT 1" % int(need_id))
    if rows:
        return rows[0][0], rows[0][1]
    return None


def source_need(need_id, subject, description, max_cost, top, dry_run,
                build_name=None):
    """Returns list of option dicts (not yet written)."""
    try:
        import picclick_rack_search as finder
        import seller_blocklist as blocklist
    except ImportError as e:
        LOG.error("cannot import finder modules: %s", e)
        return []

    # Search basis is the BUILD PLAN (wired 2026-10-27): the plan's name
    # carries the ruled spec - not a free-form paste of the need text alone.
    basis = f"{build_name} {subject}" if build_name else subject
    query = f"{basis} {description or ''}".strip()[:120]
    options = []
    if is_server_need(subject):
        from rack_server_scorer import score_candidate
        cands = finder.search(query, top=top)
        cands = blocklist.filter_blocked(cands, seller_key="seller")
        for c in cands:
            bad = trap_or_class_reason(c.get("name", ""))
            if bad:
                LOG.info("not stored (trap/class): %s - %s",
                         c.get("name", "")[:80], bad)
                continue
            try:
                scored = score_candidate(c)
                score = scored.get("score")
            except Exception as e:
                LOG.warning("scorer failed on %r: %s", c.get("name"), e)
                score = None
            options.append({
                "label": c.get("name", "")[:200],
                "price": c.get("price"),
                "score": score,
                "url": c.get("url", ""),
                "seller": c.get("seller", "unknown"),
            })
    else:
        html_text = finder.fetch_search(query)
        cands = finder.parse_listings(html_text)[:top]
        for c in cands:
            bad = trap_or_class_reason(c.get("name", ""))
            if bad:
                LOG.info("not stored (trap/class): %s - %s",
                         c.get("name", "")[:80], bad)
                continue
            seller = c.get("seller", "unknown")
            if seller != "unknown" and blocklist.is_blocked(seller):
                LOG.info("blocked seller filtered: %s", seller)
                continue
            options.append({
                "label": c.get("name", "")[:200],
                "price": c.get("price"),
                "score": None,
                "url": c.get("url", ""),
                "seller": seller,
            })
    # Budget gate (Brian 2026-10-27: SBOS accounts for his budget in solving
    # issues): 'recommended' requires a real cap and a price within it.
    # No cap set -> candidate only; no cap is NOT no limit.
    for o in options:
        if max_cost is not None and o["price"] is not None and o["price"] <= float(max_cost):
            o["status"] = "recommended"
        else:
            o["status"] = "candidate"
    # Only the single best-priced recommended option keeps 'recommended';
    # the rest stay candidates for Brian to compare.
    recs = [o for o in options if o["status"] == "recommended" and o["price"] is not None]
    if len(recs) > 1:
        recs.sort(key=lambda o: o["price"])
        for o in recs[1:]:
            o["status"] = "candidate"
    if dry_run:
        LOG.info("DRY-RUN need %s (%s): %d options", need_id, subject, len(options))
        for o in options[:5]:
            LOG.info("  [%s] %s | %s | %s", o["status"], o["label"][:80],
                     o["price"], o["url"][:60])
    return options


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dispatched", action="store_true",
                    help="required for a real run: set only when a planning "
                         "session (Brian + Muse) dispatches this hunt")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--need-id", type=int, help="source one need only")
    args = ap.parse_args(argv)
    if not args.dispatched and not args.dry_run:
        LOG.error("REFUSED: unattended sourcing run - hunts are dispatched "
                  "from a planning session (Brian 2026-10-28: no unattended "
                  "shopping). Use --dispatched from a session, or --dry-run "
                  "to see gate decisions without searching.")
        return 2

    where = "n.status='open' AND n.need_type='hardware' AND n.source LIKE 'sbos_task:%'"
    if args.need_id:
        where += f" AND n.id={int(args.need_id)}"
    rows = psql(
        "SELECT n.id, n.subject, n.description, r.max_cost, n.target_buy_price FROM "
        "dealsdesk.ecosystem_needs n LEFT JOIN successbrian_os.sbos_need_requests r "
        "ON r.need_id = n.id WHERE " + where + " ORDER BY n.urgency DESC, n.id")
    if rows is None:
        return 1
    if not rows:
        LOG.info("no open task-raised hardware needs")
        return 0

    for row in rows:
        # psql omits the trailing separator when the last column is NULL — pad.
        while len(row) < 5:
            row.append("")
        need_id, subject, description, max_cost, target_price = row
        max_cost = max_cost or None
        if max_cost is None:
            max_cost = target_price or None
        if max_cost is None:
            LOG.info("need %s: no budget cap on record - options stay candidate", need_id)
        build = build_plan_for(int(need_id))
        if build is None:
            LOG.info("need %s: NO BUILD PLAN - web search skipped "
                     "(Brian 2026-10-27: no random searching; a need with no "
                     "plan in dealsdesk.builds is not searched)", need_id)
            continue
        LOG.info("need %s: build plan #%s in force (%s)", need_id, build[0],
                 build[1])
        if args.dry_run:
            LOG.info("need %s: DRY-RUN - would source from build plan #%s "
                     "when dispatched; no search performed", need_id, build[0])
            continue
        LOG.info("sourcing need %s: %s", need_id, subject)
        options = source_need(need_id, subject, description, max_cost, args.top,
                              args.dry_run, build_name=build[1])
        approach = approach_for(subject)
        for o in options:
            price_sql = "NULL" if o["price"] is None else str(float(o["price"]))
            score_sql = "NULL" if o["score"] is None else str(float(o["score"]))
            label = f"{esc(o['label'])} [{esc(o['seller'])}] {esc(o['url'])}"
            psql(
                "INSERT INTO dealsdesk.solution_options "
                "(need_id, option_label, approach, est_cost, score, status, "
                "adequacy_note) "
                f"VALUES ({int(need_id)}, '{label}', '{approach}', {price_sql}, "
                f"{score_sql}, '{o['status']}', "
                f"'via build plan #{int(build[0])}')", write=True)
        psql(f"UPDATE dealsdesk.ecosystem_needs SET status='planned', "
             f"updated_at=NOW() WHERE id={int(need_id)}", write=True)
        LOG.info("need %s: %d options stored, marked planned", need_id, len(options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
