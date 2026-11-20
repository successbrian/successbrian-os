#!/usr/bin/env python3
"""
Pricing Brief — the evidence pack that equips a judge to judge a price.

Brian's directive (2026-11-16): Gamma was being handed pricing items with no
pricing data at all — its verdicts could only say "a price lead, a person
decides." His words: "we need a system for that." This is that system.

The brief is built by CODE, on alpha, from the desk's own evidence stores, in
the listing_teardown evidence order (price_intel -> price_reference ->
market_pricing / sold sweeps). Every number in the brief is computed here —
a model reading the brief never invents or computes a figure. When no
evidence exists on record, the brief says NO PRICE EVIDENCE in plain words:
the price is then unjudgeable from our data and routes to a person
(Brian's teardown law: no evidence = unvalued, never invented).

Usage:
  pricing_brief.py --need 44 --ask 115.94     (terms + target from the need)
  pricing_brief.py --item "Tesla M40 24GB" --ask 115.94 [--target 191]
  pricing_brief.py selftest
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

ENV_PATH = os.path.expanduser("~/successbrian-os/.env")
STALE_DAYS = 45


def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()


def _conn():
    import psycopg2
    import psycopg2.extras
    pw = os.environ.get("PGPASSWORD")
    if not pw:
        raise RuntimeError("PGPASSWORD not set (expected in ~/successbrian-os/.env)")
    return psycopg2.connect(host="localhost", dbname="ecosystem_central",
                            user="altair", password=pw,
                            cursor_factory=psycopg2.extras.RealDictCursor)


def _rows(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------- matching
def _tokens(text):
    return [t for t in re.split(r"[^A-Za-z0-9]+", text or "") if t]


def _whole_word_all(name, tokens):
    """True when every token appears in name as a whole word (case-insensitive).
    Guards against substring collisions (e.g. 'M40' inside 'CM4096...')."""
    words = set(t.lower() for t in _tokens(name))
    return all(t.lower() in words for t in tokens)


def _capacity_of(text):
    m = re.search(r"(\d+)\s*(TB|GB)\b", text or "", re.I)
    return (m.group(1) + m.group(2).upper()) if m else None


def _match_keys(terms):
    """Candidate ILIKE keys from the search terms, longest first, shortened
    progressively (never below 2 tokens)."""
    keys, seen = [], set()
    for term in terms:
        toks = _tokens(term)
        for n in range(len(toks), 1, -1):
            key = " ".join(toks[:n])
            if key.lower() not in seen:
                seen.add(key.lower())
                keys.append(key)
    return keys


def _pct(ask, ref):
    if not ref:
        return None
    return (ask - ref) / ref * 100.0


def _vs(ask, ref):
    p = _pct(ask, ref)
    if p is None:
        return None
    word = "UNDER" if p < -0.5 else ("OVER" if p > 0.5 else "AT")
    return f"{abs(p):.0f}% {word}"


def _age_days(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).days


# ---------------------------------------------------------------- evidence
def gather(cur, terms, subject):
    """Pull every pricing-evidence store for this item. Returns a dict of
    what was found (empty pieces stay empty — absence is reported, never
    filled in)."""
    ev = {"reference": None, "solds": [], "intel": [], "market": None,
          "matched_key": None}
    cap = _capacity_of(subject) or next(
        (c for c in (_capacity_of(t) for t in terms) if c), None)
    for key in _match_keys(terms):
        ktoks = _tokens(key)
        refs = _rows(cur, """
            SELECT component_name, avg_price, min_price, max_price,
                   sample_count, source, fetched_at
            FROM dealsdesk.price_reference
            WHERE component_name ILIKE %s
            ORDER BY sample_count DESC LIMIT 5
        """, (f"%{key}%",))
        refs = [r for r in refs if _whole_word_all(r["component_name"], ktoks)
                and (not cap or cap in _tokens(r["component_name"])
                     or cap in (r["component_name"] or "").upper())]
        if refs and ev["reference"] is None:
            ev["reference"] = refs[0]
            ev["matched_key"] = key
        solds = _rows(cur, """
            SELECT item_name, price, checked_at FROM public.price_history
            WHERE item_name ILIKE %s AND source LIKE 'ebay_sold_sweep%%'
            ORDER BY checked_at DESC LIMIT 25
        """, (f"%{key}%",))
        solds = [s for s in solds if _whole_word_all(s["item_name"], ktoks)
                 and (not cap or cap in (s["item_name"] or "").upper())]
        if solds and not ev["solds"]:
            ev["solds"] = solds[:5]
            ev["matched_key"] = ev["matched_key"] or key
        intel = _rows(cur, """
            SELECT item, amount, source_label, checked_on
            FROM successbrian_os.price_intel
            WHERE item ILIKE %s AND amount IS NOT NULL
            ORDER BY checked_on DESC LIMIT 3
        """, (f"%{key}%",))
        intel = [i for i in intel if _whole_word_all(i["item"], ktoks)]
        if intel and not ev["intel"]:
            ev["intel"] = intel
        mkts = _rows(cur, """
            SELECT component_model, median_sold_price, sold_count_30d,
                   sell_through_rate, last_updated
            FROM public.market_pricing
            WHERE component_model ILIKE %s LIMIT 3
        """, (f"%{key}%",))
        mkts = [m for m in mkts if _whole_word_all(m["component_model"], ktoks)]
        if mkts and ev["market"] is None:
            ev["market"] = mkts[0]
        if ev["reference"] and ev["solds"]:
            break
    return ev


# ---------------------------------------------------------------- the brief
def build_brief(terms, ask, target=None, subject=None, need_id=None):
    """Return the brief as plain text. All arithmetic happens here."""
    subject = subject or (terms[0] if terms else "unknown item")
    head = f"PRICING BRIEF — {subject}"
    if need_id:
        head += f" (need #{need_id})"
    lines = [head]
    ask = float(ask)
    if target:
        target = float(target)
        lines.append(f"Ask: ${ask:,.2f}. Brian's target: ${target:,.2f} "
                     f"(ask is {_vs(ask, target)} target).")
    else:
        lines.append(f"Ask: ${ask:,.2f}. No target price on record for this item.")
    with _conn() as conn, conn.cursor() as cur:
        ev = gather(cur, terms, subject)
    ref, solds, intel, mkt = ev["reference"], ev["solds"], ev["intel"], ev["market"]
    median = None
    if ref:
        median = float(ref["avg_price"])
        age = _age_days(ref["fetched_at"])
        stale = " — STALE" if (age is not None and age > STALE_DAYS) else ""
        lines.append(
            f"Sold evidence (DealsDesk price_reference): typical ${median:,.2f} "
            f"(range ${float(ref['min_price']):,.2f}–${float(ref['max_price']):,.2f}, "
            f"n={ref['sample_count']}, fetched {str(ref['fetched_at'])[:10]}"
            f"{', ' + str(age) + ' days old' if age is not None else ''}{stale}). "
            f"Ask is {_vs(ask, median)} that figure.")
    if solds:
        pts = "; ".join(f"${float(s['price']):,.2f} on {str(s['checked_at'])[:10]}"
                        for s in solds)
        lines.append(f"Recent actual solds (eBay sold sweep): {pts}.")
        if median is None:
            vals = sorted(float(s["price"]) for s in solds)
            median = vals[len(vals) // 2]
            lines.append(f"Ask is {_vs(ask, median)} the median of those solds "
                         f"(${median:,.2f}).")
    if mkt and mkt["median_sold_price"]:
        lines.append(
            f"Market table: median sold ${float(mkt['median_sold_price']):,.2f}, "
            f"{mkt['sold_count_30d']} sold in 30d, updated "
            f"{str(mkt['last_updated'])[:10]}.")
        if median is None:
            median = float(mkt["median_sold_price"])
    if intel:
        pts = "; ".join(f"${float(i['amount']):,.2f} ({i['source_label']}, "
                        f"{i['checked_on']})" for i in intel)
        lines.append(f"Price intel on record: {pts}.")
    if not (ref or solds or intel or (mkt and mkt["median_sold_price"])):
        lines.append("Sold evidence: NO PRICE EVIDENCE ON RECORD — no reference "
                     "rows, no sold history, no price intel for this item.")
        lines.append("Evidence state: NONE — this price cannot be judged from "
                     "our data. Route it to a person; do not estimate a market "
                     "value.")
        return "\n".join(lines)
    # evidence state
    fresh_solds = [s for s in solds
                   if (_age_days(s["checked_at"]) or 999) <= 60]
    if len(fresh_solds) >= 3 or (ref and ref["sample_count"] >= 30
                                 and (_age_days(ref["fetched_at"]) or 999) <= STALE_DAYS):
        state = "STRONG — recent, well-sampled sold evidence."
    elif ref and (_age_days(ref["fetched_at"]) or 0) > STALE_DAYS and not fresh_solds:
        state = ("STALE — real evidence exists but it is old; treat the gap "
                 "as approximate, not exact.")
    else:
        state = "THIN — some evidence, small sample or single source."
    lines.append(f"Evidence state: {state}")
    return "\n".join(lines)


def need_terms(need):
    ht = need.get("hard_terms") or {}
    if isinstance(ht, str):
        try:
            ht = json.loads(ht)
        except Exception:
            ht = {}
    return ht.get("search_terms") or [
        re.sub(r"\s*\([^)]*\)", "", need["subject"]).strip()]


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a pricing brief.")
    ap.add_argument("--need", type=int)
    ap.add_argument("--item")
    ap.add_argument("--ask", type=float, required=False)
    ap.add_argument("--target", type=float)
    args = ap.parse_args(argv)
    if args.need:
        with _conn() as conn, conn.cursor() as cur:
            got = _rows(cur, "SELECT * FROM dealsdesk.ecosystem_needs WHERE id=%s",
                        (args.need,))
        if not got:
            print(f"need #{args.need} not found")
            return 1
        need = got[0]
        if args.ask is None:
            print("--ask is required with --need")
            return 1
        print(build_brief(need_terms(need), args.ask,
                          target=need["target_buy_price"],
                          subject=need["subject"], need_id=need["id"]))
        return 0
    if args.item and args.ask is not None:
        print(build_brief([args.item], args.ask, target=args.target,
                          subject=args.item))
        return 0
    ap.print_help()
    return 1


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    check("pct math", abs(_pct(100.0, 200.0) + 50.0) < 1e-9)
    check("vs words", _vs(115.94, 191.0).endswith("UNDER")
          and _vs(639.0, 1049.0).endswith("UNDER"))
    check("whole-word guard", _whole_word_all("NVIDIA TESLA M40 24GB", ["M40"])
          and not _whole_word_all("CMS CM4096643200SO KIT", ["M40"]))
    check("capacity read", _capacity_of("Tesla M40 24GB PG600") == "24GB")
    b1 = build_brief(["Tesla M40 24GB"], 115.94, target=191.0,
                     subject="Tesla M40 24GB PG600 GPU", need_id=44)
    check("M40 brief has sold evidence", "Sold evidence" in b1
          and "NO PRICE EVIDENCE" not in b1)
    check("M40 brief computes vs target", "UNDER target" in b1)
    b2 = build_brief(["Intel Arc Pro B70 32GB GPU"], 639.0, target=1049.0,
                     subject="Intel Arc Pro B70 32GB GPU", need_id=43)
    # B70 gained real price intel 2026-11-19 (price_intel id 100, $2200
    # in-stock via the_fourth, capture 2644) — an evidence case now, not
    # no-evidence. The no-evidence behaviour is tested on MI300X below.
    check("B70 brief reports the intel evidence", "Price intel on record" in b2
          and "NO PRICE EVIDENCE" not in b2)
    # Honest no-evidence case: AMD Instinct MI300X 192GB has zero rows in
    # all four evidence stores (verified 2026-11-20, cycle 659).
    b3 = build_brief(["AMD Instinct MI300X 192GB"], 15000.0, target=20000.0,
                     subject="AMD Instinct MI300X 192GB")
    check("MI300X brief is honest no-evidence", "NO PRICE EVIDENCE" in b3)
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    sys.exit(main())
