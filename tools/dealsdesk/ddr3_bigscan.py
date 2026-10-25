"""One-off DDR3 big scan (recon for coding best sources into DealsDesk).
Runs a broad battery of PicClick/eBay queries + the full Jawa memory catalog,
classifies DDR3 listings into segments, and reports per-query yield/junk and
per-segment $/GB stats. Read-only: writes nothing to the DB."""
import json
import re
import statistics
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/home/dealsdesk/scripts")
import picclick_rack_search as p

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# Server DDR3 only. The original 2026-10-25 recon battery also measured the
# consumer segments (desktop kits, SO-DIMM, ECC unbuffered) to size them for
# exclusion; those queries were REMOVED the same day under Brian's rule:
# no consumer scraps in the database or coded into DealsDesk.
QUERIES = [
    "ddr3 ecc reg rdimm",
    "ddr3 rdimm 128gb kit",
    "ddr3 rdimm 256gb lot",
    "pc3-12800r 16gb",
    "ddr3 lrdimm 32gb",
    "ddr3 server memory lot",
]

REJECT = ["for parts", "not working", "untested", "defective", "as-is", "as is",
          "ssd", "nvme", "motherboard", "optane", "ddr4", "ddr5", "ddr2",
          "poweredge", "proliant", "optiplex", "server -", "complete server",
          "gaming pc", "laptop -"]


def cap_gb(name):
    n = name.upper()
    m = re.search(r"(\d+)\s*[X×]\s*(\d+)\s*GB", n)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = re.search(r"\b(\d{2,3})\s*GB\b", n)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(4|8|16|32)\s*GB\b", n)
    return int(m.group(1)) if m else None


def seg(name):
    n = name.upper()
    if "LRDIMM" in n or "LOAD REDUCED" in n:
        return "lrdimm"
    if "SO-DIMM" in n or "SODIMM" in n or "204-PIN" in n or "LAPTOP" in n:
        return "sodimm"
    if ("RDIMM" in n or "REGISTERED" in n or "REG " in n or "12800R" in n
            or "10600R" in n or "14900R" in n):
        return "rdimm"
    if "ECC" in n and ("UNBUFFERED" in n or "UDIMM" in n):
        return "ecc_udimm"
    return "consumer"


def main():
    seen = {}
    per_query = []
    for q in QUERIES:
        try:
            ls = p.parse_listings(p.fetch_search(q))
        except Exception as e:
            per_query.append((q, 0, 0, 0, str(e)[:40]))
            continue
        ok = junk = 0
        for l in ls:
            name = l["name"]
            low = name.lower()
            if not re.search(r"ddr3|pc3", low):
                junk += 1
                continue
            if any(w in low for w in REJECT):
                junk += 1
                continue
            gb = cap_gb(name)
            if not gb or not l["price"]:
                junk += 1
                continue
            ok += 1
            key = (name[:60], round(l["price"], 2))
            if key not in seen:
                seen[key] = {"seg": seg(name), "gb": gb, "price": l["price"],
                             "ppg": l["price"] / gb, "name": name, "src": "picclick_ebay"}
        per_query.append((q, len(ls), ok, junk, ""))

    # Jawa full memory catalog
    jawa_n = 0
    try:
        for page in range(1, 10):
            u = "https://www.jawa.gg/api/search?categoryIds=4&page=%d" % page
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
            ps = d.get("products") or []
            if not ps:
                break
            for prod in ps:
                name = prod.get("name") or ""
                if not re.search(r"ddr3|pc3", name.lower()):
                    continue
                gb = cap_gb(name)
                if not gb:
                    continue
                price = prod["price"] / 100.0
                key = (name[:60], round(price, 2))
                jawa_n += 1
                if key not in seen:
                    seen[key] = {"seg": seg(name), "gb": gb, "price": price,
                                 "ppg": price / gb, "name": name, "src": "jawa"}
    except Exception as e:
        print("jawa error:", e)

    print("=== PER-QUERY (picclick/ebay) ===")
    for q, total, ok, junk, err in per_query:
        print("%-28s raw %3d  kept %3d  junk %3d  %s" % (q, total, ok, junk, err))
    print("jawa ddr3 listings seen:", jawa_n)
    print()
    rows = list(seen.values())
    print("unique ddr3 listings:", len(rows))
    for s in ["rdimm", "lrdimm", "ecc_udimm", "consumer", "sodimm"]:
        rs = [r for r in rows if r["seg"] == s]
        if not rs:
            print("%-10s n=0" % s)
            continue
        big = [r for r in rs if r["gb"] >= 64]
        med = statistics.median(r["ppg"] for r in rs)
        med_big = statistics.median(r["ppg"] for r in big) if big else None
        print("%-10s n=%3d  median $%.2f/GB overall; >=64GB n=%d median %s; min $%.2f/GB"
              % (s, len(rs), med, len(big),
                 ("$%.2f/GB" % med_big) if med_big else "n/a",
                 min(r["ppg"] for r in rs)))
    print()
    print("=== BEST RDIMM/LRDIMM >=64GB BY $/GB ===")
    best = sorted([r for r in rows if r["seg"] in ("rdimm", "lrdimm") and r["gb"] >= 64],
                  key=lambda r: r["ppg"])[:12]
    for r in best:
        print("$%.2f/GB  $%7.2f  %3dGB  %-9s %s" % (r["ppg"], r["price"], r["gb"], r["src"], r["name"][:72]))
    print()
    print("=== BEST CONSUMER/SODIMM >=32GB ===")
    best = sorted([r for r in rows if r["seg"] in ("consumer", "sodimm") and r["gb"] >= 32],
                  key=lambda r: r["ppg"])[:6]
    for r in best:
        print("$%.2f/GB  $%7.2f  %3dGB  %-9s %s" % (r["ppg"], r["price"], r["gb"], r["src"], r["name"][:72]))


if __name__ == "__main__":
    main()
