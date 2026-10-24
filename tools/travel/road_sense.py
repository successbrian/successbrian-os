#!/usr/bin/env python3
"""road_sense.py — what does THIS machine know about its situation?

The road agent's senses (ROAD_AGENT.md). One JSON report:
battery, link, tailnet, which hubs answer, whether the console is
up, disk headroom — and a derived MODE the ladder keys off:

  home        — k11-alpha's engines answer (full fleet behind them)
  road-linked — k11-bravo answers, alpha doesn't (the train LAN)
  road-dark   — no hub answers (offline; capture + queue posture)

Every probe degrades to null on failure — a sense that can't be
read says so; it never guesses. Stdlib only.

    python3 road_sense.py             # JSON report
    python3 road_sense.py --selftest
"""
import json
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime

ENGINE_PORTS = (11437, 11438)  # Morpheus, Penny — hub liveness proof


def battery():
    base = "/sys/class/power_supply"
    out = {"present": False, "percent": None, "charging": None}
    try:
        for name in os.listdir(base):
            p = os.path.join(base, name)
            try:
                if open(os.path.join(p, "type")).read().strip() != "Battery":
                    continue
                out["present"] = True
                out["percent"] = int(
                    open(os.path.join(p, "capacity")).read().strip())
                out["charging"] = open(
                    os.path.join(p, "status")).read().strip() == "Charging"
            except Exception:
                continue
    except Exception:
        pass
    return out


def link():
    route = False
    ssid = None
    try:
        r = subprocess.run(["ip", "route", "show", "default"],
                           capture_output=True, text=True, timeout=5)
        route = bool(r.stdout.strip())
    except Exception:
        pass
    try:
        r = subprocess.run(["iwgetid", "-r"], capture_output=True,
                           text=True, timeout=5)
        ssid = r.stdout.strip() or None
    except Exception:
        pass
    return {"default_route": route, "wifi_ssid": ssid}


def tailnet():
    try:
        r = subprocess.run(["tailscale", "status", "--json"],
                           capture_output=True, text=True, timeout=8)
        data = json.loads(r.stdout)
    except Exception:
        return {"installed": False, "self": None, "peers": {}}
    peers = {}
    for p in (data.get("Peer") or {}).values():
        name = (p.get("HostName") or "").lower()
        for key in ("alpha", "bravo"):
            if key in name:
                ips = p.get("TailscaleIPs") or [None]
                peers[key] = {"online": bool(p.get("Online")),
                              "ip": ips[0]}
    self_name = (data.get("Self") or {}).get("HostName")
    return {"installed": True, "self": self_name, "peers": peers}


def engines_answer(ip):
    if not ip:
        return False
    for port in ENGINE_PORTS:
        try:
            req = urllib.request.Request(
                f"http://{ip}:{port}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            continue
    return False


def identity():
    """Who is this machine — PUBLIC fingerprints only, nothing that
    must stay secret. Home keeps the registry of known bundles
    (recorded at provisioning, with Brian present); a bundle that
    doesn't match the registry is a random device, whatever its
    hostname claims. The full machine-id never leaves the laptop —
    only a hash prefix travels."""
    import glob
    import hashlib
    bundle = {"host": socket.gethostname(), "machine_id_hash": None,
              "ssh_host_keys": {}, "tailnet_node": None}
    try:
        mid = open("/etc/machine-id").read().strip()
        bundle["machine_id_hash"] = hashlib.sha256(
            mid.encode()).hexdigest()[:16]
    except Exception:
        pass
    for pub in sorted(glob.glob("/etc/ssh/ssh_host_*_key.pub")):
        try:
            r = subprocess.run(["ssh-keygen", "-lf", pub],
                               capture_output=True, text=True, timeout=5)
            parts = r.stdout.split()
            if len(parts) >= 2:
                kind = os.path.basename(pub).replace(
                    "ssh_host_", "").replace("_key.pub", "")
                bundle["ssh_host_keys"][kind] = parts[1]
        except Exception:
            continue
    try:
        r = subprocess.run(["tailscale", "status", "--json"],
                           capture_output=True, text=True, timeout=8)
        bundle["tailnet_node"] = (json.loads(r.stdout)
                                  .get("Self") or {}).get("ID")
    except Exception:
        pass
    return bundle


def console_up():
    try:
        s = socket.create_connection(("127.0.0.1", 8799), timeout=1.5)
        s.close()
        return True
    except Exception:
        return False


def sense():
    bat = battery()
    lnk = link()
    ts = tailnet()
    # Running ON a hub: the hub is self, not a peer — probe loopback.
    self_low = (ts.get("self") or "").lower()
    for key in ("alpha", "bravo"):
        if key in self_low and key not in ts["peers"]:
            ts["peers"][key] = {"online": True, "ip": "127.0.0.1"}
    hubs = {}
    for key in ("alpha", "bravo"):
        peer = ts["peers"].get(key)
        hubs[key] = {"peer": bool(peer),
                     "online": bool(peer and peer["online"]),
                     "engines": engines_answer(peer["ip"]) if peer else False}
    if hubs["alpha"]["engines"]:
        mode = "home"
    elif hubs["bravo"]["engines"]:
        mode = "road-linked"
    elif ts["installed"] or lnk["default_route"]:
        mode = "road-dark"
    else:
        mode = "road-dark"
    st = os.statvfs(os.path.expanduser("~"))
    return {
        "host": socket.gethostname(),
        "identity": identity(),
        "at": datetime.now().isoformat(timespec="seconds"),
        "battery": bat,
        "power": ("battery" if bat["present"] and not bat["charging"]
                  else "ac" if bat["present"] else "no-battery"),
        "link": lnk,
        "tailnet": ts,
        "hubs": hubs,
        "console_up": console_up(),
        "disk_free_gb": round(st.f_bavail * st.f_frsize / 1e9),
        "mode": mode,
    }


def main():
    if "--selftest" in sys.argv:
        r = sense()
        need = {"host", "identity", "battery", "link", "tailnet",
                "hubs", "console_up", "disk_free_gb", "mode"}
        assert need <= set(r), f"missing keys: {need - set(r)}"
        assert r["mode"] in ("home", "road-linked", "road-dark")
        print(f"selftest: OK (mode={r['mode']}, "
              f"battery present={r['battery']['present']})")
        return 0
    print(json.dumps(sense(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
