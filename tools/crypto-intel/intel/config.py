"""
PURPOSE:
    Shared config for the crypto intel + testing toolkit.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
# Brian's six long-term buy-and-hold coins (hands-off in real life; paper only here)
LONG_TERM = {
    "kaspa": "KAS",
    "bitcoin": "BTC",
    "cardano": "ADA",
    "binancecoin": "BNB",
    "solana": "SOL",
    "hyperliquid": "HYPE",
}

# Trading-only coins (no long hold)
TRADING_ONLY = {
    "ethereum": "ETH",
    "dogecoin": "DOGE",
}

WATCHLIST = {**LONG_TERM, **TRADING_ONLY}

# Mover-scan threshold per Brian's research spec
MOVER_PCT = 6.0
TOP_N_SCAN = 250

# CoinGecko free tier: be polite
CG_BASE = "https://api.coingecko.com/api/v3"
CG_SLEEP = 6  # seconds between calls (free tier ~10-15/min)

# RSS feeds for the news-catalyst scan
NEWS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

SNAPSHOT_DIR = "snapshots"
CACHE_DIR = ".cache"
