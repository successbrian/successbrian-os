"""
PURPOSE:
    ±6% daily mover scan across the top-250, per Brian's research spec.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    For each mover: price, 24h change, 24h volume, market cap, and a flag for
whether volume looks elevated (vs the coin's own recent average when
history is available). News-catalyst matching happens in news.py.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
from . import coingecko as cg
from .config import MOVER_PCT, TOP_N_SCAN


def scan_movers(threshold=MOVER_PCT, top_n=TOP_N_SCAN):
    coins = cg.top_markets(per_page=top_n)
    movers = []
    for c in coins:
        chg = c.get("price_change_percentage_24h")
        if chg is None or abs(chg) < threshold:
            continue
        movers.append({
            "id": c["id"],
            "symbol": c["symbol"].upper(),
            "name": c["name"],
            "price": c["current_price"],
            "change_24h": round(chg, 2),
            "volume_24h": c.get("total_volume"),
            "market_cap": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
        })
    movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
    return {
        "generated_at": cg.stamp(),
        "threshold_pct": threshold,
        "universe": top_n,
        "mover_count": len(movers),
        "movers": movers,
    }
