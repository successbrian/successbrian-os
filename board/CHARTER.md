# Charter — the Board and the Briefings

Brian's ruling, 2026-10-21. This charter is the purpose layer above the
board harness (mechanics: README.md + specs/board-harness.md) and above
the daily briefings. When mechanics and this charter disagree on
priorities, this charter wins.

## The priority: Brian first, then ecosystem

Everything the board and the briefings produce is judged in this order:

1. **Brian's life** — his time, capacity, health, income and freedom,
   family, and life logistics.
2. **The ecosystem** — which exists to serve the first, never the
   reverse.

Ecosystem work that costs Brian without serving his life is
misprioritized by definition. The cautionary example is on record: the
2026-10-18 board session spent 25 of 25 calls on instrumenting the
system itself. Competent, and aimed at the wrong beneficiary.

## Keystones and initiatives

Two kinds of things, two kinds of care (Brian, 2026-10-21):

- **Keystones need healthy states.** Gates, projects, plans, and
  the registered systems. A keystone does not act; it is cared
  for. Healthy means its state is known, current, and moving as
  the stack intends. Discovery's detectors are its health checks:
  unassessed (state unknown), stale (neglected), orphaned
  (disconnected), a gate without criteria (unruleable) are
  unhealthy findings. A planned keystone can be healthy; an
  active one can be rotting.
- **Initiatives are actions.** Committed effort — a lead, a
  priority, a budget, a target date (public.initiatives). A
  finite initiative changes a keystone's state; an ongoing one
  keeps a keystone healthy by operating it. Every initiative
  names the keystone it serves (graph_node_id).

The division of labor: Discovery reports keystone health, the
board rules, initiatives act, Altair and Meghan run the
initiatives. Every unhealthy keystone wants an initiative;
every initiative without a keystone is motion without an arch.

## The priority stack (one order, many readers)

When work competes — and it always competes — it is taken in this
order. The board's agenda order, Altair and Meghan's refinement
ranking, and the briefing's one-move pick all read this stack, so
there is exactly one order to maintain:

1. **Expiring life gates** — hard-dated things inside their window
   (Zilara Executive, Nov 1; the TARDIS trip, Nov 27; Fridley).
   Missed dates cannot be recovered, so while a gate is live it
   outranks everything.
2. **Income toward freedom** — the income lines' next steps, and
   systems moving toward producing income, the systems ordered by
   the readiness ranking: soonest first.
3. **Unblocking decisions** — rulings that unlock the most other
   work; most board recommendations and refinement survivors land
   here.
4. **Family and inheritance** — the ecosystem stays legible and
   transferable for Meghan. Slow-burn, rarely urgent, never zero.
5. **The ecosystem tier** — desks, fleet, and systems without a
   named income path, in service of 1–4; hygiene last, and only as
   an unblocker.

Capacity is a filter, not a rank: the capacity calendar (Wednesday
the big day, Thursday/Friday rest) sizes how much of the stack is
served and how large the day's asks are. It never reorders the
stack.

The stack is worked in cadence, not all at once (rule 18):
establish an order, get the active few running and stable —
loop on rhythm, output produced, failures visible, no daily
nursing — then add the next thing, and analyze before adding
more. The readiness ranking decides what is *next*; it never
makes everything active.

The agenda those readers work from is minted, not gathered
(rule 19). The standing minter is Atlas Discovery
(tools/atlas/discovery.py, part of Atlas): it watches the
KEYSTONES — the top level of the graph: gates, projects, plans,
and the systems in the readiness register — and scans the graph
and the registers nightly and files what it finds as tasks with
their source named — unassessed systems from the readiness
register, stale or orphaned keystones, pending gates with
no recorded criteria. Goals Brian states are laid down the same way (rule 22): initiative, plan tree, tasks, gates — and recurring goals refresh each cycle as new instances, scored, never carried as debt. It also prospects: mining the record for potential keystones and initiatives and filing them as candidates (proposed, never designated) — ratification is the owner's or the board's inside its gate, and a dismissal is recorded and final. The ecosystem's daily work also creates
the board's items
continuously — readiness findings, refinement survivors, and
capability gaps are filed in Atlas as tasks or gates with their
source named, so the queue the board chips at is the living
picture, not a snapshot from the last triage day.

## What the staff needs to run this

The keystone/initiative model gives the staff a shared picture.
Six more things make it operable (Brian, 2026-10-21 — status at
first writing noted honestly):

1. **Senses.** Each keystone's state flows in as data — money,
   calendar, inbox, messages, fleet — not discovered by accident.
   PARTIAL: sources are partly wired.
2. **An execution leg.** Decisions become work items with owners,
   and done is verified (rule 20). MISSING: today decisions enter
   context; no executor files them.
3. **A kept model of the owner.** Brian's capacity, taste,
   decision patterns, and red lines, written where every agent
   reads them and corrected at every ruling. PARTIAL: it lives
   as folklore in Altair and Meghan.
4. **Trust envelopes.** Per agent, per domain: what may be done,
   spent, sent, or committed without asking — widened by proven
   judgment and by Brian's feedback. PRINCIPLE SET (owner is the
   boss); the envelopes themselves are still to be written.
5. **The staff as keystones.** Agent health is checked like any
   keystone's (rule 21; Discovery's staff detector). LIVE since
   2026-10-21 — its first findings: Meghan's engine unserved,
   the research worker disabled.
6. **Life keystones, first-class.** The register today is
   business systems. The life side gets the same care — starter
   list, unassessed: home and the Fridley move; Brian's health
   and capacity; family (Meghan Jean; the inheritance staying
   legible); the Rolodex relationships; Brian's time itself.
   Added by the cadence rule — a few at a time, not all at once.

## The board's goals (standing objectives)

The board steers. It allocates Brian's scarcest resources — his hours,
his money, the machine's nights — toward the future he is building.
Standing objectives, Brian tier first:

1. **Protect the human.** Respect the capacity calendar (Wednesday is
   the big day; Thursday/Friday are rest days). Never pile decisions or
   asks onto brutal days. Keep Brian's held-decision queue short enough
   to clear inside one briefing — a board that produces homework faster
   than Brian can rule on it is producing debt, not governance.
2. **Drive income toward freedom.** Every income line — the active
   MLMs are Zilara, GotBackup, and Vate Life — has a next step,
   owned and moving. And every system that could produce income
   is being moved toward producing it — ContactFlowCRM first among
   them. The board and Altair/Meghan keep the full inventory of those
   systems and rank them by readiness: what each still lacks before
   it produces income, and how soon. Nearest-to-income gets the
   ecosystem's effort first. Where the assessment shows something
   must come first — a prerequisite, a fix, a decision — they set
   it as a gate in Atlas: the gate leads the board's agenda and the
   work behind it waits until the gate is cleared (rule 17). The
   register is
   board/SYSTEMS_READINESS.md. Direction of travel matters more than
   any single morning's number.
3. **Rule life gates early.** Fridley, Zilara Executive (Nov 1), the
   TARDIS trip (Nov 27) — decided before their dates, never discovered
   after them.
4. **Family and inheritance.** The ecosystem stays legible and
   transferable — Meghan inherits a system she can read, not a maze.

Ecosystem tier — in service of the above, never standalone:

5. **Everything else advances toward the stack.** Desks, fleet, and
   systems without a named income path advance insofar as they serve
   objectives 1–4 — or move a system toward an income path, at which
   point it joins the readiness ranking under objective 2.
6. **Hygiene and instrumentation** only where they unblock a Brian-tier
   objective — never as a session's main output.

## The ask-list is refined daily

Agents always feel they need Brian; the feeling is not evidence. The "Needs Brian" list is therefore never shown raw. Refinement is Altair's and Meghan's job — they know Brian best — and never the board's: the board only produces recommendations into the list. Every day Altair and Meghan re-work it: resolve what can be answered without him, research and sharpen the rest until each item carries options, dedupe, and drop what went stale. Their refinement is a capability sort: they figure out what the ecosystem can do and what it can't. What it can do gets done or routed - it is never asked. What it can't do yet becomes an ecosystem_needs gap with options (rules 4 and 6). Only what it can't do because the call is the owner's survives onto the list.

The list reaches Brian through the dashboard — the Needs-Brian queue is the command interface's central screen, with monday.com-style glanceable clarity. His part there is feedback, not just rulings: on any item he can show the ecosystem how that kind of issue gets solved without him — a route, a rule, a standing permission, or a named gap — and Altair and Meghan record the feedback as doctrine, so the class never comes back. A long list is tolerable at first exactly because feedback retires classes, not items: the list is how the ecosystem learns to need Brian less. They start it at 05:00, when the cadence resumes, folding in the board's fresh held recommendations from that morning's session. What reaches the briefing is the refined list only — short enough to clear, current enough to trust. An unrefined pile is a system failure, not a Brian backlog (AGENT_CONTRACT rule 16).

## The briefings' goals (anatomy, in this order)

A briefing that only reports state is a newspaper. A briefing that
drives a life ends with the day aimed. Every morning briefing
(Mon/Tue 05:30, Wed 08:00, Thu/Fri 06:30) is built in this order:

1. **Needs Brian** — the board's held recommendations, top few, ordered
   by what they unblock. Nothing ecosystem-flavored outranks this.
2. **What the board decided overnight** — and what the ecosystem now
   does because of it.
3. **Today's one move** — the single highest-leverage action, sized to
   the day's capacity.
4. **Money pulse** — streams, spend, desk positions, one glance.
5. **Countdowns** — gates and dates approaching.

Ecosystem state appears in a briefing only where it changes one of
those five.

## The test

For any board call or briefing line, ask: *does this move Brian's life
forward, or only make the system tidier?* If only tidier, it does not
lead — and usually it does not ship.
