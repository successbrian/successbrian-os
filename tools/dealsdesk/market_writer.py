#!/usr/bin/env python3
"""market_writer.py — record a market price observation.

PURPOSE: Upsert the latest price in dealsdesk.market_prices AND append a
         row to dealsdesk.market_price_history, so the trend engine has a
         real time series instead of one stale number.
WHY:     Brian's rule: no hardcoded prices. Prices must move with the market.
         Every observation (intel research, deal vet, manual check) goes
         through here so the history is complete and the "latest" is fresh.
CALLED BY: the intel loop, deal vet, or a human with a fresh sighting.
           CLI: market_writer.py --key <component_key> --price <usd> --source <text>
NOTES:   Never auto-buys anything; it only records data. Idempotent per
         observation: call it once per sighting.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/market_writer.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/market_writer.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import subprocess
import sys

sys.path.insert(0, "/home/dealsdesk")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [market_writer] %(message)s")
LOG = logging.getLogger("market_writer")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def esc(s):
    return s.replace("'", "''")


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME]
    if write:
        cmd += ["-v", "ON_ERROR_STOP=1", "-c", sql]
    else:
        cmd += ["-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return None if write else []
    return True if write else [
        l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def record(key, price, source):
    ok = psql(f"""INSERT INTO dealsdesk.market_prices
                    (component_key, price, source, observed_at)
                  VALUES ('{esc(key)}', {price}, '{esc(source)}', NOW())
                  ON CONFLICT (component_key) DO UPDATE
                    SET price = EXCLUDED.price,
                        source = EXCLUDED.source,
                        observed_at = NOW()""", write=True)
    if not ok:
        return False
    ok = psql(f"""INSERT INTO dealsdesk.market_price_history
                    (component_key, price, source)
                  VALUES ('{esc(key)}', {price}, '{esc(source)}')""", write=True)
    if ok:
        LOG.info("recorded %s = $%.2f (%s)", key, price, source)
    return bool(ok)


def main():
    ap = argparse.ArgumentParser(description="Record a market price observation")
    ap.add_argument("--key", required=True, help="component_key, e.g. nvme_1tb_gen4_new")
    ap.add_argument("--price", type=float, required=True, help="observed USD price")
    ap.add_argument("--source", required=True, help="where the price was seen")
    a = ap.parse_args()
    if a.price <= 0:
        ap.error("price must be positive")
    sys.exit(0 if record(a.key, a.price, a.source) else 1)


if __name__ == "__main__":
    main()
