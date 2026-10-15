```python
"""PURPOSE: Render board recommendations with a convergence check.

WHY: Implements the Constitution Article 5 convergence flag: if >=70% of
today's recommendation titles fuzzy-match titles from the previous 2 sessions'
source='board' nudge_bus rows, the output is prefixed with a convergence warning.

CALLED BY:
    - board/test_dryrun.py
    - any harness code that renders recommendations

NOTES:
Fuzzy matching is deterministic, normalized word overlap (Jaccard). No LLM is
used. The renderer writes its own recommendations into nudge_bus with
source='board' so the next run can see them as a prior session.
"""

import re
from datetime import datetime, timezone

try:
    from board.harness import db
except ImportError:
    import db


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


def _to_iso(now=None):
    """Return an ISO-8601 string for now."""
    return _to_dt(now).isoformat()


def _normalize_title(title):
    """Return a normalized set of word tokens for a title."""
    title = str(title or "")
    tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
    if not tokens:
        tokens = {title.lower().strip()}
    return tokens


def _jaccard(left, right):
    """Return Jaccard similarity between two token sets."""
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def _titles_match(title, prior_titles, similarity_threshold=0.6):
    """Return True if title fuzzy-matches any prior title."""
    target = _normalize_title(title)
    return any(
        _jaccard(target, _normalize_title(prior)) >= similarity_threshold
        for prior in prior_titles
    )


def convergence_flag(
    current_titles,
    prior_sessions,
    match_threshold=0.70,
    similarity_threshold=0.6,
):
    """Return the convergence flag string, or None if not converged."""
    if not current_titles or not prior_sessions:
        return None

    combined_prior_titles = [
        title for session in prior_sessions for title in session["titles"]
    ]
    if not combined_prior_titles:
        return None

    matched = sum(
        1
        for title in current_titles
        if _titles_match(title, combined_prior_titles, similarity_threshold)
    )
    if (matched / len(current_titles)) < match_threshold:
        return None

    # Count consecutive newest prior sessions that also meet the match rate.
    running_days = 0
    for session in prior_sessions:
        session_titles = session["titles"]
        if not session_titles:
            continue
        session_matched = sum(
            1
            for title in current_titles
            if _titles_match(title, session_titles, similarity_threshold)
        )
        if (session_matched / len(current_titles)) >= match_threshold:
            running_days += 1
        else:
            break

    if running_days == 0:
        running_days = len(prior_sessions)

    return "Board converged %d days running — repetition, not deliberation." % running_days


def _coerce_recommendations(recommendations):
    """Normalize recommendations into list of dicts with title/body."""
    if isinstance(recommendations, str):
        recommendations = [recommendations]

    normalized = []
    for item in recommendations:
        if isinstance(item, str):
            title = item.strip()
            body = ""
        elif isinstance(item, dict):
            title = str(item.get("title", "") or "").strip()
            body = str(item.get("body", "") or "").strip()
        else:
            title = str(item).strip()
            body = ""
        if title:
            normalized.append({"title": title, "body": body})
    return normalized


def render_recommendations(recommendations, db_path=None, now=None):
    """Render recommendation lines, prepending a convergence flag if needed.

    The same recommendations should be feedable twice: the second run sees the
    first run's board nudge_bus rows as a prior session and flags convergence.
    """
    conn = db.get_connection(db_path)
    try:
        db.ensure_schema(conn)

        now_iso = _to_iso(now)
        recs = _coerce_recommendations(recommendations)
        current_titles = [rec["title"] for rec in recs]

        prior_sessions = db.fetch_previous_sessions(conn, before_iso=now_iso, limit=2)
        flag = convergence_flag(current_titles, prior_sessions)

        lines = ["- %s" % rec["title"] for rec in recs]
        body = "\n".join(lines)
        if flag:
            output = "%s\n%s" % (flag, body)
        else:
            output = body

        for rec in recs:
            db.insert_nudge_bus_row(
                conn,
                source="board",
                title=rec["title"],
                body=rec["body"],
                acknowledged=0,
                session_id=now_iso,
                created_at=now_iso,
            )

        return output
    finally:
        conn.close()
```
