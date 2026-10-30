#!/usr/bin/env python3
"""capacity.py — local-horsepower sensing + DealsDesk need-filing (WS-CAP).

PURPOSE: Snapshot every verified local inference node, decide from REAL
         signals whether it is saturated, and when saturation is
         SUSTAINED file ONE need into the existing SBOS->DealsDesk loop.
WHY:     Brian (2026-10-27): "we never needed the budget stuff because
         we run local — if we are short on local horsepower,
         SuccessBrian OS tells DealsDesk." There are NO dollar caps or
         budget circuit-breakers here. The scarce resource is local
         horsepower. Cloud spend is not modelled by this module.
CALLED BY: cron */10 (flock-guarded, ~/logs/capacity-sense.log), operator,
         doctor.py / agent_brief.py (read-only readers of its tables).

SIGNALS (only what the endpoints actually return, verified 2026-10-27):
  llama.cpp nodes (sonic :11439, morpheus :11437, penny :11438 — the
  WORKERS in tools/pm/repair_ladder.py):
    GET /health -> {"status":"ok"} (reachability + latency)
    GET /slots  -> [{is_processing: bool, ...}] (busy/total slots)
    /metrics is NOT supported by these builds (501) — never read.
  host node (k11-alpha-local): /proc/loadavg + /proc/meminfo.
  K11 bravo/gamma / node-zero are NOT seeded: no inference endpoint
  for them could be verified in fleet code/config on alpha.

SATURATION RULE (in code, deterministic):
  llama_cpp: reachable AND (all slots busy (slots_total>0 and
             slots_busy>=slots_total) OR health latency > 2000 ms),
             OR unreachable (a down node is zero headroom).
  host:      load1/cpu_count >= 1.0 OR memory pressure >= 90%
             (pressure = 100 * (1 - MemAvailable/MemTotal)).
  SUSTAINED = saturated in >= 6 consecutive snapshots (~1h at the
  10-minute cron cadence).

NEED-FILING SEAM (existing loop, not a new one):
  successbrian_os.sbos_need_requests — SBOS-owned handoff table.
  Its task_id FK requires a public.sbostasks row; the standing,
  active task 18201 "Workload needs handoff (SBOS -> DealsDesk)"
  is the verified owner used by the site-fleet capacity needs
  already in that table (rows 31/32). DealsDesk's own
  needs_intake.py (cron 06:20) promotes status='new' rows into
  dealsdesk.ecosystem_needs — DealsDesk's table, never written here.
  Dedupe: UNIQUE(task_id, item) in sbos_need_requests plus
  capacity_needs.dedupe_key='capacity:<node>' (one standing need
  per node). When saturation clears: our capacity_needs row is
  marked cleared; a still-'new' sbos row is marked 'dropped'
  (SBOS owns it); a promoted row is left to DealsDesk's own
  need_status_sync, and the clearing is noted in pm_decisions.

CLI: init | snapshot | view | file-need <node> (manual/test) | selftest
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guardrails_common as gc  # noqa: E402

LATENCY_SATURATED_MS = 2000
SUSTAINED_N = 6
NEED_TASK_ID = 18201  # standing "Workload needs handoff (SBOS -> DealsDesk)"
SEED_NODES = [
    ("sonic", "127.0.0.1", "http://127.0.0.1:11439", "llama_cpp"),
    ("morpheus", "127.0.0.1", "http://127.0.0.1:11437", "llama_cpp"),
    ("penny", "127.0.0.1", "http://127.0.0.1:11438", "llama_cpp"),
    ("k11-alpha-local", "127.0.0.1", None, "host"),
]


def seed_nodes(cur):
    for name, host, endpoint, kind in SEED_NODES:
        cur.execute(
            """INSERT INTO successbrian_os.capacity_nodes (name, host, endpoint, kind)
               VALUES (%s,%s,%s,%s) ON CONFLICT (name) DO NOTHING""",
            (name, host, endpoint, kind))


def fetch_json(url, timeout=3):
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        latency = int((time.time() - t0) * 1000)
        return r.status, latency, json.loads(body) if body.strip() else None


def probe_node(node):
    """node: dict with name/endpoint/kind. Returns a snapshot dict."""
    snap = {"node_name": node["name"], "reachable": False, "latency_ms": None,
            "slots_total": None, "slots_busy": None, "load1": None,
            "cpu_count": None, "mem_total_mb": None, "mem_available_mb": None,
            "mem_pressure_pct": None, "saturated": False, "detail": {}}
    if node["kind"] == "host":
        try:
            with open("/proc/loadavg") as f:
                load1 = float(f.read().split()[0])
            cpu = os.cpu_count() or 1
            mem = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, rest = line.partition(":")
                    if k in ("MemTotal", "MemAvailable"):
                        mem[k] = int(rest.split()[0]) // 1024
            total, avail = mem.get("MemTotal"), mem.get("MemAvailable")
            pressure = None
            if total and avail is not None:
                pressure = round(100.0 * (1 - avail / total), 2)
            snap.update(reachable=True, load1=load1, cpu_count=cpu,
                        mem_total_mb=total, mem_available_mb=avail,
                        mem_pressure_pct=pressure,
                        saturated=bool((load1 / cpu >= 1.0) or
                                       (pressure is not None and pressure >= 90)),
                        detail={"source": "/proc/loadavg+/proc/meminfo"})
        except Exception as e:
            snap["detail"] = {"error": f"{type(e).__name__}: {e}"}
            snap["saturated"] = True
        return snap
    # llama_cpp
    endpoint = (node.get("endpoint") or "").rstrip("/")
    try:
        status, latency, _ = fetch_json(endpoint + "/health", timeout=3)
        snap["reachable"] = status == 200
        snap["latency_ms"] = latency
    except Exception as e:
        snap["detail"] = {"health_error": f"{type(e).__name__}: {e}"}
        snap["saturated"] = True  # down = zero headroom
        return snap
    try:
        _, _, slots = fetch_json(endpoint + "/slots", timeout=3)
        if isinstance(slots, list):
            snap["slots_total"] = len(slots)
            snap["slots_busy"] = sum(1 for s in slots if s.get("is_processing"))
    except Exception as e:
        snap["detail"]["slots_error"] = f"{type(e).__name__}: {e}"
    all_busy = (snap["slots_total"] not in (None, 0) and
                snap["slots_busy"] is not None and
                snap["slots_busy"] >= snap["slots_total"])
    slow = snap["latency_ms"] is not None and snap["latency_ms"] > LATENCY_SATURATED_MS
    snap["saturated"] = bool(all_busy or slow)
    snap["detail"].update({"all_slots_busy": bool(all_busy),
                           "latency_over_threshold": bool(slow)})
    return snap


def store_snapshot(cur, snap):
    cur.execute(
        """INSERT INTO successbrian_os.capacity_snapshots
             (node_name, reachable, latency_ms, slots_total, slots_busy,
              load1, cpu_count, mem_total_mb, mem_available_mb,
              mem_pressure_pct, saturated, detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id""",
        (snap["node_name"], snap["reachable"], snap["latency_ms"],
         snap["slots_total"], snap["slots_busy"], snap["load1"],
         snap["cpu_count"], snap["mem_total_mb"], snap["mem_available_mb"],
         snap["mem_pressure_pct"], snap["saturated"],
         json.dumps(snap["detail"])))
    return cur.fetchone()[0]


def consecutive_saturated(cur, node_name):
    cur.execute(
        """SELECT saturated FROM successbrian_os.capacity_snapshots
            WHERE node_name=%s ORDER BY taken_at DESC, id DESC LIMIT 50""",
        (node_name,))
    n = 0
    for (sat,) in cur.fetchall():
        if sat:
            n += 1
        else:
            break
    return n


def need_item(node_name):
    return f"local inference capacity: {node_name}"


def file_need(cur, node_name, reason="sustained saturation"):
    """File/update the ONE standing need for a node. Returns (need_row_id, created_bool).
    Dedupe: capacity_needs.dedupe_key + sbos_need_requests UNIQUE(task_id,item)."""
    dedupe = f"capacity:{node_name}"
    item = need_item(node_name)
    specs = (f"Local inference horsepower short on node {node_name}: {reason}. "
             f"Generic workload spec (DealsDesk selects hardware): additional "
             f"local LLM inference capacity for the SBOS fleet; no cloud substitute.")
    cur.execute(
        "SELECT id, sbos_need_request_id FROM successbrian_os.capacity_needs "
        "WHERE dedupe_key=%s AND status='open'", (dedupe,))
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "UPDATE successbrian_os.capacity_needs SET last_checked_at=now() WHERE id=%s",
            (existing[0],))
        return existing[0], False
    # Stage into the SBOS->DealsDesk handoff (SBOS-owned table only).
    cur.execute(
        """INSERT INTO successbrian_os.sbos_need_requests
             (task_id, item, specs, qty, max_cost, priority)
           VALUES (%s,%s,%s,1,NULL,7)
           ON CONFLICT (task_id, item) DO NOTHING RETURNING id""",
        (NEED_TASK_ID, item, specs))
    row = cur.fetchone()
    if row:
        req_id = row[0]
    else:
        cur.execute(
            "SELECT id FROM successbrian_os.sbos_need_requests WHERE task_id=%s AND item=%s",
            (NEED_TASK_ID, item))
        req_id = cur.fetchone()[0]
        # A cleared/dropped prior row with the same key: revive it as a fresh need.
        cur.execute(
            """UPDATE successbrian_os.sbos_need_requests
                  SET status='new', specs=%s, updated_at=now()
                WHERE id=%s AND status IN ('dropped','satisfied')""",
            (specs, req_id))
    cur.execute(
        """INSERT INTO successbrian_os.capacity_needs
             (dedupe_key, node_name, item, sbos_need_request_id, status, notes)
           VALUES (%s,%s,%s,%s,'open',%s)
           ON CONFLICT (dedupe_key) DO UPDATE
             SET status='open', cleared_at=NULL, last_checked_at=now(),
                 sbos_need_request_id=EXCLUDED.sbos_need_request_id,
                 notes=EXCLUDED.notes
           RETURNING id""",
        (dedupe, node_name, item, req_id, reason))
    nid = cur.fetchone()[0]
    gc.pm_core.decide(cur, "capacity-sense",
                      f"Capacity need filed to DealsDesk loop: {item} ({reason})",
                      origin="system")
    return nid, True


def clear_need_if_open(cur, node_name):
    dedupe = f"capacity:{node_name}"
    cur.execute(
        "SELECT id, sbos_need_request_id FROM successbrian_os.capacity_needs "
        "WHERE dedupe_key=%s AND status='open'", (dedupe,))
    row = cur.fetchone()
    if not row:
        return False
    nid, req_id = row
    cur.execute(
        "UPDATE successbrian_os.capacity_needs SET status='cleared', "
        "cleared_at=now(), last_checked_at=now() WHERE id=%s", (nid,))
    if req_id:
        # SBOS owns sbos_need_requests: a not-yet-promoted need is dropped;
        # a promoted one belongs to DealsDesk — leave it, note the clearing.
        cur.execute(
            "UPDATE successbrian_os.sbos_need_requests SET status='dropped', "
            "updated_at=now() WHERE id=%s AND status='new'", (req_id,))
    gc.pm_core.decide(cur, "capacity-sense",
                      f"Capacity need cleared (saturation ended): {need_item(node_name)}",
                      origin="system")
    return True


def run_snapshot():
    c = gc.conn()
    cur = c.cursor()
    gc.ensure_schema(cur)
    seed_nodes(cur)
    c.commit()
    cur.execute("SELECT name, host, endpoint, kind FROM successbrian_os.capacity_nodes WHERE enabled ORDER BY name")
    nodes = [{"name": r[0], "host": r[1], "endpoint": r[2], "kind": r[3]} for r in cur.fetchall()]
    lines = []
    for node in nodes:
        snap = probe_node(node)
        store_snapshot(cur, snap)
        c.commit()
        streak = consecutive_saturated(cur, node["name"])
        state = "SATURATED" if snap["saturated"] else "ok"
        lines.append(f"{node['name']}: reachable={snap['reachable']} {state} "
                     f"streak={streak} latency_ms={snap['latency_ms']} "
                     f"slots={snap['slots_busy']}/{snap['slots_total']}")
        if streak >= SUSTAINED_N:
            nid, created = file_need(cur, node["name"],
                                     reason=f"saturated {streak} consecutive snapshots")
            c.commit()
            lines.append(f"  need: {'filed' if created else 'already open'} "
                         f"(capacity_needs id={nid})")
        elif not snap["saturated"]:
            if clear_need_if_open(cur, node["name"]):
                c.commit()
                lines.append("  need: cleared (saturation ended)")
    c.close()
    for ln in lines:
        print(ln)
    return lines


def view():
    c = gc.conn()
    cur = c.cursor()
    gc.ensure_schema(cur)
    seed_nodes(cur)
    c.commit()
    lines = ["Capacity — local horsepower (no dollar caps; scarcity = local compute)"]
    cur.execute("SELECT name, endpoint, kind FROM successbrian_os.capacity_nodes ORDER BY name")
    for name, endpoint, kind in cur.fetchall():
        cur.execute(
            """SELECT reachable, latency_ms, slots_total, slots_busy, load1, cpu_count, mem_pressure_pct, saturated, taken_at
                 FROM successbrian_os.capacity_snapshots
                WHERE node_name=%s ORDER BY taken_at DESC, id DESC LIMIT 1""",
            (name,))
        s = cur.fetchone()
        streak = consecutive_saturated(cur, name)
        if not s:
            lines.append(f"{name} ({kind}): no snapshots yet")
            continue
        reachable, latency_ms, slots_total, slots_busy, load1, cpu_count, mem_pressure_pct, saturated, taken_at = s
        if kind == "host":
            head = f"load1={load1}/{cpu_count}cpu mem_pressure={mem_pressure_pct}%"
        else:
            free = None
            if slots_total is not None and slots_busy is not None:
                free = slots_total - slots_busy
            head = f"slots_free={free} latency_ms={latency_ms} reachable={reachable}"
        lines.append(f"{name} ({kind}): {head} saturated={saturated} consecutive_saturated={streak} at {taken_at}")
    cur.execute(
        "SELECT dedupe_key, item, first_filed_at FROM successbrian_os.capacity_needs "
        "WHERE status='open' ORDER BY first_filed_at")
    needs = cur.fetchall()
    lines.append(f"Open capacity needs: {len(needs)}")
    for dedupe_key, item, first_filed_at in needs:
        lines.append(f"  - {item} (key={dedupe_key}, since {first_filed_at})")
    c.close()
    for ln in lines:
        print(ln)
    return lines


def selftest():
    passed = total = 0

    def check(cond, label):
        nonlocal passed, total
        total += 1
        assert cond, label
        passed += 1
        print(f"PASS {label}")

    c = gc.conn()
    cur = c.cursor()
    gc.ensure_schema(cur)
    seed_nodes(cur)
    c.commit()
    cur.execute("SELECT count(*) FROM successbrian_os.capacity_nodes WHERE name IN ('sonic','morpheus','penny','k11-alpha-local')")
    check(cur.fetchone()[0] == 4, "seed contains exactly the 4 verified nodes")
    # Probe logic against a synthetic node dict (no live dependency)
    fake = {"name": "selftest", "kind": "host", "endpoint": None}
    snap = probe_node(fake)
    check("load1" in snap and snap["reachable"] is True, "host probe returns real /proc signals")
    # Sustained-need filing + dedupe, fixture node, self-cleaning
    cur.execute("INSERT INTO successbrian_os.capacity_nodes (name, kind) VALUES ('selftest-node','host') ON CONFLICT (name) DO NOTHING")
    c.commit()
    nid1, created1 = file_need(cur, "selftest-node", reason="selftest fixture")
    c.commit()
    nid2, created2 = file_need(cur, "selftest-node", reason="selftest fixture")
    c.commit()
    check(created1 and not created2 and nid1 == nid2, "need-filing dedupes to ONE standing need per node")
    cur.execute("SELECT count(*) FROM successbrian_os.sbos_need_requests WHERE task_id=%s AND item=%s",
                (NEED_TASK_ID, need_item("selftest-node")))
    check(cur.fetchone()[0] == 1, "exactly one sbos_need_requests row staged for DealsDesk intake")
    cleared = clear_need_if_open(cur, "selftest-node")
    c.commit()
    check(cleared, "clearing an open need succeeds when saturation ends")
    # cleanup fixtures
    cur.execute("DELETE FROM successbrian_os.sbos_need_requests WHERE task_id=%s AND item=%s",
                (NEED_TASK_ID, need_item("selftest-node")))
    cur.execute("DELETE FROM successbrian_os.capacity_needs WHERE dedupe_key='capacity:selftest-node'")
    cur.execute("DELETE FROM successbrian_os.capacity_nodes WHERE name='selftest-node'")
    cur.execute("DELETE FROM successbrian_os.pm_decisions WHERE decision LIKE '%selftest-node%'")
    c.commit()
    c.close()
    print(f"SELFTEST OK: capacity {passed}/{total}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS capacity sensing (WS-CAP)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("snapshot")
    sub.add_parser("view")
    fn = sub.add_parser("file-need")
    fn.add_argument("node")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "init":
        c = gc.conn(); cur = c.cursor(); gc.ensure_schema(cur); seed_nodes(cur); c.commit(); c.close()
        print("capacity schema ready; nodes seeded (verified endpoints only)")
        return 0
    if args.cmd == "snapshot":
        run_snapshot(); return 0
    if args.cmd == "view":
        view(); return 0
    if args.cmd == "file-need":
        c = gc.conn(); cur = c.cursor(); gc.ensure_schema(cur); seed_nodes(cur)
        nid, created = file_need(cur, args.node, reason="manual file-need")
        c.commit(); c.close()
        print(f"need id={nid} {'created' if created else 'already open'}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
