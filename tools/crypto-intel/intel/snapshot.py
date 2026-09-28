"""
PURPOSE:
    Daily intel snapshot: watchlist prices + top-250 mover scan + news hits, written to snapshots/<date>.json. This is the artifact Altair's digest pipeline can consume.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    Usage:  python -m intel.snapshot   (run from the code/ directory)

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intel import coingecko as cg
from intel.config import WATCHLIST, LONG_TERM, SNAPSHOT_DIR
from intel.movers import scan_movers
from intel.news import scan_news


def build_snapshot():
    ids = list(WATCHLIST.keys())
    try:
        wl = cg.markets(ids)
    except Exception as e:
        wl = [{"id": i, "error": str(e)[:120]} for i in ids]
    watchlist = {}
    for c in wl:
        if "error" in c:
            watchlist[c["id"]] = c
            continue
        watchlist[c["id"]] = {
            "symbol": c["symbol"].upper(),
            "name": c["name"],
            "price": c["current_price"],
            "change_1h": c.get("price_change_percentage_1h_in_currency"),
            "change_24h": c.get("price_change_percentage_24h_in_currency"),
            "change_7d": c.get("price_change_percentage_7d_in_currency"),
            "change_14d": c.get("price_change_percentage_14d_in_currency"),
            "change_30d": c.get("price_change_percentage_30d_in_currency"),
            "volume_24h": c.get("total_volume"),
            "market_cap": c.get("market_cap"),
            "ath": c.get("ath"),
            "ath_change_pct": c.get("ath_change_percentage"),
            "long_term_hold": c["id"] in LONG_TERM,
        }
    try:
        movers = scan_movers()
    except Exception as e:
        movers = {"error": str(e)[:200]}
    try:
        news = scan_news()
    except Exception as e:
        news = {"error": str(e)[:200]}
    return {
        "generated_at": cg.stamp(),
        "watchlist": watchlist,
        "movers": movers,
        "news": news,
    }


def main():
    snap = build_snapshot()
    outdir = Path(__file__).resolve().parent.parent / SNAPSHOT_DIR
    outdir.mkdir(exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = outdir / f"{day}.json"
    path.write_text(json.dumps(snap, indent=2))
    n_movers = snap["movers"].get("mover_count", "?") if isinstance(snap.get("movers"), dict) else "?"
    n_news = len(snap["news"].get("hits", [])) if isinstance(snap.get("news"), dict) else "?"
    print(f"snapshot -> {path}")
    print(f"watchlist: {len(snap['watchlist'])} coins, movers: {n_movers}, news hits: {n_news}")


if __name__ == "__main__":
    main()
