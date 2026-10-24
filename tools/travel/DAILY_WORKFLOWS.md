# Daily workflows — what the two laptops must handle

Planning draft (2026-10-20). **Premise (Brian): the two laptops
become my daily drivers, even at home** — this plan is therefore
about his everyday machines, with travel as one mode among
several. Built from **evidence in Brian's own
ecosystem** — the briefing cadence, the heartbeat checklist, the
Hermes profile roster — not from guessing. Brian confirms the
ranking and the frequencies; the laptops are then provisioned so
every workflow below works at home, road-linked, and road-dark
(each in its degraded form: capture, queue, draft).

## The candidate daily set

### 1. Morning standup with Altair — daily, ~08:30
Evidence: `altair_briefing.py --for=standup` cron 08:30 weekdays;
midday sync 13:30; Sunday briefing 19:00. The briefing covers five
areas: ops health, **blog ideas**, build ideas, ecosystem
knowledge, **decisions Brian must make**.
Laptop needs: the day's briefing + pending-decisions in front of
him, chat with the home engines, decisions recorded and synced.
Modes: home ✓ · road-linked ✓ (bravo engines + synced briefing)
· road-dark — briefing must have been **pulled before the dark**
(sync set, below); decisions queue in the outbox.
Gap: **briefings live in the Hermes profile dir, outside the git
repos** — road_sync has no set for them yet (R2).

### 2. Comms triage — WhatsApp + email, several times daily
Evidence: Hermes channels + `email_gates.py` (email is a managed,
gated flow in his stack); WhatsApp is Brian's stated front door.
Laptop needs: one river, triage with Chuck-class tagging, replies
drafted by the engines, sends queued for link bursts.
Modes: home/road-linked ✓ in principle · road-dark — read the
synced snapshot, draft everything, queue sends.
Gap: the console's Comms room is a planned tile; channel state is
Hermes-profile state (R2 again).

**Phone-app integration (Brian, 2026-10-20): the actual apps on
his phone — WhatsApp, Telegram, email, SMS — integrate into the
ecosystem.** The doctrine: integrate the ACCOUNT, not the app —
the phone apps stay stock; the ecosystem connects through each
service's proper door, and both are clients of the same account.

| App | Door | Layer |
|---|---|---|
| WhatsApp | the Hermes gateway pairing his stack already runs (companion-device style, like WhatsApp Web) | account |
| Telegram | Bot API / user API — the one genuinely open door | account |
| Email | IMAP / provider API, behind his existing email gates | account |
| SMS | no account door exists for a carrier number — a phone-side forwarder (notifications/SMS mirror to laptop + home) | device |

Rules that keep it sane: **one gateway per account** (never a
second WhatsApp bridge beside the sanctioned one); **sends keep
the gates** — the ecosystem drafts, Brian approves with a phone
tap, the send executes from home's gateways on sync (queued
sends from the road ride the outbox and fire at home, they never
originate from a laptop directly); **reads become signal** — a
message from a known contact feeds standup, the People room,
and the follow-up clocks.

### 3. Deal flow — DealsDesk, daily-ish
Evidence: DealsDesk itself, the scorer doctrine, a bench of
Hermes profiles (deal-desk-web, dealdeck, arbitrage-scout,
bundle-scout…).
Laptop needs: the scorer (✓ in the console, offline), hunt
results pulled on links, decisions + seller messages queued.
Modes: scoring is the best-covered workflow in the kit — fully
road-dark capable except fresh listings.
Gap: hunt-result delivery into the console (rides git/snapshots).

### 4. People — leads, contacts, follow-ups, daily
Evidence: lead-capture-specialist, lead-enricher,
enrichment-people profiles; `people_unified.db` in ~/.hermes;
the train trip's card mission is this workflow wearing a hat.
Laptop needs: capture (card photo → outbox), the contact list
readable offline, follow-up clock visible.
Modes: capture is road-dark native ✓ · enrichment happens at
home (engines + DB) after sync.
Gap: People room (planned tile) + a people snapshot set (R3).

### 5. Content — blog + social, daily feeding
Evidence: "new blog ideas" is a standing briefing area;
blog-network.md is briefing context; instagram-scraper profile;
Brian's audience is the business's front end.
Laptop needs: idea list, drafting with Sonic (console Chat ✓),
publish queue, Brain search over past posts/docs (✓).
Modes: drafting road-linked ✓ · road-dark drafting falls to
local notes + queued prompts (no engine) — acceptable.
Gap: Content room (planned tile).

### 6. Coding / build sessions — daily
Evidence: this entire night.
Laptop needs: repos cloned, console Code room (✓), local commits
protected by road_sync's dirty-tree rules, engines for assistance.
Modes: home/road-linked ✓ · road-dark — code + commit locally,
push on link (git is the original offline-first tool).
Gap: none structural; laptops + provisioning only.

### 7. Money / CEO review — weekly + decision moments
Evidence: Meghan (CEO agent: financial + future planning),
ceo-heartbeat timer, Sunday briefing.
Laptop needs: her reports readable; decisions queued to her tier.
Gap: Meghan's seat itself (Prometheus unserved) — until then this
workflow is read-only reports (R2 set).

### 8. Ecosystem ops — the daily glance
Evidence: briefing area 1 (job failures, service health, disk).
Laptop needs: the board (✓) + eco_status (✓).
Modes: home/road-linked ✓ · road-dark — the board shows the
*laptop's own* state via road_sense; home is simply unreachable,
and the board must say that plainly.

## Calendar — the shared clock (Brian, 2026-10-20)

"Knowing my calendar is something these laptops need to do — and
my dashboard needs to know my calendar." The ecosystem already
has a canonical calendar: the **altair.calendar** schema in
ecosystem_central (`effective_day` = merged blocks + overrides),
fed by ICS import (`dashboard-api/calendar_ics.py`), already
served at **GET /api/v1/calendar** by the dashboard API, with a
calendar-page in the dashboard. life_ops / daily_director already
plan days from it. What does NOT exist yet:

- **A road path.** The calendar lives behind the home DB and
  dashboard; a laptop — above all road-dark — knows nothing.
- **Dashboard surfacing + feed freshness.** The endpoint exists;
  whether the main dashboard view shows today/next-up, and
  whether the ICS feed from Brian's real calendar is actually
  flowing, are open verification items.

The flow (rides the R3 snapshot set — calendar is data, produced
at home, consumed everywhere):
1. **Exporter** (home, heartbeat-adjacent): read
   altair.calendar.effective_day → `calendar_snapshot.json`
   (today + 14 days, minimal fields) into the sync area.
2. **road_sync snapshots set** pulls it on any link (small,
   delta-cheap). Bravo relays it like everything else.
3. **Laptops consume it twice:** the road agent is
   calendar-aware (travel-day posture on the TARDIS date,
   meeting-soon quiets the machine, standup reads the day), and
   the console shows a **Today strip** (next event + today's
   list) in the console proper — NOT on the board (calendar is
   workflow, not infrastructure; the layer rule holds).
4. **Dashboard** surfaces the same canonical source (today +
   next up) — one calendar, three readers, zero copies of truth.

Open question for Brian: where does the ICS import come from
(Google Calendar? Apple? Outlook?) — and is it live today?

## Two surfaces — the dashboard and the laptops (Brian, 2026-10-20)

Brian's framing: **the dashboard** is the web-hosted version of
the console — bring it up on any device, in any browser (today:
dashboard-api + its cloudflared tunnel; login capability is a
planned addition). **The laptops** have a more native, intimate
reach into the same thing. Verdict: sound architecture — it is
the inference access doctrine applied to interfaces. One back
end, one canonical data (calendar in ecosystem_central, repos,
profile state); what differs by surface is *reach and trust*:

| | Dashboard (web) | Laptops (native) | Phone (Pixel 10 Pro) |
|---|---|---|---|
| Reach | any browser, anywhere | these two machines | Brian's pocket |
| Trust basis | a login session (to be built) | the device itself — tailnet member, Brian's hardware | the device itself — already a tailnet member |
| Posture | a window: read-mostly — board facts, calendar, briefings, council notes | the hands: senses, queues, sync, commits, engines, full workflow depth | the glance + the tap: alerts in, answers out, capture |
| Offline | dead (fine — it's a window) | fully road-dark capable (the point) | queues its captures; ferries on cellular when it can |
| Verbs | safe ones: view, approve, queue, reply | all of them, incl. the dangerous ones | safe ones only: view, approve, answer, capture-and-send |

**The phone's tier** (Brian, 2026-10-20: "some access" — the
bound is deliberate). Two powers neither other surface has:
(1) **the ecosystem can reach Brian through it** — the phone is
where gated questions land (Lyra's workers already file "Brian
questions"; the council escalates to Meghan, then to Brian) and
where heartbeat alerts, briefing headlines and board alarms
belong; (2) **on the road it is the most-connected node** —
cellular when train Wi-Fi dies, a tailnet member in its own
right: a link mule that ferries the small vital things (questions
out, answers in, card photos home) while the laptops stay dark.
It is also the convoy's camera and microphone — card capture may
start on the phone and land in the same road inbox. What it is
never: a console, a sync hub, or a holder of dangerous verbs.

Three conditions that make it work:
1. **Auth is the whole ballgame on the web surface.** The day
   the dashboard gets a login, it is an internet-facing door.
   It must never grow native powers: no sync pushes, no commits,
   no fleet control from a browser session — those stay
   native-only. (This also raises the stakes on the known open
   item: dashboard-api's 0.0.0.0:8000 LAN bind should become
   loopback/tunnel-only in the hardening pass.)
2. **One back end, or the surfaces drift.** Dashboard pages and
   console rooms read the same API and the same canonical
   stores. The calendar is the test case: one source
   (altair.calendar), three readers, zero copies of truth.
3. **The offline asymmetry is a feature.** The dashboard dying
   without a link is correct behavior; the laptop depending on
   the dashboard would be the bug. Native reach must never
   route through the web surface.

## The interface layer — custom surfaces that gather (Brian, 2026-10-20)

Brian's correction to the stock-app story: he wants **custom
interfaces** integrated into the ecosystem that **gather data**.
Doctrine: the ecosystem's primary surfaces are its OWN. Stock
apps and their gateways are bridges for other people's channels
(WhatsApp threads, the SMS stream) — necessary plumbing, never
the face. The faces are custom, one per reach, all reading and
writing through the same API and canonical stores:

- **Phone: a custom capture/glance app** (installable web app
  first — no app-store gate; native shell only if it earns it).
  Gathers: card photos, voice notes, quick structured forms
  (new lead, deal sighting, content idea), answers to gated
  questions. Shows: today strip, alerts, approvals. On the
  travel LAN it can run against the laptop/bravo console as its
  server — a custom interface that works with home unreachable.
- **Laptop console** (exists, v1): the deep surface. Gathers
  everything typed, attached, scored, drafted, decided.
- **Web dashboard**: the bounded surface — approvals, answers,
  forms from any browser.

**Gathering is structured, not scraped.** Three kinds of data
flow inward: explicit captures (forms, photos, voice — with
fields, not free-text soup, so Chuck can tag and Lyra's workers
can enrich); workflow exhaust (every score run, draft, and
decision is itself data — the decision log is how the ecosystem
learns Brian's judgment); and context (each capture is stamped
with provenance: which device — by its identity bundle — which
interface, when, and the road_sense mode it happened in).
Provenance is what makes gathered data trustworthy enough to
act on. Offline, captures queue in the outbox and sync like
everything else — the sync fabric already carries this.

## Judgment learning — Altair and Meghan (Brian, 2026-10-20)

"Altair and Meghan learn my judgement — the nuances on when
things matter and break rules." The decision log's purpose is
not record-keeping; it is **curriculum**. Two students, two
subjects:

- **Altair learns operational judgment** — routing, priority,
  severity: which failure is a fire and which is a Tuesday.
- **Meghan learns business judgment** — money, strategy, what
  matters: which deal is worth breaking process for and which
  rule is worth breaking a deal over.

The mechanism already exists: **gated questions are tuition.**
When a worker hits the edge of a rule, the question escalates
(Lyra → Altair → Meghan → Brian) and Brian's ruling — captured
WITH its why, at the moment of decision — becomes a judgment
record the agents consult thereafter (the second brain is the
library; retrieval is how they "remember" a lesson). Doctrine
that follows:

1. **An override without a why is noise; with a why, it's a
   lesson.** Interfaces must capture it at the tap: every
   approve/deny/override in the custom surfaces carries an
   optional one-line reason field. One line now, or the nuance
   evaporates.
2. **Recurring nuances get promoted into code.** Precedent:
   Brian's "1.92TB counts as 2TB" ruling began as judgment and
   now lives in sourcing_floors.py. Judgment is the draft;
   doctrine is the published edition. The loop is: ruling →
   record → pattern → code.
3. **Judgment also learns which rules have NO edge.** The trap
   registry is absolute — "never never never" — and knowing
   that some rules don't bend is itself a nuance. The students
   learn the shape of the exceptions AND the shape of the
   absolutes.
4. **Maturity is measurable:** as the judgment record grows,
   gated questions should get fewer, better-targeted, and
   harder — the system asks only where judgment is genuinely
   missing. A rising question rate on settled ground is a
   defect, not diligence.

## The production loop — briefings + the Saturday podcast (Brian, 2026-10-20)

Atlas, the Board, Altair, Lyra, Meghan, and Spencer working
together produce the two things that land in front of Brian:
**the briefings** and **the Saturday weekly podcast** (his
private learning feed — NOT audience content; the blog network
is the audience's channel, the podcast is Brian's own).

| Party | Contributes |
|---|---|
| Atlas | the record: the week's deltas, gates, decisions (via the board pack) |
| Lyra | the workers: research and findings on briefing topics and podcast subjects; gated questions up |
| Spencer | memory and continuity: what Brian was in the middle of, check-in context |
| Altair | assembly and voice: builds the briefings, routes the production work |
| Meghan | CEO judgment: what matters this week; follow-through audit on last week's rulings |
| The Board | decisions — which become new records in Atlas, closing the loop |

**The interactive format (Brian, 2026-10-20):** the podcast is
built for the laptops as a *session*, in segments — **play the
audio, show relevant visual slides, then ask relevant
questions.** The player lives in the SBOS Console (RoadChat's
AV plumbing — mic in, spoken replies, image display — is the
seed of it). Episodes ship as **packages** produced at home by
the loop (script, narration audio, slide deck, question set)
and travel via road_sync's snapshot sets, so a session runs
fully road-dark: scripted follow-ups with no engine, live
tutoring from Sonic when a link exists. Brian's answers are
captured, transcribed, provenance-stamped, and filed home as
judgment records, decisions, and follow-ups — the question step
is a judgment-capture surface wearing a teacher's clothes, and
next week's questions adapt to this week's answers (Spencer's
memory, Meghan's judgment).

The loop is circular by design: briefings consume the graph and
produce rulings that re-enter it; podcast topics are drawn from
the same state. **Rhythm: Saturday learning → Sunday decisions
(board pack + briefing) → weekday execution (standup/sync).**

## Cross-cutting requirements the plan exposes

- **R1 (built, v1):** console + road agent + road_sense +
  road_sync + trip_prep. The skeleton exists.
- **R2 — Hermes profile-state sync set:** briefings,
  pending-decisions, Meghan's reports, and Brian's replies live
  under ~/.hermes/profiles/, OUTSIDE both git repos. road_sync
  needs a profile-state set (small files, pull on link, push
  replies) or workflows 1, 2 and 7 go dark on the road.
- **R3 — offline snapshots:** small, fresh-on-link extracts the
  dark modes read: **calendar_snapshot.json (altair.calendar)**, people_unified extract, blog-network context,
  pending decisions, hunt results. Manifest set in road_sync,
  produced by home-side exporters (Altair's heartbeat is the
  natural producer — it already assembles this state).
- **R4 — a degraded form for everything:** every workflow above
  names its road-dark form. A workflow with no dark form is a
  trip failure waiting for a tunnel.

## For Brian to confirm

1. The ranking — which of these are truly daily, and in what
   order do they eat the day?
2. What's missing — the profile roster hints at more (Oliabo
   client work across cities, real-estate leads, monetization):
   which of those are daily *for Brian personally*, vs delegated
   to agents?
3. Which laptop is primary — the road agent's knobs differ.

## The Rolodex Run (Brian, 2026-10-20 — a defined workflow)

Brian's framing: "so this is sort of a CRM loop." Yes — with
two differences that are the design. (1) A CRM dies of data
entry; this record maintains itself AROUND the conversations
(captures, gateway reads, sync) instead of demanding to be
fed. (2) A CRM tracks stages; this loop also harvests
judgment — the takes come back attached to the pipeline and
teach the matching. The base already exists (people_unified.db);
the Rolodex is its hot tier, Pipelines are the moving items,
and the Run is the workflow layer that was missing.

"I have my hot contacts... my hot Rolodex. As opportunities
and ideas flow by me I need to run these by all of my hot
contacts." Brian's word for the items is PIPELINES (others
say opportunities): each moves through stages — captured,
matched, briefed, out, takes in, decided. First names on the list: **Darius, David, Bobbie,
Lidy**, and others to be added.

The shape:

1. **Intake.** An opportunity or idea is captured wherever it
   surfaces — Brian's head (voice note in the console), Lyra's
   research, deal flow, a podcast answer, a business card on
   the train — and logged as a pipeline item with its
   one-paragraph case.
2. **Matching.** Not everything goes to everyone — spam kills
   a hot list. Altair/Lyra propose the subset ("this one is
   David and Bobbie") from each contact's domains, open
   threads, and last-contacted date; Brian rules on the match.
3. **The run.** For each matched contact, a tailored brief is
   drafted — the opportunity framed in *their* angle: why
   them, why this, what's being asked (a take, an intro, a
   yes/no). Drafts queue for Brian's approval; sends execute
   from home's gateways on their preferred channel (WhatsApp,
   email, SMS mirror) — laptops queue, never originate.
4. **Capture.** Replies land back attached to the pipeline
   item: who said what, when, verbatim where it matters. The
   opportunity closes with a decision — Brian's, informed by
   the takes, with the why recorded.
5. **The compounding part.** The takes are judgment data: over
   time the record shows whose eye is sharp on which kind of
   pipeline — Meghan-tier knowledge, earned from evidence,
   that makes the next match smarter and the briefs shorter.

Surfaces: the console's People room carries a **Hot Rolodex**
view and a **Pipelines** queue; the phone gets the
glance form (an approval tap, a reply arriving). The Rolodex
itself is data: a hot tier in people_unified.db with domains,
channel, and fatigue guards per contact.


**Product home (Brian, 2026-10-20):** "I'm trying to sell
ContactFlowCRM to network marketers... so some of this may
belong there." Sorting rule: the PATTERN is shared — SBOS is
Brian's own dogfood deployment of the loop; ContactFlowCRM
(Atlas: proj:contactflowcrm, active) is the packaged product
for network marketers. What transfers on sight: pipelines
with stages, the hot list, follow-up clocks, the record that
maintains itself around conversations. The marketer dialect
of the Run itself exists already in their world: running a
prospect by your upline — the three-way call — is the Rolodex
Run wearing a headset. What stays Brian's: his Rolodex of
advisors and the agent council around it. Which pieces ship
in which product is a board/Meghan-tier sorting.

Open question (for Brian): is the Rolodex the same body as
"the board" the board pack serves — or is the board a
different table? The pack design waits on the roster.
