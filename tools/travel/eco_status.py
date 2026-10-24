#!/usr/bin/env python3
"""eco_status.py — is my ecosystem there? (SBOS travel kit, piece #1)

Brian 2026-10-20: the travel laptops exist "so I don't feel so
disconnected from my ecosystem." This tool is the presence check: one
command, run on a travel laptop (or at home), that answers — in plain
lines, in seconds — whether the ecosystem is reachable and alive:

  - the tailnet: am I on it, is k11-alpha online, which peers are up
  - the home endpoints: Morpheus, Penny, the dashboard API
  - the code: SBOS / DealsDesk clone state (branch, dirty, ahead/behind)

Modes: --home probes localhost (run on k11-alpha itself); --away probes
through the tunnel/tailnet addresses a travel laptop would use
(127.0.0.1 after `ssh -L` tunnels are up — see tools/travel/README.md).
Pure Python 3 stdlib, like everything in the doctrine stack: it runs
on a fresh Ubuntu laptop with nothing installed.

Exit code 0 = everything probed is up; 1 = something is down (the
report says what). --selftest checks the tool's own wiring only.
"""

import json
import subprocess
import sys
import time
import urllib.request

HOME_TAILNET_IP = "100.118.53.47"     # k11-alpha
HOME_HOSTNAME = "k11-alpha"

# (display name, path) — probed at 127.0.0.1:<port> in both modes: at
# home that is the service itself; away, it is the SSH tunnel's mouth.
ENDPOINTS = [
    ("Morpheus  (Qwen2.5-14B, Altair's engine)", 11437),
    ("Penny     (Qwen2.5-7B worker)", 11438),
    ("Dashboard API", 8000),
]

REPOS = ["successbrian-os", "dealsdesk"]


def probe(port, timeout=2.0):
    """True + latency ms if an HTTP server answers on 127.0.0.1:port."""
    url = "http://127.0.0.1:%d/" % port
    t0 = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(64)
        return True, int((time.time() - t0) * 1000)
    except urllib.error.HTTPError:
        # Any HTTP answer at all (even 404) means the service is alive.
        return True, int((time.time() - t0) * 1000)
    except Exception:
        return False, None


def tailnet_peers():
    """(self_name, [(name, online), ...]) via the tailscale CLI, or None."""
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
                             capture_output=True, text=True, timeout=6)
        data = json.loads(out.stdout)
    except Exception:
        return None
    peers = []
    seen = set()
    for peer in (data.get("Peer") or {}).values():
        name = peer.get("HostName", "?")
        key = name.lower()
        # Tailscale infrastructure nodes (Funnel ingress) are not Brian's
        # machines — and shared nodes appear once per share. Presence is
        # about HIS fleet: dedupe and keep only real devices.
        if "funnel-ingress" in key or key in seen:
            continue
        seen.add(key)
        peers.append((name, bool(peer.get("Online"))))
    self_name = (data.get("Self") or {}).get("HostName", "?")
    return self_name, sorted(peers)


def repo_state(path):
    """(branch, dirty_count, ahead_behind_str) for a git repo, or None."""
    def git(*args):
        return subprocess.run(["git", "-C", path] + list(args),
                              capture_output=True, text=True,
                              timeout=6).stdout.strip()
    try:
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        if not branch:
            return None
        dirty = len([l for l in git("status", "--porcelain").splitlines()
                     if l.strip()])
        track = git("status", "-sb").splitlines()[0]
        ab = track.split("[", 1)[1].rstrip("]") if "[" in track else "in sync"
        return branch, dirty, ab
    except Exception:
        return None


def main(argv):
    if "--selftest" in argv:
        assert HOME_TAILNET_IP.startswith("100.")
        assert len(ENDPOINTS) >= 3 and len(REPOS) == 2
        print("selftest: OK (config sane; no network probed)")
        return 0
    import os
    home_mode = "--home" in argv
    all_up = True
    print("== ecosystem status (%s) ==" % ("home" if home_mode else "away"))

    ts = tailnet_peers()
    if ts is None:
        print("  [?] tailnet: tailscale CLI not answering here")
    else:
        self_name, peers = ts
        print("  tailnet: this machine is '%s'; %d peer(s) known"
              % (self_name, len(peers)))
        for name, online in peers:
            mark = "up " if online else "off"
            if name == HOME_HOSTNAME and not online:
                all_up = False
            print("    [%s] %s" % (mark, name))

    for label, port in ENDPOINTS:
        up, ms = probe(port)
        if not up:
            all_up = False
        where = "127.0.0.1:%d" % port
        print("  [%s] %s (%s)%s"
              % ("up " if up else "DOWN", label, where,
                 " %d ms" % ms if ms is not None else ""))

    home_dir = os.path.expanduser("~")
    for repo in REPOS:
        st = repo_state(os.path.join(home_dir, repo))
        if st is None:
            print("  [?] %s: no clone at ~/%s" % (repo, repo))
        else:
            branch, dirty, ab = st
            print("  [git] %s: %s, %d uncommitted change(s), %s"
                  % (repo, branch, dirty, ab))

    # The ecosystem greets Brian the way his Commodore 64 did
    # (owner request 2026-10-20): when everything is up, the word is
    # READY. — full stop, capital, period, just like 1982.
    print("== %s ==" % ("READY." if all_up
                         else "NOT READY. — see lines above"))
    return 0 if all_up else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
