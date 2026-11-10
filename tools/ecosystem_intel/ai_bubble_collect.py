#!/usr/bin/env python3
"""ai_bubble_collect.py — AI Bubble Graph weekly DATA PULL (alpha).

Migrated 2026-11-09 from the Muse-side cron ai-bubble-weekly-check
at Brian's order (pure scrape/check -> ecosystem). This script is
the DATA-PULL half only:

- Silicon Data index pages (H100 rent index SDH100RT, LLM token
  price index SDLLMTK): fetch + parse the published values; on
  failure, file an explicit source-unreachable observation (the
  graph's own grammar — a source dark two weeks running is itself a
  reportable fact for Spencer).
- SearXNG headline sweeps for the Node 1 (credit) and Node 4
  (scarcity) watch areas + the dated CoreWeave refinancing item:
  top headlines filed as low-confidence sweep observations, titles
  verbatim with URLs. NO interpretation.
- The weekly paragraph Intel Bridge capture, summarizing what was
  pulled and explicitly flagging the JUDGMENT RESIDUE.

JUDGMENT RESIDUE — never done here, always Spencer's: tells
(trigger #3, 4-week crunch-spread widening, private-raise tell,
hard events), the hysteresis rule, ANY state change in
ai_bubble_assessments / node axes, whether a headline is a
demand-driven cut vs a supply trim, and resolving the CoreWeave
unknown. RESEARCH ONLY — never trade, contact, or publish.
Cron (alpha, America/Chicago): 41 9 * * 1
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

CT = timezone(timedelta(hours=-6))
SEARX = "http://127.0.0.1:8891/search"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SD_PAGES = [
    ("bubble:the-scarcity-stack", "llm_token_price_index_check",
     "https://www.silicondata.com/products/silicon-index/llm-token-expenditure-index", "token"),
    ("bubble:the-scarcity-stack", "h100_rent_index_check",
     "https://www.silicondata.com/products/silicon-index/h100", "rent"),
]
SWEEPS = [
    ("bubble:the-money", "coreweave_refi_sweep",
     "CoreWeave refinancing 2026 debt news"),
    ("bubble:the-money", "cds_prints_sweep",
     "AI CDS CoreWeave Oracle Nvidia credit default swap news"),
    ("bubble:the-money", "sp_dc_dashboard_sweep",
     "S&P Global Ratings data centre debt dashboard downgrade"),
    ("bubble:the-borrowers", "capex_guidance_sweep",
     "hyperscaler capex guidance cut Microsoft Meta Google Amazon"),
    ("bubble:the-builders", "dc_cancellation_sweep",
     "data center project cancelled financing demand news"),
]


def fetch(url, timeout=35):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def searx(q, n=5):
    url = SEARX + "?" + urllib.parse.urlencode({"q": q,
                                                "format": "json"})
    data = json.loads(fetch(url, 45))
    return [(r.get("title", ""), r.get("url", ""))
            for r in data.get("results", [])[:n]]


def parse_index_value(html, kind):
    """Silicon Data index pages embed several products' headline
    blocks (escaped JSON inside the page payload), so the parse is
    anchored on the value+rawValue pair of a headline block, and —
    because every product block looks alike — the caller passes the
    block nearest the page's own 'As of' stat. In practice the FIRST
    value/rawValue pair on the page is the page's own product
    (verified 2026-11-09: SDLLMTK page -> 0.83 As of Nov 8)."""
    m = re.search(
        r'\\?"value\\?":\\?"\$\$?([0-9]+(?:\.[0-9]+)?)\\?",'
        r'\\?"rawValue\\?":\\?"([0-9]+(?:\.[0-9]+)?)', html)
    if m:
        return float(m.group(2))
    m = re.search(r'rawValue\\?":\\?"\$?([0-9]+(?:\.[0-9]+)?)', html)
    if m:
        return float(m.group(1))
    return None


def main():
    today = datetime.now(CT).date()
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()

    def observe(node, metric, vnum, vtext, source, conf, notes=""):
        cur.execute(
            "INSERT INTO successbrian_os.ai_bubble_observations "
            "(node_key, metric, value_num, value_text, source, "
            "source_date, checked_on, confidence, notes) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (node, metric, vnum, vtext, source, today, today, conf,
             notes))
    pulled, failed = [], []
    sd_values = {}
    for node, metric, url, kind in SD_PAGES:
        try:
            html = fetch(url)
            val = parse_index_value(html, kind)
            if val is None:
                raise ValueError("value not parseable in page")
            sd_values[metric] = val
            observe(node, metric, val, None,
                    "Silicon Data page %s (alpha ai_bubble_collect.py)"
                    % url, "medium",
                    "Data-pull only; index methodology is Silicon "
                    "Data's. Crunch-spread interpretation is Spencer "
                    "residue.")
            pulled.append("%s = %.4g" % (metric, val))
        except Exception as e:
            failed.append(metric)
            observe(node, metric + "_unreachable", None,
                    "SOURCE UNREACHABLE/UNPARSABLE from alpha this "
                    "week: %s (%s)" % (url, repr(e)[:100]),
                    "alpha ai_bubble_collect.py", "low",
                    "Second consecutive dark week is reportable per "
                    "the watch spec — Spencer to check the streak.")
    for node, metric, q in SWEEPS:
        try:
            heads = searx(q)
            text = ("Headline sweep (SearXNG, alpha collector) — "
                    "titles verbatim, NO interpretation; tell "
                    "classification is Spencer residue:\n" +
                    "\n".join("- %s | %s" % h for h in heads)) \
                if heads else "Sweep returned no results this week."
            observe(node, metric, None, text,
                    "SearXNG headline sweep — alpha ai_bubble_collect.py",
                    "low")
            pulled.append("%s (%d headlines)" % (metric, len(heads)))
        except Exception as e:
            failed.append(metric)
            observe(node, metric, None,
                    "Sweep failed this week: %s" % repr(e)[:150],
                    "alpha ai_bubble_collect.py", "low")
    body = ("AI Bubble Graph weekly data pull (alpha collector, "
            "%s). Pulled: %s. Failed/dark: %s. JUDGMENT RESIDUE for "
            "Spencer (NOT done by this collector): tells sweep "
            "interpretation (trigger #3 first broad rental cut, "
            "crunch-spread 4-week widening count, private-raise "
            "tell, hard events), hysteresis/state changes, the "
            "CoreWeave ~$4.4B refinancing resolution call, and the "
            "cancellability split on any new commitments. No state "
            "was moved." % (today.isoformat(),
                             "; ".join(pulled) or "nothing",
                             "; ".join(failed) or "none"))
    cur.execute(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s) RETURNING id",
        ("AI bubble weekly data pull %s (alpha collector)"
         % today.isoformat(), body,
         "TradesDesk/ecosystem_intel ai_bubble_collect.py on alpha "
         "(migrated from the Muse cron ai-bubble-weekly-check "
         "2026-11-09): data-pull half only. Judgment half is flagged "
         "residue for Spencer in the capture body. Research only."))
    cid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    print("ai_bubble_collect %s: pulled %d, failed %d, capture %d"
          % (today, len(pulled), len(failed), cid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
