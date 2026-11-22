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

IMPROVED 2026-11-22 at Brian's order (audit of the 2026-11-16 run:
the filing grammar was proper but the sweeps filed search junk —
Wikipedia's "S" article, a kids' alphabet page — while a material
CoreWeave loan headline sat buried and unflagged):
- Sweeps now query the SearXNG NEWS category and pull ~25 raw
  results, then filter and rank LOCALLY: junk domains and bare
  homepages are dropped, each sweep carries its own keyword set,
  and a headline must score >=2 keyword hits (or 1 strong hit) in
  title+snippet to be filed.
- Passing headlines file as INDIVIDUAL rows (metric
  <sweep>_headline, up to 3 per sweep) instead of one bundled
  blob, so they are findable and countable.
- A mechanical SIGNAL FLAG (regex over the title: $ amounts,
  loan/financing/refinancing closes, downgrade, default,
  cancellation) is recorded in the row's notes and listed
  separately in the capture. The flag is a keyword match, NOT a
  judgment — tell classification stays Spencer's residue.
- If nothing passes the filter, an explicit "no relevant
  headlines" row is filed with the raw/discarded counts, so a
  quiet sweep is distinguishable from a broken one.
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
# Each sweep: (node, metric, query, keywords, strong_keywords,
# require_any). keywords are matched case-insensitively against
# title+snippet; a headline files when hits >= 2, or >= 1 strong
# hit; when require_any is non-empty, at least one of its terms
# must also appear (added after the 2026-11-22 proof run let a
# mortgage article into the CoreWeave sweep and US sovereign
# downgrade explainers into the data-center sweep). Queries avoid
# tokens the engines mangle (the old "S&P ..." query was parsed
# as the letter "S" and returned alphabet pages).
SWEEPS = [
    ("bubble:the-money", "coreweave_refi_sweep",
     "CoreWeave refinancing loan debt",
     ["coreweave"],
     ["refinanc", "loan", "debt", "credit facilit", "ddtl",
      "billion"],
     ["coreweave"]),
    ("bubble:the-money", "cds_prints_sweep",
     "Nvidia Oracle CoreWeave credit default swap CDS spreads",
     ["cds", "credit default", "default swap", "credit spread"],
     ["cds", "credit default swap", "default swap"],
     []),
    ("bubble:the-money", "sp_dc_dashboard_sweep",
     "data center debt downgrade ratings agency outlook",
     ["data center", "data centre", "downgrade", "ratings",
      "debt"],
     ["downgrade", "missed payment", "default"],
     ["data center", "data centre", "datacenter"]),
    ("bubble:the-borrowers", "capex_guidance_sweep",
     "Microsoft Meta Google Amazon capex guidance cut spending",
     ["capex", "capital expenditure", "guidance", "spending"],
     ["capex cut", "cuts capex", "guidance cut", "trims",
      "lowers guidance"],
     []),
    ("bubble:the-builders", "dc_cancellation_sweep",
     "data center cancelled project financing lenders",
     ["data center", "data centre", "cancel", "financing",
      "lender"],
     ["cancelled", "canceled", "cancellation", "scrapped",
      "halted", "lenders scrutinize"],
     ["data center", "data centre", "datacenter"]),
]

# Domains that are never sweep intel (encyclopedias, video/social
# aggregators, government data portals, kids' sites, cert mills).
JUNK_DOMAINS = (
    "wikipedia.org", "youtube.com", "youtu.be", "tiktok.com",
    "starfall.com", "baike.baidu.com", "data.gov", "datausa.io",
    "comptia.org", "usdebtclock.org", "linkedin.com",
)

# Mechanical signal flag — keyword match only, NOT a judgment.
SIGNAL_RE = re.compile(
    r"(\$\s?\d[\d,.]*\s?(billion|bn|million|m|trillion)\b"
    r"|refinanc|loan|credit facilit|downgrad|default"
    r"|missed payment|cancel|scrapped|bankrupt)", re.I)


def fetch(url, timeout=35):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def searx_news(q, n=25):
    """News-category search; returns raw result dicts (title, url,
    content snippet, publishedDate) for local filtering."""
    url = SEARX + "?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "categories": "news"})
    data = json.loads(fetch(url, 45))
    return data.get("results", [])[:n]


def _domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _is_homepage(url):
    try:
        p = urllib.parse.urlparse(url)
        return p.path in ("", "/") and not p.query
    except Exception:
        return True


def filter_headlines(results, keywords, strong, require_any=()):
    """Drop junk/homepages, score by keyword hits in title+snippet,
    dedupe by URL. Returns (kept, n_raw, n_discarded); kept is a
    list of (score, title, url, snippet, published) best-first."""
    seen, kept = set(), []
    discarded = 0
    for r in results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("content") or "").strip()
        if not title or not url or url in seen:
            discarded += 1
            continue
        seen.add(url)
        dom = _domain(url)
        if any(dom == d or dom.endswith("." + d) for d in JUNK_DOMAINS) \
                or _is_homepage(url):
            discarded += 1
            continue
        hay = (title + " " + snippet).lower()
        if require_any and not any(k in hay for k in require_any):
            discarded += 1
            continue
        hits = sum(1 for k in keywords if k in hay)
        strong_hits = sum(1 for k in strong if k in hay)
        if hits >= 2 or strong_hits >= 1:
            kept.append((strong_hits * 3 + hits, title, url,
                         snippet, r.get("publishedDate") or ""))
        else:
            discarded += 1
    kept.sort(key=lambda t: -t[0])
    return kept, len(results), discarded


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
    flagged = []
    for node, metric, q, keywords, strong, require_any in SWEEPS:
        try:
            raw = searx_news(q)
            kept, n_raw, n_disc = filter_headlines(
                raw, keywords, strong, require_any)
            top = kept[:3]
            if not top:
                observe(node, metric, None,
                        "Sweep ran; NO relevant headlines passed "
                        "the filter this week (%d raw results, %d "
                        "discarded as junk/off-topic)."
                        % (n_raw, n_disc),
                        "SearXNG news sweep (filtered) — alpha "
                        "ai_bubble_collect.py", "low")
                pulled.append("%s (0 relevant of %d raw)"
                              % (metric, n_raw))
                continue
            for _score, title, url, snippet, pub in top:
                sig = bool(SIGNAL_RE.search(title))
                if sig:
                    flagged.append("%s: %s" % (metric, title))
                text = title + " | " + url
                if pub:
                    text += " | published " + str(pub)[:10]
                if snippet:
                    text += "\n" + snippet[:300]
                observe(node, metric + "_headline", None, text,
                        "SearXNG news sweep (filtered) — alpha "
                        "ai_bubble_collect.py", "low",
                        "Headline filed verbatim, NO interpretation; "
                        "tell classification is Spencer residue."
                        + (" SIGNAL FLAG (mechanical keyword match "
                           "in title — $ amount / financing / "
                           "downgrade / default / cancellation "
                           "term): Spencer to look."
                           if sig else ""))
            pulled.append("%s (%d relevant of %d raw, %d discarded)"
                          % (metric, len(top), n_raw, n_disc))
        except Exception as e:
            failed.append(metric)
            observe(node, metric, None,
                    "Sweep failed this week: %s" % repr(e)[:150],
                    "alpha ai_bubble_collect.py", "low")
    body = ("AI Bubble Graph weekly data pull (alpha collector, "
            "%s). Pulled: %s. Failed/dark: %s. SIGNAL-FLAGGED "
            "headlines (mechanical keyword match only, NOT a "
            "judgment): %s. JUDGMENT RESIDUE for Spencer (NOT done "
            "by this collector): tells sweep interpretation "
            "(trigger #3 first broad rental cut, crunch-spread "
            "4-week widening count, private-raise tell, hard "
            "events), hysteresis/state changes, the CoreWeave "
            "~$4.4B refinancing resolution call, and the "
            "cancellability split on any new commitments. No state "
            "was moved." % (today.isoformat(),
                             "; ".join(pulled) or "nothing",
                             "; ".join(failed) or "none",
                             "; ".join(flagged) or "none"))
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
