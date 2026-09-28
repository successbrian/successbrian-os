"""
PURPOSE:
    CoinGecko free-API client with disk caching and polite rate limiting.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    No API key needed. Only public market-data endpoints are used.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import CG_BASE, CG_SLEEP, CACHE_DIR

_cache = Path(__file__).resolve().parent.parent / CACHE_DIR
_cache.mkdir(exist_ok=True)
_last_call = 0.0


def _polite():
    global _last_call
    wait = CG_SLEEP - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _get(path, params=None, ttl=300):
    """GET with a simple JSON disk cache (ttl in seconds)."""
    key = path + "?" + json.dumps(params or {}, sort_keys=True)
    safe = "".join(c if c.isalnum() else "_" for c in key)[:120] + ".json"
    f = _cache / safe
    if f.exists() and time.time() - f.stat().st_mtime < ttl:
        return json.loads(f.read_text())
    _polite()
    r = requests.get(CG_BASE + path, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    f.write_text(json.dumps(data))
    return data


def markets(ids, vs="usd"):
    """Current market snapshot for a list of CoinGecko ids."""
    return _get("/coins/markets", {
        "vs_currency": vs,
        "ids": ",".join(ids),
        "price_change_percentage": "1h,24h,7d,14d,30d",
    }, ttl=300)


def top_markets(per_page=250, page=1):
    """Top coins by market cap (for the mover scan)."""
    return _get("/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": page,
        "price_change_percentage": "24h",
    }, ttl=600)


def market_chart(coin_id, days=90):
    """Historical daily prices [[ms, price], ...]. ttl=1h."""
    return _get(f"/coins/{coin_id}/market_chart",
                {"vs_currency": "usd", "days": days}, ttl=3600)


def trending():
    return _get("/search/trending", ttl=1800)


def global_data():
    return _get("/global", ttl=1800)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
