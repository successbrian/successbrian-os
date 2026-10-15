#!/usr/bin/env python3
"""state_snapshot.py — deterministic OS state snapshot for needs-watch.

Zero tokens. Reads successbrian-os state and emits JSON that a good agent
(Spencer, Altair, Sonic) reads alongside NEEDS_PLAYBOOK.md to decide what
the OS should scream about.

Usage: python3 state_snapshot.py [--out /path/to/snapshot.json]
Prints JSON to stdout; --out also writes it to a file.

The snapshot has two parts:
  state      — raw numbers (queue, worker, bridges, needs, disk)
  candidates — deterministic scream candidates derived from playbook thresholds.
               An agent reviews candidates and decides what to actually file
               via scream.py. Candidates are proposals, not filings.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

DB = {"host": "localhost", "user": "successbrian", "dbname": "ecosystem_central"}

# Playbook thresholds (documented in NEEDS_PLAYBOOK.md)
T_QUEUE_BACKLOG = 50        # pending tasks above this -> need more workers
T_BRIDGE_PILEUP = 200       # unread per target above this -> consumer attention
T_STALE_NEED_HOURS = 48     # 'new' need unpromoted this long -> escalate


def psql(sql):
    r = subprocess.run(
        ["psql", "-h", DB["host"], "-U", DB["user"], "-d", DB["dbname"],
         "-t", "-A", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def one(sql):
    rows = psql(sql)
    return rows[0][0] if rows else None


def worker_state():
    """Is the qwen task worker alive? When did it last log?"""
    try:
        active = subprocess.run(
            ["systemctl", "is-active", "qwen-task-worker"],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        active = "unknown"
    last_log = None
    try:
        r = subprocess.run(
            ["tail", "-1", "/home/successbrian/logs/qwen-task-worker.log"],
            capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            last_log = r.stdout.strip()[:80]
    except Exception:
        pass
    return {"service": active, "last_log": last_log}


def queue_state():
    by_status = {}
    rows = psql("SELECT status, count(*) FROM successbrian_os.qwen_task_queue "
                "GROUP BY status") or []
    for s, c in rows:
        by_status[s] = int(c)
    oldest = one("SELECT EXTRACT(EPOCH FROM (now() - min(created_at)))/3600 "
                 "FROM successbrian_os.qwen_task_queue WHERE status='pending'")
    done_24h = one("SELECT count(*) FROM successbrian_os.qwen_task_queue "
                   "WHERE status='done' AND finished_at > now() - interval '24 hours'")
    return {
        "by_status": by_status,
        "pending": by_status.get("pending", 0),
        "oldest_pending_hours": round(float(oldest), 1) if oldest else None,
        "done_last_24h": int(done_24h) if done_24h else 0,
    }


def bridge_state():
    rows = psql("SELECT target, count(*) FROM altair.knowledge_bridge "
                "WHERE read_at IS NULL GROUP BY target ORDER BY 2 DESC") or []
    return {t: int(c) for t, c in rows}


def needs_state():
    rows = psql("SELECT id, item, qty, priority, status, "
                "EXTRACT(EPOCH FROM (now() - created_at))/3600 "
                "FROM successbrian_os.sbos_need_requests "
                "WHERE status IN ('new','promoted') ORDER BY priority DESC") or []
    return [{"id": int(i), "item": it, "qty": int(q), "priority": int(p),
             "status": s, "age_hours": round(float(a), 1)}
            for i, it, q, p, s, a in rows]


def disk_state():
    try:
        r = subprocess.run(["df", "-h", "/home/successbrian", "--output=pcent"],
                           capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().split("\n")
        return lines[-1].strip() if len(lines) > 1 else "unknown"
    except Exception:
        return "unknown"


def derive_candidates(state):
    """Deterministic candidates from playbook thresholds. Proposals only."""
    cands = []
    q = state["queue"]
    if q["pending"] > T_QUEUE_BACKLOG:
        cands.append({
            "rule": "QUEUE_BACKLOG",
            "proposal": "scream for more sonic inference workers",
            "evidence": f"{q['pending']} pending (threshold {T_QUEUE_BACKLOG}), "
                        f"{q['done_last_24h']} done/24h, oldest pending "
                        f"{q['oldest_pending_hours']}h old",
            "suggested_priority": 8,
        })
    w = state["worker"]
    if w["service"] != "active":
        cands.append({
            "rule": "WORKER_DOWN",
            "proposal": "qwen task worker not active — restart service; "
                        "if restart fails, scream for worker host repair",
            "evidence": f"systemctl is-active = {w['service']}",
            "suggested_priority": 9,
        })
    for target, n in state["bridges"].items():
        if n > T_BRIDGE_PILEUP:
            cands.append({
                "rule": "BRIDGE_PILEUP",
                "proposal": f"bridge target '{target}' has no live consumer",
                "evidence": f"{n} unread (threshold {T_BRIDGE_PILEUP})",
                "suggested_priority": 6,
            })
    for need in state["needs"]:
        if need["status"] == "new" and need["age_hours"] > T_STALE_NEED_HOURS:
            cands.append({
                "rule": "STALE_NEED",
                "proposal": f"escalate need #{need['id']} ({need['item']}) — "
                            "unpromoted, re-broadcast",
                "evidence": f"age {need['age_hours']}h (threshold {T_STALE_NEED_HOURS}h)",
                "suggested_priority": min(10, need["priority"] + 1),
            })
    return cands


def main():
    state = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "queue": queue_state(),
        "worker": worker_state(),
        "bridges": bridge_state(),
        "needs": needs_state(),
        "disk_home": disk_state(),
    }
    snapshot = {"state": state, "candidates": derive_candidates(state)}
    out = json.dumps(snapshot, indent=2)
    print(out)
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            with open(sys.argv[idx + 1], "w") as f:
                f.write(out)


if __name__ == "__main__":
    main()
