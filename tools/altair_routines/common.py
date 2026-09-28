#!/usr/bin/env python3
"""
Shared helpers for Altair's routine-driven chat backend.

PURPOSE:
    One place for state-db access, second-brain logging, and the JSON-output
    contract shared by briefing.py, decisions.py, and planning.py.

WHY:
    Brian's directive (2026-09-27): Altair must run as routines a 14B model
    can execute without a high-level LLM. The 14B only paraphrases `say` text
    and classifies replies into `expect` schemas; all flow, state, and
    structure live here in Python. If these helpers break, the chat backend
    has no memory and no durable record of Brian's decisions.

CALLED BY:
    briefing.py, decisions.py, planning.py (same directory). Deployed to
    k11-alpha at ~/bin/altair_routines/; state.db lives alongside them.

NOTES:
    Runs ON k11-alpha, so it talks to Postgres directly over localhost
    (no kssh). SQL values are escaped by doubling single quotes — never
    interpolate without sq().
"""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DB = os.path.join(HERE, "state.db")

PSQL = ["psql", "-h", "localhost", "-U", "successbrian",
        "-d", "ecosystem_central", "-t", "-A"]


def today():
    return datetime.now().strftime("%Y-%m-%d")


def sq(val):
    """SQL-escape a text value (double single quotes)."""
    return str(val).replace("'", "''")


def db():
    """Open state.db, creating tables on first use."""
    fresh = not os.path.exists(STATE_DB)
    con = sqlite3.connect(STATE_DB)
    con.row_factory = sqlite3.Row
    if fresh:
        con.executescript("""
        CREATE TABLE sessions(
          id TEXT PRIMARY KEY, kind TEXT, ref_date TEXT, slot TEXT,
          created_at TEXT DEFAULT (datetime('now')), done INTEGER DEFAULT 0);
        CREATE TABLE briefing_topics(
          id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, ord INTEGER,
          area TEXT, title TEXT, detail TEXT, needs TEXT, options_json TEXT,
          feedback TEXT, covered INTEGER DEFAULT 0);
        CREATE TABLE plans(
          id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          q_index INTEGER DEFAULT 0, answers_json TEXT DEFAULT '[]',
          status TEXT DEFAULT 'open', plan_path TEXT);
        """)
        con.commit()
    return con


def out(obj):
    """Print exactly one JSON object to stdout (the 14B's whole world)."""
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def fail(msg):
    out({"error": msg, "done": True,
         "say": "Something glitched on my end — let's pick that back up in a moment.",
         "expect": "text"})
    sys.exit(1)


def sb_log(topic, content, category="observation", confidence="medium",
           source="altair-routines", tags=("altair-routines",)):
    """Append one record to the second brain (local psql, k11 only)."""
    tag_arr = "ARRAY[" + ",".join(f"'{sq(t)}'" for t in tags) + "]::text[]"
    sql = (f"INSERT INTO second_brain (topic, category, content, confidence, "
           f"source, tags) VALUES ('{sq(topic)}', '{sq(category)}', "
           f"'{sq(content)}', '{sq(confidence)}', '{sq(source)}', {tag_arr});")
    try:
        r = subprocess.run(PSQL + ["-c", sql],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:200])
    except Exception as e:
        # Second-brain logging must never break the chat flow.
        print(f"[common] second-brain log failed: {e}", file=sys.stderr)


def pg_rows(sql):
    """Run read-only SQL, return list of \\x1f-split rows."""
    r = subprocess.run(PSQL + ["-F", "\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    rows = []
    for line in r.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\x1f"))
    return rows


def pg_write(sql):
    r = subprocess.run(PSQL + ["-c", sql],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()
