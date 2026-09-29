"""
PURPOSE:
    Strategy templates for the paper engine.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    Every strategy is a pure function of market data -> list of signals.
Signals carry a human-readable reason (required by PaperPortfolio).

Included:
  SupportResistance  — Brian's actual discipline: buy near known support,
                       sell near known resistance, hold long-term otherwise.
                       Levels are configured per coin and live in one dict
                       so they can be reviewed/updated in the open.
  TrendTemplate      — a simple moving-average-crossover template, for
                       comparing a rules-based system against the
                       support/resistance discipline in backtests.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
from dataclasses import dataclass


@dataclass
class Signal:
    symbol: str
    side: str          # BUY or SELL
    reason: str


class Strategy:
    name = "base"

    def on_bar(self, symbol, price, history, portfolio):
        """Return [] or [Signal, ...]. history = list of past prices (oldest first)."""
        raise NotImplementedError


# --- Brian's support / resistance levels -------------------------------------
# Seed with placeholder bands; Brian/Altair confirm real levels before use.
# Format: SYMBOL -> {"support": float, "resistance": float}
LEVELS = {
    # "KAS": {"support": 0.030, "resistance": 0.060},
}


class SupportResistance(Strategy):
    """Buy when price touches support, sell a tranche near resistance.

    band_pct: how close to the level counts as a "touch" (default 3%).
    sell_fraction: portion of the position to trim at resistance (default 25%)
                   — never dumps the whole long-term hold.
    """
    name = "support_resistance"

    def __init__(self, levels=None, band_pct=0.03, sell_fraction=0.25):
        self.levels = levels or LEVELS
        self.band_pct = band_pct
        self.sell_fraction = sell_fraction

    def on_bar(self, symbol, price, history, portfolio):
        lv = self.levels.get(symbol.upper())
        if not lv:
            return []  # no levels on file -> no opinion
        signals = []
        pos = portfolio.positions.get(symbol.upper(), {"qty": 0.0})
        if price <= lv["support"] * (1 + self.band_pct) and pos["qty"] == 0:
            signals.append(Signal(symbol, "BUY",
                f"{self.name}: {symbol} {price:.6g} within {self.band_pct:.0%} of support {lv['support']:.6g}"))
        elif price >= lv["resistance"] * (1 - self.band_pct) and pos["qty"] > 0:
            signals.append(Signal(symbol, "SELL",
                f"{self.name}: {symbol} {price:.6g} within {self.band_pct:.0%} of resistance {lv['resistance']:.6g}; trim {self.sell_fraction:.0%}"))
        return signals


class TrendTemplate(Strategy):
    """MA-crossover template: BUY when fast MA crosses above slow MA,
    SELL on cross under. For comparison backtests only."""
    name = "trend_template"

    def __init__(self, fast=10, slow=30):
        self.fast = fast
        self.slow = slow

    @staticmethod
    def _ma(xs, n):
        return sum(xs[-n:]) / n if len(xs) >= n else None

    def on_bar(self, symbol, price, history, portfolio):
        if len(history) < self.slow + 1:
            return []
        f_now, s_now = self._ma(history, self.fast), self._ma(history, self.slow)
        f_prev = self._ma(history[:-1], self.fast)
        s_prev = self._ma(history[:-1], self.slow)
        if f_now is None or s_now is None or f_prev is None or s_prev is None:
            return []
        pos = portfolio.positions.get(symbol.upper(), {"qty": 0.0})
        if f_prev <= s_prev and f_now > s_now and pos["qty"] == 0:
            return [Signal(symbol, "BUY",
                f"{self.name}: fast({self.fast}) crossed above slow({self.slow}) at {price:.6g}")]
        if f_prev >= s_prev and f_now < s_now and pos["qty"] > 0:
            return [Signal(symbol, "SELL",
                f"{self.name}: fast({self.fast}) crossed below slow({self.slow}) at {price:.6g}")]
        return []
