#!/usr/bin/env python3
"""sourcing_worker.py — source open hardware needs via PicClick (DealsDesk side).

PURPOSE: For each open hardware need raised from a project task, scrape PicClick,
         filter blocked sellers, score server candidates, and store results in
         dealsdesk.solution_options. Budget gate decides 'candidate' vs
         'recommended'. Never buys anything.
WHY:     This is the deterministic sourcing leg of the ERP loop:
         task -> need -> sourced options -> budget gate -> human decision.
         No AI inference anywhere: scrape + Python scoring + DB writes.
CALLED BY: cron (hourly at most; respects PicClick rate limits) or operator.
         --dry-run prints what would happen without writing or scraping.
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


def esc(s):
    return str(s).replace("'", "''")


def approach_for(subject):
    s = subject.lower()
    for kw, approach in APPROACH_KEYWORDS:
        if kw in s:
            return approach
    return "other"


def is_server_need(subject):
    return bool(re.search(r"server|gen ?8|gen ?9|dl380|r730|xeon", subject, re.I))


def source_need(need_id, subject, description, max_cost, top, dry_run):
    """Returns list of option dicts (not yet written)."""
    try:
        import picclick_rack_search as finder
        import seller_blocklist as blocklist
    except ImportError as e:
        LOG.error("cannot import finder modules: %s", e)
        return []

    query = f"{subject} {description or ''}".strip()[:120]
    options = []
    if is_server_need(subject):
        from rack_server_scorer import score_candidate
        cands = finder.search(query, top=top)
        cands = blocklist.filter_blocked(cands, seller_key="seller")
        for c in cands:
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
    # Budget gate: recommended only if within max_cost (or no cap set)
    for o in options:
        if o["price"] is None or max_cost is None or o["price"] <= float(max_cost):
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
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--need-id", type=int, help="source one need only")
    args = ap.parse_args(argv)

    where = "n.status='open' AND n.need_type='hardware' AND n.source LIKE 'sbos_task:%'"
    if args.need_id:
        where += f" AND n.id={int(args.need_id)}"
    rows = psql(
        "SELECT n.id, n.subject, n.description, r.max_cost FROM "
        "dealsdesk.ecosystem_needs n LEFT JOIN successbrian_os.sbos_need_requests r "
        "ON r.need_id = n.id WHERE " + where + " ORDER BY n.urgency DESC, n.id")
    if rows is None:
        return 1
    if not rows:
        LOG.info("no open task-raised hardware needs")
        return 0

    for need_id, subject, description, max_cost in rows:
        LOG.info("sourcing need %s: %s", need_id, subject)
        options = source_need(need_id, subject, description, max_cost, args.top,
                              args.dry_run)
        if args.dry_run:
            continue
        approach = approach_for(subject)
        for o in options:
            price_sql = "NULL" if o["price"] is None else str(float(o["price"]))
            score_sql = "NULL" if o["score"] is None else str(float(o["score"]))
            label = f"{esc(o['label'])} [{esc(o['seller'])}] {esc(o['url'])}"
            psql(
                "INSERT INTO dealsdesk.solution_options "
                "(need_id, option_label, approach, est_cost, score, status) "
                f"VALUES ({int(need_id)}, '{label}', '{approach}', {price_sql}, "
                f"{score_sql}, '{o['status']}')", write=True)
        psql(f"UPDATE dealsdesk.ecosystem_needs SET status='planned', "
             f"updated_at=NOW() WHERE id={int(need_id)}", write=True)
        LOG.info("need %s: %d options stored, marked planned", need_id, len(options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
