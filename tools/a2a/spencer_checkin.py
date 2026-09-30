#!/usr/bin/env python3
"""Altair -> Spencer twice-daily check-in (Hermes --no-agent cron script).

PURPOSE: Altair reports his current work, blockers, and Brian-relevant news
    to Spencer twice daily, in his own voice, via the A2A knowledge_bridge.
WHY: Brian directed "you and Altair need to talk a lot" — this is the
    async standup. Altair's context (goal queue, recent notes, A2A inbox)
    is gathered live from his files, composed by Morpheus (his chat model),
    and inserted as sender='altair' target='spencer'.
CALLED BY: Hermes --no-agent cron jobs spencer-checkin-morning (weekdays
    9:30 AM CDT) and spencer-checkin-afternoon (weekdays 2:30 PM CDT) on
    Altair's profile. --no-agent: no agent turn, this script IS the job
    (agent turns proved unreliable for this; see specs/a2a-checkin.md).
NOTES:
    - CANONICAL SOURCE: successbrian-os/tools/a2a/spencer_checkin.py
    - DEPLOYED COPY: /home/successbrian/.hermes/profiles/altair/scripts/spencer_checkin.py
      (profile-scoped: Hermes cron resolves scripts against HERMES_HOME/scripts/)
      (edit the repo, redeploy — never edit the deployed copy in place)
    - Tiered composer (per Brian 2026-09-30): the check-in must work at
      Morpheus, DeepSeek 150B, AND DeepSeek V4 Pro (InstantlyClaw) level.
      Deterministic cheapest-first fallback: local Morpheus (free) ->
      local 150B (free, slower; this producer is Altair's and the 150B is
      designated Altair-only, so no fleet conflict) -> V4 Pro cloud, ONLY
      when a free balance probe says the rental is live (is_available and
      total > $1.00, same definition as tools/v4pro_balance.py). The rental
      key is read from k11's ~/.hermes/.env, used in-memory only, never
      logged. Tier choice is plain Python (reachability + balance probe),
      never a model decision (Brian's no-chat-model-decides rule).
    - Urgency = whether BRIAN must act (routine default). Repeat topics are
      stepped down (critical->important->routine) via the state file so
      Spencer isn't re-paged for the same in-progress issue.
    - If ALL tiers are unreachable, a routine self-report row is inserted
      ("[checkin] composer unreachable on all tiers") instead of going
      silent — an explicit failure beats a silent gap.
    - Recency-weighted: fresh signals (goal queue, <72h notes, today's A2A)
      outrank long-term memory, which is labeled background-only.
"""
import json, os, sys, glob, urllib.request, subprocess
from datetime import datetime

MEM_DIR = "/home/successbrian/.hermes/profiles/altair/memory"
QUEUE = "/home/successbrian/.hermes/profiles/altair/goal-queue/queue.jsonl"
INBOX = "/home/successbrian/.hermes/profiles/altair/inbox"
# Tiered composer endpoints (per Brian 2026-09-30). Local tiers are
# OpenAI-compatible chat-completions endpoints; V4 Pro goes through the
# InstantlyClaw gateway with the rental key (in-memory only, never logged).
TIERS = [
    {"name": "morpheus", "label": "Morpheus",
     "url": "http://127.0.0.1:11437/v1/chat/completions",
     "model": "morpheus", "timeout": 120, "max_tokens": 400},
    {"name": "deepseek-150b", "label": "DeepSeek 150B",
     "url": "http://127.0.0.1:8084/v1/chat/completions",
     "model": "DeepSeek-V4-Flash-reap-150b", "timeout": 600, "max_tokens": 300},
]
V4PRO_URL = "https://api.b.ai/v1/chat/completions"
V4PRO_MODEL = "deepseek-v4-pro"
V4PRO_BALANCE_URL = "https://api.deepseek.com/user/balance"
V4PRO_ENV_FILE = "/home/successbrian/.hermes/.env"
V4PRO_KEY_NAME = "DEEPSEEK_API_KEY"
V4PRO_MIN_USD = 1.00
PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian", "password": "postgres"}
STATE_FILE = "/home/successbrian/.hermes/scripts/spencer_checkin_state.json"
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
             "with", "is", "are", "at", "multiple"}


def tail(path, n=2000):
    try:
        with open(path) as f:
            return f.read()[-n:]
    except Exception:
        return ""


def gather_context():
    """Recency-weighted: fresh signals first, everything explicitly dated."""
    today = datetime.now().strftime("%Y-%m-%d")
    parts = ["Today is %s." % today]
    # 1. Goal queue = what Altair is actively tasked with NOW
    try:
        with open(QUEUE) as f:
            goals = [json.loads(l).get("title", "") for l in f if l.strip()][:4]
        if goals:
            parts.append("CURRENT goal queue (active work):\n- " + "\n- ".join(goals))
    except Exception:
        pass
    # 2. Memory notes from the last 72h only, explicitly dated
    try:
        cutoff = datetime.now().timestamp() - 72 * 3600
        recent = [n for n in glob.glob(os.path.join(MEM_DIR, "2026-*.md"))
                  if os.path.getmtime(n) >= cutoff]
        recent.sort(key=os.path.getmtime, reverse=True)
        for nt in recent[:2]:
            t = tail(nt, 1000)
            if t:
                parts.append("Memory note dated %s:\n%s"
                             % (os.path.basename(nt)[:10], t))
        if not recent:
            parts.append("No memory notes in the last 72h - nothing new recorded there.")
    except Exception:
        pass
    # 3. Today's A2A inbox messages
    try:
        inbox_files = [b for b in glob.glob(os.path.join(INBOX, "*"))
                       if os.path.getmtime(b) >= datetime.now().timestamp() - 24 * 3600]
        inbox_files.sort(key=os.path.getmtime, reverse=True)
        for ib in inbox_files[:3]:
            t = tail(ib, 700)
            if t:
                parts.append("A2A message received today (%s):\n%s"
                             % (os.path.basename(ib), t))
    except Exception:
        pass
    # 4. Long-term memory tail, clearly labeled as possibly dated
    mem = tail(os.path.join(MEM_DIR, "MEMORY.md"), 1500)
    if mem:
        parts.append("Long-term memory (BACKGROUND - may be dated, do not "
                     "report as current unless confirmed by fresher signals):\n" + mem)
    return "\n\n".join(parts)


def _safe_err(e):
    """One-line error summary, safe to log: never contains credentials
    (the key travels in the Authorization header, never in a URL)."""
    return str(e).replace("\n", " ")[:120]


def _call_completions(url, model, prompt, max_tokens, timeout, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps({"model": model,
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens, "stream": False,
                         "temperature": 0.5}).encode(),
        headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"]


def _read_v4pro_key():
    """Rental key from k11's .env. In-memory only — never printed or logged."""
    try:
        with open(V4PRO_ENV_FILE) as f:
            for line in f:
                s = line.strip()
                if s.startswith(V4PRO_KEY_NAME + "="):
                    return s.split("=", 1)[1].strip().strip('"').strip("'") or None
    except Exception:
        pass
    return None


def _v4pro_balance_ok(key):
    """Free balance probe: is the InstantlyClaw rental live? Same definition
    as tools/v4pro_balance.py: is_available=true AND total USD > MIN_USD."""
    try:
        req = urllib.request.Request(
            V4PRO_BALANCE_URL,
            headers={"Authorization": "Bearer " + key,
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            b = json.load(r)
        if not b.get("is_available"):
            return False
        total = 0.0
        for info in b.get("balance_infos", []):
            try:
                total += float(info.get("total_balance", 0))
            except (TypeError, ValueError):
                pass
        return total > V4PRO_MIN_USD
    except Exception:
        return False


def compose(context, slot):
    """Compose the check-in via the tiered composer. Returns (text, tier) on
    success; (None, failure_summary) when every tier is unreachable."""
    prompt = (
        "You are Altair, Brian's Sr. VP agent. Write your twice-daily check-in "
        "to Spencer (senior advisor) for the %s slot, based on the context "
        "below about your current work.\n\n"
        "Reply in EXACTLY this format:\n"
        "URGENCY: routine|important|critical\n"
        "SUBJECT: one-line summary\n"
        "BODY:\n"
        "1) Working on: ...\n"
        "2) Blockers: ...\n"
        "3) Brian should know: ...\n\n"
        "Keep it terse. WEIGHT FRESH SIGNALS: the goal queue, today's A2A messages, "
        "and recent notes describe NOW. Long-term memory is background only - "
        "never report it as current news. If fresh signals show no active "
        "blockers, say 'no active blockers' and mark the check-in routine. "
        "URGENCY is about whether BRIAN needs to act, not how dramatic the work "
        "sounds. 'routine': work in progress, nothing needed from Brian "
        "(this is the default - investigating issues counts as routine). "
        "'important': you are blocked and need Brian to decide, approve, or "
        "provide something. 'critical': Brian must act TODAY.\n\n"
        "Context:\n%s" % (slot, context))
    failures = []
    for tier in TIERS:
        try:
            text = _call_completions(tier["url"], tier["model"], prompt,
                                     tier["max_tokens"], tier["timeout"])
            trailer = ("\n\n[Composed via %s — %s.]" % (tier["label"], failures[-1])
                       if tier["name"] != "morpheus" else "")
            return text + trailer, tier["name"]
        except Exception as e:
            failures.append("%s unreachable (%s: %s)"
                            % (tier["label"], type(e).__name__, _safe_err(e)))
    # Tier 3: V4 Pro cloud — only when the rental is live. Never burn
    # rental credits on a dead-rental guess; the probe is a free call.
    key = _read_v4pro_key()
    if key and _v4pro_balance_ok(key):
        try:
            text = _call_completions(
                V4PRO_URL, V4PRO_MODEL, prompt, 400, 180,
                headers={"Authorization": "Bearer " + key})
            return (text + "\n\n[Composed via DeepSeek V4 Pro — %s.]"
                    % "; ".join(failures)), "v4pro"
        except Exception as e:
            failures.append("DeepSeek V4 Pro failed (%s: %s)"
                            % (type(e).__name__, _safe_err(e)))
    else:
        failures.append("DeepSeek V4 Pro skipped (rental not live or no key)")
    return None, "; ".join(failures)


def parse(text):
    urgency, subject, body = "routine", "Check-in", text
    lines = text.splitlines()
    bstart = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.upper().startswith("URGENCY:"):
            u = s.split(":", 1)[1].strip().lower()
            if u in ("routine", "important", "critical"):
                urgency = u
        elif s.upper().startswith("SUBJECT:"):
            subject = s.split(":", 1)[1].strip()[:120] or subject
        elif s.upper() == "BODY:":
            bstart = i + 1
    if bstart:
        body = "\n".join(lines[bstart:]).strip() or body
    return urgency, subject, body


def insert(urgency, subject, body):
    try:
        import psycopg2
        dsn = "host=%s dbname=%s user=%s password=%s" % (
            PG["host"], PG["dbname"], PG["user"], PG["password"])
        conn = psycopg2.connect(dsn, connect_timeout=10)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency)"
            " VALUES ('altair','spencer',%s,%s,%s) RETURNING id",
            (subject, body, urgency))
        row_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return row_id
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    q = ("INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
         "VALUES ('altair','spencer',$$%s$$,$$%s$$,'%s') RETURNING id;"
         % (subject.replace("$$", ""), body.replace("$$", ""), urgency))
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-c", q],
                       capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:300])
    return r.stdout.strip().split()[0]


def _stems(text):
    """Significant word stems for topic comparison."""
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


def dedup_escalation(urgency, subject, body):
    """Don't re-page for the same in-progress issue: if this check-in is
    about the same topic as the last escalated one, step urgency down one
    level (critical->important->routine)."""
    try:
        st = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    except Exception:
        st = {}
    downgraded = False
    if urgency in ("important", "critical") and st.get("urgency") in ("important", "critical"):
        prev = _stems(st.get("subject", "") + " " + st.get("body_head", ""))
        cur = _stems(subject + " " + body[:400])
        if len(prev & cur) >= 3:
            urgency = "important" if urgency == "critical" else "routine"
            subject = "[continuing] " + subject
            downgraded = True
    try:
        json.dump({"subject": subject, "urgency": urgency,
                   "body_head": body[:400],
                   "date": datetime.now().strftime("%Y-%m-%d")},
                  open(STATE_FILE, "w"))
    except Exception:
        pass
    return urgency, subject, downgraded


def main():
    hour = datetime.now().hour
    slot = "morning" if hour < 12 else "afternoon"
    context = gather_context()
    if not context:
        print("ERROR: no context gathered", file=sys.stderr)
        sys.exit(1)
    text, detail = compose(context, slot)
    if text is None:
        # Every tier unreachable: say so explicitly in the stream instead of
        # going silent. Routine urgency — this is Spencer's problem to fix,
        # not Brian's; the honest row beats a silent gap.
        subject = "[checkin] composer unreachable on all tiers"
        body = ("The check-in composer could not reach any model tier:\n- "
                + "\n- ".join(detail.split("; "))
                + "\n\nContext was gathered normally; only composition failed.")
        row_id = insert("routine", subject, body)
        print("composer down, self-report row id: %s" % row_id)
        return
    urgency, subject, body = parse(text)
    urgency, subject, _ = dedup_escalation(urgency, subject, body)
    row_id = insert(urgency, subject, body)
    print("checkin row id: %s (tier=%s)" % (row_id, detail))


if __name__ == "__main__":
    main()
