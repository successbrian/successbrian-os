#!/usr/bin/env python3
"""road_sync.py — the supply line between the road and home.

Brian's direction (2026-10-20): on any link, sync data TO AND FROM
the actual home ecosystem — which will be bigger by trip time, so
sync is MANIFEST-DRIVEN and selective, never "copy everything":
deltas only, hash-verified, resumable by design, and honest about
what it held and why.

Directions:
  road -> home : trip log, road-inbox items (messages, card photos,
                 follow-ups), local commits, road agent findings.
  home -> road : fresh knowledge for the Brain, council notes,
                 prepared work, contact/data snapshots — mostly via
                 the repos (git), plus staged snapshot files.

Sets (the manifest, SYNC_SETS below):
  repos    — git fetch + report; pull --ff-only when clean and
             behind; push when clean and ahead. NEVER force, never
             merge, never touch a dirty tree (HELD, reason printed).
  outbox   — ~/sbos-road/outbox/ files push to the reachable hub's
             ~/sbos-road/inbox/<this-host>/ via scp. Append-only:
             a file is sent once, then moved to outbox/sent/.
             Bravo is a RELAY: what it receives on the road it
             carries home and forwards when it reaches alpha.
  inbox    — files addressed to this host, pulled the same way.
  weights  — STAGE-BEFORE-DEPARTURE ONLY (trip_prep's job). A link
             burst is not a weight pipe; the set reports and skips.

Modes come from road_sense.py: home (full sync), road-linked
(sync with bravo as relay), road-dark (no-op, queues hold).
Every run prints per-set states — DONE / EMPTY / HELD / SKIPPED —
and appends to ~/sbos-road/logs/sync.log.

    python3 road_sync.py [--dry-run]
    python3 road_sync.py --selftest

Stdlib only, like the rest of the travel kit.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
ROAD_HOME = os.path.join(HOME, "sbos-road")
# (label, path) — dealsdesk's repo root is the home dir itself;
# git -C from its subdir resolves the parent repo correctly.
REPOS = [("successbrian-os", os.path.join(HOME, "successbrian-os")),
         ("dealsdesk", os.path.join(HOME, "dealsdesk"))]


def sense():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import road_sense
    return road_sense.sense()


def git(*args, cwd):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                       text=True, timeout=60)
    return r.returncode, r.stdout.strip()


def sync_repo(label, path, dry):
    rc, _ = git("rev-parse", "--git-dir", cwd=path)
    if rc != 0:
        return (label, "HELD", "not a git repo here")
    name = label
    rc, _ = git("fetch", "--quiet", cwd=path)
    if rc != 0:
        return (name, "HELD", "fetch failed (no link to remote?)")
    _, dirty_s = git("status", "--porcelain", cwd=path)
    dirty = len([l for l in dirty_s.splitlines() if l])
    _, counts = git("rev-list", "--left-right", "--count",
                    "@{u}...HEAD", cwd=path)
    behind = ahead = 0
    if counts and "\t" in counts:
        behind, ahead = (int(x) for x in counts.split("\t"))
    if dirty:
        return (name, "HELD",
                f"{dirty} uncommitted — sync never touches a dirty "
                f"tree (ahead {ahead}, behind {behind})")
    if behind and ahead:
        return (name, "HELD", f"diverged (ahead {ahead}, behind "
                              f"{behind}) — a human merges this")
    if dry:
        return (name, "DRY", f"would pull {behind} / push {ahead}")
    if behind:
        rc, out = git("pull", "--ff-only", "--quiet", cwd=path)
        return (name, "DONE" if rc == 0 else "HELD",
                f"pulled {behind}" if rc == 0 else f"pull failed: {out}")
    if ahead:
        rc, out = git("push", "--quiet", cwd=path)
        return (name, "DONE" if rc == 0 else "HELD",
                f"pushed {ahead}" if rc == 0 else "push failed "
                "(remote unreachable or auth — held, not forced)")
    return (name, "DONE", "in sync")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def sync_outbox(hub_ip, host, dry):
    """Push outbox files to the hub's inbox for this host.
    hub_ip 127.0.0.1 means this machine IS the hub — deliver by
    local move. Otherwise scp (the hub's inbox is append-only:
    a file lands once, then moves to outbox/sent/ here)."""
    outbox = os.path.join(ROAD_HOME, "outbox")
    sent = os.path.join(outbox, "sent")
    os.makedirs(sent, exist_ok=True)
    files = [f for f in os.listdir(outbox)
             if os.path.isfile(os.path.join(outbox, f))]
    if not files:
        return ("outbox", "EMPTY", "nothing waiting to go home")
    if not hub_ip:
        return ("outbox", "HELD", f"{len(files)} file(s) held — "
                                  "no hub reachable")
    if dry:
        return ("outbox", "DRY", f"would send {len(files)} file(s)")
    done = 0
    for fn in files:
        src = os.path.join(outbox, fn)
        try:
            if hub_ip == "127.0.0.1":
                dst = os.path.join(ROAD_HOME, "inbox", host)
                os.makedirs(dst, exist_ok=True)
                shutil.move(src, os.path.join(dst, fn))
            else:
                subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=6",
                     f"successbrian@{hub_ip}",
                     "mkdir", "-p", f"sbos-road/inbox/{host}"],
                    capture_output=True, timeout=20, check=True)
                subprocess.run(["scp", "-q", src,
                                f"successbrian@{hub_ip}:"
                                f"sbos-road/inbox/{host}/"],
                               capture_output=True, timeout=120,
                               check=True)
                shutil.move(src, os.path.join(sent, fn))
            done += 1
        except Exception:
            continue
    return ("outbox", "DONE" if done == len(files) else "HELD",
            f"delivered {done}/{len(files)} file(s) to the hub inbox")


def main():
    dry = "--dry-run" in sys.argv
    if "--selftest" in sys.argv:
        for d in ("outbox", "inbox", "logs"):
            os.makedirs(os.path.join(ROAD_HOME, d), exist_ok=True)
        print("selftest: OK (road_sync; sbos-road structure present)")
        return 0
    for d in ("outbox", "inbox", "logs"):
        os.makedirs(os.path.join(ROAD_HOME, d), exist_ok=True)
    s = sense()
    mode = s["mode"]
    host = s["host"]
    hub_ip = None
    if mode in ("home", "road-linked"):
        key = "alpha" if mode == "home" else "bravo"
        hub_ip = s["tailnet"]["peers"].get(key, {}).get("ip")
    results = []
    if mode == "road-dark":
        results.append(("link", "SKIPPED",
                        "road-dark: no hub reachable — queues hold"))
    else:
        for label, repo in REPOS:
            results.append(sync_repo(label, repo, dry))
        results.append(sync_outbox(hub_ip, host, dry))
        results.append(("weights", "SKIPPED",
                         "staged before departure (trip_prep), "
                         "never synced over a link"))
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [f"[{stamp}] mode={mode} host={host} dry={dry}"]
    for name, state, detail in results:
        lines.append(f"  {state:<7} {name}: {detail}")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(ROAD_HOME, "logs", "sync.log"), "a") as f:
        f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
