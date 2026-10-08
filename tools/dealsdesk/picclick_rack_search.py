#!/usr/bin/env python3
"""picclick_rack_search.py — find rack-server listings via PicClick, score them.

PURPOSE: Search PicClick (no API key needed) for rack servers, extract specs
         from listing titles, and rank candidates with rack_server_scorer.py.

WHY:     Brian 2026-10-08: the rack-server sourcing for the Colibri/DB
         expansion "should probably run off of picclick and not the api."
         The eBay Browse API needs credentials and rate-limit care; PicClick
         is a free aggregator over the same listings. This module is the
         ingestion half; rack_server_scorer.py is the ranking half. Title
         parsing is heuristic — specs it can't extract stay null and the
         scorer treats them as unknown, never as zero.

CALLED BY: DealsDesk agent (sourcing directive, knowledge_bridge row 23926);
         manually: --query "..." --score. Output JSON feeds the scorer.

NOTES:   - PicClick HTML is scraped, not API'd: keep request volume modest
           (one search per run, user-agent set). If PicClick changes markup,
           parse_listings() is the only thing that breaks.
         - Spec extraction is best-effort. "NO RAM" listings score ram_gb=0
           and the scorer REJECTs them under the 64GB floor — correct, since
           Brian's directive is for usable boxes, not barebones.
         - Prices are listing prices (Buy It Now / auction), not sold prices.
           "or Best Offer" means the real price may be lower — never present
           a listing price as a deal without saying so.
         - Threads assume 2x cores (E5-2609 v3/v4 have no HT: 1x — negligible
           for ranking; the scorer uses cores).
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/picclick_rack_search.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/picclick_rack_search.py (k11-alpha; when wired to a timer).

"""

import argparse
import html as ihtml
import json
import logging
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, __import__("os").path.dirname(__file__))
import rack_server_scorer as scorer

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [picclick] %(message)s")
LOG = logging.getLogger("picclick")

BASE = "https://picclick.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# Cores per chip for common E5 v3/v4 SKUs (key: model+version, no dash/space).
E5_CORES = {
    "2609v3": 6, "2620v3": 6, "2630v3": 8, "2637v3": 4, "2640v3": 8,
    "2643v3": 6, "2650v3": 10, "2660v3": 10, "2667v3": 8, "2670v3": 12,
    "2680v3": 12, "2683v3": 14, "2690v3": 12, "2695v3": 14, "2697v3": 14,
    "2698v3": 16, "2699v3": 18,
    "2609v4": 8, "2620v4": 8, "2630v4": 10, "2637v4": 4, "2640v4": 10,
    "2643v4": 6, "2650v4": 12, "2660v4": 14, "2667v4": 8,
    "2680v4": 14, "2690v4": 14, "2695v4": 18, "2697v4": 18, "2699v4": 22,
}

# Title must look like a server, not a part.
PART_STOPLIST = re.compile(
    r"motherboard|riser|hard drive|chassis only|media bay|backplane|"
    r"power switch|rail kit|heatsink|cable|tray\b|bezel|fan module",
    re.I,
)


def fetch_search(query):
    url = BASE + "/?q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_listings(html_text):
    """Extract {name, price, url} from PicClick search HTML."""
    out = []
    # <a href="..."><picture>...</picture>...<h3 title="T">T</h3></a><div class="price"><strong>$P</strong>
    for m in re.finditer(
        r'<a\s+href="([^"]+)"[^>]*>.*?<h3 title="([^"]+)">.*?</a>\s*'
        r'<div class="price"><strong>\$([\d,]+\.\d\d)',
        html_text, re.S,
    ):
        href, title, price = m.group(1), m.group(2), m.group(3)
        title = ihtml.unescape(title).strip()
        url = href if href.startswith("http") else BASE + href
        out.append({
            "name": title,
            "price": float(price.replace(",", "")),
            "url": url,
        })
    # de-dupe by URL, keep order
    seen, uniq = set(), []
    for c in out:
        if c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    return uniq


RAM_SIZES = {8, 16, 32, 64, 128, 256, 512, 1024}  # plausible RAM sticks/totals
DRIVE_WORD = re.compile(r"^\s*(SAS|HDD|SSD|SATA|10K|7\.2K|rpm)", re.I)


def extract_ram_gb(t):
    """RAM GB from a title. Drive sizes (300/600/900GB SAS etc.) excluded."""
    if re.search(r"\bno\s*ram\b", t, re.I):
        return 0
    # 1. explicit qualifier: "64GB RAM", "256GB DDR4", "64Gb memory"
    m = re.search(r"(\d+)\s*GB?\s*(?:RAM|DDR[345]|memory|RDIMM)\b", t, re.I)
    if m:
        return int(m.group(1))
    # 2. NxMGB kit patterns: "(2x 16GB)", "4x16GB" (stick sizes only)
    total = 0
    for m in re.finditer(r"(\d+)\s*x\s*(\d+)\s*GB\b", t, re.I):
        n, size = int(m.group(1)), int(m.group(2))
        if size in RAM_SIZES and not DRIVE_WORD.search(t[m.end():m.end() + 8]):
            total += n * size
    if total:
        return total
    # 3. bare NGB in a RAM-plausible size, not glued to a drive word
    best = 0
    for m in re.finditer(r"(\d+)\s*GB\b", t, re.I):
        size = int(m.group(1))
        if size in RAM_SIZES and not DRIVE_WORD.search(t[m.end():m.end() + 8]):
            best = max(best, size)
    return best or None


def extract_specs(title):
    """Best-effort spec extraction from a listing title. Unknowns stay None."""
    t = title
    spec = {"ram_gb": None, "ram_gen": None, "cores": None, "threads": None,
            "nvme": None, "generation": None, "psu_w": None}

    spec["ram_gb"] = extract_ram_gb(t)

    m = re.search(r"DDR(3|4|5)", t, re.I)
    if m:
        spec["ram_gen"] = "DDR" + m.group(1)

    # explicit total core counts win: "24-Core", "24C", "= 24C"
    m = re.search(r"[=\s](\d{1,2})\s*-?\s*cores?\b", t, re.I) or \
        re.search(r"=\s*(\d{1,2})C\b", t)
    if m:
        spec["cores"] = int(m.group(1))
    else:
        # "2x E5-2680 v3" / "E5-2690v4" / "2 x E5-2640 v4"
        total = 0
        for m in re.finditer(r"(\d)\s*x\s*E5[-\s]?(\d{4})\s*v\s?(3|4)", t, re.I):
            key = m.group(2) + "v" + m.group(3)
            if key in E5_CORES:
                total += int(m.group(1)) * E5_CORES[key]
        if not total:
            for m in re.finditer(r"(?<!\dx\s)E5[-\s]?(\d{4})\s*v\s?(3|4)", t, re.I):
                key = m.group(1) + "v" + m.group(2)
                if key in E5_CORES:
                    total += E5_CORES[key]
        if total:
            spec["cores"] = total
    if spec["cores"]:
        spec["threads"] = spec["cores"] * 2

    if re.search(r"NVMe", t, re.I):
        spec["nvme"] = True

    m = re.search(r"\bGen\s?(8|9|10)\b", t, re.I) or re.search(r"\bG(8|9|10)\b", t)
    if m:
        spec["generation"] = int(m.group(1))

    m = re.search(r"(\d{3,4})\s*W", t)
    if m:
        spec["psu_w"] = int(m.group(1))
    return spec


def is_server_listing(title):
    return not PART_STOPLIST.search(title)


def search(query, top=25):
    html_text = fetch_search(query)
    listings = parse_listings(html_text)
    LOG.info("query=%r -> %d raw listings", query, len(listings))
    cands = []
    for l in listings:
        if not is_server_listing(l["name"]):
            continue
        c = dict(l)
        c.update(extract_specs(l["name"]))
        cands.append(c)
        if len(cands) >= top:
            break
    return cands


def main(argv=None):
    ap = argparse.ArgumentParser(description="PicClick rack-server search + score.")
    ap.add_argument("--query", default="HP DL380 Gen9 server 64GB",
                    help="PicClick search query")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out", help="write candidate JSON here")
    ap.add_argument("--score", action="store_true",
                    help="rank candidates with rack_server_scorer and print")
    args = ap.parse_args(argv)

    cands = search(args.query, top=args.top)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(cands, f, indent=2)
        LOG.info("wrote %d candidates to %s", len(cands), args.out)
    if args.score:
        for c in scorer.rank(cands):
            LOG.info("%-50s $%8.2f score=%6.1f %-13s $/GB=%s",
                     c["name"][:50], c["price"], c["score"],
                     c["verdict"], c["dollar_per_gb_ram"])
    if not args.out and not args.score:
        print(json.dumps(cands, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
