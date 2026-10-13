#!/usr/bin/env python3
"""capacity_reconciler.py — closes the demand -> capacity loop for Sonic.

Reads desired Sonic worker count from the open need-signal, compares with
actually-running sonic-worker-* VMs across the Proxmox fleet, and starts or
stops VMs to match. Brian's order (2026-10-13): "if sonic is needed a lot we
fire up as many vms everywhere as needed to work work work."

Governors (no runaway):
- desired comes from the demand signal qty (ceil(queue/4)) — never invented.
- MAX_SONIC_VMS ceiling; exceeding it screams to Brian and clamps.
- scale-down only when the easy queue is fully drained (no flapping).
- dry-run default; --live acts.

Each sonic-worker VM runs harness_worker.py --engine sonic on its own cron;
atomic claiming (UPDATE ... WHERE status='queued') makes N workers safe.
DealsDesk provisions the VM templates; this script only starts/stops.

Usage: capacity_reconciler.py [--live]
Cron: every 30 min, staggered (9,39).
"""
import argparse, json, subprocess, sys
from datetime import datetime, timezone

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-t", "-A", "-F", "\x1f"]
CTL = "/home/successbrian/successbrian-os/tools/capacity/proxmox_ctl.py"
PREFIX = "sonic-worker-"
MAX_SONIC_VMS = 12
ITEM = "sonic inference capacity"

def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"PSQL ERROR: {r.stderr.strip()}", file=sys.stderr)
        return []
    return [ln.split("\x1f") for ln in r.stdout.strip().split("\n") if ln.strip()]

def scalar(sql, default="0"):
    rows = q(sql)
    return rows[0][0] if rows and rows[0][0] not in ("", None) else default

def ctl_json(*args):
    r = subprocess.run(["/usr/bin/python3", CTL, *args], capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stderr.strip()[:200]
    try:
        return json.loads(r.stdout), ""
    except Exception as e:
        return None, f"bad json: {e}"

def ctl_act(action, vmid, live):
    cmd = ["/usr/bin/python3", CTL, action, str(vmid)] + (["--live"] if live else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[:200])

def scream(subject, body):
    body_e = body.replace("'", "''")
    q(f"INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
      f"VALUES ('successbrian-os','dealsdesk','{subject}','{body_e}','important')")
    print(f"screamed: {subject}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc).isoformat()

    # desired from the open demand signal
    sig = q(f"SELECT id, qty FROM successbrian_os.sbos_need_requests "
            f"WHERE item='{ITEM}' AND status='new' ORDER BY id DESC LIMIT 1")
    desired = int(sig[0][1]) if sig else 0
    queue = int(scalar(
        "SELECT count(*) FROM successbrian_os.harness_jobs "
        "WHERE status IN ('queued','working') AND difficulty='easy'"))

    if desired > MAX_SONIC_VMS:
        scream(f"sonic demand {desired} exceeds ceiling {MAX_SONIC_VMS}",
               f"Open signal wants {desired} sonic workers; clamped to {MAX_SONIC_VMS}. "
               f"Brian: queue is very deep or stuck — needs your call.")
        desired = MAX_SONIC_VMS

    vms, err = ctl_json("list", "--json")
    if vms is None:
        print(f"[{now}] proxmox unreachable ({err}) — desired={desired} sonic workers, "
              f"queue={queue}. Configure PROXMOX_HOST/PROXMOX_TOKEN to enable elastic scale.")
        if desired > 0:
            scream("sonic workers desired but proxmox not configured",
                   f"Demand signal wants {desired} sonic workers (queue={queue}) but the "
                   f"Proxmox actuator has no endpoint configured. Set PROXMOX_HOST + "
                   f"PROXMOX_TOKEN on the control node.")
        return 0

    fleet = [v for v in vms if str(v.get("name", "")).startswith(PREFIX)]
    running = [v for v in fleet if v.get("status") == "running"]
    stopped = [v for v in fleet if v.get("status") == "stopped"]
    print(f"[{now}] desired={desired} running={len(running)} stopped={len(stopped)} "
          f"queue={queue} live={args.live}")

    if len(running) < desired:
        need = desired - len(running)
        if not stopped:
            scream("sonic worker VM pool exhausted",
                   f"Need {need} more sonic workers (desired={desired}) but no stopped "
                   f"{PREFIX}* VMs exist. DealsDesk: provision more from template.")
            return 0
        for v in stopped[:need]:
            print(f"{'starting' if args.live else 'would start'} {v['name']} ({v['vmid']}) on {v['node']}")
            ctl_act("start", v["vmid"], args.live)
    elif len(running) > desired and queue == 0:
        excess = len(running) - desired
        for v in sorted(running, key=lambda x: x["vmid"], reverse=True)[:excess]:
            print(f"{'stopping' if args.live else 'would stop'} {v['name']} ({v['vmid']}) on {v['node']} (queue drained)")
            ctl_act("stop", v["vmid"], args.live)
    else:
        print("fleet matches demand — nothing to do")
    return 0

if __name__ == "__main__":
    main()
