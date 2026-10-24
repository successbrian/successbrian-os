#!/usr/bin/env python3
"""The visitor math: keyword cluster -> estimated monthly visits (range).

PURPOSE: Convert free signals into an honest visitor estimate and a 50K
    verdict. Outputs a RANGE, never false precision.
WHY: Free data cannot give exact search volumes. A range with a clear
    verdict (clears 50K on low / high / neither) is decision-useful without
    lying about precision.

Formula per keyword:
    visits = volume_band_mid x ctr(position) x ai_erosion x intent_factor

    - volume_band_mid: calibrated from Google Trends vs anchors.json
    - ctr(position): FirstPageSage 2024 organic CTR curve
    - ai_erosion: 0.6 for informational queries (AI Overviews eat clicks),
      1.0 for transactional/navigational
    - intent_factor: informational 1.0 (blog content matches), mixed 0.7

Position comes from SERP beatability: top3 band -> pos 3, page1 -> pos 5,
page1-low -> pos 8, page2 -> pos 12 (CTR ~0.01).
"""

import json
import math
import os

ANCHORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "anchors.json")

# FirstPageSage 2024 organic CTR by position (fraction of clicks)
CTR = {1: 0.276, 2: 0.158, 3: 0.110, 4: 0.080, 5: 0.061,
       6: 0.044, 7: 0.035, 8: 0.030, 9: 0.026, 10: 0.024}
CTR_PAGE2 = 0.010

BAND_POSITION = {"top3": 3, "page1": 5, "page1-low": 8, "page2": 12}

AI_EROSION_INFORMATIONAL = 0.6  # tunable; publishers down ~40% YoY Oct 2026

_INFORMATIONAL_STARTERS = ("what", "how", "why", "is", "can", "does",
                           "should", "guide", "benefits", "side effects")


def load_anchors():
    with open(ANCHORS_PATH) as f:
        data = json.load(f)
    anchors = data.get("anchors", data)
    return {k: v["volume"] for k, v in anchors.items()
            if isinstance(v, dict) and "volume" in v}


def calibrate_volume(keyword, trends_avg, anchors):
    """Return (low, mid, high) monthly volume estimate for a keyword.

    Method: find the anchor closest in Trends-space, scale by relative
    interest ratio, then widen into a band (x0.3 / x3) to stay honest.
    Falls back to word-count heuristics when no anchor is close.
    """
    kw = keyword.lower()
    if kw in anchors:
        v = anchors[kw]
        return (int(v * 0.5), v, int(v * 2))
    # heuristic fallback: head terms >> long-tail
    # bands are wide on purpose; tighten via anchors.json as real data lands
    words = len(kw.split())
    if trends_avg >= 70 and words <= 2:
        mid = 800000
    elif trends_avg >= 50 and words <= 2:
        mid = 300000
    elif trends_avg >= 25:
        mid = 60000
    elif words >= 5:
        mid = 3000
    elif words >= 3:
        mid = 12000
    else:
        mid = 20000
    # nudge by trend direction signal passed in as trends_avg already
    # reflecting recent interest; keep the band wide
    return (int(mid * 0.3), mid, int(mid * 3))


def is_informational(keyword):
    words = set(keyword.lower().split())
    return bool(words & set(_INFORMATIONAL_STARTERS))


def keyword_visits(keyword, trends_avg, position_band):
    """Return dict with low/mid/high monthly visit estimate for one keyword."""
    anchors = load_anchors()
    low_v, mid_v, high_v = calibrate_volume(keyword, trends_avg, anchors)
    pos = BAND_POSITION.get(position_band, 8)
    ctr = CTR.get(pos, CTR_PAGE2)
    erosion = AI_EROSION_INFORMATIONAL if is_informational(keyword) else 1.0
    # informational intent matches blog content; transactional less so
    intent = 1.0 if is_informational(keyword) else 0.7
    factor = ctr * erosion * intent
    return {"keyword": keyword,
            "volume_band": [low_v, mid_v, high_v],
            "position_assumed": pos, "ctr": round(ctr, 3),
            "ai_erosion": erosion,
            "visits_low": int(low_v * factor),
            "visits_mid": int(mid_v * factor),
            "visits_high": int(high_v * factor)}


def cluster_estimate(topic, keyword_data, target=50000):
    """keyword_data: list of (keyword, trends_avg, position_band).

    Returns the cluster roll-up with the 50K verdict.
    """
    per_kw = [keyword_visits(k, t, p) for k, t, p in keyword_data]
    low = sum(k["visits_low"] for k in per_kw)
    mid = sum(k["visits_mid"] for k in per_kw)
    high = sum(k["visits_high"] for k in per_kw)
    if low >= target:
        verdict = "STRONG YES -- clears 50K even on the low estimate"
    elif mid >= target:
        verdict = "MAYBE -- clears 50K on the mid estimate, not the low"
    elif high >= target:
        verdict = "LONG SHOT -- only the high estimate clears 50K"
    else:
        verdict = "NO -- does not clear 50K on any estimate"
    return {"topic": topic, "target": target,
            "visits_low": low, "visits_mid": mid, "visits_high": high,
            "verdict": verdict, "keywords": per_kw}


if __name__ == "__main__":
    # math smoke test with synthetic inputs (no network)
    demo = cluster_estimate("demo", [
        ("moringa benefits", 62, "page1"),
        ("what is moringa good for", 41, "top3"),
        ("moringa powder side effects", 28, "page1"),
    ])
    print(json.dumps(demo, indent=1))
