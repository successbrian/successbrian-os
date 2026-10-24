#!/usr/bin/env python3
"""need_sources.py — target buy prices + kept sources for DealsDesk needs.

Brian 2026-10-22: "with dealsdesk, we should track a target buy price
and start keeping potential sources" / "yes build improve".

PURPOSE: DealsDesk-side operator tool for the two fields every need now
         carries: target_buy_price (Brian's per-unit buy trigger) and
         kept potential sources (dealsdesk.need_sources). Also the
         purchase write-back: recording a buy increments the need's
         qty_filled and satisfies the need when the fill completes, so
         a filled need stops surfacing.
WHY:     solution_options is worker-filled from PicClick scrapes only.
         Brian's real sources (Alibaba suppliers with MOQ terms, named
         eBay sellers, vendor stores, his street channels) had nowhere
         to be KEPT. This module is that home. Origin is recorded so a
         worker never silently overwrites a human-kept source.
RULES:   Deterministic field mapping only, no AI judgment (house rule).
         A source at/under the need's target is ACTIONABLE, above it is
         WATCHED. Sources go stale 7 days after observed_at (mirrors
         build_price_alerts STALE_DAYS) until repriced. is_anti marks a
         do-not-buy source. Nothing here buys anything, ever.
CALLED BY: operator (Brian / Muse) or cron for `stale-sweep`.
CANONICAL: successbrian-os/tools/dealsdesk/need_sources.py
DEPLOYED:  /home/dealsdesk/scripts/need_sources.py (k11-alpha)
SCHEMA:    migrations in 2026-10-22_need_targets_sources.sql.
"""

import argparse
import json
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [need_sources] %(message)s")
LOG = logging.getLogger("need_sources")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
STALE_DAYS = 7


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:300])
        return None
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return str(s).replace("'", "''")


def num_or_null(v):
    if v is None or v == "":
        return "NULL"
    return str(float(v))


def int_or_null(v):
    if v is None or v == "":
        return "NULL"
    return str(int(v))


def json_or_null(v):
    if v is None or v == "":
        return "NULL"
    parsed = json.loads(v)  # validate; raises on bad JSON
    return "'" + esc(json.dumps(parsed)) + "'::jsonb"


def cmd_add_need(a):
    rows = psql(
        "SELECT id FROM dealsdesk.ecosystem_needs WHERE subject='"
        + esc(a.subject) + "' AND status IN ('open','planned')")
    if rows:
        LOG.info("need already exists (id %s) for subject %r — not duplicating",
                 rows[0][0], a.subject)
        return 0
    rows = psql(
        "INSERT INTO dealsdesk.ecosystem_needs "
        "(need_type, subject, description, magnitude, urgency, source, status, "
        " target_buy_price, hard_terms, qty_needed) VALUES ("
        f"'{esc(a.need_type)}', '{esc(a.subject)}', "
        f"'{esc(a.description or '')}', '{esc(str(a.qty) if a.qty else '')}', "
        f"{int(a.urgency)}, 'brian', '{esc(a.status)}', "
        f"{num_or_null(a.target)}, {json_or_null(a.terms)}, "
        f"{int_or_null(a.qty)}) RETURNING id")
    if not rows:
        return 1
    LOG.info("created need %s: %s", rows[0][0], a.subject)
    return 0


def cmd_update_need(a):
    sets = []
    if a.target is not None:
        sets.append(f"target_buy_price={float(a.target)}")
    if a.qty is not None:
        sets.append(f"qty_needed={int(a.qty)}")
    if a.terms is not None:
        sets.append(f"hard_terms={json_or_null(a.terms)}")
    if a.status is not None:
        sets.append(f"status='{esc(a.status)}'")
    if not sets:
        LOG.error("update-need: nothing to update")
        return 1
    ok = psql("UPDATE dealsdesk.ecosystem_needs SET " + ", ".join(sets)
              + f", updated_at=now() WHERE id={int(a.need)}", write=True)
    LOG.info("updated need %s (%s)", a.need, ", ".join(sets))
    return 0 if ok else 1


def cmd_add_source(a):
    rows = psql(
        "INSERT INTO dealsdesk.need_sources "
        "(need_id, origin, seller, platform, url, price, shipping, terms, "
        " note, is_anti) VALUES ("
        f"{int(a.need)}, '{esc(a.origin)}', '{esc(a.seller or '')}', "
        f"'{esc(a.platform or '')}', '{esc(a.url or '')}', "
        f"{num_or_null(a.price)}, {num_or_null(a.shipping)}, "
        f"{json_or_null(a.terms)}, '{esc(a.note or '')}', "
        f"{'true' if a.anti else 'false'}) RETURNING id")
    if not rows:
        return 1
    LOG.info("kept source %s on need %s (%s @ %s)",
             rows[0][0], a.need, a.seller, a.price)
    return 0


def verdict(price, target, is_anti, status, need_terms=None, src_terms=None):
    if is_anti == "t":
        return "ANTI — do not buy"
    # Hard-terms gate (Brian 2026-10-22): a need can require a source
    # region (e.g. MZ32 rev 1.x = US source only). A cheap source from
    # the wrong region is HELD, never ACTIONABLE.
    req = (need_terms or {}).get("source_region")
    region = (src_terms or {}).get("region")
    if req and region and region != req:
        return f"HELD — {region} source; rule requires {req}"
    # Reliability gate (Brian 2026-10-22): GLOBAL rule — anything
    # bought from China must be reliable: a long-term, honest source
    # that will not ditch after purchase. Brian's aim is to BUILD
    # those relationships; until a supplier has earned it, unrated
    # is not reliable. A need may set cn_reliability to adjust the
    # required level; the default on every need is "established".
    req_rel = (need_terms or {}).get("cn_reliability", "established")
    if region == "CN":
        rel = (src_terms or {}).get("reliability", "")
        if rel != req_rel:
            return (f"HELD — CN source reliability "
                    f"'{rel or 'unrated'}'; rule requires {req_rel}")
    if status != "active":
        base = status.upper()
    elif price and target:
        base = "ACTIONABLE" if float(price) <= float(target) else "WATCHED"
    else:
        base = "KEPT (no target set)" if price else "KEPT"
    if req and not region:
        base += " (region unverified)"
    return base


def cmd_list(a):
    nq = ("SELECT id, subject, status, qty_needed, qty_filled, "
          "COALESCE(target_buy_price::text,''), "
          "COALESCE(hard_terms::text,'') FROM dealsdesk.ecosystem_needs")
    if a.need:
        nq += f" WHERE id={int(a.need)}"
    nq += " ORDER BY id"
    needs = psql(nq)
    if needs is None:
        return 1
    for nid, subject, status, qn, qf, target, hterms in needs:
        try:
            need_terms = json.loads(hterms) if hterms else {}
        except ValueError:
            need_terms = {}
        fill = f"{qf}/{qn}" if qn else f"{qf}/open"
        tgt = f"target ${float(target):,.2f}" if target else "no target"
        print(f"\nNEED {nid} [{status}] {subject}  (filled {fill}, {tgt})")
        srcs = psql(
            "SELECT ns.id, ns.seller, ns.platform, "
            "COALESCE(ns.price::text,''), ns.is_anti, ns.status, "
            "round((extract(epoch from now()-ns.observed_at)"
            "/86400)::numeric, 1), COALESCE(ns.terms::text,''), "
            "COALESCE(sup.region,''), COALESCE(sup.reliability,'') "
            "FROM dealsdesk.need_sources ns "
            "LEFT JOIN dealsdesk.suppliers sup "
            "ON sup.id = ns.supplier_id "
            f"WHERE ns.need_id={int(nid)} "
            "ORDER BY ns.is_anti, ns.price NULLS LAST")
        if not srcs:
            print("  (no sources kept)")
        for row in (srcs or []):
            # psql drops trailing empty columns on a line (an
            # unlinked source's supplier fields vanish) — pad short
            # rows back to width before unpacking.
            (sid, seller, platform, price, anti, st, age, sterms,
             sup_region, sup_rel) = (list(row) + [""] * 10)[:10]
            try:
                src_terms = json.loads(sterms) if sterms else {}
            except ValueError:
                src_terms = {}
            # The suppliers registry is the record for region and
            # reliability; it wins over per-quote tags when set.
            if sup_region:
                src_terms["region"] = sup_region
            if sup_rel:
                src_terms["reliability"] = sup_rel
            print(f"  src {sid}: {seller} [{platform}] "
                  f"${float(price):,.2f}" if price else
                  f"  src {sid}: {seller} [{platform}] price n/a",
                  f"— {verdict(price, target, anti, st, need_terms, src_terms)} "
                  f"(age {age}d, {st})")
    return 0


def cmd_reprice(a):
    ok = psql(
        "UPDATE dealsdesk.need_sources SET price=" + num_or_null(a.price)
        + ", observed_at=now(), last_checked_at=now(), status='active'"
        + (f", note='{esc(a.note)}'" if a.note else "")
        + f" WHERE id={int(a.source)}", write=True)
    LOG.info("repriced source %s -> %s", a.source, a.price)
    return 0 if ok else 1


def cmd_stale_sweep(a):
    rows = psql(
        "UPDATE dealsdesk.need_sources SET status='stale' "
        "WHERE status='active' AND observed_at < now() - interval '"
        + str(STALE_DAYS) + " days' RETURNING id")
    # psql echoes an "UPDATE n" tag line after the RETURNING rows on
    # this build; count only the numeric id lines.
    n = sum(1 for r in (rows or []) if r and r[0].isdigit())
    LOG.info("stale-sweep: %d source(s) marked stale", n)
    return 0 if rows is not None else 1


def cmd_record_purchase(a):
    rows = psql(
        "INSERT INTO dealsdesk.need_purchases "
        "(need_id, source_id, qty, unit_price, note) VALUES ("
        f"{int(a.need)}, {int_or_null(a.source)}, {int(a.qty)}, "
        f"{num_or_null(a.price)}, '{esc(a.note or '')}') RETURNING id")
    if not rows:
        return 1
    psql("UPDATE dealsdesk.ecosystem_needs SET qty_filled = qty_filled + "
         f"{int(a.qty)}, updated_at=now() WHERE id={int(a.need)}", write=True)
    if a.source:
        psql("UPDATE dealsdesk.need_sources SET status='bought' "
             f"WHERE id={int(a.source)}", write=True)
    chk = psql("SELECT qty_needed, qty_filled FROM dealsdesk.ecosystem_needs "
               f"WHERE id={int(a.need)}")
    if chk and chk[0][0] and int(chk[0][1]) >= int(chk[0][0]):
        psql("UPDATE dealsdesk.ecosystem_needs SET status='satisfied', "
             f"updated_at=now() WHERE id={int(a.need)}", write=True)
        LOG.info("need %s SATISFIED (%s/%s)", a.need, chk[0][1], chk[0][0])
    else:
        LOG.info("purchase recorded on need %s (filled %s)",
                 a.need, chk[0][1] if chk else "?")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("add-need")
    n.add_argument("--subject", required=True)
    n.add_argument("--need-type", default="hardware")
    n.add_argument("--description", default="")
    n.add_argument("--qty", type=int)
    n.add_argument("--target", type=float)
    n.add_argument("--terms")
    n.add_argument("--urgency", type=int, default=3)
    n.add_argument("--status", default="open")
    n.set_defaults(fn=cmd_add_need)

    u = sub.add_parser("update-need")
    u.add_argument("--need", type=int, required=True)
    u.add_argument("--target", type=float)
    u.add_argument("--qty", type=int)
    u.add_argument("--terms")
    u.add_argument("--status")
    u.set_defaults(fn=cmd_update_need)

    s = sub.add_parser("add-source")
    s.add_argument("--need", type=int, required=True)
    s.add_argument("--seller", required=True)
    s.add_argument("--platform", default="")
    s.add_argument("--url", default="")
    s.add_argument("--price", type=float)
    s.add_argument("--shipping", type=float)
    s.add_argument("--terms")
    s.add_argument("--note", default="")
    s.add_argument("--origin", default="manual")
    s.add_argument("--anti", action="store_true")
    s.set_defaults(fn=cmd_add_source)

    l = sub.add_parser("list")
    l.add_argument("--need", type=int)
    l.set_defaults(fn=cmd_list)

    r = sub.add_parser("reprice")
    r.add_argument("--source", type=int, required=True)
    r.add_argument("--price", type=float, required=True)
    r.add_argument("--note")
    r.set_defaults(fn=cmd_reprice)

    sub.add_parser("stale-sweep").set_defaults(fn=cmd_stale_sweep)

    b = sub.add_parser("record-purchase")
    b.add_argument("--need", type=int, required=True)
    b.add_argument("--qty", type=int, required=True)
    b.add_argument("--source", type=int)
    b.add_argument("--price", type=float)
    b.add_argument("--note", default="")
    b.set_defaults(fn=cmd_record_purchase)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
