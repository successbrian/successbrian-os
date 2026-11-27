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

DAILY PRICE PULL + EFFICIENCY PASS (2026-11-27, Brian's order —
sources discovered by the consumer/prosumer pricing dig, Intel
Bridge capture #3595):
- AI-COMPUTE-ONLY RULE (Brian, 2026-11-27: "factor out gaming
  volume and do our best to only consider AI compute volume"):
  every volume/price signal here must be an AI-compute signal --
  datacenter shipments, AI accelerator cards, server memory,
  GPU rental rates. Consumer/gaming signals are OUT: the
  videocardprices consumer GPU index and the RTX 3090 pull were
  removed under this rule (2026-11-27), and the JPR sweep keys
  on the datacenter line only, never add-in-board or client.
- New daily-capable price sources, all filing under the Scarcity
  node as data-pull observations: rackbites.com/gpu used-GPU
  eBay ask medians (V100 32GB / A100 40GB — the
  server-pull watch), DRAMeXchange spot session averages
  (DDR5 16Gb / DDR4 16Gb).
- A JPR shipments sweep joins the weekly sweeps (Jon Peddie
  Research quarterly DATACENTER unit numbers are the volume
  indicator -- the client/AIB lines are gaming volume, excluded).
- Efficiency: all page fetches and sweeps run in PARALLEL
  (ThreadPoolExecutor); each fetch retries once; a content-hash
  state file skips re-parsing pages that did not change; price
  metrics file CHANGE-ONLY (a row is filed when the value moved,
  or as a 7-day heartbeat so the series never goes stale);
  identical (metric, value, source_date) rows are never
  duplicated; all inserts are batched into one executemany.
- Modes: default run = full on Mondays, price-pull-only other
  days (cron fires daily; the script picks). --full / --daily
  force a mode. A price-only run files its Intel Bridge capture
  ONLY when something changed or failed (quiet days stay quiet);
  the full weekly run always captures, as before.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
    ("bubble:the-scarcity-stack", "jpr_shipments_sweep",
     "Jon Peddie Research datacenter GPU shipments",
     ["gpu", "shipments", "datacenter", "data center",
      "jon peddie"],
     ["jon peddie", "jpr", "datacenter gpu", "data center gpu"],
     ["gpu"]),
]

# Daily price sources (2026-11-27, capture #3595). Each entry:
# (page_key, url, parser_name). Parsers return a list of
# (metric, value_num, notes) filed under the Scarcity node.
PRICE_PAGES = [
    ("rackbites",
     "https://rackbites.com/gpu",
     "parse_rackbites"),
    ("dramexchange",
     "https://dramexchange.com/",
     "parse_dramexchange"),
]
PRICE_NODE = "bubble:the-scarcity-stack"
PRICE_SOURCE_LABEL = {
    "rackbites": "rackbites.com/gpu eBay asking prices "
                 "(alpha ai_bubble_collect.py)",
    "dramexchange": "DRAMeXchange spot prices "
                    "(alpha ai_bubble_collect.py)",
}
STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "state",
    "ai_bubble_collect_http.json")

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


def fetch(url, timeout=35, retries=1):
    """GET with one retry on transient failure (2026-11-27: a
    single timeout used to dark a source for a whole week)."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url,
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(2)
    raise last


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass  # state is an optimization, never a hard dependency


def fetch_unchanged(url, state):
    """Fetch a page; return None when its content hash matches
    the last run's (page unchanged -> nothing new to file)."""
    html = fetch(url)
    h = hashlib.sha256(html.encode("utf-8", "ignore")).hexdigest()
    if state.get(url, {}).get("sha256") == h:
        return None
    state[url] = {"sha256": h,
                  "seen": datetime.now(CT).isoformat()}
    return html


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


def _strip(html):
    return re.sub(r"\s+", " ",
                  re.sub(r"<[^>]+>", " ", html)).strip()


def _usd(s):
    return float(s.replace(",", ""))


def parse_rackbites(html):
    """Used-GPU eBay ASKING prices. Stripped-text rows read:
    'Tesla V100 32GB ... $1,250 ...' = name, VRAM, listing
    count, low, median. Watch metrics file the MEDIAN."""
    txt = _strip(html)
    out = []
    for name_re, metric, label in (
            (r"Tesla V100 32GB", "used_v100_32gb_ask_median",
             "Tesla V100 32GB"),
            (r"A100 40GB", "used_a100_40gb_ask_median",
             "A100 40GB")):
        m = re.search(name_re + r" (\d+) \$([\d,]+) \$([\d,]+)",
                      txt)
        if m:
            out.append((metric, _usd(m.group(3)),
                        "%s eBay asking MEDIAN $%s (low $%s, %s "
                        "listings, rackbites). Asking, not sold. "
                        "Data-pull only; server-pull "
                        "interpretation is Spencer residue."
                        % (label, m.group(3), m.group(2),
                           m.group(1))))
    return out


def parse_dramexchange(html):
    """DRAM spot table. Stripped-text rows read: 'DDR5 16Gb
    (2Gx8) 4800/5600 71.45 45.00 71.40 45.00 60.333 -0.71 %' =
    daily high/low, session high/low, SESSION AVERAGE, change.
    Watch metrics file the session average."""
    txt = _strip(html)
    out = []
    for item_re, metric, label in (
            (r"DDR5 16Gb \(2Gx8\) 4800/5600", "ddr5_16gb_spot",
             "DDR5 16Gb"),
            (r"DDR4 16Gb \(2Gx8\) 3200", "ddr4_16gb_spot",
             "DDR4 16Gb")):
        m = re.search(item_re + r" ([-\d.]+) ([-\d.]+) "
                      r"([-\d.]+) ([-\d.]+) ([-\d.]+) "
                      r"([-\d.]+) %", txt)
        if m:
            out.append((metric, float(m.group(5)),
                        "%s spot SESSION AVERAGE $%s, day change "
                        "%s%% (DRAMeXchange). Data-pull only; "
                        "memory-market interpretation is "
                        "Spencer residue."
                        % (label, m.group(5), m.group(6))))
    return out


def main():
    argv = sys.argv[1:]
    today = datetime.now(CT).date()
    full = ("--full" in argv) or (
        "--daily" not in argv and today.weekday() == 0)
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()
    rows = []

    def queue(node, metric, vnum, vtext, source, conf, notes=""):
        rows.append((node, metric, vnum, vtext, source, today,
                     today, conf, notes))

    def last_filed(metric):
        cur.execute(
            "SELECT value_num, checked_on FROM "
            "successbrian_os.ai_bubble_observations WHERE metric "
            "= %s ORDER BY id DESC LIMIT 1", (metric,))
        return cur.fetchone()

    def queue_index(node, metric, val, source, notes):
        """Change-only filing for numeric index/price metrics:
        file when the value moved, or as a 7-day heartbeat so
        the series never goes stale; never duplicate an
        identical (metric, value, source_date) row."""
        last = last_filed(metric)
        if last and last["value_num"] is not None \
                and float(last["value_num"]) == float(val) \
                and (today - last["checked_on"]).days < 7:
            return False
        queue(node, metric, val, None, source, "medium", notes)
        return True

    state = load_state()
    pulled, failed, changed = [], [], []

    # --- Fetch phase (parallel; workers touch no DB) ---
    def sd_job(spec):
        node, metric, url, kind = spec
        try:
            html = fetch_unchanged(url, state)
            if html is None:
                return ("sd-skip", metric, None)
            val = parse_index_value(html, kind)
            if val is None:
                raise ValueError("value not parseable in page")
            return ("sd", metric, (node, val, url))
        except Exception as e:
            return ("sd-fail", metric, (node, url, repr(e)[:100]))

    def price_job(spec):
        key, url, parser_name = spec
        try:
            html = fetch_unchanged(url, state)
            if html is None:
                return ("price-skip", key, None)
            items = globals()[parser_name](html)
            if not items:
                raise ValueError("no metrics parseable in page")
            return ("price", key, items)
        except Exception as e:
            return ("price-fail", key, repr(e)[:120])

    def sweep_job(spec):
        node, metric, q, keywords, strong, require_any = spec
        raw = searx_news(q)
        kept, n_raw, n_disc = filter_headlines(
            raw, keywords, strong, require_any)
        return (node, metric, kept, n_raw, n_disc)

    jobs = [("sd", s) for s in SD_PAGES]
    jobs += [("price", p) for p in PRICE_PAGES]
    if full:
        jobs += [("sweep", s) for s in SWEEPS]
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {}
        for kind, spec in jobs:
            fn = {"sd": sd_job, "price": price_job,
                  "sweep": sweep_job}[kind]
            futs[ex.submit(fn, spec)] = (kind, spec)
        for fut, (kind, spec) in futs.items():
            key = spec[1] if kind in ("sd", "sweep") else spec[0]
            try:
                results[(kind, key)] = fut.result()
            except Exception as e:
                results[(kind, key)] = ("job-fail", key,
                                        repr(e)[:150])

    # --- Silicon Data indexes ---
    for node, metric, url, kind in SD_PAGES:
        r = results.get(("sd", metric))
        if r is None or r[0] == "job-fail":
            failed.append(metric)
            queue(node, metric + "_unreachable", None,
                  "SOURCE UNREACHABLE/UNPARSABLE from alpha this "
                  "run: %s" % url,
                  "alpha ai_bubble_collect.py", "low",
                  "Second consecutive dark run is reportable per "
                  "the watch spec — Spencer to check the streak.")
        elif r[0] == "sd-skip":
            pulled.append("%s (unchanged)" % metric)
        elif r[0] == "sd-fail":
            failed.append(metric)
            queue(node, metric + "_unreachable", None,
                  "SOURCE UNREACHABLE/UNPARSABLE from alpha this "
                  "run: %s (%s)" % (url, r[2][2]),
                  "alpha ai_bubble_collect.py", "low",
                  "Second consecutive dark run is reportable per "
                  "the watch spec — Spencer to check the streak.")
        else:
            _, _, (n2, val, u2) = r
            if queue_index(
                    node, metric, val,
                    "Silicon Data page %s (alpha "
                    "ai_bubble_collect.py)" % u2,
                    "Data-pull only; index methodology is "
                    "Silicon Data's. Crunch-spread "
                    "interpretation is Spencer residue."):
                changed.append(metric)
            pulled.append("%s = %.4g" % (metric, val))

    # --- Daily price sources (2026-11-27) ---
    for key, url, parser_name in PRICE_PAGES:
        r = results.get(("price", key))
        label = PRICE_SOURCE_LABEL[key]
        if r is None or r[0] in ("job-fail", "price-fail"):
            failed.append(key)
            queue(PRICE_NODE, key + "_unreachable", None,
                  "SOURCE UNREACHABLE/UNPARSABLE from alpha "
                  "this run: %s (%s)"
                  % (url, r[2] if r else "no result"),
                  "alpha ai_bubble_collect.py", "low",
                  "Second consecutive dark run is reportable "
                  "per the watch spec — Spencer to check.")
        elif r[0] == "price-skip":
            pulled.append("%s (unchanged)" % key)
        else:
            for metric, val, notes in r[2]:
                if queue_index(PRICE_NODE, metric, val, label,
                               notes):
                    changed.append(metric)
                pulled.append("%s = %.4g" % (metric, val))

    # --- Weekly headline sweeps (full mode only) ---
    flagged = []
    if full:
        for node, metric, q, keywords, strong, require_any \
                in SWEEPS:
            r = results.get(("sweep", metric))
            if r is None or (isinstance(r, tuple) and len(r)
                             and r[0] == "job-fail"):
                failed.append(metric)
                queue(node, metric, None,
                      "Sweep failed this run: %s"
                      % (r[2] if r else "no result"),
                      "alpha ai_bubble_collect.py", "low")
                continue
            _, _, kept, n_raw, n_disc = r
            top = kept[:3]
            if not top:
                queue(node, metric, None,
                      "Sweep ran; NO relevant headlines passed "
                      "the filter this run (%d raw results, %d "
                      "discarded as junk/off-topic)."
                      % (n_raw, n_disc),
                      "SearXNG news sweep (filtered) — alpha "
                      "ai_bubble_collect.py", "low")
                pulled.append("%s (0 relevant of %d raw)"
                              % (metric, n_raw))
                continue
            for _score, title, surl, snippet, pub in top:
                sig = bool(SIGNAL_RE.search(title))
                if sig:
                    flagged.append("%s: %s" % (metric, title))
                text = title + " | " + surl
                if pub:
                    text += " | published " + str(pub)[:10]
                if snippet:
                    text += "\n" + snippet[:300]
                queue(node, metric + "_headline", None, text,
                      "SearXNG news sweep (filtered) — alpha "
                      "ai_bubble_collect.py", "low",
                      "Headline filed verbatim, NO "
                      "interpretation; tell classification is "
                      "Spencer residue."
                      + (" SIGNAL FLAG (mechanical keyword "
                         "match in title — $ amount / financing "
                         "/ downgrade / default / cancellation "
                         "term): Spencer to look."
                         if sig else ""))
            pulled.append("%s (%d relevant of %d raw, %d "
                          "discarded)"
                          % (metric, len(top), n_raw, n_disc))

    # --- Batch insert ---
    if rows:
        cur.executemany(
            "INSERT INTO successbrian_os.ai_bubble_observations "
            "(node_key, metric, value_num, value_text, source, "
            "source_date, checked_on, confidence, notes) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s)", rows)

    # --- Capture: full runs always; price-only runs only when
    # something changed or failed (quiet days stay quiet) ---
    cid = None
    if full or changed or failed:
        mode = "full weekly" if full else "daily price"
        body = ("AI Bubble Graph %s data pull (alpha collector, "
                "%s). Pulled: %s. Changed: %s. Failed/dark: %s. "
                "SIGNAL-FLAGGED headlines (mechanical keyword "
                "match only, NOT a judgment): %s. JUDGMENT "
                "RESIDUE for Spencer (NOT done by this "
                "collector): tells sweep interpretation "
                "(trigger #3 first broad rental cut, "
                "crunch-spread 4-week widening count, "
                "private-raise tell, hard events), "
                "hysteresis/state changes, the CoreWeave ~$4.4B "
                "refinancing resolution call, and the "
                "cancellability split on any new commitments. "
                "No state was moved."
                % (mode, today.isoformat(),
                   "; ".join(pulled) or "nothing",
                   "; ".join(changed) or "none",
                   "; ".join(failed) or "none",
                   "; ".join(flagged) or "none"))
        cur.execute(
            "INSERT INTO atlas.scattered_captures (title, "
            "raw_text, context) VALUES (%s, %s, %s) RETURNING id",
            ("AI bubble %s data pull %s (alpha collector)"
             % (mode, today.isoformat()), body,
             "TradesDesk/ecosystem_intel ai_bubble_collect.py "
             "on alpha (migrated from the Muse cron "
             "ai-bubble-weekly-check 2026-11-09; daily price "
             "sources added 2026-11-27, capture #3595): "
             "data-pull half only. Judgment half is flagged "
             "residue for Spencer in the capture body. "
             "Research only."))
        cid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    save_state(state)
    print("ai_bubble_collect %s (%s): pulled %d, changed %d, "
          "failed %d, rows %d, capture %s"
          % (today, "full" if full else "daily", len(pulled),
             len(changed), len(failed), len(rows),
             cid if cid else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
