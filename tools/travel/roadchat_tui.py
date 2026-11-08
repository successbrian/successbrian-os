#!/usr/bin/env python3
"""roadchat_tui.py — RoadChat in the terminal (SBOS travel kit).

The TUI twin of roadchat.py: same engines, same tools, no browser.
Line-based on purpose — it works over any SSH session, in tmux, on a
console with nothing else alive. Pure Python 3 stdlib.

    python3 roadchat_tui.py [--engine penny|morpheus]

Commands inside the chat:
    /penny /morpheus   switch engine
    /status            ecosystem presence (eco_status, same as web)
    /people <name>     look a person up in the identity layer
    /score             score a listing — paste one line of JSON fields
    /quit              leave
Anything else is a message to the current engine. Replies stream.
"""

import json
import os
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "dealsdesk"))

ENGINES = {"penny": 11438, "morpheus": 11437}

# People lookup (Brian 2026-11-08): same localhost-mouth doctrine
# as the web twin — the alpha people-api shim on 127.0.0.1:8011,
# with the staged snapshot as the road-dark fallback.
PEOPLE_API = "http://127.0.0.1:8011"
PEOPLE_SNAPSHOT = os.path.join(os.path.expanduser("~"), "sbos-road",
                               "people-snapshot.json")


def stream_chat(engine, messages):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % ENGINES[engine],
        data=json.dumps({"model": engine, "messages": messages,
                         "stream": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    acc = ""
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = (json.loads(data)["choices"][0]
                         .get("delta", {}).get("content") or "")
            except Exception:
                delta = ""
            if delta:
                acc += delta
                sys.stdout.write(delta)
                sys.stdout.flush()
    print()
    return acc


def show_status():
    import eco_status
    for label, port in eco_status.ENDPOINTS:
        up, ms = eco_status.probe(port)
        print("  [%s] %s (%s)" % ("up " if up else "DOWN",
                                  label.strip(),
                                  "%d ms" % ms if ms else "—"))
    ts = eco_status.tailnet_peers()
    if ts:
        up = [n for n, o in ts[1] if o]
        print("  tailnet: %s; online peers: %s"
              % (ts[0], ", ".join(up) if up else "none"))


def do_score(line):
    import mini_node_scorer
    try:
        candidate = json.loads(line)
    except Exception as e:
        print("  scorer needs one line of JSON fields (%s)" % e)
        return
    r = mini_node_scorer.score_candidate(candidate)
    print("  verdict: %s — score %s (delivered $%s)"
          % (r["verdict"], r["score"], r["delivered_usd"]))
    for n in r["notes"]:
        print("   · %s" % n)
    for p in r.get("pull_parts") or []:
        print("   pull part: %s" % p)


def do_people(query):
    """Basic /people: ranked candidates from the live endpoint,
    or from the staged snapshot when road-dark (labeled)."""
    import urllib.parse
    try:
        req = urllib.request.Request(
            PEOPLE_API + "/people?q=" + urllib.parse.quote(query))
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results", [])
        if not results:
            print("  no candidates — UNKNOWN: not in the identity "
                  "layer under that name or handle")
            return
        for e in results:
            if e["kind"] == "person":
                print("  person %s  %s  score %.2f  breadth %s/%s  "
                      "[%s]" % (e["person_id"], e["display_name"],
                                e["score"], e.get("profile_count"),
                                e.get("platform_count"),
                                ", ".join(e.get("platforms") or [])))
            else:
                print("  profile %s (unlinked)  %s  score %.2f  [%s]"
                      % (e["profile_id"], e["display_name"],
                         e["score"],
                         ", ".join(e.get("platforms") or [])))
            for r in e.get("reasons") or []:
                print("      - %s" % r)
        print("  (open the web RoadChat People room for the full "
              "card with profile URLs)")
        return
    except Exception as e:
        live_err = e
    try:
        with open(PEOPLE_SNAPSHOT, encoding="utf-8") as f:
            snap = json.load(f)
    except Exception:
        print("  people lookup unavailable — endpoint down (%s) "
              "and no snapshot at %s" % (live_err, PEOPLE_SNAPSHOT))
        return
    print("  road-dark: staged snapshot dated %s"
          % snap.get("generated_at"))
    ql = query.strip().lower()
    qt = set(ql.split())
    hits = 0
    for p in snap.get("people", []):
        name = (p.get("name") or "")
        handles = [(pf.get("handle") or "").lower()
                   for pf in p.get("profiles", [])]
        if (qt and qt <= set(name.lower().split())) \
                or ql in name.lower() \
                or ql.lstrip("@") in handles:
            hits += 1
            print("  person %s  %s  breadth %s/%s"
                  % (p["person_id"], name, p.get("profile_count"),
                     p.get("platform_count")))
            for pf in p.get("profiles", []):
                print("      %s @%s  %s"
                      % (pf.get("platform"), pf.get("handle"),
                         pf.get("profile_url") or "url unknown"))
            print("      %s" % p.get("intel_line"))
    if not hits:
        print("  no candidates in the snapshot — UNKNOWN")


def main(argv):
    if "--selftest" in argv:
        assert set(ENGINES) == {"penny", "morpheus"}
        assert callable(do_people)
        print("selftest: OK")
        return 0
    engine = "morpheus"
    if "--engine" in argv:
        engine = argv[argv.index("--engine") + 1]
    messages = []
    # The C64 greeting (owner request 2026-10-20): the ecosystem opens
    # the way his Commodore 64 did.
    print("**** SBOS TRAVEL CONSOLE ****")
    print("READY.")
    print("RoadChat TUI — engine: %s. /status, /score, /people, "
          "/penny, /morpheus, /quit." % engine)
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line == "/quit":
            return 0
        if line in ("/penny", "/morpheus"):
            engine = line[1:]
            print("  engine: %s" % engine)
            continue
        if line == "/status":
            show_status()
            continue
        if line.startswith("/people"):
            q = line[len("/people"):].strip()
            if q:
                do_people(q)
            else:
                print("  usage: /people <name or handle>")
            continue
        if line == "/score":
            print("  paste candidate JSON, one line:")
            try:
                do_score(input("  json> "))
            except (EOFError, KeyboardInterrupt):
                print()
            continue
        messages.append({"role": "user", "content": line})
        try:
            reply = stream_chat(engine, messages)
            messages.append({"role": "assistant", "content": reply})
        except (urllib.error.URLError, OSError) as e:
            print("  ⚠ engine unreachable — is link_up running? (%s)" % e)
            messages.pop()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
