#!/usr/bin/env python3
"""build_price_alerts.py — DealsDesk build-tracker alert loop.

PURPOSE: Evaluate target prices on dealsdesk.build_items against the live
         public.price_history feed. When a watched component's fresh market
         price hits its target, flip the item and notify Brian via
         public.successbrian_outbox (which feeds his digest).
WHY:     Every prior generation of the build tracker died because nothing
         scheduled the checker. This is the missing loop — a DealsDesk
         routine (systemd timer), not anyone's side-cron.
CALLED BY: systemd build-price-alerts.timer (every 6h, offset from price-refresh).
NOTES:   - Only sightings fresher than STALE_DAYS (7) are evaluated.
         - alert_sent suppresses duplicate alerts; a strictly lower fresh
           sighting re-arms the alert.
         - Listing-name matching is conservative token overlap.
         - Alerts are notifications only. Nothing auto-buys, ever.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/build_price_alerts.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/build_price_alerts.py (k11-alpha; systemd timers).

"""

import logging
import re
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [build_price_alerts] %(message)s",
)
LOG = logging.getLogger("build_price_alerts")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
STALE_DAYS = 7

STOPWORDS = {
    "the", "a", "an", "for", "with", "and", "or", "of", "in", "on",
    "new", "oem", "bulk", "lot", "genuine", "original",
}


def psql(sql):
    """Run read-only SQL, return rows as lists."""
    result = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        LOG.error("psql failed: %s", result.stderr.strip()[:200])
        return []
    rows = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            rows.append(line.split("\x1f"))
    return rows


def psql_write(sql):
    result = subprocess.run(
        ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        LOG.error("psql write failed: %s", result.stderr.strip()[:200])
        return False
    return True


def tokens(name):
    toks = re.findall(r"[a-z0-9]+", name.lower())
    return [t for t in toks if t not in STOPWORDS and len(t) > 1]


def key_tokens(component_name, limit=5):
    """Distinctive tokens that must all appear in a listing name."""
    seen = []
    for t in tokens(component_name):
        if t not in seen:
            seen.append(t)
        if len(seen) >= limit:
            break
    return seen


def best_sighting(item_tokens, sightings):
    """Cheapest fresh listing whose name contains all key tokens."""
    best = None
    for name, price_s, source, checked_at in sightings:
        try:
            price = float(price_s)
        except (TypeError, ValueError):
            continue
        name_toks = set(tokens(name))
        if all(t in name_toks for t in item_tokens):
            if best is None or price < best[1]:
                best = (name, price, source, checked_at)
    return best


def esc(s):
    return (s or "").replace("'", "''")


def main():
    targets = psql(
        """SELECT i.id, b.name, i.component_name, i.target_price,
                  COALESCE(i.alert_sent, FALSE), i.last_seen_price
           FROM dealsdesk.build_items i
           JOIN dealsdesk.builds b ON b.id = i.build_id
           WHERE i.target_price IS NOT NULL"""
    )
    if not targets:
        LOG.info("no targets with target_price set; nothing to evaluate")
        return

    sightings = psql(
        f"""SELECT item_name, price, source, checked_at
            FROM public.price_history
            WHERE checked_at > NOW() - INTERVAL '{STALE_DAYS} days'"""
    )
    LOG.info("%d targets, %d fresh sightings", len(targets), len(sightings))

    hits = 0
    for row in targets:
        row = (row + [""] * 6)[:6]
        item_id, build_name, comp, target_s, alert_sent_s, prev_seen_s = row
        try:
            target = float(target_s)
        except (TypeError, ValueError):
            continue
        alert_sent = alert_sent_s == "t"
        try:
            prev_seen = float(prev_seen_s) if prev_seen_s else None
        except (TypeError, ValueError):
            prev_seen = None

        kt = key_tokens(comp)
        if not kt:
            continue
        sight = best_sighting(kt, sightings)
        if not sight:
            continue
        name, price, source, checked_at = sight

        # Always refresh the last-seen fields so the tracker shows live data.
        psql_write(
            f"""UPDATE dealsdesk.build_items
                SET last_seen_price = {price},
                    last_seen_at = '{esc(checked_at)}',
                    last_seen_source = '{esc(source)}',
                    updated_at = NOW()
                WHERE id = {item_id}"""
        )

        if price <= target and (not alert_sent or (prev_seen is not None and price < prev_seen)):
            ok = psql_write(
                f"""UPDATE dealsdesk.build_items
                    SET item_status = 'priced', alert_sent = TRUE, updated_at = NOW()
                    WHERE id = {item_id}"""
            )
            if ok:
                psql_write(
                    f"""INSERT INTO dealsdesk.item_whys (item_id, aspect, why, source)
                        VALUES ({item_id}, 'status_change',
                            'Price target hit: seen at $' || {price}
                                || ' vs target $' || {target}
                                || ' via ' || '{esc(source)}' || '.',
                            'price_alerts')"""
                )
            msg = (
                f"PRICE TARGET HIT — {comp} at ${price:,.2f} "
                f"(target ${target:,.2f}) for build '{build_name}'. "
                f"Source: {source}. Brian decides; nothing auto-buys."
            )
            psql_write(
                f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
                    VALUES ('dealsdesk', '{esc(msg)}', 3)"""
            )
            if ok:
                hits += 1
                LOG.info("HIT: %s @ %.2f (target %.2f)", comp, price, target)

    LOG.info("done: %d target hit(s)", hits)
    psql_write(
        f"""INSERT INTO system_operations_log (subsystem, action_type, status, payload)
            VALUES ('build_price_alerts', 'evaluate',
                    'OK', jsonb_build_object('targets', {len(targets)},
                                              'sightings', {len(sightings)},
                                              'hits', {hits}))
            """
    )


if __name__ == "__main__":
    main()
