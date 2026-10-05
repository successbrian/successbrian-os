#!/usr/bin/env python3
"""token_collector.py — weekly ecosystem token-production telemetry.

PURPOSE: Parse per-model token counts from k11-alpha journald logs and store
         daily/weekly aggregates in telemetry.token_daily / token_weekly.
WHY:     Brian wants weekly token output by model class, graphed over time,
         for social/blog content (attention, job inquiries). llama.cpp
         --metrics is disabled (501) and services must NOT be restarted, so
         journald timing lines are the authoritative source.
CALLED BY: token-collector.timer (weekly, Mon 07:00 America/Chicago);
           manual runs for backfill: token_collector.py --since YYYY-MM-DD
NOTES:   - llama-server prints INCREMENTAL n_gen lines per task: NEVER sum
           them. Only the final per-task print_timing block counts, deduped
           by task ID (morpheus) or (slot, timestamp) when task=0 (penny).
         - colibri-deepseek (150B) logs prefill progress only (v4_prefill
           X/Y tokens): prompt tokens = max(Y) per request burst; generated
           tokens are NOT logged anywhere -> stored as NULL, honestly.
         - Aggregate stats only. Prompts are never stored or transmitted.
         - Days with no log coverage get NO row (NULL/missing, never zero).
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/token_collector.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/token_collector.py (k11-alpha; systemd timers).

"""

import argparse
import logging
import re
import subprocess
from datetime import date, datetime, timedelta

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [token_collector] %(message)s")
LOG = logging.getLogger("token_collector")

DB_USER = "successbrian"
DB_NAME = "ecosystem_central"

# journal short-iso: 2026-10-01T02:35:28-0500 ...
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})")

PROMPT_RE = re.compile(
    r"slot print_timing: id +(\d+) \| task +(-?\d+) \| prompt eval time =\s*[\d.]+ ms / +(\d+) tokens")
GEN_RE = re.compile(
    r"slot print_timing: id +(\d+) \| task +(-?\d+) \| +eval time =\s*[\d.]+ ms / +(\d+) tokens")
PREFILL_RE = re.compile(r"v4_prefill (\d+)/(\d+) tokens")

SERVICES = {
    "morpheus": {"unit": "morpheus", "kind": "llama",
                 "source": "journald morpheus.service print_timing (final block)"},
    "penny": {"unit": "penny", "kind": "llama",
              "source": "journald penny.service print_timing (final block)"},
    "deepseek-150b": {"unit": "colibri-deepseek", "kind": "prefill",
                      "source": "journald colibri-deepseek.service v4_prefill (prompt only)"},
}


def journal_lines(unit, since):
    r = subprocess.run(
        ["journalctl", "-u", unit, "--since", since, "-o", "short-iso",
         "--no-pager"],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        LOG.error("journalctl -u %s failed: %s", unit, r.stderr.strip()[:200])
        return []
    return r.stdout.splitlines()


def parse_llama(unit, since):
    """Final per-task blocks only. Returns list of (day, prompt, gen)."""
    tasks = {}
    order = []
    for line in journal_lines(unit, since):
        m = TS_RE.match(line)
        if not m:
            continue
        day = m.group(1)
        ts_key = f"{m.group(2)}:{m.group(3)}:{m.group(4)}"
        pm = PROMPT_RE.search(line)
        gm = None if pm else GEN_RE.search(line)
        if not (pm or gm):
            continue
        slot, task, ntok = (pm or gm).group(1), (pm or gm).group(2), int((pm or gm).group(3))
        # Dedupe: real task IDs when present; penny logs task 0 for everything.
        key = f"task:{task}" if task not in ("0", "-1") else f"slot:{slot}@{ts_key}"
        if key not in tasks:
            tasks[key] = {"day": day, "prompt": None, "gen": None}
            order.append(key)
        rec = tasks[key]
        if pm:
            rec["prompt"] = ntok if rec["prompt"] is None else max(rec["prompt"], ntok)
        else:
            rec["gen"] = ntok if rec["gen"] is None else max(rec["gen"], ntok)
    out = []
    for key in order:
        rec = tasks[key]
        if rec["prompt"] is None and rec["gen"] is None:
            continue
        out.append((rec["day"], rec["prompt"] or 0, rec["gen"] or 0))
    return out


def parse_prefill(unit, since):
    """v4_prefill X/Y progress lines -> one request per burst (<=120s gap),
    prompt tokens = max(Y). Generated tokens are not logged -> NULL."""
    events = []
    for line in journal_lines(unit, since):
        m = TS_RE.match(line)
        pm = PREFILL_RE.search(line)
        if not (m and pm):
            continue
        ts = datetime.strptime(m.group(1) + "T" + ":".join(m.group(2, 3, 4)),
                               "%Y-%m-%dT%H:%M:%S")
        events.append((ts, int(pm.group(2))))
    events.sort()
    bursts = []
    cur = []
    for ts, total in events:
        if cur and (ts - cur[-1][0]).total_seconds() > 120:
            bursts.append(cur)
            cur = []
        cur.append((ts, total))
    if cur:
        bursts.append(cur)
    return [(b[0][0].strftime("%Y-%m-%d"), max(t for _, t in b), None)
            for b in bursts]


def psql(sql):
    r = subprocess.run(["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A",
                        "-F\x1f", "-c", sql],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr.strip()[:300])
    return r.stdout


def ensure_schema():
    psql("""CREATE SCHEMA IF NOT EXISTS telemetry;
CREATE TABLE IF NOT EXISTS telemetry.token_daily (
  day DATE NOT NULL, model_class TEXT NOT NULL,
  prompt_tokens BIGINT, generated_tokens BIGINT,
  tasks INT NOT NULL DEFAULT 0, source TEXT,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (day, model_class));
CREATE TABLE IF NOT EXISTS telemetry.token_weekly (
  week_start DATE NOT NULL, model_class TEXT NOT NULL,
  prompt_tokens BIGINT, generated_tokens BIGINT,
  tasks INT NOT NULL DEFAULT 0,
  PRIMARY KEY (week_start, model_class));
GRANT ALL ON SCHEMA telemetry TO successbrian;
GRANT ALL ON telemetry.token_daily TO successbrian;
GRANT ALL ON telemetry.token_weekly TO successbrian;""")


def esc(s):
    return s.replace("'", "''")


def store_daily(model_class, rows, source):
    # rows: list of (day, prompt_or_None, gen_or_None)
    by_day = {}
    for day, p, g in rows:
        d = by_day.setdefault(day, {"p": 0, "g": 0, "n": 0,
                                    "p_any": False, "g_any": False})
        d["n"] += 1
        if p is not None:
            d["p"] += p
            d["p_any"] = True
        if g is not None:
            d["g"] += g
            d["g_any"] = True
    for day, d in sorted(by_day.items()):
        p_sql = str(d["p"]) if d["p_any"] else "NULL"
        g_sql = str(d["g"]) if d["g_any"] else "NULL"
        psql(f"""INSERT INTO telemetry.token_daily
                   (day, model_class, prompt_tokens, generated_tokens, tasks, source)
                 VALUES ('{day}', '{esc(model_class)}', {p_sql}, {g_sql},
                         {d["n"]}, '{esc(source)}')
                 ON CONFLICT (day, model_class) DO UPDATE SET
                   prompt_tokens = EXCLUDED.prompt_tokens,
                   generated_tokens = EXCLUDED.generated_tokens,
                   tasks = EXCLUDED.tasks, source = EXCLUDED.source,
                   collected_at = NOW();""")
    LOG.info("%s: %d tasks across %d day(s)", model_class,
             sum(d["n"] for d in by_day.values()), len(by_day))


def rollup_weekly():
    psql("""INSERT INTO telemetry.token_weekly
              (week_start, model_class, prompt_tokens, generated_tokens, tasks)
            SELECT date_trunc('week', day)::date, model_class,
                   SUM(prompt_tokens), SUM(generated_tokens), SUM(tasks)
            FROM telemetry.token_daily GROUP BY 1, 2
            ON CONFLICT (week_start, model_class) DO UPDATE SET
              prompt_tokens = EXCLUDED.prompt_tokens,
              generated_tokens = EXCLUDED.generated_tokens,
              tasks = EXCLUDED.tasks;""")
    LOG.info("weekly rollup done")


def main():
    ap = argparse.ArgumentParser(description="Collect token telemetry from journald")
    ap.add_argument("--since", default=None,
                    help="e.g. 2026-09-29 (default: 8 days ago)")
    args = ap.parse_args()
    since = args.since or (date.today() - timedelta(days=8)).strftime("%Y-%m-%d")
    ensure_schema()
    parsers = {"llama": parse_llama, "prefill": parse_prefill}
    for model_class, cfg in SERVICES.items():
        rows = parsers[cfg["kind"]](cfg["unit"], since)
        store_daily(model_class, rows, cfg["source"])
    rollup_weekly()
    LOG.info("done")


if __name__ == "__main__":
    main()
