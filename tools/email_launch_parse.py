#!/usr/bin/env python3
"""
Scan recent email from known launch/affiliate senders; record launch candidates.

WHY:
    Brian's inbox already receives direct vendor launch announcements,
    launch-webinar invites, and review-site promos. The vendor names and
    dates in that mail are intel the affiliate pipeline can cross-check
    against MunchEye — but it was all filed under "launch-hype, ignore".
    This script extracts launch candidates deterministically (vendor,
    product, launch date, commission, price) and records them into
    affiliate_intel.launches on k11-alpha, where the MunchEye monolith's
    vetting can pick them up. If this is removed, email launch intel goes
    back to being ignored.

CALLED BY:
    Humans; future cron (twice-weekly alongside marketer-watch-poll, TBD).
    Reads tools/email_launch_senders.yaml.

NOTES:
    - DETERMINISTIC EXTRACTION ONLY. Regexes over subject + body lead.
      Anything not found stays NULL. The raw subject is always preserved on
      the candidate so a human (or later agent pass) can recover what the
      regexes missed. Never invent a vendor, product, price, or date.
    - Vendor derivation: the From display name when it's a real brand/name;
      for infra senders (gotowebinar.com, zoom.us, ...) the vendor is
      extracted from the subject ("X's webinar", "X: ...") and falls back
      to the display name — never guessed from thin air.
    - DB writes go to affiliate_intel.launches on k11-alpha via kssh + psql
      (base64 pattern per AGENTS.md — no nested-quote quoting bugs). Inserts
      use ON CONFLICT (vendor_id, product_name) DO NOTHING: rows the MunchEye
      monolith already vetted (tier/vet_score set) are never overwritten by
      email candidates.
    - The launches table has no source column as of 2026-10-04; email rows
      are identifiable by tier IS NULL AND muncheye_url IS NULL. Adding a
      source column is a schema decision for the monolith's (private) repo.
    - If the DB write fails, candidates print as a KB_FALLBACK JSON block
      (from=email-launch-parse, to=all) for the driver to push through
      altair.knowledge_bridge. Exit stays 0 — the payload IS the delivery.
    - Archive scan reads ~49k JSON files (~60s). Live Gmail via --gmail uses
      hatch_gws_cli (must be connected; run `hatch_gws_cli gmail status`
      first). Live Outlook via --live-outlook uses the outlook-mail skill;
      its query syntax is best-effort — verify output before trusting it.
    - This repo is PUBLIC: sender domains are public vendor facts, but keep
      Brian's personal inbox details out of code and logs.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SENDERS_YAML = os.path.join(HERE, "email_launch_senders.yaml")
ARCHIVE = os.path.join(os.path.expanduser("~"), "workspace",
                       "outlook-mail-download", "archive-brian.lathe", "cur")
KSSH = os.path.join(os.path.expanduser("~"), "workspace", "bin", "kssh")
UA_GWS = "/opt/hatch/bin/hatch_gws_cli"

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


# ---------------------------------------------------------------- config

def load_senders(path=SENDERS_YAML):
    """Minimal YAML parse (same hand-rolled style as marketer_watch.py)."""
    senders, cur = [], None
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- domain:"):
            cur = {"domain": s.split(":", 1)[1].strip()}
            senders.append(cur)
        elif cur is not None and ":" in s and not s.startswith("-"):
            k, v = s.split(":", 1)
            cur[k.strip()] = v.strip()
    return senders


def sender_domain(from_header):
    if isinstance(from_header, dict):
        from_header = from_header.get("email", "")
    m = re.search(r"@([\w.\-]+\.\w+)", from_header or "")
    return m.group(1).lower() if m else ""


def norm_from(frm):
    """Normalize a From header that may be a 'Name <addr>' string or a
    {'name':..., 'email':...} dict (gmail +read shape)."""
    if isinstance(frm, dict):
        name, email = frm.get("name", ""), frm.get("email", "")
        return f"{name} <{email}>" if name else email
    return frm or ""


# ---------------------------------------------------------------- extraction

def parse_email_date(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def derive_vendor(from_header, subject, domain, kind):
    """Vendor name from From display name, or subject for infra senders."""
    m = re.match(r"\s*(.*?)\s*<[^>]+>", from_header or "")
    disp = (m.group(1).strip().strip("\"'") if m else "").strip()
    junk = {"", "noreply", "no-reply", "notifications", "mailer",
            "info", "support", "hello"}
    if kind == "infra" or disp.lower() in junk or not disp:
        m2 = re.match(r"\s*([A-Z][\w .&'\-]{2,50})['\u2019]s\b", subject or "")
        if m2:
            return m2.group(1).strip()
        m3 = re.match(r"\s*([A-Z][\w .&'\-]{2,50})\s*[:|\-\u2013]", subject or "")
        if m3 and len(m3.group(1).split()) <= 6:
            return m3.group(1).strip()
        if disp and disp.lower() not in junk:
            return disp
        return domain.split(".")[0].replace("-", " ").title()
    return disp


PRODUCT_RES = [
    re.compile(r"^\s*(.+?)\s+(?:Review|Reviews|Bonus|Bonuses|Demo|Launch|"
               r"Launches|Webinar|Webclass|Masterclass)\b", re.I),
    re.compile(r"\b[lL]aunching\s+([A-Z][\w][\w\s&'\-.]{1,50})"),
    re.compile(r"\bIntroducing\s+([A-Z][\w][\w\s&'\-.]{1,50})"),
    re.compile(r"\b([A-Z][\w][\w\s&'\-.]{1,40}?)\s+2\.0\b"),
]

_GENERIC = re.compile(
    r"(?i)^(new|this|your|free|live|today|now|special|exclusive|limited|hot|"
    r"big|last|final|join|watch|register|reminder|invitation|you're invited)$")

# Vendor product names in this niche are CamelCase (ProductsPilot, CueVue)
# or ALLCAPS (DIRECTOR AI). These catch real subjects like
# "FREE tools + ProductsPilot" or "At 10am.. DIRECTOR AI !".
_CAMEL_RE = re.compile(r"\b([A-Z][a-z0-9]*[A-Z][\w]*)\b")
_CAPS_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,}(?:\s+[A-Z][A-Z0-9]{2,})?)\b")
_TOKEN_STOP = {
    "FREE", "TODAY", "GONE", "HINT", "HUGE", "NEW", "LAST", "DAYS", "JOIN",
    "LIVE", "WEBINAR", "REMINDER", "REPLAY", "BONUS", "LAUNCH", "TONIGHT",
    "HOURS", "LIMITED", "EXCLUSIVE", "SPECIAL", "UPGRADE", "INSIDE",
    "TRAINING", "GIVEAWAY", "SALE", "DEAL", "OFFER", "ALERT", "UPDATE",
    "UPDATES", "INTRODUCING", "LAUNCHING",
}
_AMBASSADOR_RE = re.compile(
    r"[Bb]ecome an?\s+([A-Z][\w .&'\-]{2,40}?)\s+(?:Ambassador|Affiliate)\b")


def clean_product(p):
    if not p:
        return None
    p = re.sub(r"\s+", " ", p).strip(" -\u2013\u2014|:\"'")
    p = re.sub(r"\s+(Review|Reviews|Bonus|Bonuses|Demo|Launch|Launches)$",
               "", p, flags=re.I).strip()
    if len(p) < 3 or len(p) > 80 or _GENERIC.fullmatch(p):
        return None
    return p


def extract_product(subject, body):
    for rx in PRODUCT_RES:
        m = rx.search(subject or "")
        if m:
            p = clean_product(m.group(1))
            if p:
                return p
    # body fallback: first 500 chars only, same patterns
    for rx in PRODUCT_RES:
        m = rx.search((body or "")[:500])
        if m:
            p = clean_product(m.group(1))
            if p:
                return p
    # ambassador/affiliate-program announcements name the program
    m = _AMBASSADOR_RE.search(subject or "")
    if m:
        p = clean_product(m.group(1))
        if p:
            return p
    # product-style tokens: CamelCase (ProductsPilot) or ALLCAPS (DIRECTOR AI)
    for rx in (_CAMEL_RE, _CAPS_RE):
        for m in rx.finditer(subject or ""):
            tok = m.group(1).strip()
            if tok.upper() in _TOKEN_STOP or len(tok) < 3:
                continue
            p = clean_product(tok)
            if p:
                return p
    return None


MD_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)


def extract_launch_date(text, email_dt):
    m = MD_RE.search(text or "")
    if m:
        month = MONTHS[m.group(1)[:3].lower()]
        day = int(m.group(2))
        year = email_dt.year
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            return None
        if d < email_dt.date() - timedelta(days=2):
            try:
                d = datetime(year + 1, month, day).date()
            except ValueError:
                return None
        return d.isoformat()
    m = re.search(r"\blaunch(?:es|ing)?\s+(today|tomorrow)\b", text or "", re.I)
    if m:
        delta = 0 if m.group(1).lower() == "today" else 1
        return (email_dt + timedelta(days=delta)).date().isoformat()
    return None


def extract_commission(text):
    m = re.search(r"(\d{1,3})\s*%\s*commission", text or "", re.I)
    if m and int(m.group(1)) <= 100:
        return int(m.group(1))
    return None


def extract_price(subject):
    m = re.search(r"\$\s?(\d{1,4}(?:\.\d{2})?)", subject or "")
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def extract_candidate(frm, subject, body, email_dt, domain, kind):
    product = extract_product(subject, body)
    if not product:
        return None
    text = f"{subject}\n{(body or '')[:2000]}"
    return {
        "vendor": derive_vendor(frm, subject, domain, kind),
        "product": product,
        "launch_date": extract_launch_date(text, email_dt),
        "commission_pct": extract_commission(text),
        "price": extract_price(subject),
        "subject": (subject or "")[:200],
        "email_date": email_dt.date().isoformat(),
    }


# ---------------------------------------------------------------- sources

def scan_archive(senders, since):
    """Scan the local Outlook archive. Returns candidate dicts."""
    by_domain = {s["domain"]: s for s in senders}
    cands, scanned, hits = [], 0, 0
    for fn in os.listdir(ARCHIVE):
        if not fn.endswith(".json"):
            continue
        scanned += 1
        try:
            d = json.load(open(os.path.join(ARCHIVE, fn)))
        except Exception:
            continue
        frm, subj = d.get("from") or "", d.get("subject") or ""
        dom = sender_domain(frm)
        if dom not in by_domain:
            continue
        dt = parse_email_date(d.get("date") or d.get("message_received_at"))
        if not dt or dt < since:
            continue
        hits += 1
        c = extract_candidate(frm, subj, d.get("body") or "", dt, dom,
                              by_domain[dom].get("kind", "vendor"))
        if c:
            cands.append(c)
    print(f"archive: scanned {scanned} files, {hits} sender+date hits, "
          f"{len(cands)} candidates", file=sys.stderr)
    return cands


def _gws(args, timeout=120):
    r = subprocess.run([UA_GWS] + args, capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"hatch_gws_cli failed: {r.stderr.strip()[:200]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("hatch_gws_cli returned non-JSON output")


def scan_gmail(senders, since, max_msgs=50):
    """Live Gmail via the gmail skill. Returns candidate dicts."""
    ors = " OR ".join(f"from:{s['domain']}" for s in senders)
    query = f"({ors}) after:{since.strftime('%Y/%m/%d')}"
    data = _gws(["gmail", "+triage", "--query", query,
                 "--max", str(max_msgs), "--format", "json"])
    msgs = data if isinstance(data, list) else data.get("messages", [])
    by_domain = {s["domain"]: s for s in senders}
    cands = []
    for m in msgs:
        mid = m.get("id") or m.get("message_id")
        if not mid:
            continue
        full = _gws(["gmail", "+read", "--id", mid, "--headers",
                     "--format", "json"])
        # +read returns top-level from/subject/date/body_text; fall back
        # to a headers list if the shape ever changes.
        hdrs = {h.get("name", "").lower(): h.get("value", "")
                for h in full.get("headers", [])}
        frm = norm_from(full.get("from") or hdrs.get("from", ""))
        subj = full.get("subject") or hdrs.get("subject", "")
        date_s = full.get("date") or hdrs.get("date", "")
        dom = sender_domain(frm)
        if dom not in by_domain:
            continue
        dt = parse_email_date(date_s)
        if not dt or dt < since:
            continue
        body = (full.get("body_text") or full.get("body")
                or full.get("snippet") or "")
        c = extract_candidate(frm, subj, body, dt, dom,
                              by_domain[dom].get("kind", "vendor"))
        if c:
            cands.append(c)
    print(f"gmail: {len(msgs)} messages triaged, {len(cands)} candidates",
          file=sys.stderr)
    return cands


def scan_live_outlook(senders, since, page_size=20):
    """Live Outlook via the outlook-mail skill (best-effort query syntax)."""
    import shutil
    if not shutil.which("outlook-mail"):
        raise RuntimeError("outlook-mail CLI not on PATH")
    by_domain = {s["domain"]: s for s in senders}
    cands = []
    for s in senders:
        r = subprocess.run(
            ["outlook-mail", "search", f"from:{s['domain']}",
             "--page-size", str(page_size)],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"outlook-mail search failed for {s['domain']}: "
                  f"{r.stderr.strip()[:150]}", file=sys.stderr)
            continue
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            print(f"outlook-mail non-JSON for {s['domain']}, skipped",
                  file=sys.stderr)
            continue
        msgs = data.get("messages", []) if isinstance(data, dict) else []
        for m in msgs:
            frm, subj = m.get("from", ""), m.get("subject", "")
            dom = sender_domain(frm)
            if dom not in by_domain:
                continue
            dt = parse_email_date(m.get("date") or
                                  m.get("message_received_at"))
            if not dt or dt < since:
                continue
            c = extract_candidate(frm, subj, m.get("preview", "") or "",
                                  dt, dom, by_domain[dom].get("kind",
                                                              "vendor"))
            if c:
                cands.append(c)
    print(f"live-outlook: {len(cands)} candidates", file=sys.stderr)
    return cands


# ---------------------------------------------------------------- db write

def _sql_lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


TOOL_KW = ("tool", "software", "builder", "generator", "automation", "ai ",
           "app", "platform")


def candidate_sql(c):
    v, p = _sql_lit(c["vendor"]), _sql_lit(c["product"])
    tool_type = "software" if any(k in c["product"].lower()
                                  for k in TOOL_KW) else "other"
    recurring = "TRUE" if "recurring" in c["product"].lower() else "FALSE"
    return (
        "WITH v AS ("
        "INSERT INTO affiliate_intel.vendors (name) VALUES (%s) "
        "ON CONFLICT (name) DO UPDATE SET last_seen = NOW() RETURNING id) "
        "INSERT INTO affiliate_intel.launches "
        "(vendor_id, product_name, price, commission_pct, launch_date, "
        "launch_status, evergreen, recurring_commission, tool_type) "
        "SELECT id, %s, %s, %s, %s, 'upcoming', FALSE, %s, '%s' FROM v "
        "ON CONFLICT (vendor_id, product_name) DO NOTHING;"
        % (v, p, _sql_lit(c["price"]), _sql_lit(c["commission_pct"]),
           _sql_lit(c["launch_date"]), recurring, tool_type))


def kssh_psql(sql):
    """Run SQL on k11-alpha's ecosystem_central via kssh (base64 pattern)."""
    b64 = base64.b64encode(sql.encode()).decode()
    cmd = (f"psql -h /var/run/postgresql -U successbrian "
           f"-d ecosystem_central -v ON_ERROR_STOP=1 -t -A "
           f"-c \"$(echo {b64} | base64 -d)\"")
    r = subprocess.run([KSSH, cmd], capture_output=True, text=True,
                       timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"kssh psql failed: {r.stderr.strip()[:300]}")
    return r.stdout


def db_existing_keys():
    rows = kssh_psql(
        "SELECT lower(v.name), lower(l.product_name) "
        "FROM affiliate_intel.vendors v "
        "JOIN affiliate_intel.launches l ON l.vendor_id = v.id;")
    keys = set()
    for line in rows.splitlines():
        if "|" in line:
            a, b = line.split("|", 1)
            keys.add((a.strip(), b.strip()))
    return keys


def db_record(cands):
    """Insert candidates; returns (inserted, skipped_existing)."""
    if not cands:
        return 0, 0
    try:
        existing = db_existing_keys()
    except Exception as e:
        raise RuntimeError(f"dedupe read failed: {e}")
    fresh, seen = [], set()
    for c in cands:
        key = (c["vendor"].lower(), c["product"].lower())
        if key in existing or key in seen:
            continue
        seen.add(key)
        fresh.append(c)
    skipped = len(cands) - len(fresh)
    if not fresh:
        return 0, skipped
    sql = "\n".join(candidate_sql(c) for c in fresh)
    kssh_psql(sql)
    return len(fresh), skipped


def kb_fallback(cands):
    payload = {"from": "email-launch-parse", "to": "all",
               "type": "email_launch_candidates", "candidates": cands}
    print("KB_FALLBACK " + json.dumps(payload))


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(
        description="Scan recent email from launch/affiliate senders; "
                    "record launch candidates into affiliate_intel.launches.")
    ap.add_argument("--check", action="store_true",
                    help="scan and record (DB write, or KB fallback)")
    ap.add_argument("--dry-run", action="store_true",
                    help="scan and show candidates, no writes")
    ap.add_argument("--days", type=int, default=4,
                    help="lookback window in days (default 4)")
    ap.add_argument("--gmail", action="store_true",
                    help="use live Gmail (hatch_gws_cli) instead of the "
                         "local Outlook archive")
    ap.add_argument("--live-outlook", action="store_true",
                    help="use live Outlook (outlook-mail skill) instead of "
                         "the local archive")
    ap.add_argument("--max", type=int, default=200,
                    help="cap candidates processed (default 200)")
    args = ap.parse_args()

    if not args.check and not args.dry_run:
        ap.print_help()
        return 2

    senders = load_senders()
    since = (datetime.now(timezone.utc) - timedelta(days=args.days))
    if args.gmail:
        cands = scan_gmail(senders, since, max_msgs=args.max)
    elif args.live_outlook:
        cands = scan_live_outlook(senders, since)
    else:
        cands = scan_archive(senders, since)
    cands = cands[:args.max]

    if args.dry_run:
        print(f"{len(cands)} candidate(s) (dry run, nothing recorded)")
        for c in cands:
            bits = [f"{c['vendor']} :: {c['product']}"]
            if c["launch_date"]:
                bits.append(f"launch {c['launch_date']}")
            if c["commission_pct"]:
                bits.append(f"{c['commission_pct']}%")
            if c["price"]:
                bits.append(f"${c['price']:g}")
            print("  - " + ", ".join(bits))
            print(f"    subject: {c['subject'][:100]}")
        return 0

    try:
        inserted, skipped = db_record(cands)
    except Exception as e:
        print(f"DB write failed ({e}); falling back to knowledge_bridge "
              f"payload", file=sys.stderr)
        kb_fallback(cands)
        print(f"done: 0 recorded, {len(cands)} via KB fallback")
        return 0
    print(f"done: {inserted} recorded, {skipped} already known")
    return 0


if __name__ == "__main__":
    sys.exit(main())
