#!/usr/bin/env python3
"""proxmox_ctl.py — start/stop/status VMs on Brian's Proxmox cluster.

The elastic actuator for the demand->capacity loop: when DealsDesk's capacity
plan says "we need another sonic worker VM", this is what flips the switch.

Config (env, never hardcoded):
  PROXMOX_HOST        e.g. 100.64.0.5  (or hostname)
  PROXMOX_PORT        default 8006
  PROXMOX_TOKEN       "user@realm!tokenid=secret"  (API token from Datacenter > Permissions > API Tokens)
  PROXMOX_NODE        default node name for VM actions (can be overridden per-call)
  PROXMOX_VERIFY_SSL  "1" to verify (default 0 — homelab self-signed certs)

Usage:
  proxmox_ctl.py list [--node N]
  proxmox_ctl.py status <vmid|name>
  proxmox_ctl.py start <vmid|name> [--live]
  proxmox_ctl.py stop <vmid|name> [--live]
  proxmox_ctl.py shutdown <vmid|name> [--live]

--dry-run is the DEFAULT for start/stop/shutdown. Pass --live to act.
stdlib only. Deterministic, zero tokens.
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.error, urllib.parse

def cfg():
    host = os.environ.get("PROXMOX_HOST")
    if not host:
        sys.exit("PROXMOX_HOST not set — export it (and PROXMOX_TOKEN) first.")
    return {
        "host": host,
        "port": os.environ.get("PROXMOX_PORT", "8006"),
        "token": os.environ.get("PROXMOX_TOKEN", ""),
        "node": os.environ.get("PROXMOX_NODE", ""),
        "verify": os.environ.get("PROXMOX_VERIFY_SSL", "0") == "1",
    }

def api(c, method, path, data=None):
    url = f"https://{c['host']}:{c['port']}/api2/json{path}"
    req = urllib.request.Request(url, method=method)
    if c["token"]:
        req.add_header("Authorization", f"PVEAPIToken={c['token']}")
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        req.data = body
    ctx = None if c["verify"] else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return json.load(r)["data"]
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)["errors"]
        except Exception:
            detail = e.read().decode()[:200]
        sys.exit(f"Proxmox API {e.code}: {detail}")

def resolve_vm(c, ident):
    """ident may be vmid or name -> (node, vmid, name, status)."""
    nodes = [c["node"]] if c["node"] else [
        n["node"] for n in api(c, "GET", "/nodes")]
    for node in nodes:
        for vm in api(c, "GET", f"/nodes/{node}/qemu"):
            if str(vm["vmid"]) == str(ident) or vm.get("name") == ident:
                return node, vm["vmid"], vm.get("name"), vm.get("status")
    sys.exit(f"VM '{ident}' not found on searched nodes.")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--node"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("status"); p.add_argument("vm")
    for name in ("start", "stop", "shutdown"):
        p = sub.add_parser(name); p.add_argument("vm"); p.add_argument("--live", action="store_true")
    a = ap.parse_args()
    c = cfg()

    if a.cmd == "list":
        nodes = [a.node or c["node"]] if (a.node or c["node"]) else [
            n["node"] for n in api(c, "GET", "/nodes")]
        out = []
        for node in nodes:
            if not a.json:
                print(f"== {node} ==")
            for vm in api(c, "GET", f"/nodes/{node}/qemu"):
                rec = {"node": node, "vmid": vm["vmid"], "name": vm.get("name", "-"),
                       "status": vm.get("status", "?"),
                       "cpus": vm.get("cpus"), "mem_mb": vm.get("maxmem", 0) // 1024 // 1024}
                out.append(rec)
                if not a.json:
                    print(f"  {vm['vmid']:>5}  {vm.get('status','?'):>8}  {vm.get('name','-')}  "
                          f"cpus={vm.get('cpus','?')} mem={vm.get('maxmem',0)//1024//1024}MB")
        if a.json:
            print(json.dumps(out))
        return

    node, vmid, name, status = resolve_vm(c, a.vm)
    if a.cmd == "status":
        print(f"{vmid} ({name}) on {node}: {status}")
        return

    action = {"start": "start", "stop": "stop", "shutdown": "shutdown"}[a.cmd]
    if not a.live:
        print(f"DRY-RUN: would {action} VM {vmid} ({name}) on {node} [currently {status}]")
        print("pass --live to act")
        return
    api(c, "POST", f"/nodes/{node}/qemu/{vmid}/status/{action}")
    print(f"sent {action} -> VM {vmid} ({name}) on {node}")

if __name__ == "__main__":
    main()
