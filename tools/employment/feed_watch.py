#!/usr/bin/env python3
"""SuccessBrian OS employment stream: free job-board feed watch ->
public.job_tracking.

PURPOSE: Poll the free, machine-readable job boards (RemoteOK public
    JSON API, We Work Remotely RSS, Himalayas public API) and file
    postings whose titles match Brian's target-title playbook into
    public.job_tracking, so the employment stream keeps flowing between
    mailbox scans and never silently dies again.
WHY: Brian 2026-11-21 - "Wire up the free job-feed watch in
    SuccessBrian OS." The mailbox stream (scan_mailbox.py) went silent
    2026-10-17 when its daily cron vanished and nothing noticed for five
    weeks; job_tracking froze at 977 rows. This watcher is registered
    in successbrian_os.program_registry at birth
    (program_key='employment-feed-watch-py', log-mtime probe on
    ~/logs/feed-watch.log) and watched by QA check
    sbos-program-registry/feed-watch-proof-fresh, so a silent death
    now raises an exception instead of passing unnoticed.
CALLED BY: alpha crontab, every 6 hours, under flock:
        25 0,6,12,18 * * * flock -n /home/successbrian/logs/feed-watch.lock \
            python3 /home/successbrian/successbrian-os/tools/employment/feed_watch.py \
            >> /home/successbrian/logs/feed-watch.log 2>&1
    CLI: python3 feed_watch.py [--dry-run] [--pages N] [--since-hours H]
NOTES:
    - Matching is deterministic title-phrase in/out. The playbook is
      the 2026-11-21 FlexJobs reverse-engineering report SS7b (filed
      as a brief in the AnythingLLM Career workspace): core titles
      below, one phrase per title family. NO scoring layer - Brian
      ruled scoring out; fit grading stays with grade_skills.py /
      extract_entities.py downstream, so rows land with verdict and
      track NULL for that pipeline to grade.
    - Brian's ruled exclusions are HARD rejects, checked before any
      include: bare "Automation Consultant" (the factory/PLC title -
      the AI-prefixed "AI Automation Consultant" is a different title
      family, one of the report's five most common names for this
      work, and stays includable), any "Solutions Consultant"
      (presales), and title negatives: PLC, SCADA, robotics,
      manufacturing, controls, Selenium, QA/test titles, presales,
      sales engineer, research scientist, PhD, intern, annotation/
      labeling.
    - Sales/support roles count only at AI companies (Brian's fit
      lanes: AI sales / AI customer success): the title must carry a
      sales/support phrase AND an AI signal (AI in the title, or an
      AI tag/category on the posting, or AI language at the head of
      the description). Deterministic phrase logic, no model.
    - FlexJobs is deliberately NOT a source: its Terms of Use ban
      automated access (2026-11-21 research verdict: legitimate
      board, but skip the bots).
    - ai-jobs.net was dropped at build time (2026-11-21): the domain
      now 301-redirects to foorilla.com, an unrelated site - the job
      feed described in the research no longer exists.
    - Himalayas' API ignores its q/seniority query parameters
      (verified live 2026-11-21: filtered and unfiltered calls return
      the same firehose), so the watcher pages the newest-first feed
      with a cursor under a bounded page budget and title-filters
      locally. Page size is capped at 20 server-side; at the observed
      ingest rate (~150 jobs/hour) 60 pages covers ~8 hours.
    - Dedupe: message_id_hash = sha256('feed_watch|<board>|<canonical
      url>') reuses job_tracking's existing unique index, so re-runs
      are idempotent (INSERT .. ON CONFLICT DO NOTHING). Title+company
      hash is the fallback when a feed item carries no URL. The same
      posting syndicated to two boards lands once per board - the
      downstream pipeline dedupes across sources, as it already does
      for mailbox leads.
    - A dead or changed source logs an ERROR line and the run
      continues with the remaining sources; the run exits non-zero
      only if the database write itself fails.
    - RemoteOK data comes from its public API; attribution is kept in
      every row's notes, per the notice in element 0 of that API.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.expanduser("~/successbrian-os/.env")
UA = ("SuccessBrianOS-feed-watch/1.0 (personal job watcher; "
      "SuccessBrian OS employment stream)")
HTTP_TIMEOUT = 30

# ------------------------------------------------------------------ env / db
# Same pattern as tools/dealsdesk/component_scout.py: credentials from
# ~/successbrian-os/.env via the process environment, never from source.


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

DB_HOST = "localhost"
DB_NAME = "ecosystem_central"
DB_USER = "altair"

try:
    import psycopg2
except ImportError:
    print("[FEEDWATCH] psycopg2 not available - cannot run", flush=True)
    sys.exit(1)


def log(msg):
    print("[%s] %s" % (datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), msg), flush=True)


# ------------------------------------------------------------------ matching
# Title playbook (report SS7b). Matching runs on the normalized title:
# lowercased, punctuation folded to spaces, whitespace collapsed.

CORE_PHRASES = [
    "ai automation engineer",
    "ai automation specialist",
    "ai automation consultant",   # AI-prefixed only; the bare title is a reject
    "ai workflow automation",     # engineer / specialist / lead variants
    "workflow automation engineer",
    "workflow automation specialist",
    "forward deployed",           # Forward Deployed Engineer family
    "applied ai engineer",
    "ai solutions engineer",
    "ai solutions architect",
    "ai implementation",          # specialist / consultant / manager / engineer
    "ai integration",             # specialist / engineer / architect
    "internal tools",
    "internal tooling",
    "ai infrastructure engineer",
    "ai deployment",              # engineer / specialist
]

N8N_RE = re.compile(r"\bn8n\b")

SALES_SUPPORT_PHRASES = [
    "account executive",
    "customer success",
    "customer support",
    "sales representative",
    "sales development",
    "sales manager",
]

# Hard rejects (Brian's ruled exclusions), checked before includes.
REJECT_PHRASES = [
    "solutions consultant",       # presales family, incl. "(AI)" variants
    "sales engineer",             # presales
    "presales",
    "pre sales",
    "research scientist",
    "annotation",
    "labeling",
    "labelling",
]
REJECT_WORDS = [
    "plc", "scada", "robotics", "manufacturing", "controls",
    "selenium", "qa", "test", "phd", "intern", "internship",
]
REJECT_WORD_RE = re.compile(r"\b(%s)\b" % "|".join(REJECT_WORDS))
# Bare "Automation Consultant" = factory/PLC work. The negative
# lookbehind keeps the AI-prefixed title family includable.
BARE_AUTOMATION_CONSULTANT_RE = re.compile(r"(?<!ai )automation consultant")
PHD_DOT_RE = re.compile(r"\bph d\b")

AI_WORD_RE = re.compile(r"\bai\b")
AI_TEXT_RE = re.compile(
    r"artificial intelligence|generative ai|large language model|"
    r"\bllm\b|\bgenai\b|machine learning", re.I)
TAG_AI_RE = re.compile(r"ai|ml|llm|machine-learning|artificial", re.I)


def norm_title(title):
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def reject_reason(tnorm):
    """Brian's hard exclusions; returns a reason string or None."""
    if "solutions consultant" in tnorm:
        return "solutions_consultant"
    if BARE_AUTOMATION_CONSULTANT_RE.search(tnorm):
        return "bare_automation_consultant"
    for phrase in REJECT_PHRASES:
        if phrase in tnorm:
            return "neg:" + phrase.replace(" ", "_")
    m = REJECT_WORD_RE.search(tnorm)
    if m:
        return "neg:" + m.group(1)
    if PHD_DOT_RE.search(tnorm):
        return "neg:phd"
    return None


def ai_signal(title_norm, company, tags, text_head):
    """Deterministic 'this is an AI company/role' signal for the
    sales/support lane: AI in the title, an AI-ish tag/category, or
    AI language at the head of the description."""
    if AI_WORD_RE.search(title_norm):
        return True
    for tag in tags or []:
        if TAG_AI_RE.search(str(tag)):
            return True
    if text_head and AI_TEXT_RE.search(text_head[:1200]):
        return True
    return False


def match_kind(item):
    """Return 'core' | 'sales_support' | None, and the reject reason
    when a hard exclusion fired (for the run log)."""
    tnorm = norm_title(item["title"])
    reason = reject_reason(tnorm)
    if reason:
        return None, reason
    for phrase in CORE_PHRASES:
        if phrase in tnorm:
            return "core", None
    if N8N_RE.search(tnorm):
        return "core", None
    for phrase in SALES_SUPPORT_PHRASES:
        if phrase in tnorm:
            if ai_signal(tnorm, item.get("company"),
                         item.get("tags"), item.get("text_head")):
                return "sales_support", None
            return None, None
    return None, None


# ------------------------------------------------------------------ pay
def pay_fields(annual_low=None, annual_high=None,
               hourly_low=None, hourly_high=None):
    """Mirror scan_mailbox.normalize_pay's convention: whichever side
    is known, derive the other at 2080 h/yr so rows compare directly
    against the criteria floor/target."""
    out = {"pay_hourly_low": None, "pay_hourly_high": None,
           "pay_annual_low": None, "pay_annual_high": None,
           "pay_range": ""}
    if annual_low or annual_high:
        lo = annual_low or annual_high
        hi = annual_high or annual_low
        out["pay_annual_low"], out["pay_annual_high"] = lo, hi
        out["pay_hourly_low"] = round(lo / 2080, 2)
        out["pay_hourly_high"] = round(hi / 2080, 2)
        out["pay_range"] = "$%s-$%s/yr" % (format(int(lo), ","),
                                           format(int(hi), ","))
    elif hourly_low or hourly_high:
        lo = hourly_low or hourly_high
        hi = hourly_high or hourly_low
        out["pay_hourly_low"], out["pay_hourly_high"] = lo, hi
        out["pay_annual_low"] = round(lo * 2080, 2)
        out["pay_annual_high"] = round(hi * 2080, 2)
        out["pay_range"] = "$%s-$%s/hr" % (lo, hi)
    return out


# ------------------------------------------------------------------ fetch
def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text)


def fetch_remoteok():
    """RemoteOK public JSON API. Element 0 is the legal/attribution
    notice and is skipped, per the API's own terms."""
    data = json.loads(http_get("https://remoteok.com/api"))
    items = []
    for job in data[1:]:
        if not isinstance(job, dict) or not job.get("position"):
            continue
        smin = job.get("salary_min") or None
        smax = job.get("salary_max") or None
        pay = pay_fields(annual_low=smin, annual_high=smax)
        loc = (job.get("location") or "").strip()
        items.append({
            "title": job["position"].strip(),
            "company": (job.get("company") or "").strip(),
            "url": (job.get("url") or "").strip(),
            "tags": job.get("tags") or [],
            "text_head": strip_html(job.get("description") or ""),
            "employment_type": ("contract" if "contract" in
                                [str(t).lower() for t in
                                 job.get("tags") or []] else None),
            "location": loc,
            "pay": pay,
            "attribution": "via RemoteOK API (remoteok.com)",
        })
    return items


WWR_FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]


def fetch_wwr():
    """We Work Remotely RSS (main + Programming + DevOps/Sysadmin
    category feeds). Item titles are 'Company: Job Title'."""
    items = []
    seen_links = set()
    for feed in WWR_FEEDS:
        root = ET.fromstring(http_get(feed))
        for it in root.find("channel").findall("item"):
            link = (it.findtext("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            raw_title = (it.findtext("title") or "").strip()
            if ": " in raw_title:
                company, title = raw_title.split(": ", 1)
            else:
                company, title = "", raw_title
            items.append({
                "title": title.strip(),
                "company": company.strip(),
                "url": link,
                "tags": [],
                "text_head": strip_html(it.findtext("description") or ""),
                "employment_type": None,
                "location": "",
                "pay": pay_fields(),
                "attribution": "via We Work Remotely RSS",
            })
    return items


HIMALAYAS_API = "https://himalayas.app/jobs/api"


def fetch_himalayas(max_pages, since_hours):
    """Himalayas public API, newest first, cursor-paginated under a
    page budget. The API ignores its search/filter params (verified
    live 2026-11-21), so this pages the firehose and the caller
    title-filters locally. Stops early once a page's oldest posting
    predates the since-window."""
    items = []
    cursor = None
    cutoff = time.time() - since_hours * 3600
    for _ in range(max_pages):
        url = HIMALAYAS_API + "?limit=20"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        data = json.loads(http_get(url))
        jobs = data.get("jobs") or []
        if not jobs:
            break
        oldest = None
        for job in jobs:
            pub = job.get("pubDate") or 0
            oldest = pub if oldest is None else min(oldest, pub)
            if job.get("expiryDate") and job["expiryDate"] < time.time():
                continue
            pay = pay_fields()
            cur = (job.get("currency") or "").upper()
            smin, smax = job.get("minSalary"), job.get("maxSalary")
            if (smin or smax) and cur in ("USD", ""):
                period = (job.get("salaryPeriod") or "annual").lower()
                if period.startswith("month"):
                    pay = pay_fields(
                        annual_low=(smin or smax) * 12,
                        annual_high=(smax or smin) * 12)
                elif period.startswith("hour"):
                    pay = pay_fields(hourly_low=smin, hourly_high=smax)
                else:
                    pay = pay_fields(annual_low=smin, annual_high=smax)
            emp = (job.get("employmentType") or "").strip()
            emp_map = {"Full Time": "w2", "Part Time": "w2",
                       "Contractor": "contract", "Freelance": "freelance"}
            locs = job.get("locationRestrictions") or []
            items.append({
                "title": (job.get("title") or "").strip(),
                "company": (job.get("companyName") or "").strip(),
                "url": (job.get("applicationLink") or "").strip(),
                "fallback_id": str(job.get("guid") or ""),
                "tags": (job.get("categories") or []) +
                        (job.get("parentCategories") or []),
                "text_head": strip_html(job.get("excerpt") or
                                        job.get("description") or ""),
                "employment_type": emp_map.get(emp),
                "location": ", ".join(locs),
                "pay": pay,
                "attribution": "via Himalayas API (himalayas.app)",
            })
        cursor = data.get("nextCursor")
        if not cursor or (oldest is not None and oldest < cutoff):
            break
        time.sleep(0.3)
    return items


# ------------------------------------------------------------------ storage
def canonical_url(url):
    return (url or "").strip().lower().split("?")[0].rstrip("/")


def lead_hash(board_key, item):
    if item.get("url"):
        basis = "feed_watch|%s|%s" % (board_key, canonical_url(item["url"]))
    else:
        basis = "feed_watch|%s|%s|%s" % (
            board_key, norm_title(item["title"]),
            norm_title(item.get("company") or item.get("fallback_id", "")))
    return hashlib.sha256(basis.encode()).hexdigest()


def to_lead(board_key, board_name, item, kind):
    pay = item["pay"]
    notes_bits = [item["attribution"]]
    if item.get("location"):
        notes_bits.append("locations: " + item["location"])
    if kind == "sales_support":
        notes_bits.append("lane: ai_company_sales_support")
    return {
        "title": item["title"][:200],
        "company": item["company"][:120],
        "status": "open",
        "source": "feed_watch",
        "source_detail": board_name,
        "contact_name": "",
        "contact_email": "",
        "pay_range": pay["pay_range"][:60],
        "pay_hourly_low": pay["pay_hourly_low"],
        "pay_hourly_high": pay["pay_hourly_high"],
        "pay_annual_low": pay["pay_annual_low"],
        "pay_annual_high": pay["pay_annual_high"],
        "remote": True,
        "ai_role": True,
        "company_confidence": "parsed" if item["company"] else "none",
        "employment_type": item.get("employment_type"),
        "track": None,
        "application_status": "lead",
        "next_action": None,
        "message_id_hash": lead_hash(board_key, item),
        "notes": "; ".join(notes_bits)[:500],
        "profile_flags": "",
        "gaps": "" if pay["pay_range"] else "pay_unknown",
        "verdict": None,
        "url": item["url"] or None,
    }


INSERT_SQL = (
    "INSERT INTO public.job_tracking (title, company, status, source,"
    " source_detail, contact_name, contact_email, pay_range,"
    " pay_hourly_low, pay_hourly_high, pay_annual_low, pay_annual_high,"
    " remote, ai_role, company_confidence, employment_type, track,"
    " application_status, next_action, message_id_hash, notes,"
    " profile_flags, gaps, verdict, url, discovered_at) VALUES ("
    " %(title)s, %(company)s, %(status)s, %(source)s, %(source_detail)s,"
    " %(contact_name)s, %(contact_email)s, %(pay_range)s,"
    " %(pay_hourly_low)s, %(pay_hourly_high)s, %(pay_annual_low)s,"
    " %(pay_annual_high)s, %(remote)s, %(ai_role)s,"
    " %(company_confidence)s, %(employment_type)s, %(track)s,"
    " %(application_status)s, %(next_action)s, %(message_id_hash)s,"
    " %(notes)s, %(profile_flags)s, %(gaps)s, %(verdict)s, %(url)s, now())"
    " ON CONFLICT (message_id_hash) WHERE message_id_hash IS NOT NULL"
    " DO NOTHING"
)


def insert_leads(leads):
    pw = os.environ.get("PGPASSWORD")
    if not pw:
        raise RuntimeError("PGPASSWORD is not set (~/successbrian-os/.env)")
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME,
                            user=DB_USER, password=pw)
    inserted = 0
    try:
        cur = conn.cursor()
        for lead in leads:
            cur.execute(INSERT_SQL, lead)
            inserted += cur.rowcount
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return inserted


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + match only; write nothing")
    ap.add_argument("--pages", type=int, default=60,
                    help="Himalayas page budget (20 jobs/page)")
    ap.add_argument("--since-hours", type=int, default=8,
                    help="Himalayas firehose window to page back through")
    args = ap.parse_args()

    log("feed_watch run start (dry_run=%s)" % args.dry_run)
    fetchers = [
        ("remoteok", "RemoteOK", fetch_remoteok),
        ("wwr", "We Work Remotely", fetch_wwr),
        ("himalayas", "Himalayas",
         lambda: fetch_himalayas(args.pages, args.since_hours)),
    ]
    leads = []
    total_fetched = 0
    for board_key, board_name, fetch in fetchers:
        try:
            items = fetch()
        except Exception as exc:  # dead/changed source: degrade, continue
            log("SOURCE %s ERROR: %s: %s" % (board_name,
                                             type(exc).__name__, exc))
            continue
        matched, rejected = [], {}
        for item in items:
            if not item.get("title"):
                continue
            kind, reason = match_kind(item)
            if kind:
                matched.append(to_lead(board_key, board_name, item, kind))
            elif reason:
                rejected[reason] = rejected.get(reason, 0) + 1
        total_fetched += len(items)
        leads.extend(matched)
        log("SOURCE %s: fetched=%d matched=%d rejected=%s" % (
            board_name, len(items), len(matched),
            json.dumps(rejected, sort_keys=True) if rejected else "{}"))
        for lead in matched[:5]:
            log("  MATCH [%s] %s @ %s" % (board_name, lead["title"],
                                          lead["company"] or "?"))

    log("TOTAL: fetched=%d matched=%d" % (total_fetched, len(leads)))
    if args.dry_run:
        log("dry-run: no rows written")
        return 0
    if leads:
        try:
            inserted = insert_leads(leads)
        except Exception as exc:
            log("DB ERROR: %s: %s" % (type(exc).__name__, exc))
            return 1
        log("DB: inserted=%d duplicates_skipped=%d" % (
            inserted, len(leads) - inserted))
    else:
        log("DB: nothing to insert")
    log("feed_watch run done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
