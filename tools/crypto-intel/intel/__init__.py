"""Market-intelligence gathering package (package init).

PURPOSE
    Make tools.crypto-intel.intel a package: the free market-data half of
    the crypto-intel toolkit -- CoinGecko client (coingecko.py), daily
    movers/volume vs 30-day avg/news catalysts (movers.py, news.py),
    snapshot.py JSON output that Altair's digest pipeline reads.

WHY
    The intel half answers Brian's research spec with zero API keys and
    zero cost: daily +/-6% movers, volume vs 30-day average, news
    catalysts for his watchlist. Splitting intel/ off testing/ keeps the
    market-data gathering (safe, read-only, public endpoints) separate
    from the trading simulators, so nothing in the data path can ever be
    mistaken for trade-execution code.

CALLED BY
    - tools/crypto-intel/intel/snapshot.py (digest JSON for Altair)
    - tools/crypto-intel/testing/backtest.py and paper.py (feed the
      simulators with cached market data)
    - Manual runs: python -m intel.snapshot (from tools/crypto-intel/)

NOTES
    - Paper-only toolchain: no exchange keys, no order endpoints, no
      wallet signing anywhere in this codebase.
"""
