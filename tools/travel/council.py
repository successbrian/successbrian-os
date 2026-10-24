#!/usr/bin/env python3
"""council.py — the heartbeat council for the console / road-kit build.

Brian's standing order (2026-10-20): Altair, Meghan and Lyra think
through the build-out with each heartbeat. This script is that
council's clerk. It runs just after Altair's heartbeat (cron :07/:37;
Altair beats at :05/:35, the CEO heartbeat on the :00/:30 timer):

  1. Snapshots the build state (trip_prep verdict, repo state, the
     tail of the previous council note for continuity).
  2. Puts the standing question to each seat through the seat's REAL
     channel, and records the answer verbatim:
       Altair — orchestrator, via Sonic :11439 (the heartbeat's own
                thinking channel).
       Lyra   — the worker/research layer (governor.py's coded loop
                is her logic; her council voice rides Morpheus
                :11437, the logic tier). Findings + gated questions,
                the way Lyra workers file them.
       Meghan — CEO agent, above Altair (business_core). Her engine
                is Prometheus (Gemma 4 26B); until it is served her
                seat is recorded ABSENT with the reason — in Brian's
                own tier design, an unanswered question at her tier
                escalates to Brian.
  3. Writes ONE note: tools/travel/council/YYYY-MM-DD-HHMM.md.

The council THINKS. It does not act: no commits, no config changes,
no messages sent. Notes accumulate uncommitted for Brian / Muse to
build from. Stop switch: remove the council line from crontab.

    python3 council.py             # convene once
    python3 council.py --selftest

Stdlib only, like the rest of the travel kit.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
COUNCIL_DIR = os.path.join(HERE, "council")
HOME = os.path.expanduser("~")

MISSION = """\
Standing mission (Brian, 2026-10-20): unified software — the SBOS
Console on the two travel laptops — that manages Brian's whole
workflow (WhatsApp, contacts, email, documents, SEO strategy,
blogging, coding), integrating SuccessBrian OS, DealsDesk,
AnythingLLM and Altair's second brain, escalating compute to
k11-class nodes when necessary. The two laptops are becoming Brian's DAILY DRIVERS (at home as
well as on the road — 'road' is a mode, not a place), so the
console is his primary daily surface, not trip gear. Brian also
reaches the ecosystem from his phone (Pixel 10 Pro, tailnet
member): a bounded glance/answer/capture tier — and the device
gated questions and alerts should land on. The road kit must be ready for
UNKNOWN work on the Chicago TARDIS train trip (Minneapolis/St. Paul
to Chicago, ~8h, both Dells + k11-bravo as road hub; the trip's
business goal is collecting contacts — "when you're free, call me").
Console v1 exists (Chat/Fleet/Code/Brain rooms live; People/Comms/
Content are planned tiles). SCENARIOS.md holds the 13-scenario
coverage matrix; trip_prep.py is the readiness checker. Each laptop
will also carry a stripped, offline-first Hermes road agent (one
profile per laptop — ROAD_AGENT.md): the console's resident senses
and hands on that machine, sensing battery/link/hubs via
road_sense.py, holding the offline queues, syncing when any link
appears, and filing the trip log home for this council to read."""

SEATS = [
    {
        "name": "Altair",
        "channel": "Sonic :11439 (the heartbeat's thinking channel)",
        "url": "http://127.0.0.1:11439/v1/chat/completions",
        "system": ("You are Altair, orchestrator of Brian's ecosystem. "
                   "You route work across the fleet and the named "
                   "models. Be concrete, brief, and build-focused. "
                   "No flattery, no filler."),
        "ask": ("From the state below: sequence the next three build "
                "steps for the console / road kit, name the top risk, "
                "and say what you would delegate to Lyra's workers. "
                "Under 250 words."),
    },
    {
        "name": "Lyra",
        "channel": "worker layer, voiced via Morpheus :11437 (logic tier)",
        "url": "http://127.0.0.1:11437/v1/chat/completions",
        "system": ("You are Lyra, the worker/research layer of "
                   "Brian's ecosystem. You file findings and gated "
                   "questions for the tiers above you (Altair, then "
                   "Meghan, then Brian). Be precise about what is "
                   "verified vs unknown."),
        "ask": ("From the state below: list what facts are still "
                "missing before the trip, what should be verified "
                "next, and any questions gated for Altair, Meghan or "
                "Brian. Under 250 words."),
    },
    {
        "name": "Meghan",
        "channel": "CEO agent — engine Prometheus (Gemma 4 26B), not yet served",
        "url": None,
        "absent": ("seat vacant: Prometheus is not served on this "
                   "fleet yet. Serving it seats Meghan. Until then "
                   "her questions escalate to Brian."),
        "system": ("You are Meghan, CEO agent of Brian's ecosystem — "
                   "financial and future planning, above Altair."),
        "ask": ("CEO review of the state below: does this build "
                "order serve the business (contacts, content, "
                "clients)? What would you cut or reprioritize? "
                "Under 250 words."),
    },
]


def ask_seat(seat, brief):
    body = json.dumps({
        "messages": [{"role": "system", "content": seat["system"]},
                     {"role": "user", "content": brief + "\n\n" + seat["ask"]}],
        "max_tokens": 550, "temperature": 0.6, "stream": False,
    }).encode()
    req = urllib.request.Request(seat["url"], data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=280) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def snapshot():
    parts = []
    try:
        r = subprocess.run([sys.executable,
                            os.path.join(HERE, "trip_prep.py")],
                           capture_output=True, text=True, timeout=120)
        parts.append("TRIP_PREP (readiness, live):\n" + r.stdout.strip())
    except Exception as e:
        parts.append(f"TRIP_PREP: unavailable ({e})")
    for name, path in (("successbrian-os", "successbrian-os"),
                       ("dealsdesk", "dealsdesk")):
        try:
            out = subprocess.run(
                ["git", "-C", os.path.join(HOME, path), "status",
                 "--porcelain"], capture_output=True, text=True,
                timeout=20).stdout
            n = len([l for l in out.splitlines() if l])
            parts.append(f"REPO {name}: {n} uncommitted changes")
        except Exception as e:
            parts.append(f"REPO {name}: unknown ({e})")
    prev = ""
    try:
        notes = sorted(f for f in os.listdir(COUNCIL_DIR)
                       if f.endswith(".md"))
        if notes:
            with open(os.path.join(COUNCIL_DIR, notes[-1]),
                      encoding="utf-8") as f:
                prev = f.read()[-1500:]
    except Exception:
        pass
    if prev:
        parts.append("PREVIOUS COUNCIL NOTE (tail, for continuity — "
                     "do not repeat settled points):\n" + prev)
    return "\n\n".join(parts)


def convene():
    os.makedirs(COUNCIL_DIR, exist_ok=True)
    lock = os.path.join(COUNCIL_DIR, ".lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 900:
        return "already sitting (lock held)"
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    try:
        now = datetime.now()
        state = snapshot()
        brief = MISSION + "\n\nCURRENT STATE:\n" + state
        lines = [f"# Council — {now:%Y-%m-%d %H:%M}",
                 "", "Standing mission: the unified console + road-kit "
                 "build-out (see council.py MISSION).", "",
                 "## State snapshot", "", "```", state, "```", ""]
        for seat in SEATS:
            lines += [f"## {seat['name']} — {seat['channel']}", ""]
            if not seat["url"]:
                lines += [f"ABSENT — {seat['absent']}", ""]
                continue
            try:
                lines += [ask_seat(seat, brief), ""]
            except Exception as e:
                lines += [f"SEAT ERROR — {e}", ""]
        lines += ["---", "Notes only. No actions taken, nothing "
                  "committed. Recorded by council.py."]
        path = os.path.join(COUNCIL_DIR, f"{now:%Y-%m-%d-%H%M}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def main():
    if "--selftest" in sys.argv:
        print("selftest: OK (council seats: "
              + ", ".join(s["name"] for s in SEATS) + ")")
        return 0
    print(convene())
    return 0


if __name__ == "__main__":
    sys.exit(main())
