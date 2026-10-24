#!/usr/bin/env python3
"""Google Trends interest-over-time via direct HTTP (no pytrends dependency).

PURPOSE: Relative search demand (0-100) for keywords. Free, no API key.
WHY: pytrends isn't installed on k11 and adds a dependency; the Trends API
    is plain HTTP underneath. This implements the minimal flow we need.
CALLED BY: estimate.py
"""

import json
import time
import urllib.parse

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_EXPLORE = "https://trends.google.com/trends/api/explore"
_WIDGET = "https://trends.google.com/trends/api/widgetdata/multiline"


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    # prime cookies with a plain page hit
    s.get("https://trends.google.com/trends/", timeout=20)
    return s


def get_interest(keywords, timeframe="today 12-m", geo="US", retries=2):
    """Return {keyword: {'avg': float, 'peak': float, 'trend': str}}.

    avg/peak are 0-100 relative values. trend is 'rising'|'flat'|'falling'
    from comparing the last 3 months against the first 3.
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [k for k in keywords if k][:5]  # API limit per batch
    last_err = None
    for _ in range(retries + 1):
        try:
            return _fetch(keywords, timeframe, geo)
        except Exception as e:  # noqa: BLE001 - transient network/API hiccups
            last_err = e
            time.sleep(3)
    raise RuntimeError("trends fetch failed: %s" % last_err)


def _fetch(keywords, timeframe, geo):
    s = _session()
    comp = [{"keyword": k, "geo": geo, "time": timeframe} for k in keywords]
    req = {"comparisonItem": comp, "category": 0, "property": ""}
    params = {"hl": "en-US", "tz": "-360",
              "req": json.dumps(req)}
    r = s.get(_EXPLORE, params=params, timeout=30)
    r.raise_for_status()
    payload = json.loads(r.text[len(")]}',"):])
    widget = None
    for w in payload.get("widgets", []):
        if w.get("id") == "TIMESERIES":
            widget = w
            break
    if not widget:
        raise RuntimeError("no TIMESERIES widget in trends response")
    token = widget["token"]
    req2 = dict(widget["request"])
    r2 = s.get(_WIDGET, params={"hl": "en-US", "tz": "-360",
                                "req": json.dumps(req2),
                                "token": token}, timeout=30)
    r2.raise_for_status()
    data = json.loads(r2.text[len(")]}',"):])
    out = {}
    for i, kw in enumerate(keywords):
        vals = []
        for point in data.get("default", {}).get("timelineData", []):
            v = point.get("value", [])
            if i < len(v):
                vals.append(v[i])
        if not vals:
            out[kw] = {"avg": 0.0, "peak": 0.0, "trend": "flat"}
            continue
        avg = sum(vals) / len(vals)
        peak = max(vals)
        n = len(vals)
        head = sum(vals[: max(1, n // 4)]) / max(1, n // 4)
        tail = sum(vals[-max(1, n // 4):]) / max(1, n // 4)
        if tail > head * 1.25:
            trend = "rising"
        elif tail < head * 0.75:
            trend = "falling"
        else:
            trend = "flat"
        out[kw] = {"avg": round(avg, 1), "peak": peak, "trend": trend}
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(get_interest(sys.argv[1:]), indent=1))
