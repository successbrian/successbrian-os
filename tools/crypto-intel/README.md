# Crypto Intel + Testing Toolkit

Two halves, one rule: **paper only**. Nothing here can place a real order —
there are no exchange keys, no order endpoints, no wallet signing anywhere
in this codebase. Brian's standing rules are coded in: paper trading first,
live execution only on his explicit approval, no martingale, every trade
carries a written reason.

## intel/ — market intelligence gathering

- `config.py` — the watchlist: Brian's six long-term holds (KAS, BTC, ADA,
  BNB, SOL, HYPE) plus trading-only ETH/DOGE; mover threshold (±6%);
  RSS feeds.
- `coingecko.py` — free CoinGecko client (no key). Disk cache + 6s
  politeness delay between calls.
- `movers.py` — scans the top 250 for ±6% daily moves (Brian's spec).
- `news.py` — scans CoinDesk + CoinTelegraph RSS for last-24h items
  mentioning watchlist coins → catalyst candidates.
- `snapshot.py` — runs everything, writes `snapshots/YYYY-MM-DD.json`.
  This is the artifact Altair's digest pipeline consumes.

Run it:

```bash
cd code
python -m intel.snapshot
```

## testing/ — paper trading + strategy tests

- `paper.py` — `PaperPortfolio`: virtual cash + positions, virtual fills at
  live prices, every trade logged to SQLite **with a required reason**.
  `buy()`/`sell()` raise if reason is empty. `mark()` records equity.
- `strategies.py` — strategy interface + two templates:
  - `SupportResistance` — Brian's actual discipline: buy near support,
    trim near resistance (default 25%, never dumps the hold). Levels live
    in the `LEVELS` dict — seed real ones before use.
  - `TrendTemplate` — MA-crossover baseline for comparison.
- `backtest.py` — replays CoinGecko history through a strategy:

```bash
cd code
python -m testing.backtest KAS --days 90 --strategy trend_template
```

## Data layout

- `snapshots/` — daily intel JSON (gitignored if large)
- `.cache/` — CoinGecko response cache
- `paper*.db` — paper trade logs + equity marks

## Roadmap

1. Seed real support/resistance `LEVELS` per coin (needs Brian/Altair).
2. Wire `intel.snapshot` into a daily cron on k11-alpha feeding Altair's
   research digest (Altair picks the handoff format — see altair-brain
   brief #9).
3. Yield-monitor half: best yields on high-liquidity pools, top BNB/Solana
   DEXes + CEX earn, no meme coins (DOGE excluded from DeFi anyway),
   no risky coins. (Brian to pick: yield monitor or spot paper-trading
   framework first — this repo starts the paper-trading side.)
