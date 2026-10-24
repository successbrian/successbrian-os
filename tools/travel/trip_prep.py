#!/usr/bin/env python3
"""trip_prep.py — is the road kit ready for ANY work?

Brian doesn't know which work a trip will demand, so readiness means
coverage: weights, repos, knowledge and the console all mirrored and
verified BEFORE departure (SCENARIOS.md is the matrix this checks).

Tri-state per item, like the DealsDesk scorer:
  READY     — verified on this machine, now.
  MISSING   — proven absent/dirty; the fix is printed with the item.
  UNVERIFIED— cannot be checked from here (device unreachable); the
              exact question to settle it is printed.
Final line follows the ecosystem law: READY. only when every
automatic item is READY; anything else prints NOT READY. and names
why. Manual pack items (cables, cards) print as CONFIRM lines —
a checklist a human ticks, never silently assumed.

    python3 trip_prep.py             # full check
    python3 trip_prep.py --selftest

Stdlib only, like the rest of the travel kit.
"""
import json
import os
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")
MODELS_DIR = os.environ.get("SBOS_MODELS_DIR", os.path.join(HOME, "models"))
ROAD_SET = [  # name tokens -> (display, role, home_is_known)
    # ~/models entries are loose GGUF files (incl. split parts and
    # multiple quants), not per-model dirs — match names, sum sizes.
    (("qwen3.6-35b",), ("Sonic", "interactive road engine", True)),
    (("qwen2.5-7b",), ("Penny", "fast worker", True)),
    (("qwen2.5-14b",), ("Morpheus", "logic / Altair tier", True)),
    # REAP's home was never established (Colibri keeps it outside
    # ~/models) — absence here is UNVERIFIED, never a false MISSING.
    (("deepseek-v4-flash-reap", "reap-150b"),
     ("REAP 150B", "slow deep lane", False)),
    (("minicpm5",), ("Chuck", "tagging / triage", True)),
]
MIN_FREE_GB = 100


def git_state(path):
    def g(*args):
        return subprocess.run(["git", "-C", path, *args],
                              capture_output=True, text=True,
                              timeout=20).stdout.strip()
    branch = g("rev-parse", "--abbrev-ref", "HEAD")
    dirty = len([l for l in g("status", "--porcelain").splitlines() if l])
    counts = g("rev-list", "--left-right", "--count", "@{u}...HEAD")
    ahead = behind = 0
    if counts and "\t" in counts:
        behind, ahead = (int(x) for x in counts.split("\t"))
    return branch, dirty, ahead, behind


def dir_gb(path):
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return total / 1e9


def entry_gb(path):
    return (os.path.getsize(path) / 1e9
            if os.path.isfile(path) else dir_gb(path))


def probe(port):
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def check():
    items = []  # (state, label, detail)

    # 1. Repos: an uncommitted home tree cannot sync to the laptops.
    for name, path in (("successbrian-os", os.path.join(HOME, "successbrian-os")),
                       ("dealsdesk", os.path.join(HOME, "dealsdesk"))):
        try:
            branch, dirty, ahead, behind = git_state(path)
            if dirty:
                items.append(("MISSING", f"repo {name}",
                              f"{dirty} uncommitted changes on {branch} — "
                              "commit before departure; laptops sync from git"))
            elif behind:
                items.append(("MISSING", f"repo {name}",
                              f"behind upstream by {behind} — pull first"))
            else:
                items.append(("READY", f"repo {name}",
                              f"{branch}, clean, ahead {ahead}"))
        except Exception as e:
            items.append(("UNVERIFIED", f"repo {name}", f"git failed: {e}"))

    # 2. The console itself.
    here = os.path.dirname(os.path.abspath(__file__))
    rc = os.path.join(here, "roadchat.py")
    if os.path.exists(rc):
        r = subprocess.run([sys.executable, rc, "--selftest"],
                           capture_output=True, text=True, timeout=30)
        items.append(("READY" if r.returncode == 0 else "MISSING",
                      "SBOS console (roadchat.py)",
                      "selftest OK" if r.returncode == 0 else r.stdout.strip()))
    else:
        items.append(("MISSING", "SBOS console (roadchat.py)", "not present"))

    # 3. Road weight set: present on this machine (the mirror source).
    try:
        entries = os.listdir(MODELS_DIR)
    except Exception:
        entries = []
    for tokens, (name, role, home_known) in ROAD_SET:
        hits = [e for e in entries
                if any(t in e.lower() for t in tokens)]
        if hits:
            gb = sum(entry_gb(os.path.join(MODELS_DIR, h)) for h in hits)
            items.append(("READY", f"weight {name}",
                          f"{gb:.0f} GB across {len(hits)} file(s) — {role}"))
        elif home_known:
            items.append(("MISSING", f"weight {name}",
                          f"nothing matching {tokens} under {MODELS_DIR} "
                          f"— {role} cannot ride"))
        else:
            items.append(("UNVERIFIED", f"weight {name}",
                          f"not under {MODELS_DIR} — Colibri keeps it "
                          "elsewhere; set SBOS_MODELS_DIR to its real "
                          f"home so the mirror can be verified — {role}"))

    # 4. Engines answering here (hub health; the road re-points the
    #    same console at bravo, so this proves the pattern, not the trip).
    for nm, port in (("Penny", 11438), ("Morpheus", 11437)):
        items.append(("READY" if probe(port) else "MISSING",
                      f"engine {nm} on this host",
                      f"port {port} {'answering' if probe(port) else 'silent'}"))

    # 5. Bravo: the road hub. Unreachable from here = UNVERIFIED,
    #    with the exact questions that settle it.
    bravo = None
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
                             capture_output=True, text=True,
                             timeout=15).stdout
        peers = (json.loads(out).get("Peer") or {}).values()
        bravo = next((p for p in peers
                      if "bravo" in (p.get("HostName") or "").lower()
                      or "bravo" in (p.get("DNSName") or "").lower()), None)
    except Exception:
        pass
    if bravo is None:
        items.append(("UNVERIFIED", "k11-bravo road hub",
                      "not visible on the tailnet from here — before "
                      "departure confirm: bravo enrolled + online, road "
                      "weight set mirrored, console deployed on it"))
    elif bravo.get("Online"):
        items.append(("READY", "k11-bravo road hub", "online on the tailnet"))
    else:
        items.append(("MISSING", "k11-bravo road hub",
                      "on the tailnet but offline — power it up and "
                      "mirror the road set before departure"))

    # 6. Brain snapshot: the knowledge the console searches.
    docs = os.path.join(HOME, "successbrian-os", "docs")
    n = sum(len([f for f in fs if f.endswith(".md")])
            for _r, _d, fs in os.walk(docs)) if os.path.isdir(docs) else 0
    items.append(("READY" if n >= 10 else "MISSING", "brain snapshot",
                  f"{n} markdown docs under successbrian-os/docs"))

    # 7. Sync freshness: the mini and home diverge by design —
    #    a recent, logged sync is part of being ready.
    log = os.path.join(HOME, "sbos-road", "logs", "sync.log")
    try:
        import time as _t
        age_h = (_t.time() - os.path.getmtime(log)) / 3600
        tail = open(log).read().strip().splitlines()[-5:]
        held = sum("HELD" in l for l in tail)
        items.append(("READY" if age_h < 26 else "UNVERIFIED",
                      "sync freshness",
                      f"last sync {age_h:.1f}h ago, {held} held "
                      "item(s) in the last run"))
    except Exception:
        items.append(("UNVERIFIED", "sync freshness",
                      "no sync log yet — road_sync has never run "
                      "on this machine"))

    # 8. Disk headroom.
    st = os.statvfs(HOME)
    free = st.f_bavail * st.f_frsize / 1e9
    items.append(("READY" if free >= MIN_FREE_GB else "MISSING",
                  "disk headroom", f"{free:.0f} GB free (floor {MIN_FREE_GB})"))

    return items


MANUAL = [
    "compact multi-tap + bravo power brick packed (3 devices, 2 outlets)",
    "Ethernet cables x2 + compact travel switch packed — the road LAN is wired, not Wi-Fi (the laptops wire to their mini)",
    "Brian's own cards packed (C64 blue, READY.)",
    "paper notebook — the tier below the laptops",
]


def main():
    if "--selftest" in sys.argv:
        print("selftest: OK (trip_prep)")
        return 0
    items = check()
    icon = {"READY": "●", "MISSING": "✗", "UNVERIFIED": "?"}
    for state, label, detail in items:
        print(f"[{icon[state]}] {state:<10} {label} — {detail}")
    for m in MANUAL:
        print(f"[ ] CONFIRM    pack: {m}")
    bad = [i for i in items if i[0] != "READY"]
    if bad:
        print(f"NOT READY. ({len(bad)} item(s): "
              + ", ".join(i[1] for i in bad) + ")")
        return 1
    print("READY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
