#!/usr/bin/env python3
"""guardrails_common.py — shared DB + defensive-section helpers for guardrails.

PURPOSE: One connection helper and one schema bootstrap for the
         tools/guardrails/ modules (capacity, autonomy, doctor,
         agent_brief), mirroring tools/pm/pm_core.py conventions.
WHY:     Guardrails is a cross-cutting home beside tools/pm/ (Brian
         2026-10-27 WS-CAP); it must not duplicate pm_core, so it
         imports it for the decision stream / step filing.
CALLED BY: the guardrails modules only. Deterministic; no model calls.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pm"))
import pm_core  # noqa: E402

DBNAME = "ecosystem_central"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_nodes (
    name TEXT PRIMARY KEY,
    host TEXT,
    endpoint TEXT,
    kind TEXT NOT NULL DEFAULT 'llama_cpp',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_snapshots (
    id BIGSERIAL PRIMARY KEY,
    node_name TEXT NOT NULL REFERENCES successbrian_os.capacity_nodes(name),
    taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reachable BOOLEAN NOT NULL DEFAULT false,
    latency_ms INT,
    slots_total INT,
    slots_busy INT,
    load1 NUMERIC,
    cpu_count INT,
    mem_total_mb INT,
    mem_available_mb INT,
    mem_pressure_pct NUMERIC,
    saturated BOOLEAN NOT NULL DEFAULT false,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS capacity_snapshots_node_time_idx
    ON successbrian_os.capacity_snapshots (node_name, taken_at DESC);
CREATE TABLE IF NOT EXISTS successbrian_os.capacity_needs (
    id BIGSERIAL PRIMARY KEY,
    dedupe_key TEXT UNIQUE NOT NULL,
    node_name TEXT NOT NULL,
    item TEXT NOT NULL,
    sbos_need_request_id INT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','cleared')),
    first_filed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    cleared_at TIMESTAMPTZ,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS successbrian_os.autonomy_action_types (
    action_type TEXT PRIMARY KEY,
    display_name TEXT,
    current_level INT NOT NULL DEFAULT 0 CHECK (current_level BETWEEN 0 AND 3),
    streak INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.autonomy_events (
    id BIGSERIAL PRIMARY KEY,
    action_type TEXT NOT NULL REFERENCES successbrian_os.autonomy_action_types(action_type),
    outcome TEXT NOT NULL CHECK (outcome IN ('approved_clean','approved_edited','rejected')),
    actor TEXT,
    note TEXT,
    level_before INT,
    level_after INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS successbrian_os.guardrails_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO successbrian_os.guardrails_config (key, value)
VALUES ('autonomy_promote_n','5')
ON CONFLICT (key) DO NOTHING;
"""


def conn(dict_cursor=False):
    if dict_cursor:
        import psycopg2.extras
        return pm_core.psycopg2.connect(
            dbname=DBNAME, host="localhost",
            cursor_factory=psycopg2.extras.RealDictCursor)
    return pm_core.conn()


def ensure_schema(cur):
    cur.execute(SCHEMA_SQL)


def defensive(fn, conn, fallback_prefix="unavailable"):
    """chat_brief pattern: a failed source becomes a line, never a crash."""
    try:
        return fn()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return f"{fallback_prefix}: {type(e).__name__}: {e}"
