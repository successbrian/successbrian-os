# The Board Flow — a serious flow that can work, improved daily

Designed by Brian in the hash-out of 2026-10-23 (evening), on top of the day's board work. This is the flow the judging and the Board of Directors run on, end to end. Every stage names its owner, its input, its output, and its failure rule. The flow is built in stages (below); a stage counts only when it is proven in the live system, never when code merely exists.

## The flow

**1. Inflow.** Topics arrive all day (Atlas tasks and gates, desk findings, signals, Brian's own filings). Nothing arrives as a bare title and gets judged — a title is an input to the clerk, not a packet.

**2. The clerk builds group packets.** Long term, the clerk builds them (Brian, 2026-10-23). Topics are grouped (a group packet is the decider layer's unit of work). Each packet carries, per topic:
- **Why it matters** — the stakes, in plain words
- **What the dilemma is** — the actual tension to be decided
- **Many easy questions** — the clerk breaks the dilemma into easy questions for the judges; the judges answer the easy ones and the complexity is drawn out by the set of answers (Brian's packet law)

**The decomposition law (Brian, 2026-10-23):** a hard, difficult question is never handed whole to a 14B judge. The clerk pulls the complex question apart into many easy ones, built around the decision crisis, and those easy questions **stay together as a group** — the group is one hard question and its decomposition. The combined answers answer the one hard question: "not with a 14B — we make this 14B easy." This is the capability strategy under the whole design: the hard thinking lives in the clerk's breakdown, each piece is sized so a 14B answers it reliably, and that is why small judges on under-$500 minis are enough.

Until the clerk exists as its own box, the clerk's duties run in software on existing hardware (the standing software-first verdict).

**3. The judges rule.** The four-seat panel (Qwemstral: Morpheus pair + Rassilon pair, Mistral seats as they are stood up) answers the easy questions on every topic — four seats, the same ~100 topics a night, each seat on its own machine, working in parallel (pipelined, not lockstep). Every ruling is written down the moment it is made (per-decision persistence), with its seat's name on it. A seat that blows its per-item time budget parks that item, not the night. (PROPOSAL — Muse's, not ruled by Brian: bench a seat that keeps stalling for the rest of the night and write the gap in the minutes.)

**4. The deciders work group packets, one per heartbeat.** Each heartbeat, Altair and Meghan grab one new group packet — with the judges' rulings in it — and start working it. Working it means: Altair and Meghan, using Sonic as their engine, piece the judges' answers together into the story of the packet, then go back and forth on it **until they both 100% agree**. Unanimity is the finish line; a packet is never done on one pass or one decider's say-so. (R35 holds throughout: the board judges and suggests; Altair and Meghan decide; Brian owns above all.)

**5. The research branch.** If **either** Altair **or** Meghan decides more research is needed, they put in research requests (Lyra layer / board research orders). That packet group goes **on hold until all of its research is completed** — no partial-research rulings. The heartbeats take other groups meanwhile. When the research lands, it goes into the packet and the back-and-forth resumes.

**6. The record.** Everything lands in the record as it happens: the rulings ledger (every ruling, its seat, its packet), the packet stories, the agreement state of each group, research requests and their completion, holds and releases. The morning reads this record — recorded vs verified is checked, never assumed.

## Failure rules (the anti-chaos layer)

Learned from the nights that actually broke (the beta stall; the lost 72 rulings; the skipped closer):
- A hang parks an **item**, never the night (3x per-item budget + stuck store, already built).
- A ruling that is not **recorded and verified** did not happen (per-decision persistence, already built; morning analysis checks the counts).
- A formatting quirk must never discard a good ruling (parser fallback, already built).
- A dead machine **degrades** the panel; it does not kill the night (seats on separate boxes; the gap is named in the minutes).
- A packet group waiting on research is **on hold**, visibly — it is never ruled half-informed and never silently dropped.
- The closer/summary step gets its **own time budget** (still open: task:board-closer-budget).

## Daily improvements

The flow improves daily by the standing morning loop (Brian, 2026-10-23, through ~2026-11-13): each morning takes the night's flow output, picks **one** capacity-sized improvement, and ships it as code before the next night's run. The morning reads these flow gauges, all from the record:
- Packets built vs topics waiting (is the clerk keeping up?)
- Per-seat ruling counts (is the load even across the four seats, night after night?)
- Decider agreement: how many packets reached 100%, how many rounds the back-and-forth took
- Holds: how many groups are on research hold, and how long research takes to complete
- Losses: rulings recorded vs verified; items parked and re-presented

## Build order (stages)

1. **Packet builder in software** (clerk duties before clerk hardware): group topics, write why-it-matters + the dilemma, generate the easy-question set. Extends harness/enrich.py; feeds on the Atlas record (summaries at filing — task:broken-audit:atlas-summaries — remain the entry fee).
2. **Panel mechanics**: four seats judging every topic in parallel, per-seat counts in the minutes (task:board-panel-2plus2; pipelining per the 05:00 analysis verdict).
3. **Decider loop**: group-packet queue for Altair/Meghan, one grab per heartbeat, story-piecing, 100%-agreement state per packet (task:board-decider-queue, extended by tonight's rulings).
4. **Research holds**: research requests filed from a packet put that group on hold; completion of all requests releases it.
5. **Meghan's engine served** — the flow's biggest known hole: Meghan cannot yet think on her own engine (Prometheus not served), so her seat in the decider loop is not real until this lands (roadmap Stage 2).
6. **Closer budget** (task:board-closer-budget) and the standing 02:30 trigger, so the night starts and ends on rails.

## Still open (Brian to rule)

- The endgame when research is complete and Altair and Meghan still split — escalation limit/trigger to Brian.
- Whether "has this been decided before?" and "what standing rules touch this?" are always among the clerk's easy questions.
- The grouping rule itself: what makes topics one group (theme, goal, business line, deadline)?

## Why this can work

Every piece has either already run in the live system or has a measured budget behind it: rulings at ~15s against a ~72s-per-topic pace at 100 topics; a full judge call under 1,000 tokens against an 8k sizing (packets have room to grow); heartbeats that already exist; a research layer that already takes orders. The flow's discipline — record everything, park items not nights, hold packets not decisions, one improvement every morning — is what keeps it from becoming chaos.
