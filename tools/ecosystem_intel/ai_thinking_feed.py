#!/usr/bin/env python3
"""ai_thinking_feed.py — Brian's monthly AI-thinking feed (alpha).

Brian (2026-11-10 00:54 CST): "what matters to BRIAN is learning
more and more about AI and what businesses are thinking in
regards to how AI solves their problems." The clerk tags
captures with that lens (board/scatter_clerk.py
match_ai_thinking; verdicts + reasons stored in
successbrian_os.ai_thinking_tags). This reader assembles one
month's tagged items — newest first, each with the tagger's
reason in words — for Brian's monthly positioning pulse (the
Crew2/UNITE goal's monthly rhythm, beside the
aptean_unite_watch on the 15th).

Read-only: it never writes, never contacts anyone, and files
nothing. If the tags table is empty for the month it says so
plainly; a month with no tagged items is a true statement
about the intake, not an error.

Usage: ai_thinking_feed.py [--month YYYY-MM] [--json]
                           [--limit N]
A successful text run ends with AI_THINKING_FEED_OK.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

CT = timezone(timedelta(hours=-6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None,
                    help="YYYY-MM (default: current month, CT)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()
    month = a.month or datetime.now(CT).strftime("%Y-%m")
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian",
                            cursor_factory=RealDictCursor)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT c.id, c.title, c.created_at, t.patterns, "
            "t.reason FROM successbrian_os.ai_thinking_tags t "
            "JOIN atlas.scattered_captures c "
            "ON c.id = t.capture_id "
            "WHERE t.ai_thinking AND to_char(c.created_at "
            "AT TIME ZONE 'America/Chicago', 'YYYY-MM') = %s "
            "ORDER BY c.created_at DESC, c.id DESC LIMIT %s",
            (month, a.limit))
        rows = cur.fetchall()
        cur.execute("SELECT count(*) AS n FROM "
                    "successbrian_os.ai_thinking_tags")
        total_tags = cur.fetchone()["n"]
    except Exception as e:
        conn.close()
        print("AI-THINKING FEED: tags table not readable "
              f"({e}) — run board/scatter_clerk.py "
              "--ai-thinking-backfill first")
        print("AI_THINKING_FEED_OK")
        return 0
    conn.close()
    items = [{"id": r["id"], "title": r["title"],
              "created_at": r["created_at"].isoformat()
              if r["created_at"] else None,
              "patterns": r["patterns"], "reason": r["reason"]}
             for r in rows]
    if a.json:
        print(json.dumps({"month": month, "count": len(items),
                          "items": items}, indent=1, default=str))
        return 0
    print(f"AI-THINKING FEED — {month}: {len(items)} item(s) "
          "where businesses talk about AI solving their "
          "problems (newest first)")
    if total_tags == 0:
        print("  (no captures tagged yet — run "
              "board/scatter_clerk.py --ai-thinking-backfill)")
    for it in items:
        day = (it["created_at"] or "")[:10]
        print(f"- [{day}] #{it['id']} {it['title']}")
        print(f"    reason: {it['reason']}")
    print("AI_THINKING_FEED_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
