"""
PURPOSE:
    Backtest runner: replay CoinGecko history through a strategy on the paper engine. Virtual money only.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.
    Usage:
    python -m testing.backtest KAS --days 90 --strategy trend_template
    python -m testing.backtest KAS --days 90 --strategy support_resistance

For support_resistance you must seed LEVELS in strategies.py first.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intel import coingecko as cg
from testing.paper import PaperPortfolio
from testing.strategies import SupportResistance, TrendTemplate

CG_IDS = {"KAS": "kaspa", "BTC": "bitcoin", "ADA": "cardano",
          "BNB": "binancecoin", "SOL": "solana", "ETH": "ethereum",
          "DOGE": "dogecoin", "HYPE": "hype"}

STRATEGIES = {"trend_template": TrendTemplate, "support_resistance": SupportResistance}


def run(symbol, days=90, strategy_name="trend_template", cash=10000.0,
        trade_usd=1000.0):
    coin_id = CG_IDS[symbol.upper()]
    data = cg.market_chart(coin_id, days=days)
    prices = [p[1] for p in data.get("prices", [])]
    if not prices:
        print("no price history returned")
        return
    strat = STRATEGIES[strategy_name]()
    pf = PaperPortfolio(starting_cash=cash,
                        db_path=Path(__file__).resolve().parent.parent / f"paper_{symbol}_{strategy_name}.db")
    history = []
    trades = 0
    for price in prices:
        history.append(price)
        for sig in strat.on_bar(symbol, price, history, pf):
            try:
                if sig.side == "BUY":
                    qty = trade_usd / price
                    pf.buy(symbol, qty, price, sig.reason, strategy_name)
                else:
                    pos = pf.positions.get(symbol.upper(), {"qty": 0})
                    qty = pos["qty"] * (strat.sell_fraction if hasattr(strat, "sell_fraction") else 1.0)
                    if qty > 0:
                        pf.sell(symbol, qty, price, sig.reason, strategy_name)
                trades += 1
                print(f"  {sig.side} {symbol} @ {price:.6g} — {sig.reason[:90]}")
            except ValueError as e:
                print(f"  skip: {e}")
    mark = pf.mark({symbol.upper(): prices[-1]})
    ret = (mark["total"] / cash - 1) * 100
    buy_hold = (prices[-1] / prices[0] - 1) * 100
    print(f"\n{symbol} {strategy_name} over {days}d: {trades} paper trades")
    print(f"  portfolio: ${mark['total']:.2f} ({ret:+.1f}%)  vs buy&hold {buy_hold:+.1f}%")
    return mark


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="e.g. KAS")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--strategy", default="trend_template", choices=list(STRATEGIES))
    ap.add_argument("--cash", type=float, default=10000.0)
    ap.add_argument("--trade-usd", type=float, default=1000.0)
    a = ap.parse_args()
    run(a.symbol, a.days, a.strategy, a.cash, a.trade_usd)
