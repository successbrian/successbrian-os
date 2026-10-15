```python
"""PURPOSE: Build the morning brief.

WHY: Implements the brief sections required by Constitution Articles 4-5:
  1. "What changed in the last 24 hours"
  2. "Brian's response to your last session"
The builder must fail if either section is missing, and must never invent
deltas when a brief source is unavailable.

CALLED BY:
    - board/test_dryrun.py
    - CLI: python3 -m board.harness.brief_builder --db <db_path>

NOTES:
Sources may be `table` rows in ecosystem_state or `file`/`jsonl` rows in a
JSONL file. A broken source contributes the line "<source_name>: unavailable"
and causes a non-zero CLI exit, so an invalid brief is not silently emitted.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

try:
    from board.harness import db
except ImportError:
    import db


class BriefBuildError(RuntimeError):
    """Raised when a required morning brief section is missing."""


def _to_dt(now=None):
    """Return a timezone-aware datetime for now."""
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now
    text = str(now)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _read_jsonl_source(location, since_iso):
    """Read deltas from a JSONL file. Missing path raises FileNotFoundError."""
    rows = []
    with open(location, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            changed_at = str(obj.get("changed_at", ""))
            if changed_at >= since_iso:
                rows.append(
                    {
                        "title": str(obj.get("title", "") or ""),
                        "body": str(obj.get("body", "") or ""),
                        "changed_at": changed_at,
                        "created_at": str(obj.get("created_at", changed_at)),
                    }
                )
    return rows


def _read_table_source(conn, source_id, since_iso):
    """Read deltas from ecosystem_state."""
    rows = db.fetch_ecosystem_deltas(conn, source_id, since_iso)
    return [dict(row) for row in rows]


def _read_source_deltas(conn, source, since_iso):
    """Read deltas for one configured source."""
    kind = str(source["kind"]).lower()
    if kind == "table":
        return _read_table_source(conn, source["source_id"], since_iso)
    if kind in ("file", "jsonl"):
        return _read_jsonl_source(source["location"], since_iso)
    raise ValueError("unsupported brief source kind: %s" % kind)


def build_morning_brief_with_status(db_path=None, now=None):
    """Build the brief and also return any unavailable source ids.

    Returns:
        (brief_text, unavailable_source_ids)
    """
    conn = db.get_connection(db_path)
    try:
        db.ensure_schema(conn)

        now_dt = _to_dt(now)
        since_iso = (now_dt - timedelta(hours=24)).isoformat()

        sources = db.fetch_brief_sources(conn)

        delta_lines = []
        unavailable = []

        if not sources:
            delta_lines.append("- no brief sources configured")

        for src in sources:
            src_name = src["source_name"]
            try:
                rows = _read_source_deltas(conn, src, since_iso)
                if rows:
                    for row in rows:
                        title = str(row.get("title", "") or "").strip()
                        if not title:
                            title = "untitled"
                        delta_lines.append("- %s: %s" % (src_name, title))
                else:
                    delta_lines.append(
                        "- %s: no changes in the last 24 hours" % src_name
                    )
            except Exception:
                delta_lines.append("- %s: unavailable" % src_name)
                unavailable.append(src["source_id"])

        if delta_lines:
            delta_section = (
                "What changed in the last 24 hours\n" + "\n".join(delta_lines)
            )
        else:
            delta_section = "What changed in the last 24 hours\n- no changes"

        response_rows = db.fetch_nudge_bus_responses(conn, limit=5)
        if response_rows:
            feedback_lines = []
            for row in response_rows:
                title = str(row["title"] or "").strip() or "untitled"
                body = str(row["body"] or "").strip()
                if body:
                    feedback_lines.append("- %s: %s" % (title, body))
                else:
                    feedback_lines.append("- %s" % title)
        else:
            feedback_lines = ["- no acknowledged board responses yet"]

        feedback_section = (
            "Brian's response to your last session\n"
            + "\n".join(feedback_lines)
        )

        brief = "%s\n\n%s" % (delta_section, feedback_section)

        if (
            "What changed in the last 24 hours" not in brief
            or "Brian's response to your last session" not in brief
        ):
            raise BriefBuildError("morning brief is missing a required section")

        return brief, unavailable
    finally:
        conn.close()


def build_morning_brief(db_path=None, now=None):
    """Build the morning brief and return its text."""
    brief, _ = build_morning_brief_with_status(db_path=db_path, now=now)
    return brief


def main(argv=None):
    """CLI entry point. Exits 0 on a complete brief, 1 if any source is
    unavailable, and 2 if the required brief sections are missing."""
    parser = argparse.ArgumentParser(description="Build the board morning brief")
    parser.add_argument("--db", default=None, help="SQLite DB path")
    args = parser.parse_args(argv)

    try:
        brief, unavailable = build_morning_brief_with_status(db_path=args.db)
    except BriefBuildError as exc:
        print("brief_builder: %s" % exc, file=sys.stderr)
        return 2

    print(brief)
    if unavailable:
        print(
            "brief_builder: unavailable sources: %s" % ", ".join(unavailable),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
