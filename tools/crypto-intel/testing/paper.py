"""
PURPOSE:
    Paper-trading engine. VIRTUAL MONEY ONLY.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    Design rule, non-negotiable: this module has NO capability to place real
orders. It knows no exchange API keys, no order endpoints, no wallet
signing. It prices fills off public market data and logs everything to
SQLite for review. Brian's rule stands: paper first, live only on his
explicit approval, no martingale, no unexplained trades.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "paper.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,          -- BUY or SELL
    qty REAL NOT NULL,
    price REAL NOT NULL,         -- fill price (live market price at fill time)
    notional REAL NOT NULL,      -- qty * price
    reason TEXT NOT NULL,        -- WHY: strategy name + signal; never empty
    strategy TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    total REAL NOT NULL
);
"""


class PaperPortfolio:
    """A virtual portfolio. Cash + positions, marked to live prices."""

    def __init__(self, starting_cash=10000.0, db_path=DB):
        self.db_path = str(db_path)
        self.cash = float(starting_cash)
        self.positions = {}  # symbol -> {"qty": float, "avg_cost": float}
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.commit()
        con.close()

    # ---- execution (virtual fills at the given live price) ----
    def buy(self, symbol, qty, price, reason, strategy):
        symbol = symbol.upper()
        if not reason:
            raise ValueError("refusing order with no reason — every trade must be explained")
        notional = qty * price
        if notional > self.cash:
            raise ValueError(f"insufficient paper cash: need {notional:.2f}, have {self.cash:.2f}")
        self.cash -= notional
        pos = self.positions.get(symbol, {"qty": 0.0, "avg_cost": 0.0})
        new_qty = pos["qty"] + qty
        pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + notional) / new_qty
        pos["qty"] = new_qty
        self.positions[symbol] = pos
        self._log(symbol, "BUY", qty, price, notional, reason, strategy)
        return {"symbol": symbol, "side": "BUY", "qty": qty, "price": price, "reason": reason}

    def sell(self, symbol, qty, price, reason, strategy):
        symbol = symbol.upper()
        if not reason:
            raise ValueError("refusing order with no reason — every trade must be explained")
        pos = self.positions.get(symbol)
        if not pos or pos["qty"] < qty:
            raise ValueError(f"insufficient paper position in {symbol}")
        notional = qty * price
        self.cash += notional
        pos["qty"] -= qty
        if pos["qty"] <= 1e-12:
            del self.positions[symbol]
        self._log(symbol, "SELL", qty, price, notional, reason, strategy)
        return {"symbol": symbol, "side": "SELL", "qty": qty, "price": price, "reason": reason}

    def _log(self, symbol, side, qty, price, notional, reason, strategy):
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO trades (ts, symbol, side, qty, price, notional, reason, strategy)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), symbol, side, qty, price, notional, reason, strategy),
        )
        con.commit()
        con.close()

    # ---- valuation ----
    def mark(self, prices):
        """prices: {SYMBOL: live_price}. Records an equity mark, returns totals."""
        pv = sum(pos["qty"] * prices.get(sym, 0.0) for sym, pos in self.positions.items())
        total = self.cash + pv
        con = sqlite3.connect(self.db_path)
        con.execute(
            "INSERT INTO equity_marks (ts, cash, positions_value, total) VALUES (?, ?, ?, ?)",
            (time.time(), self.cash, pv, total),
        )
        con.commit()
        con.close()
        return {"cash": self.cash, "positions_value": pv, "total": total,
                "positions": dict(self.positions)}

    def trade_history(self, limit=50):
        con = sqlite3.connect(self.db_path)
        rows = con.execute(
            "SELECT ts, symbol, side, qty, price, notional, reason, strategy"
            " FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return rows
