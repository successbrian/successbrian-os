#!/usr/bin/env python3
"""aptean_unite_watch.py — monthly UNITE 2027 intel watch (alpha).

Migrated 2026-11-09 from the Muse-side cron aptean-unite-2027-watch
at Brian's order (pure scrape/check -> ecosystem). Watch only —
never contact Aptean or Crew2, never register for anything.

Baseline (Intel Bridge capture #604, 2026-10-29): UNITE is Aptean's
premier annual customer conference. UNITE 2025: Oct 6-9, Orlando.
UNITE 2026: Oct 5-8, Kansas City (Ascent launched). As of the
baseline, UNITE 2027 dates/location/registration were NOT announced.

Each run: read the latest filed UNITE facts from
atlas.scattered_captures, search the fleet SearXNG (127.0.0.1:8891)
for UNITE 2027 news, and try the likely event page directly. If
nothing material is new: stay silent (state file + log only — the
QA freshness check reads the state file). If a candidate announcement
appears (a 2027 event page or official result not in prior filings):
file ONE intel capture with the headlines, labeled CANDIDATE for
Spencer to verify against the source page before it is treated as
fact. The verification judgment stays agent-side; this script never
invents a date, city, price, or deadline.
Cron (alpha, America/Chicago): 41 9 15 * *

SESSION-PICK RULE (Brian's lens, 2026-11-10): when the UNITE
2027 agenda publishes and sessions are ranked for Brian, AI
content ranks FIRST — sessions where businesses present how
AI solves their problems (operator results, measured
outcomes, the ASCENT line) outrank product-roadmap and spec
sessions. The rule lives in SESSION_PICK_RULE below, beside
the watch that will spot the agenda's arrival; the picking
itself stays Spencer/Brian-side, and the ranking becomes
executable when an agenda exists to rank.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state", "aptean_unite_watch.json")
CT = timezone(timedelta(hours=-6))
SEARX = "http://127.0.0.1:8891/search"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
QUERIES = ["Aptean UNITE 2027", "Aptean UNITE 2027 registration",
           "Aptean UNITE 2027 call for speakers",
           "site:events.aptean.com UNITE"]
EVENT_URLS = ["https://events.aptean.com/unite2027/home",
              "https://events.aptean.com/unite2027"]

# SESSION-PICK RULE (Brian, 2026-11-10 00:54 CST: "what matters
# to BRIAN is learning more and more about AI and what
# businesses are thinking in regards to how AI solves their
# problems"). When an agenda exists, rank sessions carrying
# these markers first; a session whose title/abstract matches
# the clerk's AI-thinking lens (board/scatter_clerk.py
# match_ai_thinking) outranks one that matches only product
# markers. Config, not code path: nothing ranks anything
# until an agenda publishes.
SESSION_PICK_RULE = {
    "rank_first": "ai_business_thinking",
    "why": "Brian's lens (2026-11-10): learning what "
           "businesses think about how AI solves their "
           "problems outranks product and spec content",
    "ai_first_markers": ["ai", "artificial intelligence",
                         "agent", "automation", "ascent",
                         "outcome", "case study", "results",
                         "roi", "customer panel"],
    "lens": "board/scatter_clerk.py match_ai_thinking",
}


def searx(q):
    url = SEARX + "?" + urllib.parse.urlencode({"q": q,
                                                "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8")).get("results", [])


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"seen_urls": []}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, default=str)


def main():
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM atlas.scattered_captures WHERE "
                "title ILIKE '%UNITE%' ORDER BY id DESC LIMIT 10")
    prior = cur.fetchall()
    prior_text = " ".join(r["title"] for r in prior).lower()
    state = load_state()
    seen = set(state.get("seen_urls", []))
    candidates = []
    all_urls = set(seen)
    for q in QUERIES:
        try:
            results = searx(q)
        except Exception as e:
            print("searx failed for %r: %s" % (q, e), file=sys.stderr)
            results = []
        for r in results[:8]:
            u = r.get("url", "")
            all_urls.add(u)
            title = (r.get("title") or "")
            if "2027" in title and "unite" in title.lower() \
                    and u not in seen \
                    and ("aptean.com" in u or "bizzabo" in u):
                candidates.append((title, u))
    event_live = []
    for u in EVENT_URLS:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", "ignore")
            if r.status == 200 and "2027" in body:
                event_live.append(u)
        except Exception:
            pass
    today = datetime.now(CT).date()
    filed = None
    if candidates or event_live:
        lines = ["CANDIDATE UNITE 2027 material found by the alpha "
                 "watch — Spencer to verify against the source pages "
                 "before treating any date/location/deadline as fact:"]
        for t, u in candidates:
            lines.append("- %s | %s" % (t, u))
        for u in event_live:
            lines.append("- event page live: %s" % u)
        lines.append("Prior filings compared: %d UNITE captures "
                     "(latest id %s)." % (len(prior),
                                          prior[0]["id"] if prior
                                          else "none"))
        cur.execute(
            "INSERT INTO atlas.scattered_captures (title, raw_text, "
            "context) VALUES (%s, %s, %s) RETURNING id",
            ("UNITE 2027 watch: candidate announcement found %s"
             % today.isoformat(), "\n".join(lines),
             "Aptean UNITE 2027 monthly watch (alpha "
             "aptean_unite_watch.py, migrated from the Muse cron "
             "2026-11-09). Serves Brian's Crew2/Aptean watch. "
             "Watch only — no contact, no registration."))
        filed = cur.fetchone()["id"]
        conn.commit()
    state["seen_urls"] = sorted(all_urls)
    state["last_run"] = datetime.now(CT).isoformat()
    state["last_result"] = ("candidate capture %s" % filed) if filed \
        else "no new announcements"
    state["prior_captures_compared"] = len(prior)
    save_state(state)
    conn.close()
    print("UNITE 2027 watch %s: %s" % (today, state["last_result"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
