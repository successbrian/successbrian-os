#!/usr/bin/env python3
"""reap_loop_status.py - READ-ONLY status for the REAP intel loop.

Brian directive 2026-11-13: feed DeepSeek REAP 150B (gamma) the
right intel in runway-sized packets and return its knowledge to
the ecosystem. This tool only MEASURES the loop: bus health,
sizing watch (oversized senders surface as high avg max_tokens
in failed/dead_letter rows), the stalled reap_queue side path,
and the outbox return flow, plus the knowledge_index growth
from REAP returns (BUILD_QUEUE B4: the collector now runs on
cadence, and this status shows what it landed). It writes nothing.

Usage: reap_loop_status.py [--selftest]
"""
import subprocess, sys

DB = ["psql", "-d", "ecosystem_central", "-At"]

QUERIES = [
    ("bus reap_infer totals",
     "select status||'='||count(*) from bus.events "
     "where event_type='reap_infer' group by status order by status"),
    ("bus reap_infer last 24h",
     "select status||'='||count(*) from bus.events "
     "where event_type='reap_infer' "
     "and created_at > now()-interval '24 hours' group by status order by status"),
    ("sizing watch: avg max_tokens by status",
     "select status||' avg_max_tokens='||round(avg((payload->>'max_tokens')::int)) "
     "from bus.events where event_type='reap_infer' group by status order by status"),
    ("oldest pending (minutes)",
     "select coalesce(round(extract(epoch from now()-min(created_at))/60)::text,'none') "
     "from bus.events where event_type='reap_infer' and status='pending'"),
    ("reap_queue (stalled side path)",
     "select status||'='||count(*) from successbrian_os.reap_queue group by status order by status"),
    ("outbox gamma inference_result total",
     "select count(*)::text from successbrian_os.outbox "
     "where source_agent='gamma' and message_type='inference_result'"),
    ("outbox latest result",
     "select coalesce(max(created_at)::text,'none') from successbrian_os.outbox "
     "where source_agent='gamma' and message_type='inference_result'"),
    ("gamma unhandled (7d)",
     "select count(*)::text from successbrian_os.outbox "
     "where source_agent='gamma' and message_type='gamma_unhandled' "
     "and created_at > now()-interval '7 days'"),
    ("knowledge_index REAP returns landed",
     "select count(*)::text from successbrian_os.knowledge_index "
     "where kind='reap-inference'"),
    ("knowledge_index REAP returns last 24h",
     "select count(*)::text from successbrian_os.knowledge_index "
     "where kind='reap-inference' "
     "and created_at > now()-interval '24 hours'"),
    ("knowledge_index REAP returns latest landed",
     "select coalesce(max(created_at)::text,'none') "
     "from successbrian_os.knowledge_index where kind='reap-inference'"),
    ("knowledge_return unlanded intel verdicts",
     "select ((select count(*) from successbrian_os.outbox "
     "where source_agent='gamma' and message_type='inference_result' "
     "and body like '%ROUTING: intel%') - "
     "(select count(*) from successbrian_os.knowledge_index "
     "where kind='reap-inference'))::text"),
]

def run(sql):
    out = subprocess.run(DB + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]

def report():
    lines = ["REAP INTEL LOOP STATUS (read-only)"]
    for label, sql in QUERIES:
        vals = run(sql)
        lines.append(f"{label}: " + (", ".join(vals) if vals else "none"))
    return "\n".join(lines)

def selftest():
    # invariant: every done bus job has exactly one outbox result
    done = int(run("select count(*)::text from bus.events "
                   "where event_type='reap_infer' and status='done'")[0])
    outb = int(run("select count(*)::text from successbrian_os.outbox "
                   "where source_agent='gamma' and message_type='inference_result'")[0])
    assert done == outb, f"done({done}) != outbox results({outb})"
    # sizing fields must be numeric on every reap_infer payload
    bad = int(run("select count(*)::text from bus.events where event_type='reap_infer' "
                  "and (payload->>'max_tokens') !~ '^[0-9]+$'")[0])
    assert bad == 0, f"{bad} payloads lack numeric max_tokens"
    # B4: landed REAP returns never exceed outbox results, and every
    # landed row carries the collector's canonical_id shape
    landed = int(run("select count(*)::text from successbrian_os.knowledge_index "
                     "where kind='reap-inference'")[0])
    assert landed <= outb, f"landed({landed}) > outbox results({outb})"
    misshapen = int(run("select count(*)::text from successbrian_os.knowledge_index "
                        "where kind='reap-inference' "
                        "and canonical_id not like 'ki:reap-infer-%'")[0])
    assert misshapen == 0, f"{misshapen} landed rows lack ki:reap-infer- id"
    print(f"SELFTEST OK (done==outbox=={done}; sizing fields numeric; "
          f"landed={landed} REAP returns, ids shaped)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(report())
