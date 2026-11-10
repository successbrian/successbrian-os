#!/usr/bin/env python3
"""stock_watch.py — TradesDesk daily stock watches (alpha-native).

Migrated 2026-11-09 from the Muse-side crons amd-stock-daily-watch,
intc-stock-daily-watch and duol-bottom-watch-2026 (daily close check)
at Brian's order: pure scrape/check watches run on his own ecosystem
to save credits. Specs of record: the Muse cron bodies in
~/workspace/goals/automated-trading-system-build/crons/ (hatch) and
Intel Bridge capture filed 2026-11-09 (scrape-watch-migration).

Data source: Nasdaq public API (api.nasdaq.com) — script-readable from
alpha with a browser UA. (Finnhub has no key on alpha; Stooq is
bot-walled from alpha.) Every figure comes from the API response of
this run; nothing is invented.

WATCH-ONLY: never buys, sells, places orders, or contacts a broker.
Judgment stays with Spencer/Brian: when a trigger fires this script
files a TRIGGER capture labeled for Spencer's evaluation (INTC bottom
formation -> full buy evaluation; DUOL bottom formation / deadline ->
full evaluation). It never evaluates.

Filing pattern follows DealsDesk gpu_watch_daily.py: one Intel Bridge
capture per symbol per run (atlas.scattered_captures), then the
reading as price state in successbrian_os.price_intel (capture_id FK),
then the capture's raw_text is updated with the full stat set.
State files (bottom counts, reported zones) live in ./state/.

Usage:
    python3 stock_watch.py --symbol AMD|INTC|DUOL|ALL
    python3 stock_watch.py --selftest     (live fetch + parse, no writes)
Cron (alpha, America/Chicago): 41 15 * * 1-5  stock_watch.py --symbol ALL
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CT = timezone(timedelta(hours=-6))  # America/Chicago (CST; CDT shifts are immaterial for a date label)

ANCHORS = {
    "AMD": {"anchor": 578.44, "anchor_date": "2026-10-28"},
    "INTC": {"crash_close": 65.76, "crash_date": "2026-10-30",
             "zones": [60.0, 55.0, 50.0, 43.75]},
    "DUOL": {"watch_start": "2026-10-26", "base_low": 133.68,
             "zones": [125.0, 120.0, 107.0, 92.0],
             "deadline": "2026-12-31"},
}
NAMES = {"AMD": "Advanced Micro Devices", "INTC": "Intel",
         "DUOL": "Duolingo"}


def db():
    return psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)


def money(s):
    if s is None:
        return None
    s = str(s).replace("$", "").replace(",", "").replace("%", "").strip()
    if s in ("", "N/A", "NA", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_stats(sym):
    """Return dict of today's stats + full history rows (newest first)."""
    info = fetch_json("https://api.nasdaq.com/api/quote/%s/info"
                      "?assetclass=stocks" % sym)["data"]
    fromdate = (date.today() - timedelta(days=220)).strftime("%Y-%m-%d")
    hist = fetch_json("https://api.nasdaq.com/api/quote/%s/historical"
                      "?assetclass=stocks&fromdate=%s"
                      % (sym, fromdate))["data"]
    rows = []
    for r in hist["tradesTable"]["rows"]:
        d = datetime.strptime(r["date"], "%m/%d/%Y").date()
        rows.append({"date": d, "close": money(r["close"]),
                     "open": money(r["open"]), "high": money(r["high"]),
                     "low": money(r["low"]),
                     "volume": money(r["volume"])})
    rows.sort(key=lambda x: x["date"], reverse=True)
    pd = info["primaryData"]
    rng = info.get("keyStats", {}).get("fiftyTwoWeekHighLow", {}).get("value", "")
    wk = [money(x) for x in rng.replace("-", " ").split()] if rng else []
    return {
        "symbol": sym,
        "close": money(pd["lastSalePrice"]),
        "change": money(pd["netChange"]),
        "pct": money(pd["percentageChange"]),
        "volume": money(pd["volume"]),
        "trade_date": rows[0]["date"] if rows else None,
        "day_open": rows[0]["open"] if rows else None,
        "day_high": rows[0]["high"] if rows else None,
        "day_low": rows[0]["low"] if rows else None,
        "prev_close": rows[1]["close"] if len(rows) > 1 else None,
        "wk52_low": wk[0] if len(wk) == 2 else None,
        "wk52_high": wk[1] if len(wk) == 2 else None,
        "rows": rows,
    }


def ma(rows, n, end=0):
    seg = rows[end:end + n]
    if len(seg) < n:
        return None
    return sum(r["close"] for r in seg) / n


def state_path(sym):
    return os.path.join(STATE_DIR, sym.lower() + ".json")


def load_state(sym):
    p = state_path(sym)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return {}


def save_state(sym, st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(sym), "w") as f:
        json.dump(st, f, indent=1, default=str)


def file_capture(cur, title, context, raw=""):
    cur.execute("INSERT INTO atlas.scattered_captures (title, raw_text, "
                "context) VALUES (%s, %s, %s) RETURNING id",
                (title, raw, context))
    return cur.fetchone()["id"]


def stat_block(st):
    lines = [
        "%s (%s) — %s" % (st["symbol"], NAMES[st["symbol"]],
                          st["trade_date"].isoformat()),
        "close %.2f | change %+.2f (%+.2f%%) | prev close %.2f" % (
            st["close"], st["change"] or 0, st["pct"] or 0,
            st["prev_close"] or 0),
        "day range %.2f-%.2f (open %.2f) | volume %s" % (
            st["day_low"] or 0, st["day_high"] or 0, st["day_open"] or 0,
            ("%d" % st["volume"]) if st["volume"] else "n/a"),
    ]
    if st["wk52_low"]:
        lines.append("52-week range %.2f-%.2f" % (st["wk52_low"],
                                                  st["wk52_high"]))
    m50 = ma(st["rows"], 50)
    if m50:
        lines.append("50-day MA %.2f" % m50)
    return "\n".join(lines)


def base_filing(cur, st, extra_context):
    """File the daily capture + price_intel row. Returns capture_id."""
    today = datetime.now(CT).date()
    cid = file_capture(
        cur, "%s daily stats %s" % (st["symbol"],
                                    st["trade_date"].isoformat()),
        "%s daily stats (TradesDesk stock_watch.py on alpha, migrated "
        "from the Muse cron 2026-11-09). Source: Nasdaq API "
        "(api.nasdaq.com), checked %s America/Chicago. Watch-only. %s"
        % (st["symbol"], today.isoformat(), extra_context))
    cur.execute(
        "SELECT id FROM successbrian_os.price_intel WHERE item=%s AND "
        "checked_on=%s::date",
        ("%s — daily close (TradesDesk stock watch)" % st["symbol"],
         st["trade_date"].isoformat()))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO successbrian_os.price_intel (capture_id, item, "
            "amount, currency, source_label, source_url, statement, "
            "checked_on, valid_until) VALUES (%s, %s, %s, 'USD', %s, %s, "
            "%s, %s::date, now() + interval '7 days')",
            (cid, "%s — daily close (TradesDesk stock watch)" % st["symbol"],
             st["close"], "Nasdaq API via alpha stock_watch.py",
             "https://api.nasdaq.com/api/quote/%s/info?assetclass=stocks"
             % st["symbol"],
             "%s close %.2f on %s (%+.2f%%); 52wk %.2f-%.2f; 50d MA %s"
             % (st["symbol"], st["close"], st["trade_date"].isoformat(),
                st["pct"] or 0, st["wk52_low"] or 0, st["wk52_high"] or 0,
                ("%.2f" % ma(st["rows"], 50)) if ma(st["rows"], 50) else "n/a"),
             st["trade_date"].isoformat()))
    return cid


def finish_capture(cur, cid, raw):
    cur.execute("UPDATE atlas.scattered_captures SET raw_text=%s "
                "WHERE id=%s", (raw, cid))


def trigger(cur, sym, title, body):
    return file_capture(
        cur, "%s TRIGGER %s: %s" % (sym, datetime.now(CT).date().isoformat(),
                                    title),
        "Filed by alpha stock_watch.py (TradesDesk) for Spencer to "
        "surface / evaluate. Watch-only — no order, no evaluation by "
        "this script.", body)


# ---------------------------------------------------------------- AMD
def run_amd(cur, st):
    a = ANCHORS["AMD"]
    trig = []
    if st["pct"] is not None and abs(st["pct"]) >= 5:
        trig.append("day move %+.2f%% (>= 5%%)" % st["pct"])
    if st["wk52_high"] and st["close"] >= st["wk52_high"]:
        trig.append("new 52-week high (close %.2f >= %.2f)"
                    % (st["close"], st["wk52_high"]))
    if st["wk52_low"] and st["close"] <= st["wk52_low"]:
        trig.append("new 52-week low (close %.2f <= %.2f)"
                    % (st["close"], st["wk52_low"]))
    m50_now, m50_prev = ma(st["rows"], 50, 0), ma(st["rows"], 50, 1)
    if m50_now and m50_prev and st["prev_close"]:
        if (st["prev_close"] - m50_prev) * (st["close"] - m50_now) < 0:
            trig.append("close crossed the 50-day MA (prev %.2f vs MA "
                        "%.2f; now %.2f vs MA %.2f)"
                        % (st["prev_close"], m50_prev, st["close"], m50_now))
    derate = st["close"] <= a["anchor"] * 0.80
    if derate:
        trig.append("price %.2f is >=20%% below the 2026-10-28 anchor "
                    "$578.44 (reporting trigger only, NOT a buy line)"
                    % st["close"])
    cid = base_filing(cur, st, "Anchor $578.44 (2026-10-28); AMD fails "
                               "Brian's accumulation screen (forward P/E "
                               "~135 vs his ~25 ceiling) — watch-only.")
    raw = stat_block(st)
    raw += "\nvs anchor $578.44: %+.1f%% | vs 52wk high: %+.1f%%" % (
        (st["close"] / a["anchor"] - 1) * 100,
        (st["close"] / st["wk52_high"] - 1) * 100 if st["wk52_high"] else 0)
    raw += "\nTRIGGERS: " + ("; ".join(trig) if trig else "none")
    finish_capture(cur, cid, raw)
    for t in trig:
        trigger(cur, "AMD", t, raw)
    return trig


# ---------------------------------------------------------------- INTC
def run_intc(cur, st):
    a = ANCHORS["INTC"]
    rows = [r for r in st["rows"]
            if r["date"] >= date(2026, 10, 30)]
    rows_asc = list(reversed(rows))  # oldest first, today last
    state = load_state("INTC")
    seeded = "reported_zones" in state
    reported = set(state.get("reported_zones", []))
    trig = []
    if st["pct"] is not None and abs(st["pct"]) >= 5:
        trig.append("day move %+.2f%% (>= 5%%)" % st["pct"])
    # lowest close since the crash, before today
    prior = rows_asc[:-1]
    if prior:
        low_prior = min(r["close"] for r in prior)
        if st["close"] < low_prior:
            trig.append("NEW closing low since the 2026-10-30 crash: "
                        "%.2f < %.2f (bottom count resets to 0)"
                        % (st["close"], low_prior))
    low_row = min(rows_asc, key=lambda r: r["close"])
    sessions_since = len([r for r in rows_asc
                          if r["date"] > low_row["date"]])
    # zone first entries (seeded silently from history on first run)
    for z in a["zones"]:
        entered = [r for r in rows_asc if r["close"] <= z]
        if entered and z not in reported:
            if seeded or entered[0]["date"] == st["trade_date"]:
                trig.append("close entered review zone $%s for the "
                            "first time (close %.2f on %s) — proposal "
                            "zone for Brian's review, NOT a buy line"
                            % (("%g" % z), st["close"],
                               entered[0]["date"].isoformat()))
            reported.add(z)
    # bottom formation: >=5 sessions no new low + reclaim close today
    after_low = [r for r in rows_asc if r["date"] > low_row["date"]]
    reclaim = False
    if after_low:
        prior_highs = [r["high"] for r in after_low[:-1]
                       if r["high"] is not None]
        reclaim = (st["close"] > 70 or
                   (prior_highs and st["close"] > max(prior_highs)))
    formation = (sessions_since >= 5 and reclaim
                 and st["close"] > low_row["close"])
    if formation and not state.get("formation_reported"):
        trig.append("BOTTOM FORMATION COMPLETE: %d sessions with no new "
                    "closing low since %.2f (%s) + reclaim close %.2f. "
                    "FOR SPENCER: deliver the full buy evaluation per "
                    "the INTC watch spec; any purchase still needs "
                    "Brian's explicit go with size/budget."
                    % (sessions_since, low_row["close"],
                       low_row["date"].isoformat(), st["close"]))
        state["formation_reported"] = True
    cid = base_filing(cur, st, "Crash anchor $65.76 (2026-10-30 close). "
                               "Bottom rule: 5 sessions no new closing "
                               "low + reclaim close. Review zones are "
                               "proposals, not buy lines.")
    raw = stat_block(st)
    raw += ("\nlowest close since 2026-10-30: %.2f (%s) | sessions "
            "without a new closing low: %d/5 | reclaim today: %s"
            % (low_row["close"], low_row["date"].isoformat(),
               sessions_since, "yes" if reclaim else "no"))
    raw += "\nTRIGGERS: " + ("; ".join(trig) if trig else "none")
    finish_capture(cur, cid, raw)
    for t in trig:
        trigger(cur, "INTC", t, raw)
    state["reported_zones"] = sorted(reported)
    state["last_run"] = datetime.now(CT).isoformat()
    state["lowest_close"] = low_row["close"]
    state["sessions_since_low"] = sessions_since
    save_state("INTC", state)
    return trig


# ---------------------------------------------------------------- DUOL
def run_duol(cur, st):
    a = ANCHORS["DUOL"]
    state = load_state("DUOL")
    if not state:
        # Seed from Brian's checkpoint of record (hatch
        # duol-watch-state.md, last checked Mon 2026-11-09).
        state = {"lowest_close": 128.00, "lowest_date": "2026-11-03",
                 "level_13368_reported": True, "reported_zones": [],
                 "formation_reported": False,
                 "terminal_delivered": False, "earnings_evaluated": True,
                 "deadline_filed": False}
    rows = [r for r in st["rows"]
            if r["date"] >= date(2026, 10, 26)]
    rows_asc = list(reversed(rows))
    trig = []
    today_close = st["close"]
    if today_close < state["lowest_close"]:
        trig.append("LEVEL: new closing low for this leg: %.2f < prior "
                    "lowest close %.2f (%s). Bottom count resets."
                    % (today_close, state["lowest_close"],
                       state["lowest_date"]))
        state["lowest_close"] = today_close
        state["lowest_date"] = st["trade_date"].isoformat()
        state["formation_reported"] = False
    if today_close < a["base_low"] and not state["level_13368_reported"]:
        trig.append("LEVEL: first close below $133.68 base low: %.2f"
                    % today_close)
        state["level_13368_reported"] = True
    reported = set(state.get("reported_zones", []))
    for z in a["zones"]:
        if today_close <= z and z not in reported:
            trig.append("LEVEL: first close in/below the $%g zone: %.2f"
                        % (z, today_close))
            reported.add(z)
    state["reported_zones"] = sorted(reported)
    # sessions since the lowest close (from full history in window)
    low_date = date.fromisoformat(state["lowest_date"])
    after = [r for r in rows_asc if r["date"] > low_date]
    sessions = len(after)
    highs_since = [r["high"] for r in after[:-1] if r["high"] is not None]
    formation = (sessions >= 5 and today_close >= state["lowest_close"]
                 and (today_close > 140 or
                      (highs_since and today_close > max(highs_since))))
    if formation and not state["formation_reported"]:
        trig.append("BOTTOM FORMATION: %d consecutive sessions with no "
                    "new closing low since %.2f (%s) + close %.2f above "
                    "$140 / the range high since the low. FOR SPENCER: "
                    "run the FULL EVALUATION per the DUOL watch spec "
                    "and deliver it — that is the main deliverable of "
                    "this watch. Evaluation only; Brian is the gate on "
                    "any purchase."
                    % (sessions, state["lowest_close"],
                       state["lowest_date"], today_close))
        state["formation_reported"] = True
    # deadline: last weekday on or before 2026-12-31
    today = datetime.now(CT).date()
    dl = date(2026, 12, 31)
    nxt = today + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    if today <= dl and nxt > dl and not state["deadline_filed"]:
        trig.append("DEADLINE: last weekday check on or before "
                    "2026-12-31. FOR SPENCER: deliver the final DUOL "
                    "evaluation even though no other trigger fired, "
                    "and state the watch is ending.")
        state["deadline_filed"] = True
    cid = base_filing(cur, st, "DUOL bottom watch (Brian 2026-10-26). "
                               "CLOSE CHECK ONLY on alpha — the full "
                               "evaluation at a trigger is Spencer's.")
    raw = stat_block(st)
    raw += ("\nlowest close (watch, since 2026-10-26): %.2f (%s) | "
            "sessions since low: %d/5 | earnings evaluated: yes "
            "(2026-11-03) | terminal evaluation delivered: no"
            % (state["lowest_close"], state["lowest_date"], sessions))
    raw += "\nTRIGGERS: " + ("; ".join(trig) if trig else "none")
    finish_capture(cur, cid, raw)
    for t in trig:
        trigger(cur, "DUOL", t, raw)
    state["last_run"] = datetime.now(CT).isoformat()
    state["last_close"] = today_close
    save_state("DUOL", state)
    return trig


RUNNERS = {"AMD": run_amd, "INTC": run_intc, "DUOL": run_duol}


def main(argv):
    if "--selftest" in argv:
        st = fetch_stats("AMD")
        print(stat_block(st))
        print("selftest ok: live Nasdaq fetch + parse")
        return 0
    syms = ["AMD", "INTC", "DUOL"]
    if "--symbol" in argv:
        s = argv[argv.index("--symbol") + 1].upper()
        syms = syms if s == "ALL" else [s]
    conn = db()
    cur = conn.cursor()
    rc = 0
    for sym in syms:
        try:
            st = fetch_stats(sym)
            if st["close"] is None or not st["rows"]:
                raise RuntimeError("no data in Nasdaq response")
            trig = RUNNERS[sym](cur, st)
            conn.commit()
            print("%s %s close %.2f (%+.2f%%) triggers: %s"
                  % (sym, st["trade_date"], st["close"], st["pct"] or 0,
                     "; ".join(trig) if trig else "none"))
        except Exception as e:
            conn.rollback()
            rc = 1
            try:
                file_capture(
                    cur, "%s daily stats FAILED %s"
                    % (sym, datetime.now(CT).date().isoformat()),
                    "TradesDesk stock_watch.py on alpha: the %s check "
                    "FAILED — no reading was filed. Error: %s"
                    % (sym, repr(e)[:300]),
                    "check failed: %s" % repr(e)[:300])
                conn.commit()
            except Exception:
                conn.rollback()
            print("%s FAILED: %s" % (sym, e), file=sys.stderr)
    conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
