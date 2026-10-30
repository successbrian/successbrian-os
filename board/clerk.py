#!/usr/bin/env python3
"""clerk.py — THE CLERK: a smart script with a job menu and functions.

Brian, 2026-10-24: "we are building out the concept of having a full
time 'clerk' role with some defined jobs for the ecosystem. it's not
an agent, it's a worker or a worker/harness... it just needs to be a
smart script with a job menu and functions."

THE RULE THIS FILE ENCODES: if a job is not on the menu, the clerk
does not do it. Adding work to the clerk means adding a menu entry
and a function — an auditable code change, never a prompt, a persona,
or discretion. Models appear only inside individual functions, as
bounded calls with parsed outputs (the architecture law).

JOB MENU (each entry maps to one function below):
  sweep    Look at the Intel Bridge (the scatter) and sort what's
           new three ways: board packets (Workflow #1), Workflow
           #3 intel filings to their knowledge homes, and kick-
           asides to Altair (Workflow #2). [hourly cron; was
           scatter_clerk.py]
  file     File specific capture ids through Workflow #3 by hand
           (backfill / retry). Usage: clerk.py file <id> [id...]
  status   Watermark, packets filed today, queue depth. Read-only.
  jobs     Print this menu.
  deepen   After a first read: merge each packet's questions,
           answer what the house holds (decided before?
           standing rules?), stamp due dates, flag duplicates,
           and file the rest as outside requests.
  factcheck Verify a deepened packet's claims against their
           house sources before the guidance read; claims that
           don't match are flagged, never dropped.
  blogqa   Watched blog QA signals (checks 336/338/339/340): when
           one is failing or stale, file a Workflow #2 kick-aside
           for Altair naming the check + its status. Detect only
           — the clerk never fixes. Also runs inside sweep.

Usage: clerk.py <job> [args]
"""
import sys
from datetime import date

import scatter_clerk  # the sweep's implementation lives there


CHECKIN_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.clerk_checkins (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    tasks_created INT NOT NULL DEFAULT 0,
    queue_depth INT NOT NULL DEFAULT 0,
    captures_in INT NOT NULL DEFAULT 0,
    board_filed INT NOT NULL DEFAULT 0,
    sent_altair INT NOT NULL DEFAULT 0,
    bounced INT NOT NULL DEFAULT 0,
    filed_kept INT NOT NULL DEFAULT 0,
    rechecks_sent INT NOT NULL DEFAULT 0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
# Brian, 2026-10-24: 'more table, less text. query-able.' The flow
# numbers live in COLUMNS Lyra and January can aggregate with SQL —
# never baked into the prose line, never trapped in a blob.
CHECKIN_ALTERS = [
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS metrics JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS captures_in INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS board_filed INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS sent_altair INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS bounced INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS filed_kept INT NOT NULL DEFAULT 0",
    "ALTER TABLE successbrian_os.clerk_checkins "
    "ADD COLUMN IF NOT EXISTS rechecks_sent INT NOT NULL DEFAULT 0",
]


def write_checkin(tasks_created, metrics):
    """The hourly report to Lyra: one line, with the flow's numbers.

    Brian, 2026-10-24: 'maybe it puts one line hourly in a table
    somewhere to tell Lyra it's still ok. hi lyra, clerk checking in.
    created 14 tasks this hour, see ya next hour...' — extended the
    same morning: 'hourly numbers to measure the flow — as part of
    the hourly report to lyra.' The line is both the pattern's
    liveness signal (if it stops appearing, the ladder knows the
    pattern is broken — silence = death, never health) and the
    flow's hourly instrument reading. The metrics JSONB grows as
    the pattern gains phases (Sonic/Gemma timings, bounce counts);
    the message stays one human line.
    """
    import json as _json

    con = scatter_clerk.pm_core.conn()
    cur = con.cursor()
    cur.execute(CHECKIN_DDL)
    for alter in CHECKIN_ALTERS:
        cur.execute(alter)
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status = 'queued' AND node_key LIKE 'task:ssb-packet-%%'"
    )
    queue_depth = cur.fetchone()[0]
    metrics = dict(metrics or {})
    metrics["queue_depth"] = queue_depth
    # More table, less text: the line is just the pulse now; every
    # number is a column.
    message = "hi lyra, clerk checking in. see ya next hour"
    cur.execute(
        "INSERT INTO successbrian_os.clerk_checkins "
        "(source, message, tasks_created, queue_depth, captures_in, "
        "board_filed, sent_altair, bounced, filed_kept, "
        "rechecks_sent, metrics) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("clerk", message, tasks_created, queue_depth,
         int(metrics.get("captures_in", 0)), int(metrics.get("board_filed", 0)),
         int(metrics.get("sent_altair", 0)), int(metrics.get("bounced", 0)),
         int(metrics.get("filed_kept", 0)),
         int(metrics.get("rechecks_sent", 0)),
         _json.dumps(metrics)),
    )
    con.commit()
    con.close()
    print(f"hourly report written: tasks={tasks_created} "
          f"captures_in={metrics.get('captures_in', 0)} "
          f"board_filed={metrics.get('board_filed', 0)} "
          f"sent_altair={metrics.get('sent_altair', 0)} "
          f"bounced={metrics.get('bounced', 0)} "
          f"filed_kept={metrics.get('filed_kept', 0)} "
          f"rechecks_sent={metrics.get('rechecks_sent', 0)} "
          f"queue={queue_depth}")


# ---------------------------------------------------------------------
# BLOG QA WATCH (WS3, Brian's upgrade order 2026-10-29 21:38 CDT).
# The blog QA checks that went on record tonight — 336
# blog-todo-coverage, 338 blog-pipeline-completeness, 339
# blog-launch-issue-coverage, 340 blog-launch-state-derivation —
# are watched signals in the clerk's hourly WF1 check (job_sweep).
# A check is a problem when its last_status is not 'pass', or it is
# STALE: no run within twice its own interval. Detect -> WF2
# kick-aside (an Atlas task for Altair naming the check + status).
# The clerk NEVER fixes a failing check.
BLOG_QA_WATCH = (336, 338, 339, 340)


def _blog_qa_problems():
    """[(check_id, check_key, status_text)] for watched checks
    that are failing or stale; [] when all are passing fresh.
    None when the house DB is unavailable (reported, not read as
    'all fine')."""
    rows = _pg_rows(
        "SELECT id, check_key, last_status, last_run_at, interval_s "
        "FROM successbrian_os.pm_project_checks WHERE id = ANY(%s) "
        "ORDER BY id", (list(BLOG_QA_WATCH),))
    if rows is None:
        return None
    problems, seen = [], set()
    for cid, key, status, last_run, interval_s in rows:
        seen.add(cid)
        stale = last_run is None or (
            (datetime.now(last_run.tzinfo) - last_run).total_seconds()
            > 2 * (interval_s or 86400))
        if status != "pass" or stale:
            problems.append((cid, key,
                             f"last_status={status}; "
                             f"last_run_at={last_run}; "
                             f"interval_s={interval_s}; "
                             f"stale={'yes' if stale else 'no'}"))
    for cid in BLOG_QA_WATCH:
        if cid not in seen:
            problems.append((cid, "(missing)",
                             "watched check row not found in "
                             "successbrian_os.pm_project_checks"))
    return problems


def job_blogqa(args=None):
    """Watched blog QA signals: file a WF2 kick-aside for each failing/stale blog check (336/338/339/340). Detect only, never fix."""
    import subprocess as _sp
    problems = _blog_qa_problems()
    if problems is None:
        print("blogqa: house DB unavailable — watched blog QA "
              "checks could not be read (not read as all-fine)")
        return []
    if not problems:
        print("blogqa: watched blog QA checks 336/338/339/340 all "
              "passing and fresh — no kick-aside filed")
        return []
    filed = []
    for cid, key, status_text in problems:
        task_key = (f"task:clerk-blogqa-{cid}-"
                    f"{date.today().isoformat()}")
        existing = _pg_rows(
            "SELECT node_key FROM atlas.nodes WHERE node_key = %s "
            "AND status = 'queued'", (task_key,))
        if existing:
            print(f"blogqa: check {cid} ({key}) already kicked "
                  f"aside today as {task_key} — not duplicated")
            continue
        details = {
            "question": (
                f"WORKFLOW #2 KICK-ASIDE from the clerk's hourly "
                f"blog QA watch: blog QA check {cid} ({key}) is "
                f"failing or stale. STATUS: {status_text}. "
                f"Source: successbrian_os.pm_project_checks + "
                f"pm_project_qa_runs, read by clerk.py job_blogqa "
                f"on {datetime.now().astimezone().isoformat(timespec='seconds')}. "
                f"Altair: look at why this check is in that state "
                f"and restore it through the owning machinery. "
                f"The clerk detected this only — it does not fix "
                f"checks."),
            "theme": "wf2-blog-qa-watch",
            "found_by": "clerk-blogqa-watch",
            "check_id": cid, "check_key": key,
        }
        if args and "--dry-run" in args:
            print(f"[dry-run] would kick check {cid} ({key}) -> "
                  f"{task_key} ({status_text})")
            filed.append(task_key)
            continue
        r = _sp.run(
            ["python3", scatter_clerk.ATLAS_PY, "add-node", task_key,
             "atlas_task",
             (f"Blog QA check {cid} ({key}) failing/stale — "
              f"clerk watch kick-aside")[:180],
             "--status", "queued", "--details", json.dumps(details)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"blogqa: kick-aside for check {cid} failed: "
                  f"{r.stderr[:300]}")
            continue
        filed.append(task_key)
        print(f"blogqa: check {cid} ({key}) {status_text} -> "
              f"WF2 kick-aside {task_key}")
    return filed


def job_sweep(_args=None):
    """The hourly look at the Intel Bridge: sort everything new."""
    state = scatter_clerk.load_state()
    before = state.get("last_capture_id", 0)
    keys, wf3_results, rechecks = scatter_clerk.run()
    after = scatter_clerk.load_state().get("last_capture_id", before)
    captures_in = 0
    if keys or wf3_results:
        con = scatter_clerk.pm_core.conn()
        cur = con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM atlas.scattered_captures "
            "WHERE id > %s AND id <= %s", (before, after))
        captures_in = cur.fetchone()[0]
        con.close()
    kept = [r for r in wf3_results if r["outcome"] == "kept"]
    kicked = [r for r in wf3_results if r["outcome"] == "kicked"]
    # Watched blog QA signals (WS3): failing/stale blog checks
    # 336/338/339/340 kick aside to WF2 from this hourly check.
    blogqa_kicks = job_blogqa()
    metrics = {
        "captures_in": captures_in,
        "board_filed": len(keys),
        "sent_altair": len(kicked) + len(blogqa_kicks),
        "bounced": 0,
        "filed_kept": len(kept),
        "rechecks_sent": len(rechecks),
        "blog_qa_kickasides": len(blogqa_kicks),
    }
    write_checkin(len(keys) + len(kicked) + len(rechecks)
                  + len(blogqa_kicks), metrics)


def job_file(args=None):
    """File capture ids through Workflow #3 (backfill / retry)."""
    ids = []
    for a in (args or []):
        try:
            ids.append(int(a))
        except ValueError:
            print(f"file: '{a}' is not a capture id")
    if not ids:
        print("usage: clerk.py file <capture-id> [capture-id...]")
        return
    done = []
    for cid in ids:
        cap = scatter_clerk.fetch_capture(cid)
        if cap is None:
            print(f"file: capture #{cid} not found")
            continue
        if cap["status"] != "raw":
            print(f"file: capture #{cid} is '{cap['status']}', "
                  f"not raw — skipping (already dispositioned)")
            continue
        res = scatter_clerk.file_wf3(cap)
        done.append(res)
        print(f"wf3 {res['outcome']} capture #{res['id']} -> "
              f"{res['workspace'] or 'wf2'} ({res['detail']})")
    if done:
        con = scatter_clerk.pm_core.conn()
        cur = con.cursor()
        scatter_clerk.pm_core.decide(
            cur, "scatter-clerk",
            "Workflow #3 manual filing: "
            + "; ".join(f"#{r['id']} {r['outcome']} -> "
                        f"{r['workspace'] or 'wf2'}" for r in done),
            origin="system")
        con.commit()
        con.close()


def job_status(_args=None):
    """Watermark, packets filed today, board queue depth. Read-only."""
    wm = scatter_clerk.load_state().get("last_capture_id", 0)
    con = scatter_clerk.pm_core.conn()
    cur = con.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM atlas.scattered_captures WHERE status='raw' AND id > %s",
        (wm,),
    )
    unswept = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_key LIKE 'task:ssb-packet-%%' "
        "AND created_at::date = %s",
        (date.today(),),
    )
    packets_today = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM atlas.nodes WHERE node_type='atlas_task' "
        "AND status = 'queued' AND node_key LIKE 'task:ssb-packet-%%'"
    )
    packets_queued = cur.fetchone()[0]
    con.close()
    print(f"clerk status: watermark capture #{wm}; unswept raw captures: {unswept}; "
          f"packets filed today: {packets_today}; packets queued for the board: {packets_queued}")


# ---------------------------------------------------------------------
# STAGE TWO — deepen + factcheck (Brian, 2026-10-25). The flow's middle
# stages: after the board's first read (questions only), the clerk
# deepens each packet from the house record, then fact-checks the
# packet before the guidance read. Retrieval, merging, filing, and
# shape-checking only — the clerk never judges, never calls a model.
# Inside the house the clerk reads directly (the minutes-dir ledgers,
# PostgreSQL); outside needs leave as filed requests.
import json
import os
import re
from datetime import datetime, timedelta

MINUTES_DIR = os.environ.get(
    "CLERK_MINUTES_DIR",
    os.path.expanduser("~/workspace/altair-brain/inbox"))
RULE_FILES = [p for p in os.environ.get("CLERK_RULE_FILES", "").split(":")
              if p] or [
    os.path.expanduser("~/successbrian-os/board/CHARTER.md"),
    os.path.expanduser(
        "~/successbrian-os/board/docs/board-serious-flow-2026-10-23.md"),
]

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "for", "on", "and", "or", "is",
    "are", "was", "were", "be", "been", "this", "that", "these", "those",
    "with", "from", "into", "over", "after", "before", "about", "should",
    "would", "could", "what", "when", "which", "there", "their", "they",
    "them", "then", "than", "have", "has", "had", "not", "but", "all",
    "any", "per", "via", "inbox",
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _read_jsonl(path):
    """All rows of a jsonl file; a missing file is an empty list."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return rows


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _stage_files(prefix):
    """Minutes-dir files named <prefix><tag>.jsonl, oldest first."""
    try:
        names = [n for n in os.listdir(MINUTES_DIR)
                 if n.startswith(prefix) and n.endswith(".jsonl")]
    except FileNotFoundError:
        return []
    return [os.path.join(MINUTES_DIR, n) for n in sorted(names)]


def _tag_of(path, prefix):
    name = os.path.basename(path)
    return name[len(prefix):-len(".jsonl")]


def _norm(text):
    """Lowercase, punctuation to spaces, whitespace collapsed."""
    return re.sub(r"\s+", " ",
                  re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def _terms(text):
    """Salient terms: normalized words of 4+ chars, no stopwords/digits."""
    out = set()
    for w in _norm(text).split():
        if len(w) >= 4 and w not in _STOPWORDS and not any(
                c.isdigit() for c in w):
            out.add(w)
    return out


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _pg_rows(sql, params=()):
    """House lookup in PostgreSQL; None means the lookup was unavailable
    ( reported, never silently read as 'nothing found')."""
    try:
        con = scatter_clerk.pm_core.conn()
        cur = con.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        con.close()
        return rows
    except Exception as exc:  # DB down must not kill the stage
        print(f"  (house lookup unavailable: {exc})")
        return None


def _load_rulings():
    rows = []
    for path in _stage_files("board-rulings-"):
        rows.extend(_read_jsonl(path))
    return rows


def _prior_decisions(item_key, title, rulings):
    """ALWAYS-ASK (a): has this been decided before? The rulings ledger
    (same item_key, plus near-title matches) and atlas.board_suggestions."""
    found, my_terms = [], _terms(title)
    for row in rulings:
        if row.get("event") != "ruled":
            continue
        entry = {
            "source": "rulings-ledger",
            "item_key": row.get("item_key"),
            "seat": row.get("seat"),
            "call": row.get("call"),
            "confidence": row.get("confidence"),
            "verdict": row.get("verdict"),
            "session_tag": row.get("session_tag"),
        }
        if row.get("item_key") == item_key:
            entry["match"] = "item_key"
            found.append(entry)
        elif _norm(row.get("title")) == _norm(title) or _jaccard(
                my_terms, _terms(row.get("title"))) >= 0.6:
            entry["match"] = "title"
            found.append(entry)
    rows = _pg_rows(
        "SELECT item_key, seat, suggestion, gate_score, session_ref "
        "FROM atlas.board_suggestions WHERE item_key = %s", (item_key,))
    if rows:
        for r in rows:
            found.append({
                "source": "board_suggestions",
                "item_key": r[0], "seat": r[1], "call": r[2],
                "confidence": r[3], "session_ref": r[4],
                "match": "item_key",
            })
    return found


def _standing_rules(title):
    """ALWAYS-ASK (b): what standing rules touch this? Keyword search
    of the charter and the serious-flow doc by the title's terms."""
    terms = _terms(title)
    hits = []
    for path in RULE_FILES:
        try:
            with open(path) as f:
                lines = f.readlines()
        except FileNotFoundError:
            continue
        for i, line in enumerate(lines, 1):
            text = line.strip()
            if len(text) < 12:
                continue
            if terms & _terms(text):
                hits.append({"file": os.path.basename(path),
                             "line_no": i, "excerpt": text[:240]})
            if len(hits) >= 10:
                return hits
    return hits


def _date_mentions(text, today=None):
    """Every date/deadline phrase in text, deterministically parsed:
    ISO dates, month-name dates, 'by <weekday>', a bare 'deadline'."""
    today = today or date.today()
    out = []
    low = (text or "").lower()
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", low):
        out.append({"phrase": m.group(0),
                    "date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}"})
    for m in re.finditer(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
            r"[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?\b",
            low):
        month = _MONTHS[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            found = date(year, month, day)
        except ValueError:
            continue
        if not m.group(3) and found < today:
            found = date(year + 1, month, day)
        out.append({"phrase": m.group(0), "date": found.isoformat()})
    for m in re.finditer(
            r"\bby (monday|tuesday|wednesday|thursday|friday|saturday|"
            r"sunday)\b", low):
        ahead = (_WEEKDAYS[m.group(1)] - today.weekday()) % 7 or 7
        out.append({"phrase": m.group(0),
                    "date": (today + timedelta(days=ahead)).isoformat()})
    if not out and re.search(r"\bdeadline\b", low):
        out.append({"phrase": "deadline", "date": None})
    return out


_BLOG_Q_WORDS = ("state", "next step", "blocker", "checklist",
                 "launch", "pp01", "pp02", "pp03", "pp04", "pp05",
                 "pp06", "pp07", "pp08", "pp09", "pp10", "pp11",
                 "pp12", "open item", "open issue")


def _blog_context_for_item(item):
    """Blog context for a deepen item, or None. A packet question
    about a named blog's structure (its state, next step, open
    blockers, checklist presence) is answered from the house:
    blog_launch.py's derivation over campaignsdesk.blogs /
    blog_checklist + Atlas issue tasks, via scatter_clerk —
    stamped with its source and check time in the packet."""
    try:
        probe = {"title": item.get("title") or "",
                 "context": "",
                 "raw": " ".join(item.get("merged", {}).values())}
        return scatter_clerk.match_blog(probe)
    except Exception as exc:
        print(f"  (blog lookup unavailable: {exc})")
        return None


def job_deepen(args=None):
    """Deepen each first-read packet from the house record (merge asks, answer what's held, file the rest)."""
    args = args or []
    qfiles = _stage_files("board-questions-")
    if args:
        tag = args[0]
        qpath = os.path.join(MINUTES_DIR, f"board-questions-{tag}.jsonl")
        if not os.path.exists(qpath):
            print(f"deepen: no questions file for tag '{tag}'")
            return
    elif qfiles:
        qpath = qfiles[-1]
        tag = _tag_of(qpath, "board-questions-")
    else:
        print("deepen: no board-questions-*.jsonl in the minutes dir yet "
              "— nothing to deepen")
        return
    qrows = _read_jsonl(qpath)

    # DEDUPE (Brian, 2026-10-25): the same packet already in flow in an
    # earlier session gets flagged here — never silently dropped.
    earlier = {}
    for path in qfiles:
        etag = _tag_of(path, "board-questions-")
        if etag == tag:
            continue
        for row in _read_jsonl(path):
            earlier.setdefault(row.get("item_key"),
                               {"tag": etag, "title": row.get("title")})

    rulings = _load_rulings()

    # Group this session's questions per item, merging duplicates
    # across seats (normalized dedupe, first-seen wording kept).
    items = {}
    for row in qrows:
        if row.get("event") != "questions":
            continue
        item = items.setdefault(row.get("item_key"), {
            "item_key": row.get("item_key"), "title": row.get("title") or "",
            "merged": {}, "order": [],
        })
        for q in row.get("questions") or []:
            key = _norm(q)
            if not key:
                continue
            if key not in item["merged"]:
                item["merged"][key] = q.strip()
                item["order"].append(key)

    deepened, requests = [], []
    n_house = n_out = n_dup = 0
    filed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    for item in items.values():
        priors = _prior_decisions(item["item_key"], item["title"], rulings)
        rules = _standing_rules(item["title"])

        house_answers = [{
            "question": "Has this been decided before?",
            "answer": (f"{len(priors)} prior decision(s) on record — see "
                       "prior_decisions in this packet."
                       if priors else "no prior decision on record"),
            "source": "rulings-ledger + atlas.board_suggestions",
        }, {
            "question": "What standing rules touch this?",
            "answer": (f"{len(rules)} matching rule line(s) — see "
                       "standing_rules in this packet."
                       if rules else "none found"),
            "source": "CHARTER.md + board-serious-flow-2026-10-23.md",
        }]
        # BLOG STRUCTURE (WS3): if this packet names a registered
        # blog, its state / next step / open blockers / checklist
        # presence are house facts — answered here from the
        # blog_launch derivation, source-stamped, not escalated.
        blog_ctx = _blog_context_for_item(item)
        blog_stamp = None
        if blog_ctx:
            blog_stamp = (f"{blog_ctx['source']}; checked "
                          f"{blog_ctx['checked_at']}")
            nxt = blog_ctx.get("next_step") or {}
            house_answers.append({
                "question": (f"What is the {blog_ctx['slug']} blog's "
                             f"current launch state, next step, and "
                             f"open blockers?"),
                "answer": (
                    f"state {blog_ctx.get('state')}; tier "
                    f"{blog_ctx['tier']}; next step "
                    f"{nxt.get('key', 'none')} — "
                    f"{nxt.get('title', 'none')}; open blockers "
                    f"{blog_ctx['open_issue_count']}"
                    + (f" ({', '.join(blog_ctx['blockers'])})"
                       if blog_ctx["blockers"] else "")
                    + f"; checklist items present: "
                      f"{', '.join(blog_ctx['checklist_present']) or 'none recorded'}"
                    + f"; checklist items open: "
                      f"{', '.join(blog_ctx['checklist_open']) or 'none'}"),
                "source": blog_stamp,
            })
        house_text = " ".join(
            [p.get("call") or "" for p in priors]
            + [p.get("title") or "" for p in priors]
            + [r["excerpt"] for r in rules])
        house_terms = _terms(house_text)

        merged_questions, outside = [], []
        for key in item["order"]:
            q = item["merged"][key]
            merged_questions.append(q)
            nq = _norm(q)
            if "decided before" in nq or "standing rule" in nq:
                continue  # the always-ask pair, answered above
            if blog_ctx and any(w in nq for w in _BLOG_Q_WORDS):
                house_answers.append({
                    "question": q,
                    "answer": (
                        f"Answered from blog structure for "
                        f"{blog_ctx['slug']}: state "
                        f"{blog_ctx.get('state')}; next step "
                        f"{(blog_ctx.get('next_step') or {}).get('key', 'none')}; "
                        f"open blockers "
                        f"{blog_ctx['open_issue_count']}; checklist "
                        f"presence in blog_context in this packet."),
                    "source": blog_stamp,
                })
                n_house += 1
            elif len(_terms(q) & house_terms) >= 2:
                house_answers.append({
                    "question": q,
                    "answer": "Answered from the house record — see "
                              "prior_decisions / standing_rules in "
                              "this packet.",
                    "source": "rulings-ledger / rule docs",
                })
                n_house += 1
            else:
                outside.append(q)
                requests.append({
                    "item_key": item["item_key"], "question": q,
                    "session_tag": tag, "filed_at": filed_at,
                })
                n_out += 1

        dup_of = None
        prev = earlier.get(item["item_key"])
        if prev:
            dup_of = prev["tag"]
        else:
            my_terms = _terms(item["title"])
            for ekey, einfo in earlier.items():
                if _norm(einfo["title"]) == _norm(item["title"]) or \
                        _jaccard(my_terms, _terms(einfo["title"])) >= 0.75:
                    dup_of = einfo["tag"]
                    break
        if dup_of:
            n_dup += 1

        mentions = _date_mentions(item["title"] + " " +
                                  " ".join(merged_questions))
        deepened.append({
            "item_key": item["item_key"],
            "title": item["title"],
            "due_hint": mentions[0] if mentions else None,
            "duplicate_of": dup_of,
            "prior_decisions": priors,
            "standing_rules": rules,
            "blog_context": blog_ctx,
            "merged_questions": merged_questions,
            "house_answers": house_answers,
            "outside_requests": [{"question": q} for q in outside],
        })

    dpath = os.path.join(MINUTES_DIR, f"board-deepened-{tag}.jsonl")
    rpath = os.path.join(MINUTES_DIR, f"board-requests-{tag}.jsonl")
    _write_jsonl(dpath, deepened)
    _write_jsonl(rpath, requests)
    total_q = sum(len(d["merged_questions"]) for d in deepened)
    print(f"deepen {tag}: {len(deepened)} item(s); {total_q} question(s) "
          f"merged from {len(qrows)} first-read row(s); "
          f"{n_house + 2 * len(deepened)} answered from the house; "
          f"{n_out} outside request(s) filed to "
          f"{os.path.basename(rpath)}; {n_dup} duplicate(s) flagged; "
          f"deepened packets in {os.path.basename(dpath)}")


def job_factcheck(args=None):
    """Verify a deepened packet's claims against their house sources (fidelity: flag what doesn't match, never drop)."""
    args = args or []
    dfiles = _stage_files("board-deepened-")
    if args:
        tag = args[0]
        dpath = os.path.join(MINUTES_DIR, f"board-deepened-{tag}.jsonl")
        if not os.path.exists(dpath):
            print(f"factcheck: no deepened file for tag '{tag}'")
            return
    elif dfiles:
        dpath = dfiles[-1]
        tag = _tag_of(dpath, "board-deepened-")
    else:
        print("factcheck: no board-deepened-*.jsonl in the minutes dir "
              "yet — run deepen first")
        return
    rows = _read_jsonl(dpath)
    rulings = _load_rulings()
    ruled = [r for r in rulings if r.get("event") == "ruled"]

    price_rows = _pg_rows(
        "SELECT item, amount, currency, checked_on, valid_until "
        "FROM successbrian_os.price_intel") or []
    price_dates = {str(r[3]) for r in price_rows} | \
        {str(r[4]) for r in price_rows if r[4]}

    rule_lines = {}
    for path in RULE_FILES:
        try:
            with open(path) as f:
                rule_lines[os.path.basename(path)] = f.readlines()
        except FileNotFoundError:
            pass

    out = []
    tv = tf = tc = 0
    for row in rows:
        verified, flagged, conflicts = [], [], []

        # (a) prior-decision claims must exist in their source, exact.
        for p in row.get("prior_decisions") or []:
            claim = (f"prior decision by {p.get('seat')}: "
                     f"{(p.get('call') or '')[:80]}")
            if p.get("source") == "rulings-ledger":
                match = [r for r in ruled
                         if r.get("item_key") == p.get("item_key")
                         and r.get("seat") == p.get("seat")]
                if not match:
                    flagged.append({
                        "claim": claim,
                        "reason": "not found in the rulings ledger"})
                elif any(r.get("call") == p.get("call") for r in match):
                    verified.append({"claim": claim,
                                     "source": "rulings-ledger"})
                else:
                    conflicts.append({
                        "claim": claim, "source": "rulings-ledger",
                        "packet_says": p.get("call"),
                        "source_says": match[0].get("call")})
            elif p.get("source") == "board_suggestions":
                srows = _pg_rows(
                    "SELECT suggestion FROM atlas.board_suggestions "
                    "WHERE item_key = %s AND seat = %s",
                    (p.get("item_key"), p.get("seat")))
                if srows is None:
                    flagged.append({
                        "claim": claim,
                        "reason": "house DB unavailable — could not "
                                  "re-verify"})
                elif not srows:
                    flagged.append({
                        "claim": claim,
                        "reason": "not found in atlas.board_suggestions"})
                elif any(r[0] == p.get("call") for r in srows):
                    verified.append({"claim": claim,
                                     "source": "board_suggestions"})
                else:
                    conflicts.append({
                        "claim": claim, "source": "board_suggestions",
                        "packet_says": p.get("call"),
                        "source_says": srows[0][0]})

        # (a2) standing-rule excerpts must match their file line, exact.
        for r in row.get("standing_rules") or []:
            lines = rule_lines.get(r.get("file"))
            claim = f"rule excerpt: {r.get('excerpt', '')[:80]}"
            if lines is None or not (1 <= (r.get("line_no") or 0)
                                     <= len(lines)):
                flagged.append({
                    "claim": claim,
                    "reason": "rule source/line not found for re-check"})
            elif lines[r["line_no"] - 1].strip().startswith(
                    r.get("excerpt", "")):
                verified.append({"claim": claim, "source": r.get("file")})
            else:
                conflicts.append({
                    "claim": claim, "source": r.get("file"),
                    "packet_says": r.get("excerpt"),
                    "source_says": lines[r["line_no"] - 1].strip()[:240]})

        # (b) numbers/dates in the packet text vs price_intel.
        text = (row.get("title") or "") + " " + " ".join(
            row.get("merged_questions") or [])
        amounts = set()
        for m in re.finditer(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)", text):
            amounts.add(m.group(1))
        for m in re.finditer(r"\b(\d+\.\d{2})\b", text):
            amounts.add(m.group(1))
        for a in sorted(amounts):
            try:
                val = float(a.replace(",", ""))
            except ValueError:
                continue
            hit = [r for r in price_rows
                   if r[1] is not None and abs(float(r[1]) - val) < 0.005]
            if hit:
                verified.append({
                    "claim": f"price ${a}", "source": "price_intel",
                    "detail": f"{hit[0][0]}: {hit[0][1]} {hit[0][2]} "
                              f"checked {hit[0][3]}, valid until "
                              f"{hit[0][4]}"})
            else:
                flagged.append({
                    "claim": f"price ${a}",
                    "reason": "no matching successbrian_os.price_intel "
                              "record — unverified"})
        due = (row.get("due_hint") or {}).get("date")
        for mention in _date_mentions(text):
            d = mention["date"]
            if not d:
                continue
            if d in price_dates:
                verified.append({
                    "claim": f"date {mention['phrase']}",
                    "source": "price_intel",
                    "detail": f"matches a price check/valid date ({d})"})
            elif due and d == due:
                verified.append({
                    "claim": f"date {mention['phrase']}",
                    "source": "packet due stamp"})
            else:
                flagged.append({
                    "claim": f"date {mention['phrase']}",
                    "reason": "no house source carries this date — "
                              "unverified"})

        out.append({"item_key": row.get("item_key"), "verified": verified,
                    "flagged": flagged, "source_conflicts": conflicts})
        tv += len(verified)
        tf += len(flagged)
        tc += len(conflicts)

    fpath = os.path.join(MINUTES_DIR, f"board-factcheck-{tag}.jsonl")
    _write_jsonl(fpath, out)
    print(f"factcheck {tag}: {len(out)} item(s); {tv} claim(s) verified; "
          f"{tf} flagged (kept in the packet, marked unverified); "
          f"{tc} source conflict(s); results in "
          f"{os.path.basename(fpath)}")



def job_reconcile(args=None):
    """Reconcile the three knowledge stores against the master index:
    ticket first for every mismatch, verify in-house, fix only what
    an SOP covers (board/kindex.py); held fixes packet to the board."""
    import kindex
    kindex.reconcile(dry_run=bool(args and "--dry-run" in args))


def job_integrity(args=None):
    """Standing integrity checks on the knowledge plumbing:
    AnythingLLM files present, second-brain sink landing, ID
    carriers where the index says (board/kindex.py)."""
    import kindex
    kindex.integrity(dry_run=bool(args and "--dry-run" in args))


def job_jobs(_args=None):
    """Print this menu."""
    print("THE CLERK — job menu (if it's not on the menu, the clerk doesn't do it):")
    for name, fn in sorted(JOBS.items()):
        lines = (fn.__doc__ or "").strip().splitlines()
        print(f"  {name:8s} {lines[0] if lines else ''}")


JOBS = {
    "sweep": job_sweep,
    "file": job_file,
    "status": job_status,
    "jobs": job_jobs,
    "deepen": job_deepen,
    "factcheck": job_factcheck,
    "reconcile": job_reconcile,
    "integrity": job_integrity,
    "blogqa": job_blogqa,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        job_jobs()
        sys.exit(0 if len(sys.argv) == 2 and sys.argv[1] == "jobs" else 2)
    JOBS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
