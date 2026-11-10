#!/usr/bin/env python3
"""Weather dataset collector for Kalshi daily city high-temperature markets.

Settlement (per Kalshi rules_primary, verified 2026-11-08): maximum temperature
recorded at the city's climate station (e.g. Minneapolis CLIMSP, Chicago CLIMDW,
NYC CLINYC) according to The Weather Company. The matching ASOS station's daily
max (via Iowa State IEM) is our recorded proxy for the actual; the NWS daily
climate report for the same station is the underlying source.

Two modes:
  collect  - snapshot today's + tomorrow's Kalshi brackets (bid/ask) plus
             multi-model forecasts (Open-Meteo: ECMWF IFS, GFS, ICON) into
             ../weather/weather_log.csv  (append; one row per market per run)
  settle   - for a given date (default yesterday), fetch each station's actual
             daily max from IEM and append to ../weather/actuals.csv

No keys, no auth, deterministic. Usage:
  python3 weather_collect.py collect
  python3 weather_collect.py settle [YYYY-MM-DD]
"""
import csv, json, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "weather"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"

# city: (kalshi series, IEM network, IEM station, lat, lon, open-meteo timezone)
CITIES = {
    "Minneapolis": ("KXHIGHTMIN", "MN_ASOS", "MSP", 44.8848, -93.2223, "America/Chicago"),
    "Chicago":     ("KXHIGHCHI",  "IL_ASOS", "MDW", 41.7868, -87.7522, "America/Chicago"),
    "New York":    ("KXHIGHNY",   "NY_ASOS", "NYC", 40.7789, -73.9692, "America/New_York"),
    "Denver":      ("KXHIGHDEN",  "CO_ASOS", "DEN", 39.8561, -104.6737, "America/Denver"),
    "Miami":       ("KXHIGHMIA",  "FL_ASOS", "MIA", 25.7959, -80.2870, "America/New_York"),
    "Austin":      ("KXHIGHAUS",  "TX_ASOS", "AUS", 30.1975, -97.6664, "America/Chicago"),
}
MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sbos-weather-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                print(f"WARN failed {url[:110]}: {e}", file=sys.stderr)
                return {}
            time.sleep(2 * (i + 1))

def date_code(d):
    return f"{str(d.year)[2:]}{MONTHS[d.month-1]}{d.day:02d}"

def forecasts(lat, lon, tz):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "daily": "temperature_2m_max",
        "temperature_unit": "fahrenheit", "timezone": tz,
        "models": "ecmwf_ifs025,gfs_seamless,icon_seamless", "forecast_days": 4,
    })
    j = get(f"https://api.open-meteo.com/v1/forecast?{q}")
    d = j.get("daily", {}) if j else {}
    out = {}
    times = d.get("time", [])
    for key, vals in d.items():
        if key == "time" or vals is None:
            continue
        for t, v in zip(times, vals):
            out.setdefault(t, {})[key] = v
    return out

def collect():
    OUT.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    rows = []
    for city, (series, net, stn, lat, lon, tz) in CITIES.items():
        fc = forecasts(lat, lon, tz)
        time.sleep(0.5)
        j = get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=200")
        today = datetime.now().date()
        wanted = {date_code(today): today.isoformat(),
                  date_code(today + timedelta(days=1)): (today + timedelta(days=1)).isoformat()}
        for m in j.get("markets", []):
            tick = m.get("ticker", "")
            code = next((c for c in wanted if f"-{c}-" in tick), None)
            if not code:
                continue
            dstr = wanted[code]
            f = fc.get(dstr, {})
            vals = [v for v in f.values() if isinstance(v, (int, float))]
            rows.append({
                "snapshot_utc": now_utc.isoformat(timespec="seconds"),
                "city": city, "series": series, "station": stn, "date": dstr,
                "ticker": tick, "market_title": m.get("title"),
                "yes_bid": m.get("yes_bid_dollars"), "yes_ask": m.get("yes_ask_dollars"),
                "fc_ecmwf": f.get("temperature_2m_max_ecmwf_ifs025"),
                "fc_gfs": f.get("temperature_2m_max_gfs_seamless"),
                "fc_icon": f.get("temperature_2m_max_icon_seamless"),
                "fc_median": sorted(vals)[len(vals)//2] if vals else None,
            })
        time.sleep(0.7)
    path = OUT / "weather_log.csv"
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["snapshot_utc","city","series","station","date","ticker",
                                          "market_title","yes_bid","yes_ask","fc_ecmwf","fc_gfs",
                                          "fc_icon","fc_median"])
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"weather collect: {len(rows)} market rows across {len(CITIES)} cities")

def settle(datestr=None):
    OUT.mkdir(parents=True, exist_ok=True)
    d = datetime.fromisoformat(datestr).date() if datestr else datetime.now().date() - timedelta(days=1)
    rows = []
    for city, (series, net, stn, lat, lon, tz) in CITIES.items():
        j = get(f"https://mesonet.agron.iastate.edu/api/1/daily.json?network={net}&stations={stn}&date={d.isoformat()}")
        data = j.get("data", []) if isinstance(j, dict) else []
        if data:
            rows.append({"date": d.isoformat(), "city": city, "station": stn,
                         "actual_max_f": data[0].get("max_tmpf"),
                         "actual_min_f": data[0].get("min_tmpf"),
                         "source": "IEM ASOS daily (proxy for NWS climate report / The Weather Company)"})
        time.sleep(0.5)
    path = OUT / "actuals.csv"
    existing = set()
    if path.exists():
        with open(path) as f:
            existing = {(r["date"], r["station"]) for r in csv.DictReader(f)}
    rows = [r for r in rows if (r["date"], r["station"]) not in existing]
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","city","station","actual_max_f","actual_min_f","source"])
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"weather settle {d}: {len(rows)} new actuals")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if mode == "collect":
        collect()
    elif mode == "settle":
        settle(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print("usage: weather_collect.py collect|settle [YYYY-MM-DD]")
        sys.exit(1)
