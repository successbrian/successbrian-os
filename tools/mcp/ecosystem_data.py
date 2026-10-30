#!/usr/bin/env python3
"""Ecosystem Data MCP server (per Brian 2026-10-11).

PURPOSE
    Expose Brian's ecosystem data as MCP tools so his agents query it
    conversationally instead of hand-writing SQL. Stolen from Precisely's
    MCP-server move; built Brian's way (free, local, FastMCP on k11).

TOOLS
    second_brain_search  - search learnings in the second brain
    pipeline_health      - latest pipeline health check + active alerts
    ingest_candidates    - proposed income streams/audiences/campaigns
    inbox_recent         - recent dashboard inbox reports

WHY
    Hand-writing SQL for every "what did we learn about X" question is
    slow and error-prone; agents were re-querying the same tables by
    memory. Exposing the ecosystem's read models as named tools means
    any agent asks in plain language and gets the canonical answer.
    Read-only by design: agents should converse with the data, never
    mutate it from chat. Stolen from Precisely's MCP-server move, built
    Brian's way (free, local, FastMCP on k11) so zero tokens are spent
    per query once it is wired in.

RUN
    python3 ecosystem_data_mcp.py   (stdio transport; wire into the
    agent's MCP client config)

NOTES
    - Read-only. Every tool is a SELECT; nothing here writes.
    - DB auth follows the k11 pattern (PGPASSWORD env, postgres superuser).
    - stdlib + mcp (FastMCP) only.
"""

import os
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ecosystem-data")


def _psql(sql):
    """Run a read-only query. Returns (rows, error)."""
    env = dict(os.environ)
    r = subprocess.run(
        ["psql", "-h", "localhost", "-U", "postgres",
         "-d", "ecosystem_central",
         "-v", "ON_ERROR_STOP=1", "-X", "-q", "-t", "-A", "-F", "\t"],
        input=sql, capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0:
        return None, r.stderr.strip()[-300:]
    return [l for l in r.stdout.splitlines() if l.strip()], None


def _like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") \
            .replace("'", "''")


@mcp.tool()
def second_brain_search(query: str, limit: int = 10) -> str:
    """Search the second brain's learnings by keyword.

    Args:
        query: Keywords to search for in topic and content.
        limit: Max results (default 10, max 50).
    """
    limit = max(1, min(int(limit), 50))
    q = _like_escape(query)
    rows, err = _psql(
        "SELECT topic, left(content, 300), confidence, created_at"
        " FROM public.second_brain"
        " WHERE topic ILIKE '%%%s%%' ESCAPE '\\'"
        "    OR content ILIKE '%%%s%%' ESCAPE '\\'"
        " ORDER BY created_at DESC LIMIT %d;" % (q, q, limit))
    if err:
        return "error: %s" % err
    if not rows:
        return "no learnings match '%s'" % query
    out = []
    for r in rows:
        topic, content, conf, created = r.split("\t")
        out.append("- [%s] %s (%s)\n  %s" % (created[:10], topic, conf,
                                            content))
    return "\n".join(out)


@mcp.tool()
def pipeline_health() -> str:
    """Latest pipeline health check: what is up, what is down, and whether
    an alert is active."""
    rows, err = _psql(
        "SELECT check_time, sources_active, sources_error, alert_triggered,"
        " alert_reason FROM public.pipeline_health"
        " ORDER BY check_time DESC LIMIT 1;")
    if err:
        return "error: %s" % err
    if not rows:
        return "no health checks recorded"
    check_time, active, errors, alert, reason = rows[0].split("\t")
    status = "ALERT" if alert == "t" else "OK"
    out = ("pipeline health [%s] as of %s: %s sources active, %s in error"
           % (status, check_time, active, errors))
    if alert == "t" and reason:
        out += "\nreasons: %s" % reason
    return out


@mcp.tool()
def ingest_candidates(kind: str = "", limit: int = 20) -> str:
    """Proposed income streams, audiences, campaigns, and ideas from the
    ingest engine that are still awaiting the entrepreneur's review.

    Args:
        kind: Filter: income_stream, audience, campaign, idea (default all).
        limit: Max results (default 20, max 50).
    """
    limit = max(1, min(int(limit), 50))
    filt = ""
    if kind:
        if kind not in ("income_stream", "audience", "campaign", "idea"):
            return "unknown kind '%s'" % kind
        filt = "AND kind='%s'" % kind
    rows, err = _psql(
        "SELECT id, kind, score, title, left(summary, 150)"
        " FROM successbrian_os.ingest_candidates"
        " WHERE status='proposed' %s"
        " ORDER BY score DESC, id LIMIT %d;" % (filt, limit))
    if err:
        return "error: %s" % err
    if not rows:
        return "no proposed candidates"
    out = []
    for r in rows:
        cid, k, score, title, summary = r.split("\t")
        out.append("#%s [%s] (%s) %s -- %s" % (cid, score, k, title,
                                              summary))
    return "\n".join(out)


@mcp.tool()
def inbox_recent(limit: int = 10) -> str:
    """Recent dashboard inbox reports (newest first).

    Args:
        limit: Max results (default 10, max 30).
    """
    limit = max(1, min(int(limit), 30))
    rows, err = _psql(
        "SELECT created_at, report_type, title FROM successbrian_os.reports"
        " ORDER BY created_at DESC LIMIT %d;" % limit)
    if err:
        return "error: %s" % err
    if not rows:
        return "inbox is empty"
    out = []
    for r in rows:
        created, rtype, title = r.split("\t")
        out.append("- [%s] (%s) %s" % (created[:16], rtype, title))
    return "\n".join(out)


@mcp.tool()
def lyra_chain_status() -> str:
    """Lyra worker chain status: halted?, queue depth, recent completions,
    V4 balance. The fast way to see if the machine is running."""
    out = []
    rows, err = _psql(
        "SELECT key, value FROM successbrian_os.chain_controls "
        "WHERE key IN ('lyra_chain_halted', 'lyra_daily_spend_cap_usd');")
    if not err and rows:
        out.append("controls: " + ", ".join(
            "%s=%s" % tuple(r.split("\t")) for r in rows))
    rows, err = _psql(
        "SELECT status, count(*) FROM successbrian_os.v4pro_handoffs "
        "WHERE created_at > now() - interval '24 hours' "
        "GROUP BY status;")
    if not err and rows:
        out.append("handoffs (24h): " + ", ".join(
            "%s=%s" % (r.split("\t")[0], r.split("\t")[1]) for r in rows))
    rows, err = _psql(
        "SELECT usd, available FROM successbrian_os.v4pro_balance_history "
        "ORDER BY checked_at DESC LIMIT 1;")
    if not err and rows:
        usd, avail = rows[0].split("\t")
        out.append("V4 balance: $%s (available=%s)" % (usd, avail))
    rows, err = _psql(
        "SELECT count(*) FROM successbrian_os.v4pro_worker_learnings "
        "WHERE status = 'active';")
    if not err and rows:
        out.append("active learnings: %s" % rows[0])
    return "\n".join(out) if out else "chain status unavailable"


@mcp.tool()
def lyra_escalations(tier: str = "", limit: int = 10) -> str:
    """Open Lyra worker escalations by tier (altair/meghan/brian).

    Args:
        tier: Filter by tier (default all open).
        limit: Max results (default 10, max 50).
    """
    limit = max(1, min(int(limit), 50))
    filt = ""
    if tier:
        if tier not in ("altair", "meghan", "brian"):
            return "unknown tier '%s'" % tier
        filt = "AND tier='%s'" % tier
    rows, err = _psql(
        "SELECT id, tier, priority, left(question, 120), status "
        "FROM successbrian_os.worker_escalations "
        "WHERE status = 'open' %s "
        "ORDER BY priority DESC, created_at DESC LIMIT %d;" % (filt, limit))
    if err:
        return "error: %s" % err
    if not rows:
        return "no open escalations"
    return "\n".join(
        "#%s [%s p%s] %s (%s)" % tuple(r.split("\t")) for r in rows)


@mcp.tool()
def lyra_learnings(kind: str = "", limit: int = 10) -> str:
    """Recent active Lyra worker learnings — what the fleet has learned.

    Args:
        kind: Filter by worker kind (default all).
        limit: Max results (default 10, max 50).
    """
    limit = max(1, min(int(limit), 50))
    filt = ""
    if kind:
        filt = "AND worker_kind='%s'" % _like_escape(kind)
    rows, err = _psql(
        "SELECT id, worker_kind, left(learning, 160) "
        "FROM successbrian_os.v4pro_worker_learnings "
        "WHERE status = 'active' %s "
        "ORDER BY created_at DESC LIMIT %d;" % (filt, limit))
    if err:
        return "error: %s" % err
    if not rows:
        return "no learnings yet"
    return "\n".join(
        "#%s [%s] %s" % tuple(r.split("\t")) for r in rows)


if __name__ == "__main__":
    mcp.run()
