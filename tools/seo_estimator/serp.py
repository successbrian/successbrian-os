#!/usr/bin/env python3
"""SERP competition analysis via DuckDuckGo HTML (free, rarely blocked).

PURPOSE: For each keyword, who ranks in the top 10 and are they beatable?
WHY: Volume without rankability is fantasy. A keyword owned by Mayo Clinic
    and Healthline is not the same as one owned by Reddit threads and thin
    affiliates -- even at identical search volume.
CALLED BY: estimate.py

Beatability signals (deterministic, no APIs):
    + forums/UGC in top 10 (reddit, quora, facebook groups) -> weak
    + thin affiliate / MFA-looking domains -> weak
    + outdated content (old dates in snippets) -> weak-ish
    - authority giants (webmd, mayoclinic, healthline, etc.) -> strong
    - major publishers / brands -> strong-ish
"""

import re
import time
import urllib.parse
from collections import Counter

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_DDG = "https://html.duckduckgo.com/html/"

_UGC = ("reddit.com", "quora.com", "facebook.com", "tiktok.com",
        "pinterest.com", "youtube.com")
_GIANTS = ("webmd.com", "mayoclinic.org", "healthline.com", "medicalnewstoday",
           "verywell", "clevelandclinic.org", "nih.gov", "cdc.gov",
           "forbes.com", "nytimes.com", "amazon.com", "wikipedia.org")


def fetch_serp(keyword, retries=2):
    """Return list of (domain, title) for top ~10 organic results."""
    last_err = None
    for _ in range(retries + 1):
        try:
            r = requests.post(_DDG, data={"q": keyword},
                              headers={"User-Agent": UA}, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            out = []
            for res in soup.select(".result"):
                a = res.select_one(".result__a")
                if not a:
                    continue
                href = a.get("href", "")
                # DDG wraps links: //duckduckgo.com/l/?uddg=<encoded>
                m = re.search(r"uddg=([^&]+)", href)
                url = urllib.parse.unquote(m.group(1)) if m else href
                dom = urllib.parse.urlparse(url).netloc.lower()
                dom = dom[4:] if dom.startswith("www.") else dom
                if dom:
                    out.append((dom, a.get_text(strip=True)[:120]))
                if len(out) >= 10:
                    break
            return out
        except Exception as e:  # noqa: BLE001 - transient
            last_err = e
            time.sleep(3)
    raise RuntimeError("serp fetch failed for %r: %s" % (keyword, last_err))


def beatability(results):
    """Score 0-100: how beatable is this SERP for a new quality site?

    Also returns a realistic position band a good new site could reach
    within 6-12 months: 'top3' | 'page1' | 'page1-low' | 'page2'.
    """
    if not results:
        return 50, "page1"
    doms = [d for d, _ in results]
    ugc_hits = sum(1 for d in doms if any(u in d for u in _UGC))
    giant_hits = sum(1 for d in doms if any(g in d for g in _GIANTS))
    uniq = len(set(doms))

    score = 55  # baseline: an average SERP
    score += ugc_hits * 12          # forums ranking = weak competition
    score -= giant_hits * 15        # authority giants = entrenched
    if uniq >= 8:
        score += 5                  # fragmented SERP, no dominant player
    score = max(5, min(95, score))

    if score >= 70:
        band = "top3"
    elif score >= 50:
        band = "page1"
    elif score >= 30:
        band = "page1-low"
    else:
        band = "page2"
    return score, band


def analyze(keyword):
    results = fetch_serp(keyword)
    score, band = beatability(results)
    top_domains = [d for d, _ in results[:5]]
    return {"keyword": keyword, "top_domains": top_domains,
            "beatability": score, "position_band": band,
            "result_count": len(results)}


if __name__ == "__main__":
    import sys, json
    print(json.dumps(analyze(" ".join(sys.argv[1:])), indent=1))
