#!/bin/bash
# Atlas seed: the daily-driver platform upgrade program (2026-10-20).
# Born in the 2026-10-20 session: SBOS Console v1, heartbeat council,
# road kit (senses/sync/prep), and the planning corpus in
# successbrian-os/tools/travel/ (DAILY_WORKFLOWS.md, ROAD_AGENT.md,
# SCENARIOS.md). Nodes point at those docs — Atlas tracks, the docs
# hold the substance. One source of truth.
cd /home/successbrian/successbrian-os/tools/atlas
A="python3 atlas.py"
N() { $A add-node "$1" "$2" "$3" --status "$4" --details "$5"; }
E() { if [ -n "$4" ]; then $A add-edge "$1" "$2" "$3" --notes "$4"; else $A add-edge "$1" "$2" "$3"; fi; }

# ---------- PROJECT ----------
N proj:daily-driver-platform project "Daily-driver laptops + SBOS Console platform" active '{"note":"the two Dell laptops become Brians daily drivers (home + road); unified console manages the whole workflow (WhatsApp, contacts, email, documents, SEO, blogging, coding); road is a mode, not a place. Docs: tools/travel/DAILY_WORKFLOWS.md"}'

# ---------- PLANS (Meghan CEO enforcement layer + build plans) ----------
N plan:step-zero-commits plan "Step zero: commit the code (SBOS + DealsDesk)" active '{"note":"everything syncs from git; SBOS 42 uncommitted + ahead 25, dealsdesk home-repo backlog. Ranked #1 independently by Altair, the heartbeat council, and Muse. Nothing else unblocks until this lands"}'
N plan:console-rooms plan "SBOS Console rooms: People / Comms / Content" active '{"note":"console v1 live (Chat/Fleet/Code/Brain) in tools/travel/roadchat.py; People (contacts + train-card inbox), Comms (WhatsApp+email river), Content (SEO to blogging) are labeled planned tiles with wiring named"}'
N plan:heartbeat-council plan "Heartbeat council (Altair / Lyra / Meghan seats)" active '{"note":"tools/travel/council.py; cron :07/:37 after Altairs :05/:35 heartbeat; notes in tools/travel/council/; thinks only, never acts. Altair via Sonic :11439, Lyra via Morpheus :11437; Meghan seat VACANT until Prometheus is served"}'
N plan:seat-meghan-prometheus plan "Serve Prometheus to seat Meghan (CEO agent)" planned '{"note":"Gemma 4 26B weight on k11-alpha, no service running. Seating her completes the council and gives the CEO tier a voice in the build-out"}'
N plan:laptop-provisioning plan "Provision the two Dell laptops (Ubuntu 26.04, Hermes road profiles)" planned '{"note":"CRITICAL PATH. Ubuntu 26.04, tailnet enroll, git clones, console + road agent, stripped Hermes profiles road-vostro / road-7420. Includes the identity ceremony: bundle registry at home, TPM-backed key on the 7420. Design: tools/travel/ROAD_AGENT.md"}'
N plan:sync-sets-r2-r3 plan "road_sync sets: profile-state (R2) + snapshots incl. calendar (R3)" planned '{"note":"briefings/decisions/Meghan reports live in ~/.hermes/profiles, OUTSIDE git - road_sync needs a profile-state set. Snapshots: calendar_snapshot.json exported from altair.calendar.effective_day, people_unified extract, blog context, hunt results"}'
N plan:dashboard-hardening-login plan "Dashboard: login capability + bind hardening" planned '{"note":"the web surface (any browser) gets auth; safe verbs only, never native powers. Includes open audit item #1: dashboard-api 0.0.0.0:8000 rebind to loopback/tunnel-only"}'
N plan:phone-capture-app plan "Phone custom capture/glance app" planned '{"note":"installable web app on the Pixel: structured captures (cards, voice, lead/deal/idea forms) provenance-stamped by device identity; answers gated questions; on the travel LAN it runs against the laptop/bravo console as its server"}'
N plan:tardis-acceptance-test plan "Chicago TARDIS acceptance test (scored)" planned '{"note":"pass marks written BEFORE departure in tools/travel/SCENARIOS.md: every daily workflow from a laptop, zero data loss in dark stretches, card mission end-to-end, deliberate failure injection, power discipline, post-trip council grade. Failures become the build list"}'

# ---------- EDGES ----------
E proj:daily-driver-platform plan:step-zero-commits requires "nothing syncs until the code is committed"
E proj:daily-driver-platform proj:chicago-tardis requires "the TARDIS (Nov 27-29, Westin Chicago Lombard) is the platform acceptance test"
E plan:laptop-provisioning proj:daily-driver-platform enables "the drivers themselves"
E plan:console-rooms proj:daily-driver-platform supports ""
E plan:heartbeat-council proj:daily-driver-platform supports ""
E plan:seat-meghan-prometheus plan:heartbeat-council enables "seats the CEO seat"
E plan:sync-sets-r2-r3 proj:daily-driver-platform supports ""
E plan:dashboard-hardening-login proj:daily-driver-platform supports ""
E plan:phone-capture-app proj:daily-driver-platform supports ""
E plan:tardis-acceptance-test proj:chicago-tardis supports "scored criteria in tools/travel/SCENARIOS.md"
