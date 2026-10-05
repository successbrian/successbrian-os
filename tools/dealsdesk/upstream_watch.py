#!/usr/bin/env python3
"""upstream_watch.py — daily upstream release watcher for the fleet's harnesses.

PURPOSE: Check GitHub for new releases of the tools Brian's ecosystem depends
         on (OpenClaw, AnythingLLM, llama.cpp, Hermes agent, Ollama). On a new
         release: record it and notify Altair via knowledge_bridge so he can
         evaluate it; security/breaking releases also go to Brian's outbox.
WHY:     Brian 2026-10-01: keep the ecosystem on the latest-and-greatest
         without anyone having to remember to check.
CALLED BY: upstream-watch.timer (daily 06:30 America/Chicago).
NOTES:   Unauthenticated GitHub API (60 req/hr); 5 repos once daily is gentle.
         First sighting of a repo only sets the baseline — no alert spam.
         Muse (Meta) has no machine-readable changelog; it is deliberately NOT
         watched here (see report 2026-10-01).
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/upstream_watch.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/upstream_watch.py (k11-alpha; systemd timers).

"""

import json
import logging
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [upstream] %(message)s")
LOG = logging.getLogger("upstream")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"
UA = "successbrian-os-upstream-watch/1.0"
API = "https://api.github.com/repos/{slug}/releases/latest"
SEC_RE = re.compile(r"securi|CVE-\d|breaking[ -]change|vulnerab|\bRCE\b|privilege escalation", re.I)


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


def latest_release(slug):
    req = urllib.request.Request(API.format(slug=slug), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        LOG.error("%s: fetch failed: %s", slug, e)
        return -1, None


def main():
    dry = "--dry-run" in sys.argv
    rows = psql("""SELECT id, repo, display_name, COALESCE(last_seen_tag,'')
                   FROM successbrian_os.upstream_watch ORDER BY repo""")
    # NOTE: \x1f IS Python whitespace (isspace()->True), so the global .strip()
    # in psql() eats a trailing separator on the last row. Pad defensively.
    rows = [(r + ["", "", "", ""])[:4] for r in rows]
    for rid, slug, name, seen in rows:
        status, rel = latest_release(slug)
        if dry:
            tag = (rel or {}).get("tag_name", "?") if rel else f"HTTP {status}"
            LOG.info("dry %s -> latest %s (seen %s)", slug, tag, seen or "none")
            continue
        if status == 403:
            LOG.error("%s: rate limited, stopping run", slug)
            break
        if status == 404 or rel is None:
            psql(f"""UPDATE successbrian_os.upstream_watch
                     SET last_checked = NOW(),
                         notes = COALESCE(notes,'') || ' [no releases endpoint {time.strftime("%F")}]'
                     WHERE id = {rid}""", write=True)
            LOG.warning("%s: no releases endpoint (HTTP %s)", slug, status)
            time.sleep(1)
            continue
        tag = rel.get("tag_name", "")
        rname = rel.get("name", "") or tag
        url = rel.get("html_url", "")
        body = (rel.get("body") or "")[:800]
        psql(f"UPDATE successbrian_os.upstream_watch SET last_checked = NOW() WHERE id = {rid}",
             write=True)
        if not seen:
            psql(f"""UPDATE successbrian_os.upstream_watch
                     SET last_seen_tag = '{esc(tag)}' WHERE id = {rid}""", write=True)
            LOG.info("%s: baseline set to %s (no alert)", slug, tag)
        elif tag != seen:
            psql(f"""UPDATE successbrian_os.upstream_watch
                     SET last_seen_tag = '{esc(tag)}' WHERE id = {rid}""", write=True)
            subj = f"upstream release: {name} {tag}"
            msg = (f"{name} released {rname} ({tag}). {url}\n\n"
                   f"Notes excerpt:\n{body}")
            psql(f"""INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency)
                     VALUES ('spencer', 'altair', '{esc(subj)}', '{esc(msg)}', 'routine')""",
                 write=True)
            LOG.info("%s: NEW %s -> bridge notified", slug, tag)
            if SEC_RE.search(rname + "\n" + body):
                out = (f"UPSTREAM SECURITY/BREAKING: {name} {tag}. {url} "
                       f"Altair is evaluating; hold upgrades until he clears it.")
                psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
                         VALUES ('spencer', '{esc(out)}', 2)""", write=True)
                LOG.info("%s: security/breaking keywords -> outbox notified", slug)
        else:
            LOG.info("%s: unchanged (%s)", slug, tag)
        time.sleep(1)
    LOG.info("upstream watch done")


if __name__ == "__main__":
    main()
