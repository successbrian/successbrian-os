"""
Enrich: write the detail into each decision BEFORE a seat rules on it
(Brian 2026-10-23: "we need to give them more details to go on for
the decisions — something needs to write more details in each
decision").

WHY:
    In the 2026-10-23 beta the seats ruled on titles. Atlas items
    carry a name and, often, a NULL summary and a few details keys —
    so a seat saw one sentence and a key, and ruled from the brief's
    general context. Thin input, thin rulings. This pass is the
    clerk's framing duty in software: for every agenda item it pulls
    the item's own Atlas record (summary, details, age) and its
    connections (atlas.edges, both directions), and appends a plain
    DETAILS block to the item text the seat actually reads. It also
    stamps item.meta (details/created_at/summary) for the priority
    scorer. Deterministic, read-only, and failure-isolated: an item
    that cannot be enriched keeps its original text and the session
    never breaks over enrichment.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _run_psql(sql: str, via: str) -> str:
    if via == "kssh":
        kssh = os.path.expanduser("~/workspace/bin/kssh")
        inner = f"psql -d ecosystem_central -tAF '\\t' -c {_q(sql)}"
        proc = subprocess.run(f"{kssh} {_q(inner)}", shell=True,
                              capture_output=True, timeout=60)
    else:
        proc = subprocess.run(
            ["psql", "-d", "ecosystem_central", "-tAF", "\t", "-c", sql],
            capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip()[:200])
    return proc.stdout.decode(errors="replace")


def enrich_items(items, via: str = "direct") -> int:
    """Append a DETAILS block to each item's text from its Atlas row
    and edges; stamp item.meta. Returns the number enriched. Items
    whose key is not an Atlas node (e.g. JSONL queues) are skipped
    silently. Never raises."""
    if not items:
        return 0
    keys = [i.key for i in items]
    in_list = ",".join("'" + k.replace("'", "''") + "'" for k in keys)
    try:
        rows_out = _run_psql(
            "SELECT node_key, coalesce(summary,''), coalesce(details::text,'{}'), "
            f"created_at FROM atlas.nodes WHERE node_key IN ({in_list})", via)
        edges_out = _run_psql(
            "SELECT from_node, to_node, edge_type FROM atlas.edges "
            f"WHERE from_node IN ({in_list}) OR to_node IN ({in_list}) "
            "ORDER BY created_at", via)
    except Exception:  # noqa: BLE001 - enrichment must never break the queue
        return 0

    nodes = {}
    for line in rows_out.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        key, summary, details_txt, created = parts[:4]
        try:
            details = json.loads(details_txt) if details_txt else {}
        except json.JSONDecodeError:
            details = {}
        nodes[key.strip()] = {
            "summary": summary.strip(), "details": details,
            "created_at": created.strip(),
        }

    edges: dict[str, list[str]] = {}
    for line in edges_out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        frm, to, etype = (p.strip() for p in parts[:3])
        if frm in nodes or frm in keys:
            edges.setdefault(frm, []).append(f"--[{etype}]--> {to}")
        if to in nodes or to in keys:
            edges.setdefault(to, []).append(f"<--[{etype}]-- {frm}")

    now = datetime.now(timezone.utc)
    enriched = 0
    for item in items:
        node = nodes.get(item.key)
        if not node:
            continue
        try:
            details = node["details"]
            lines = ["", "DETAILS FOR THE SEAT (assembled before this session):"]
            if node["summary"]:
                lines.append(f"- Summary: {node['summary']}")
            about = details.get("about") or details.get("question")
            if about:
                lines.append(f"- About: {about}")
            for label, key in (("Source", "source"), ("Filed by", "found_by"),
                               ("Model hint", "model"), ("Deadline", "deadline")):
                if details.get(key):
                    lines.append(f"- {label}: {details[key]}")
            created = None
            try:
                created = datetime.fromisoformat(
                    node["created_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                created = None
            if created is not None:
                age = max(0, (now - created).days)
                lines.append(
                    f"- Waiting: {age} day(s) in the queue "
                    f"(filed {created.date().isoformat()})")
            item_edges = edges.get(item.key, [])[:6]
            if item_edges:
                lines.append("- Connected in Atlas: " + "; ".join(item_edges))
            item.text = item.text.rstrip() + "\n" + "\n".join(lines)
            item.meta = {
                "details": details,
                "summary": node["summary"],
                "created_at": node["created_at"],
            }
            enriched += 1
        except Exception:  # noqa: BLE001 - one bad row must not stop the rest
            continue
    return enriched
