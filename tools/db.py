```python
"""PURPOSE: SQLite helpers for the board harness.

WHY: Keeps runtime state in tables so brief building and rendering are
deterministic and dry-runable without external services.

CALLED BY:
    - board/harness/brief_builder.py
    - board/harness/render.py
    - board/test_dryrun.py

NOTES:
The production table is successbrian_os.nudge_bus. In this SQLite dry-run
schema we use main.nudge_bus so the harness can run locally. Swap get_connection
for the production database adapter if Postgres is used.
"""

import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board.db")


def get_connection(db_path=None):
    """Open and return the runtime SQLite connection."""
    path = db_path or os.environ.get("BOARD_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn):
    """Create the harness tables if they do not exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS brief_source (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            location TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ecosystem_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            changed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nudge_bus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            acknowledged INTEGER NOT NULL DEFAULT 0,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def fetch_brief_sources(conn):
    """Return all configured brief sources, ordered by name."""
    return conn.execute(
        "SELECT source_id, source_name, kind, location "
        "FROM brief_source ORDER BY source_name"
    ).fetchall()


def fetch_ecosystem_deltas(conn, source_id, since_iso):
    """Return ecosystem rows for one source changed at or after since_iso."""
    return conn.execute(
        """
        SELECT source_id, title, body, changed_at, created_at
        FROM ecosystem_state
        WHERE source_id = ?
          AND changed_at >= ?
        ORDER BY changed_at DESC
        """,
        (source_id, since_iso),
    ).fetchall()


def fetch_nudge_bus_responses(conn, limit=5):
    """Return latest acknowledged board-response rows, newest first."""
    return conn.execute(
        """
        SELECT source, title, body, acknowledged, session_id, created_at
        FROM nudge_bus
        WHERE source = 'board'
          AND acknowledged = 1
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_previous_sessions(conn, before_iso, limit=2):
    """Return up to `limit` prior board sessions and their titles.

    A session is identified by the session_id written by the renderer. The
    query excludes the current render by filtering created_at < before_iso.
    """
    session_rows = conn.execute(
        """
        SELECT session_id, MAX(created_at) AS max_created
        FROM nudge_bus
        WHERE source = 'board'
          AND created_at < ?
        GROUP BY session_id
        ORDER BY max_created DESC
        LIMIT ?
        """,
        (before_iso, limit),
    ).fetchall()

    sessions = []
    for row in session_rows:
        title_rows = conn.execute(
            """
            SELECT title
            FROM nudge_bus
            WHERE source = 'board' AND session_id = ?
            ORDER BY id
            """,
            (row["session_id"],),
        ).fetchall()
        sessions.append(
            {
                "session_id": row["session_id"],
                "titles": [r["title"] for r in title_rows],
            }
        )
    return sessions


def insert_nudge_bus_row(
    conn,
    source,
    title,
    body,
    acknowledged,
    session_id,
    created_at,
):
    """Insert one nudge_bus row."""
    conn.execute(
        """
        INSERT INTO nudge_bus
            (source, title, body, acknowledged, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source, title, body, acknowledged, session_id, created_at),
    )
    conn.commit()
```
