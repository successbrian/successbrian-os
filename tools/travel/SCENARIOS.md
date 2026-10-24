# Train scenarios — the Chicago TARDIS

**The test date (from Brian's Atlas, proj:chicago-tardis):
Nov 27–29, 2026 (Fri–Sun), Westin Chicago Lombard.** About five
and a half weeks out from 2026-10-20 — provisioning has a real
deadline now.

Brian doesn't know which work the trip will demand, so the kit is
built for **coverage, not prediction**: every scenario below must
find its tools already packed. Each lists what it needs, what covers
it today, and the honest gap. `trip_prep.py` verifies the packable
items before departure — its verdict law is the ecosystem's law:
**READY.** only when everything checks; anything else is
**NOT READY.** with the items named.

## People scenarios (the trip's actual mission)

1. **The demo moment** — someone leans over: "what *is* that?"
   Needs: Sonic live on bravo, the console, C64 mode, the map.
   Covered: console Chat + C64 mode + ecosystem map. Gap: the map
   must exist as a local file on the laptop (offline), not only as
   a hosted page.
2. **Card capture** — a paper card lands in Brian's hand.
   Needs: photo → contact + note + follow-up clock.
   Covered: RoadChat image attach (plumbing). Gap: the People room
   (card inbox) is a planned tile — until it lands, cards go to the
   road inbox as photos + a typed note.
3. **The follow-up** — 48 hours later, "when you're free, call me"
   becomes an actual call. Needs: the contact, the context of the
   conversation, a reminder that fires at home.
   Covered: road inbox syncs home via link_up. Gap: People room.

## Work scenarios (any of Brian's seven stations, unplanned)

4. **Blog the trip** — his audience expects a post; the trip IS the
   content. Needs: drafting (Sonic/Morpheus on bravo), SEO notes
   (Brain), publish on the next connectivity burst (queue).
   Covered: Chat + Brain today. Gap: Content room; publishing is a
   queued road-inbox item until then.
5. **Email / WhatsApp backlog** — station-stop connectivity bursts.
   Needs: sync fast when a link appears, triage offline, replies
   queue and send on the next burst.
   Covered: doctrine (road inbox). Gap: Comms room is a planned
   tile; Gmail/WhatsApp not yet wired into the console.
6. **Code session** — SBOS or DealsDesk work en route.
   Needs: repos cloned on the laptops and COMMITTED at home before
   departure (an uncommitted home tree cannot sync), local engines
   for assistance, push on return.
   Covered: console Code room + git doctrine. Gap: laptops not yet
   provisioned; tonight's code batch not yet committed (step zero).
7. **A deal drops** — a fleet listing surfaces during a stop.
   Needs: the scorer, NOW, offline. Covered in full: the DealsDesk
   scorer runs in-process in the console. Seller messages queue in
   the road inbox.
8. **The deep question** — a prospect asks something hard.
   Needs: a ladder — Brain search instantly, Sonic for synthesis,
   REAP's slow lane on bravo for depth, or the job queues for alpha
   when the link returns. Covered: the ladder exists by design;
   REAP rides bravo as the background lane.
9. **A document on the spot** — a one-pager for the person across
   the aisle. Needs: draft in Chat, save as markdown, hand over
   later by email. Covered: Chat drafting. Gap: the Docs room and
   templates are planned.
10. **Fleet ops from the train** — check home while away.
    Needs: tailnet up. Covered: Fleet room + eco_status.

## Failure scenarios (designed, not feared)

11. **No link for hours** — the normal state, not an emergency:
    bravo is the hub, the travel LAN is private, Tailscale is only
    an uplink. Everything above degrades one tier, nothing stops.
12. **No seat power / battery discipline** — local inference is
    plugged-in work; on battery the laptops are consoles and bravo
    (or home) is the engine. Saver mode is in the console already;
    the multi-tap is a manual pack item in trip_prep.
13. **A machine dies** — two laptops, either can run the console;
    bravo carries the weights; the repos live in git in three
    places. Annoying, not fatal.

## The rule the scenarios teach

Unknown work ⇒ maximize **local completeness** (weights, repos,
knowledge, contacts all mirrored before departure), **queue
everything outbound** (road inbox), and **degrade in tiers**
(alpha → bravo → laptop → paper). trip_prep.py is the checklist
that proves the first of those before the train leaves.
## The Test — how the TARDIS grades the platform

Brian's framing (2026-10-20): the laptops are becoming his daily
drivers, and **the trip is the hard test to see it work in
reality.** Home is the soft environment (power, Wi-Fi, the whole
fleet in the next room); the train is the hard one. So the trip
is run as an acceptance test, scored against criteria written
down BEFORE departure — the failures become the build list, and
a pass is what licenses daily-driver trust.

**Pass marks:**
1. **Every daily workflow, at least once, from a laptop** —
   standup + a decision recorded, comms triaged, a deal scored,
   a post drafted, a code change committed on the road and
   pushed on a link burst. (DAILY_WORKFLOWS.md is the list.)
2. **Zero data loss across the dark stretches** — everything
   created offline (captures, drafts, commits, notes) is present
   at home after: outboxes empty, sync log clean, queues drained
   100%. This is the supply line's exam.
3. **The card mission, end to end** — cards captured on the road
   arrive home as contacts with follow-up clocks set. The
   trip's business goal, graded like everything else.
4. **Continuity under failure (deliberate)** — at least once,
   on purpose: close one laptop mid-task and finish on the
   other; run one leg with Wi-Fi off entirely. A hard test
   injects its failures while they're cheap.
5. **Power discipline held** — no dead-machine moment; saver
   posture engaged on battery; inference stayed plugged-in work.
6. **One interactive podcast session, road-dark** — a packaged
   episode played on a laptop with no link: audio heard, slides
   seen, questions answered, and the answers present at home
   afterward as filed records.
7. **The loop closes** — the road agent's trip log reaches home,
   and the heartbeat council's first post-trip sitting reviews
   the test: what passed, what failed, what gets built next.
   The platform's builders grade its exam.

**Scoring law:** a criterion is PASS only on evidence (sync
logs, repo state, the contact list, the council's review) —
never on "it seemed fine." Anything else is a finding, and
findings are the next build list. That is what makes it a test
instead of a ride.
