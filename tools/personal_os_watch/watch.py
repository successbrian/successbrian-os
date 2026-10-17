#!/usr/bin/env python3
"""
personal_os_watch — watch for Max Mitcham's AI personal-OS code drop and
scan for similar AI personal-OS / agent-harness projects.

Why: Brian flagged the Mitcham video (Oct 2026) as dashboard-relevant intel.
The code release was promised "later this week" with no repo link yet.

Sources (stdlib + urllib only):
  1. Mitcham's YouTube channel RSS — new uploads mentioning open source / repo
  2. GitHub code search API — new repos matching personal-OS / AI-harness terms
  3. HN Algolia API — stories about AI personal OS / agent dashboards

Findings -> ecosystem_intel facts (dashboard-relevant angle noted).
A confirmed code drop -> pending_questions (Brian decides the teardown) +
ecosystem_events.

State: state.json next to this script (seen video IDs, seen repos, seen HN IDs).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "business_core"))
from core import lit  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "ecosystem_intel"))
from intel import record_fact as intel_record_fact  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")

# Filled in at deploy; @handle resolved to channel ID at runtime.
YT_HANDLE = "@MaxMitchamAgents"
GITHUB_QUERIES = [
    "AI personal OS",
    "personal operating system AI agent",
    "AI agent harness dashboard",
]
HN_QUERIES = [
    "AI personal OS",
    "personal operating system",
]


def _pg_env():
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
    })
    return env


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) personal-os-watch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"videos": [], "repos": [], "hn": [], "code_drop": False}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1)


def record_fact(key, value, source):
    intel_record_fact("brian", key, value, category="personal-os-watch",
                      source=source)


def file_question(question, why):
    dup = subprocess.run(
        ["psql", "-t", "-A", "-c",
         "SELECT 1 FROM successbrian_os.pending_questions "
         f"WHERE question ILIKE {lit(question[:60] + '%')} "
         "AND status='open' LIMIT 1;"],
        capture_output=True, text=True, env=_pg_env(), timeout=60)
    if dup.stdout.strip():
        return
    pg_exec(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, context, status) VALUES "
        f"('personal_os_watch', {lit(question)}, {lit(why)}, 'open');")


def yt_channel_id(handle):
    try:
        page = fetch(f"https://www.youtube.com/{handle}")
    except Exception:
        return None
    m = re.search(r'"channelId":"(UC[^"]+)"', page)
    return m.group(1) if m else None


def yt_feed(channel_id, max_items=8):
    try:
        xml = fetch(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    except Exception:
        return []
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns)[:max_items]:
        vid = (e.findtext("a:id", default="", namespaces=ns) or "")
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = e.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        pub = (e.findtext("a:published", default="", namespaces=ns) or "")[:10]
        if vid and title:
            out.append({"id": vid, "title": title, "link": link,
                        "published": pub})
    return out


def github_search(query, max_items=5):
    import urllib.parse
    q = urllib.parse.quote(query)
    url = ("https://api.github.com/search/repositories"
           f"?q={q}&sort=stars&order=desc&per_page={max_items}")
    try:
        data = json.loads(fetch(url))
    except Exception:
        return []
    out = []
    for r in data.get("items", []):
        out.append({"full_name": r.get("full_name", ""),
                    "url": r.get("html_url", ""),
                    "stars": r.get("stargazers_count", 0),
                    "desc": (r.get("description") or "")[:200],
                    "pushed": (r.get("pushed_at") or "")[:10]})
    return out


def hn_search(query, max_items=5):
    import urllib.parse
    q = urllib.parse.quote(query)
    url = ("https://hn.algolia.com/api/v1/search"
           f"?query={q}&tags=story&hitsPerPage={max_items}")
    try:
        data = json.loads(fetch(url))
    except Exception:
        return []
    out = []
    for h in data.get("hits", []):
        out.append({"id": str(h.get("objectID", "")),
                    "title": h.get("title", ""),
                    "url": h.get("url") or
                    f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "points": h.get("points", 0),
                    "date": (h.get("created_at") or "")[:10]})
    return out


DASHBOARD_ANGLES = ("dashboard", "workspace", "brain", "memory", "card",
                    "automation", "voice", "bot", "agent")


def dashboard_angle(text):
    t = text.lower()
    hits = [w for w in DASHBOARD_ANGLES if w in t]
    return ("Dashboard-relevant: " + ", ".join(sorted(set(hits)))
            if hits else "No direct dashboard angle")


def main():
    state = load_state()
    today = datetime.date.today().isoformat()
    new_finds = 0

    # 1. Mitcham channel — the code drop
    cid = yt_channel_id(YT_HANDLE)
    if cid:
        for v in yt_feed(cid):
            if v["id"] in state["videos"]:
                continue
            state["videos"].append(v["id"])
            t = v["title"].lower()
            if any(k in t for k in ("open source", "open-source", "github",
                                    "repo", "release", "source code")):
                detail = (f"Max Mitcham posted '{v['title']}' ({v['published']}): "
                          f"{v['link']}. Possible code-drop announcement.")
                record_fact("personal-os mitcham code drop?", detail, v["link"])
                file_question(
                    "Max Mitcham's AI personal-OS repo may be live — tear it down for dashboard steals?",
                    detail + " Watch for the actual GitHub URL, then evaluate "
                    "workspace brains, social dashboard, automations-to-cards.")
                pg_exec(
                    "INSERT INTO successbrian_os.ecosystem_events "
                    "(event_type, source_plugin, project_ref, title, detail) "
                    f"VALUES ('intel_code_drop', 'personal_os_watch', "
                    f"'dashboard', {lit('Mitcham personal-OS repo may be live')}, "
                    f"{lit(detail)});")
                state["code_drop"] = True
                new_finds += 1

    # 2. GitHub — similar ideas
    for q in GITHUB_QUERIES:
        for r in github_search(q):
            if r["full_name"] in state["repos"]:
                continue
            state["repos"].append(r["full_name"])
            topic = f"github {r['full_name']}"
            detail = (f"{r['stars']} stars, pushed {r['pushed']}: {r['desc']} "
                      f"{dashboard_angle(r['full_name'] + ' ' + r['desc'])} "
                      f"{r['url']}")
            record_fact(topic, detail, r["url"])
            new_finds += 1

    # 3. HN — similar ideas (recent + AI-relevant only)
    cutoff = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    for q in HN_QUERIES:
        for h in hn_search(q):
            if h["id"] in state["hn"]:
                continue
            state["hn"].append(h["id"])
            if h["date"] < cutoff:
                continue
            if not any(k in h["title"].lower()
                       for k in ("ai", "agent", "bot", "llm", "claude",
                                 "dashboard")):
                continue
            topic = f"hn {h['title'][:80]}"
            detail = (f"{h['points']} points, {h['date']}: {h['url']} "
                      f"{dashboard_angle(h['title'])}")
            record_fact(topic, detail, h["url"])
            new_finds += 1

    save_state(state)
    print(f"{today}: {new_finds} new finds, "
          f"code_drop={state['code_drop']}")


if __name__ == "__main__":
    main()
