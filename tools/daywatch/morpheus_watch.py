#!/usr/bin/env python3
"""Morpheus day-watch: Morpheus looks at fleet health throughout the day.

PURPOSE: Every 30 min during the day, Morpheus triages the fleet's health
    snapshot and reports what looks wrong, new, or worse. This is the
    correlation + judgment layer on top of Lyra's deterministic 15-min
    threshold checks ("these 5 workers went quiet together - common
    cause?"), running entirely on k11-alpha with zero AI credits.
WHY: Brian: "morpheus needs to be looking and doing what it can all
    throughout the day - reliably run right off of k11 alpha without
    needing any ai credits." Deterministic checks catch threshold
    breaches; a local model adds triage across signals for free.
CALLED BY: Hermes --no-agent cron job morpheus-daywatch on Lyra's profile
    (every 30 min, 7 AM - 7 PM daily). --no-agent: no agent turn, this
    script IS the job.
NOTES:
    - CANONICAL SOURCE: successbrian-os/tools/daywatch/morpheus_watch.py
    - DEPLOYED COPY: /home/successbrian/.hermes/profiles/lyra/scripts/morpheus_watch.py
      (edit the repo, redeploy - never edit the deployed copy in place)
    - Morpheus LOOKS and TRIAGES. It does not act: no service restarts, no
      kills, no config changes, no deletions (Brian's no-chat-model-decides
      rule). Findings become knowledge_bridge rows (sender='lyra',
      target='spencer'); remediation stays with deterministic auto-fix or
      humans. The "doing" is: correlating incidents, prioritizing the
      broken-things list, and handing Altair/Spencer concrete next steps.
    - Quiet unless something is new, wrong, or worse: repeat findings are
      deduped via the state file so an ongoing incident doesn't page every
      30 min. Silence is health; the state's last_run timestamp proves
      liveness.
    - Morpheus: http://127.0.0.1:11437 (Qwen2.5-14B, local, free).
"""
import json, os, sys, glob, urllib.request, subprocess
from datetime import datetime, timedelta

MORPHEUS_URL = "http://127.0.0.1:11437/v1/chat/completions"
PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian", "password": "postgres"}
HEALTH_LOG = "/home/successbrian/.hermes/profiles/lyra/state/lyra_health_15min.log"
STATE_FILE = "/home/successbrian/.hermes/profiles/lyra/state/morpheus_watch_state.json"
# Services whose restart counts are worth watching (crash loops hide here).
WATCH_SERVICES = ["email-tracking.service", "autonomous-huddle-executor.service",
                  "n8n.service", "altair-api.service"]
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
             "with", "is", "are", "at", "multiple"}


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def snapshot():
    """Deterministic health snapshot. No model involved - just facts."""
    parts = ["Snapshot taken %s (k11-alpha, local)." %
             datetime.now().strftime("%Y-%m-%d %H:%M")]
    # 1. Lyra's 15-min deterministic check, last 2 hours
    try:
        with open(HEALTH_LOG) as f:
            lines = f.read().strip().splitlines()[-8:]
        if lines:
            parts.append("Lyra 15-min health (last ~2h):\n" + "\n".join(lines))
        else:
            parts.append("Lyra 15-min health log is EMPTY - check may not be running.")
    except Exception as e:
        parts.append("Could not read Lyra health log: %s" % e)
    # 2. Failed systemd units right now
    failed = _run(["systemctl", "list-units", "--type=service",
                   "--state=failed", "--no-legend", "--no-pager"])
    parts.append("Failed services now:\n" + (failed or "(none)"))
    # 3. Restart counts on watched services (crash loops)
    restarts = []
    for svc in WATCH_SERVICES:
        n = _run(["systemctl", "show", svc, "-p", "NRestarts", "--value"])
        if n and n.isdigit():
            restarts.append("%s restarts=%s" % (svc, n))
    if restarts:
        parts.append("Restart counts:\n" + "\n".join(restarts))
    # 4. Resource pressure right now
    df = _run(["df", "-h", "/", "--output=pcent"])
    mem = _run(["free", "-g"])
    mem_line = ""
    for ln in mem.splitlines():
        if ln.startswith("Mem:"):
            p = ln.split()
            mem_line = "mem total=%sG used=%sG avail=%sG" % (p[1], p[2], p[6])
    parts.append("Resources: disk %s used; %s" %
                 (df.splitlines()[-1].strip() if df else "?",
                  mem_line or "mem unknown"))
    # 5. Urgent bridge rows in the last 2 hours (what the fleet flagged)
    parts.append("Urgent bridge rows (last 2h):\n" + _recent_urgent())
    return "\n\n".join(parts)


def _recent_urgent():
    q = ("SELECT sender, urgency, subject FROM altair.knowledge_bridge "
         "WHERE created_at > NOW() - INTERVAL '2 hours' "
         "AND urgency IN ('important','critical') "
         "ORDER BY created_at DESC LIMIT 10;")
    try:
        import psycopg2
        conn = psycopg2.connect(
            "host=%s dbname=%s user=%s password=%s connect_timeout=10" % (
                PG["host"], PG["dbname"], PG["user"], PG["password"]))
        cur = conn.cursor()
        cur.execute(q)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except ImportError:
        env = dict(os.environ, PGPASSWORD=PG["password"])
        r = subprocess.run(
            ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
             "-t", "-A", "-F", "|", "-c", q],
            capture_output=True, text=True, env=env, timeout=30)
        if r.returncode != 0:
            return "(bridge query failed)"
        rows = [tuple(ln.split("|")) for ln in r.stdout.strip().splitlines()
                if ln.strip()]
    if not rows:
        return "(none)"
    return "\n".join("- [%s/%s] %s" % (s, u, subj) for s, u, subj in rows)


def triage(snapshot_text, previous):
    prompt = (
        "You are doing a fleet-health triage pass for k11-alpha (Brian's home "
        "lab). Below is a deterministic health snapshot plus what was "
        "reported on the previous pass. Your job: say what looks WRONG, NEW, "
        "or WORSE. Correlate across signals (e.g. several workers quiet at "
        "the same time suggests a common cause).\n\n"
        "Reply in EXACTLY this format:\n"
        "VERDICT: ALL_CLEAR | FINDINGS\n"
        "URGENCY: routine|important   (only if FINDINGS)\n"
        "FINDINGS:\n"
        "- [title]: what you see + why it matters + suggested next diagnostic step\n\n"
        "Rules:\n"
        "- Be conservative. No change since last pass = ALL_CLEAR. An "
        "  in-progress investigation with no new signal = ALL_CLEAR.\n"
        "- If a previously reported issue got WORSE, prefix its line with "
        "  WORSENED: - that is the one case a repeat finding is reported.\n"
        "- URGENCY is whether BRIAN must act, not how dramatic it sounds. "
        "  'routine': FYI / for Altair or Spencer to handle (the default). "
        "  'important': Brian must decide, approve, or provide something.\n"
        "- You LOOK and TRIAGE only. Never present a remediation step as "
        "  something you will do yourself - phrase next steps as suggestions "
        "  for Altair or Spencer.\n\n"
        "Previous pass reported:\n%s\n\n"
        "Current snapshot:\n%s" % (previous or "(first pass - nothing reported yet)",
                                   snapshot_text))
    req = urllib.request.Request(
        MORPHEUS_URL,
        data=json.dumps({"model": "morpheus",
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 500, "stream": False,
                         "temperature": 0.3}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"]


def parse_verdict(text):
    verdict, urgency, findings = "ALL_CLEAR", "routine", []
    in_findings = False
    for ln in text.splitlines():
        s = ln.strip()
        if s.upper().startswith("VERDICT:"):
            v = s.split(":", 1)[1].strip().upper()
            verdict = "FINDINGS" if "FINDING" in v else "ALL_CLEAR"
        elif s.upper().startswith("URGENCY:"):
            u = s.split(":", 1)[1].strip().lower()
            if u in ("routine", "important"):
                urgency = u
        elif s.upper() == "FINDINGS:":
            in_findings = True
        elif in_findings and s.startswith("-"):
            findings.append(s[1:].strip())
    return verdict, urgency, findings


def _stems(text):
    out = set()
    for w in text.lower().split():
        w = w.strip(".,;:!?()[]{}").lower()
        if not w or w in STOPWORDS or len(w) < 3:
            continue
        for suf in ("ally", "ingly", "ing", "edly", "ed", "ies", "es", "ly", "al", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


def load_state():
    try:
        if os.path.exists(STATE_FILE):
            return json.load(open(STATE_FILE))
    except Exception:
        pass
    return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(state, open(STATE_FILE, "w"))
    except Exception:
        pass


def dedup(findings, state):
    """An ongoing incident reports once. Returns (new_findings, titles).

    Compares full-finding word stems (>=3 shared): the bracketed titles
    alone are too short to match reliably."""
    prev = state.get("findings", [])
    prev_stems = [_stems(p) for p in prev]
    new, titles = [], []
    for f in findings:
        titles.append(f.split(":")[0].strip())
        fs = _stems(f)
        matched = any(len(fs & ps) >= 3 for ps in prev_stems)
        if not matched or f.upper().startswith("WORSENED:"):
            new.append(f)
    return new, titles


def insert(urgency, subject, body):
    try:
        import psycopg2
        conn = psycopg2.connect(
            "host=%s dbname=%s user=%s password=%s connect_timeout=10" % (
                PG["host"], PG["dbname"], PG["user"], PG["password"]))
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency)"
            " VALUES ('lyra','spencer',%s,%s,%s) RETURNING id",
            (subject, body, urgency))
        row_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
        return row_id
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    q = ("INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
         "VALUES ('lyra','spencer',$$%s$$,$$%s$$,'%s') RETURNING id;"
         % (subject.replace("$$", ""), body.replace("$$", ""), urgency))
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-c", q],
                       capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:300])
    return r.stdout.strip().split()[0]


def main():
    snap = snapshot()
    state = load_state()
    prev_summary = "; ".join(f.split(":")[0].strip() for f in state.get("findings", []))
    try:
        text = triage(snap, prev_summary)
    except Exception as e:
        # Morpheus itself down: record it, don't crash silently.
        state["last_run"] = datetime.now().isoformat()
        state["last_error"] = "morpheus unreachable: %s" % str(e)[:120]
        save_state(state)
        print("ERROR: morpheus unreachable: %s" % str(e)[:120], file=sys.stderr)
        sys.exit(1)
    verdict, urgency, findings = parse_verdict(text)
    state["last_run"] = datetime.now().isoformat()
    state.pop("last_error", None)
    if verdict != "FINDINGS" or not findings:
        save_state(state)
        print("daywatch: ALL_CLEAR")
        return
    new_findings, titles = dedup(findings, state)
    state["findings"] = [f for f in findings]  # full lines: dedup needs the detail
    save_state(state)
    if not new_findings:
        print("daywatch: only repeat findings, staying quiet")
        return
    subject = "[daywatch] " + new_findings[0].split(":")[0][:100]
    body = ("Morpheus day-watch triage (%s):\n\n" %
            datetime.now().strftime("%Y-%m-%d %H:%M")
            + "\n".join("- " + f for f in new_findings)
            + "\n\nFull snapshot on k11: %s" % HEALTH_LOG)
    row_id = insert(urgency, subject, body)
    print("daywatch row id: %s (urgency=%s, findings=%d)" %
          (row_id, urgency, len(new_findings)))


if __name__ == "__main__":
    main()
