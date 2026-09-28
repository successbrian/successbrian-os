"""
PURPOSE:
    News-catalyst scan: pull crypto RSS feeds, keep items from the last 24h that mention any watchlist coin (by symbol or name), for pairing with price movers.

WHY:
    Brian's research spec: daily ±6% movers, volume vs 30-day avg, news catalysts.

CALLED BY:
- Altair's digest pipeline (snapshot.py JSON output)
    - Manual runs: python -m intel.snapshot / testing.backtest (from this dir)

NOTES:
    Moved 2026-09-28 from ~/workspace/goals/crypto-research-feed-for-hermes-agent/code/ (night-shift consolidation). Data dirs (.cache/, snapshots/) resolve relative to this package.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

from . import coingecko as cg
from .config import NEWS_FEEDS, WATCHLIST


def _fetch_rss(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "spencer-intel/1.0"})
    r.raise_for_status()
    return r.text


def _items(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        desc = (item.findtext("description") or "")[:500]
        yield {"title": title, "link": link, "published": pub, "summary": desc}


def _recent(pub_str, hours=24):
    try:
        dt = parsedate_to_datetime(pub_str)
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt < timedelta(hours=hours)


def _mentions(text, coin_id, symbol):
    t = text.lower()
    name = coin_id.replace("-", " ")
    return bool(re.search(rf"\b{re.escape(symbol.lower())}\b", t)
                or re.search(rf"\b{re.escape(name)}\b", t))


def scan_news(hours=24):
    hits = []
    for feed in NEWS_FEEDS:
        try:
            xml_text = _fetch_rss(feed)
        except Exception as e:
            hits.append({"feed": feed, "error": str(e)[:120]})
            continue
        for it in _items(xml_text):
            if not _recent(it["published"], hours):
                continue
            blob = f"{it['title']} {it['summary']}"
            coins = [sym for cid, sym in WATCHLIST.items()
                     if _mentions(blob, cid, sym)]
            if coins:
                it["coins"] = coins
                it["feed"] = feed
                hits.append(it)
    return {"generated_at": cg.stamp(), "window_hours": hours, "hits": hits}
