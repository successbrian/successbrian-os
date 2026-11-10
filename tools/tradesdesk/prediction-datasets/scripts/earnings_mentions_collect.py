#!/usr/bin/env python3
"""Earnings-mention dataset collector (Kalshi, public API, no auth).

Builds two outputs in ../earnings_mentions/:
  live_snapshot.csv  - currently open mention markets for the tracked tech names:
                       company, event segment, word/phrase, min mentions required,
                       yes bid/ask (dollars), close time, ticker.
  base_rates.csv     - from Kalshi's OWN settled history (/historical/markets):
                       per company + word: times offered, times resolved YES,
                       base rate. This is the v1 base-rate table; transcript
                       analysis is a later layer for never-offered words.

Word/threshold parsing: rules_primary reads e.g.
  "If Rubin (3+ times) is said by any NVIDIA Corporation representative ..."
Deterministic parsing only. No LLM anywhere in this pipeline.

Usage: python3 earnings_mentions_collect.py
"""
import csv, json, re, sys, time, urllib.request
from pathlib import Path

BASE = "https://api.elections.kalshi.com/trade-api/v2"
OUT = Path(__file__).resolve().parent.parent / "earnings_mentions"
COMPANIES = ["NVDA", "AMD", "AVGO", "ORCL", "CRWV", "PLTR",
             "AAPL", "MSFT", "META", "GOOGL", "AMZN", "MRVL"]
SERIES = {c: f"KXEARNINGSMENTION{c}" for c in COMPANIES}

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sbos-mention-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                print(f"WARN failed {url[:100]}: {e}", file=sys.stderr)
                return {}
            time.sleep(2 * (i + 1))

WORD_RE = re.compile(r"^If (.+?) is said", re.I)
COUNT_RE = re.compile(r"\((\d+)\+\s*times\)\s*$")

def parse_word(rules, ticker):
    if rules:
        m = WORD_RE.match(rules.strip())
        if m:
            phrase = m.group(1).strip()
            cm = COUNT_RE.search(phrase)
            if cm:
                return phrase[:cm.start()].strip(), int(cm.group(1))
            return phrase, 1
    return ticker.rsplit("-", 1)[-1], None

def event_segment(ticker):
    parts = ticker.split("-")
    return parts[1] if len(parts) > 2 else ""

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    live_rows, hist_rows = [], []
    for comp, series in SERIES.items():
        # live
        j = get(f"{BASE}/markets?series_ticker={series}&status=open&limit=200")
        for m in j.get("markets", []):
            word, need = parse_word(m.get("rules_primary"), m.get("ticker", ""))
            live_rows.append({
                "company": comp, "event": event_segment(m.get("ticker", "")),
                "word": word, "min_mentions": need,
                "yes_bid": m.get("yes_bid_dollars"), "yes_ask": m.get("yes_ask_dollars"),
                "volume": m.get("volume_fp"), "close_time": m.get("close_time"),
                "ticker": m.get("ticker"),
            })
        time.sleep(0.7)
        # settled history, paginated
        cursor, pages = None, 0
        while pages < 10:
            url = f"{BASE}/historical/markets?series_ticker={series}&limit=200"
            if cursor:
                url += f"&cursor={cursor}"
            j = get(url)
            ms = j.get("markets", [])
            if not ms:
                break
            for m in ms:
                if m.get("result") not in ("yes", "no"):
                    continue
                word, need = parse_word(m.get("rules_primary"), m.get("ticker", ""))
                hist_rows.append({
                    "company": comp, "event": event_segment(m.get("ticker", "")),
                    "word": word, "min_mentions": need,
                    "result": m.get("result"),
                    "last_price": m.get("last_price_dollars"),
                    "ticker": m.get("ticker"),
                })
            cursor = j.get("cursor")
            pages += 1
            if not cursor:
                break
            time.sleep(0.7)

    with open(OUT / "live_snapshot.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "event", "word", "min_mentions",
                                          "yes_bid", "yes_ask", "volume", "close_time", "ticker"])
        w.writeheader(); w.writerows(live_rows)
    with open(OUT / "history_raw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "event", "word", "min_mentions",
                                          "result", "last_price", "ticker"])
        w.writeheader(); w.writerows(hist_rows)

    # base rates: group by company + normalized word + threshold
    agg = {}
    for r in hist_rows:
        key = (r["company"], (r["word"] or "").lower(), r["min_mentions"])
        a = agg.setdefault(key, {"offered": 0, "yes": 0, "events": set()})
        a["offered"] += 1; a["events"].add(r["event"])
        if r["result"] == "yes":
            a["yes"] += 1
    base = []
    for (comp, word, need), a in sorted(agg.items()):
        base.append({"company": comp, "word": word, "min_mentions": need,
                     "times_offered": a["offered"], "times_yes": a["yes"],
                     "base_rate": round(a["yes"] / a["offered"], 3) if a["offered"] else None,
                     "distinct_calls": len(a["events"])})
    with open(OUT / "base_rates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "word", "min_mentions",
                                          "times_offered", "times_yes", "base_rate", "distinct_calls"])
        w.writeheader(); w.writerows(base)
    print(f"live rows: {len(live_rows)} | settled history rows: {len(hist_rows)} | base-rate keys: {len(base)}")

if __name__ == "__main__":
    main()
