#!/usr/bin/env python3
"""Jive — the successbrian-os conversation synthesis worker.

Reads the conversation ledger (what the entrepreneur's agents talked about
and did) and produces a running "state of everything": a summary, duplicate
detection (same request seen across different sessions), and related-item
links (keyword overlap across sessions). Fully deterministic — no model, no
cloud, no per-token cost.

WHY:
    An entrepreneur running several agents loses track of what's been asked,
    answered, and done — the same request gets repeated in different
    sessions and related work never gets connected. Jive is the ledger's
    reader: it turns raw conversation captures into a summary an
    entrepreneur (or a digest cron) can skim, and it flags duplicates and
    relations as data, never as decisions. It proposes; the entrepreneur
    decides. (Brian 2026-10-02: jive is officially part of
    successbrian-os, and it runs only when there is new input to process.)

CALLED BY:
    - Cron `jive-synthesis` (every 30 min on k11-alpha) runs
      `python3 tools/jive/jive.py run`. The watermark guard makes idle runs
      a single cheap query that exits silently — jive does real work only
      when new captures or completed tasks exist.
    - Agents call `tools/jive/capture.py` (or import it) to write
      conversation captures; jive reads them.
    - Humans: `jive.py status` shows the watermark and pending input.

NOTES:
    - CANONICAL: successbrian-os/tools/jive/ (moved 2026-10-02 from the
      decommissioned KiloCode agent workspace
      /home/agents/workspace/scripts/jive.py, per the move policy:
      move -> test from new location -> quarantine the original).
    - On-demand semantics: the old worker inserted a jive_summary row on
      EVERY run, even with zero input (48 junk rows/day). This version
      tracks last_capture_id + last_run_at in successbrian_os.jive_state
      and exits without writing anything when there is nothing new.
    - Duplicate/link detection compares each NEW capture against prior
      history, so every (new, prior) pair is evaluated exactly once —
      re-runs never re-flag. Summary rows are written only when new input
      exists.
    - Bounded lookback: tasks since the last run, but never more than
      24h back — a fresh watermark must not backfill years of completed
      tasks into one summary.
    - Duplicate detection is exact-match on normalized text (lowercased,
      punctuation stripped, stopwords kept — same normalization as the
      original worker). Link detection is Jaccard >= 0.5 on token sets.
      Thresholds are constants below; tune deliberately, not casually.
    - Auth: psql CLI over the local socket as the invoking OS user, same
      as the original worker's peer-auth setup. No passwords in code.
    - Generic-entrepreneur rule: no Brian-specific data in code. Agent
      names (altair, dealsdesk, ...) appear only as data in the DB.
"""

import argparse
import csv
import datetime
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

PG = {
    "host": os.environ.get("ECOSYSTEM_DB_HOST", "localhost"),
    "dbname": os.environ.get("ECOSYSTEM_DB_NAME", "ecosystem_central"),
    "user": os.environ.get("ECOSYSTEM_DB_USER", os.environ.get("USER", "successbrian")),
}

SCHEMA = "successbrian_os"
DUP_LOOKBACK_DAYS = 90
LINK_LOOKBACK_DAYS = 30
MAX_NEW_CAPTURES = 500
LINK_THRESHOLD = 0.5

_STOPWORDS = {
    "the", "and", "for", "are", "with", "our", "how", "not", "but", "has",
    "have", "was", "were", "you", "this", "that", "they", "them", "what",
    "when", "where", "which", "your", "its", "can", "will", "just", "all",
}


# ---------------------------------------------------------------- DB helpers

def _psql_args():
    args = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
            "-v", "ON_ERROR_STOP=1", "-q"]
    return args


def _read_csv(sql):
    """Run a SELECT via COPY TO STDOUT (csv) and return list of dicts."""
    cmd = _psql_args() + ["-c", "COPY (%s) TO STDOUT WITH (FORMAT csv, HEADER)" % sql]
    env = dict(os.environ)
    if "ECOSYSTEM_DB_PASSWORD" in os.environ:
        env["PGPASSWORD"] = os.environ["ECOSYSTEM_DB_PASSWORD"]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("psql read failed: " + p.stderr.strip()[-500:])
    if not p.stdout.strip():
        return []
    return list(csv.DictReader(io.StringIO(p.stdout)))


def _write_sql(statements):
    """Run INSERT/UPDATE statements inside one transaction."""
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write("BEGIN;\n")
        for s in statements:
            f.write(s.rstrip() + ";\n")
        f.write("COMMIT;\n")
        path = f.name
    try:
        cmd = _psql_args() + ["-f", path]
        env = dict(os.environ)
        if "ECOSYSTEM_DB_PASSWORD" in os.environ:
            env["PGPASSWORD"] = os.environ["ECOSYSTEM_DB_PASSWORD"]
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if p.returncode != 0:
            raise RuntimeError("psql write failed: " + p.stderr.strip()[-500:])
    finally:
        os.unlink(path)


def _q(v):
    """Quote a Python value as a SQL literal (standard_conforming_strings=on)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


# ------------------------------------------------------- deterministic core

def _normalize(s):
    import re
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s):
    return [w for w in _normalize(s).split() if len(w) >= 3 and w not in _STOPWORDS]


def _jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ------------------------------------------------------------------ worker

def _get_state():
    rows = _read_csv(
        "SELECT key, value FROM %s.jive_state WHERE key IN "
        "('last_capture_id','last_run_at')" % SCHEMA)
    state = {r["key"]: r["value"] for r in rows}
    return (int(state.get("last_capture_id", "0") or "0"),
            state.get("last_run_at", "2000-01-01 00:00:00+00"))


def _fetch_new_captures(last_id):
    return _read_csv(
        "SELECT id, session_id, platform, source_agent, user_message, "
        "assistant_response, created_at "
        "FROM %s.conversation_captures WHERE id > %d "
        "ORDER BY id LIMIT %d" % (SCHEMA, last_id, MAX_NEW_CAPTURES))


def _fetch_new_tasks(last_run_at):
    # Bounded lookback: tasks since the last run, but never more than
    # 24h back — a fresh watermark must not backfill years of history
    # into one summary.
    return _read_csv(
        "SELECT id, assigned_to, title, completion_summary, completed_at "
        "FROM %s.tasks WHERE status='completed' "
        "AND completed_at > GREATEST(%s::timestamptz, NOW() - interval '24 hours') "
        "ORDER BY completed_at DESC" % (SCHEMA, _q(last_run_at)))


def _fetch_history(table_cols, days, exclude_ids=()):
    where = "created_at > NOW() - interval '%d days'" % days
    if exclude_ids:
        where += " AND id NOT IN (%s)" % ",".join(str(int(i)) for i in exclude_ids)
    return _read_csv(
        "SELECT %s FROM %s.conversation_captures WHERE %s ORDER BY id"
        % (table_cols, SCHEMA, where))


def _build_summary(new_convos, new_tasks, since):
    agents = {}
    for c in new_convos:
        a = c["source_agent"] or "?"
        agents[a] = agents.get(a, 0) + 1
    since_label = "full history" if since[:4] < "2020" else since
    lines = [
        "jive summary since %s: %d conversation turns across %d agents%s" % (
            since_label, len(new_convos), len(agents),
            " (%s)" % ", ".join("%s:%d" % kv for kv in sorted(agents.items()))
            if agents else ""),
        "%d tasks completed since last run" % len(new_tasks),
    ]
    for t in new_tasks[:5]:
        lines.append("  - [done] %s: %s" % (t["title"], (t["completion_summary"] or "")[:80]))
    for c in new_convos[:5]:
        um = (c["user_message"] or "").strip().replace("\n", " ")
        lines.append("  - [%s/%s] %s" % (c["source_agent"], c["platform"], um[:100]))
    return "\n".join(lines)


def run(dry_run=False):
    last_id, last_run_at = _get_state()
    new_convos = _fetch_new_captures(last_id)
    new_tasks = _fetch_new_tasks(last_run_at)

    if not new_convos and not new_tasks:
        return {"conversations": 0, "tasks": 0, "duplicates": 0,
                "links": 0, "summary": None, "skipped": True}

    new_ids = [int(c["id"]) for c in new_convos]
    statements = []
    dup_flags = 0
    links = 0

    if new_convos:
        hist = _fetch_history(
            "id, session_id, user_message", DUP_LOOKBACK_DAYS,
            exclude_ids=new_ids)
        link_hist = [h for h in _fetch_history(
            "id, session_id, user_message", LINK_LOOKBACK_DAYS,
            exclude_ids=new_ids)]
        for c in new_convos:
            norm = _normalize(c.get("user_message") or "")
            if len(norm) >= 6:
                match = None
                for h in hist:
                    if _normalize(h.get("user_message") or "") != norm:
                        continue
                    if (h.get("session_id") or "") == (c.get("session_id") or ""):
                        continue
                    match = h
                    break
                if match is not None:
                    ids = "%s,%s" % (match["id"], c["id"])
                    statements.append(
                        "INSERT INTO %s.jive_flags (flag_type, severity, message, source_ref) "
                        "VALUES ('duplicate','warn',%s,%s)" % (
                            SCHEMA,
                            _q("duplicate request across sessions: '%s'" % norm[:80]),
                            _q("conversation_captures:%s" % ids)))
                    dup_flags += 1
            toks = _tokens(c.get("user_message") or "")
            if toks:
                for h in link_hist:
                    if (h.get("session_id") or "") == (c.get("session_id") or ""):
                        continue
                    score = _jaccard(toks, _tokens(h.get("user_message") or ""))
                    if score >= LINK_THRESHOLD:
                        statements.append(
                            "INSERT INTO %s.jive_links "
                            "(source_type, source_id, target_type, target_id, relation, score) "
                            "VALUES ('conversation',%d,'conversation',%d,'related',%s)" % (
                                SCHEMA, int(c["id"]), int(h["id"]),
                                _q(round(score, 3))))
                        links += 1

    summary = _build_summary(new_convos, new_tasks, last_run_at)
    statements.append(
        "INSERT INTO %s.jive_summary (window_start, window_end, summary_text) "
        "VALUES (%s, NOW(), %s)" % (SCHEMA, _q(last_run_at), _q(summary)))

    max_id = max(new_ids) if new_ids else last_id
    statements.append(
        "UPDATE %s.jive_state SET value=%s, updated_at=NOW() "
        "WHERE key='last_capture_id'" % (SCHEMA, _q(str(max_id))))
    statements.append(
        "UPDATE %s.jive_state SET value=to_char(NOW(), "
        "'YYYY-MM-DD HH24:MI:SSOF'), updated_at=NOW() "
        "WHERE key='last_run_at'" % SCHEMA)

    if not dry_run:
        _write_sql(statements)

    return {"conversations": len(new_convos), "tasks": len(new_tasks),
            "duplicates": dup_flags, "links": links,
            "summary": summary, "skipped": False,
            "dry_run": dry_run}


def status():
    last_id, last_run_at = _get_state()
    pending = _read_csv(
        "SELECT count(*) AS n FROM %s.conversation_captures WHERE id > %d"
        % (SCHEMA, last_id))
    return {"last_capture_id": last_id, "last_run_at": last_run_at,
            "pending_captures": int(pending[0]["n"]) if pending else 0}


def main(argv=None):
    ap = argparse.ArgumentParser(description="successbrian-os jive worker")
    sub = ap.add_subparsers(dest="action", required=True)
    p_run = sub.add_parser("run", help="process new captures (no-op when idle)")
    p_run.add_argument("--dry-run", action="store_true",
                       help="compute but do not write")
    sub.add_parser("status", help="show watermark and pending input")
    args = ap.parse_args(argv)

    if args.action == "status":
        s = status()
        print("jive status: last_capture_id=%d last_run_at=%s pending=%d" % (
            s["last_capture_id"], s["last_run_at"], s["pending_captures"]))
        return 0

    result = run(dry_run=args.dry_run)
    if result["skipped"]:
        print("jive: nothing new since last run, skipped")
    else:
        print("jive: %d turns, %d tasks, %d duplicates, %d links%s" % (
            result["conversations"], result["tasks"],
            result["duplicates"], result["links"],
            " (dry-run)" if result.get("dry_run") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
