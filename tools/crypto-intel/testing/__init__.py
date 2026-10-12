"""Strategy-testing package: paper trading and backtesting (package init).

PURPOSE
    Make tools.crypto-intel.testing a package: the strategy-evaluation half
    of the crypto-intel toolkit -- paper.py (VIRTUAL MONEY ONLY live-paper
    engine), backtest.py (historical replay), strategies.py (the rules
    under test).

WHY
    Brian's standing rule is paper first: every strategy must prove itself
    against historical and live-paper data before live execution is even a
    conversation, and live still needs his explicit approval. This package
    is the sandbox where that proof happens. Keeping testing/ separate
    from intel/ keeps the simulators away from the data-gathering path --
    and the design rule is non-negotiable: this module has NO capability
    to place real orders (no exchange keys, no order endpoints, no wallet
    signing; fills priced off public market data, everything logged to
    SQLite).

CALLED BY
    - Manual/scheduled evaluation runs: python -m testing.backtest,
      python -m testing.paper (from tools/crypto-intel/)
    - Reads cached market data produced by the intel/ package.

NOTES
    - No martingale, no unexplained trades: every trade carries a written
      reason (coded in, not a convention).
"""
