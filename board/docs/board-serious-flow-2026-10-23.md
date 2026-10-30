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

---

## Adopted revision — 2026-10-25: problems in, guidance out; read-and-ask; the fact check

Adopted by Brian 2026-10-25 08:32 CDT ("let's go with this"), designed across
that morning's session (Intel Bridge captures #61, #63–#65, #67–#73). This
revision supersedes stage 3 above ("the judges rule" on first contact) and
sharpens the board's product. The Oct 23 stages 1, 2, 4, 5, 6 stand except
where this revision amends them.

**The board's product (Brian, 2026-10-25 07:37):** problems are presented to
the board; the board guides the course of the future, or gives suggestions
on how to solve the problems. Approve/disapprove is not the product (R35
holds: the board advises; Altair/Meghan decide; Brian owns above all).

**Seats carry well-defined profiles (Brian, 2026-10-25 07:55).** Eight-part
anatomy: problems owned / know-this-cold / standing questions /
how-you-weigh / not-your-problem edges / guardrails / guidance shape /
standing data needs. First citizen: Chief MLM Officer (template at
~/workspace/builds/board-profiles/chief-mlm-profile-template.md, wired into
both board configs). The other 13 seats roll out on the same anatomy.

**The flow (Brian's consolidation, 2026-10-25 08:26):**
1. **The clerk assembles a packet** and sends it to the board.
2. **First read = read and ask.** No seat rules, votes, or decides on the
   first read. The packet's 4–7 reader seats each send the clerk their
   questions — what they need to know more about to judge this well.
3. **The clerk works the questions.** It answers what it can from inside the
   house — PostgreSQL, the brains, AnythingLLM are its own lookups — and
   files **requests** to tool-holders for everything outside (web search
   and the like). If the inside record shows Brian personally knows a
   person the packet concerns, the clerk tells **Altair to ask Brian**
   (the David Foesch example). The clerk files requests instead of doing
   tool work *so it never blocks*: its pace is decoupled from the slowest
   fetch, and it keeps every other packet moving.
4. **Requests return; the packet is processed again** — deepened by the
   combined asks, not generic enrichment. The packet is now essentially
   ready.
5. **The clerk fact-checks the packet** (Brian, 2026-10-25): a fidelity
   check against sources — inside claims matched to the records, returned
   answers matched to what sources actually said, numbers/dates exact,
   check-dates stamped, stale facts flagged, unverifiable claims flagged
   IN the packet (never silently dropped), source conflicts entered as
   controversy. Only after the fact check does the packet go on.
6. **Guidance read + deciders.** Seats guide on the checked packet; Altair
   and Meghan work it in the decider loop to 100% agreement (stage 4/5
   above, research branch included).

**It is a flow, not a hold pile (Brian, 2026-10-25 08:09).** A packet
between stages is in motion — stage, owner, next step — never parked.
Language law for this pipeline: flow and stages, never pile/waiting.

**Solved well over solved fast (Brian, 2026-10-25 08:14).** Days of
back-and-forth pressing are the correct treatment for problems whose
wrongness is expensive. Session clocks (2h cap, 3x budgets) end meetings;
problem clocks may run for days. Never bam-bam.

**Gap detection is layered.** The clerk catches form gaps (packet-law
shapes — domain knowledge compiled into shapes at design time) and
inventory gaps (the house holds it; the packet lacks it — the clerk's
whole-house view). Seats catch domain gaps (profile checklists: standing
questions, standing data needs). Deciders catch truth gaps (research
branch). In-session, the send-back built 2026-10-25 (seat answers
"RETURN: <needs>"; clerk intake board-sendbacks.jsonl; item stays unruled)
is the ask mechanic's session-scale form.

**Still open (not settled by the adoption):** who picks the 4–7 readers
(working design: the clerk, by fit, extending the best-four rule); the
always-ask pair ("has this been decided before?" / "what standing rules
touch this?" on every packet); packet clock classes (hard-dated vs open —
proposal only).

**Build order for this revision:** (1) profiles for the remaining 13 seats;
(2) first-read ask pass in the harness (seats return questions, not calls;
clerk collects per packet); (3) clerk menu jobs: deepen (in-house answers +
filed requests + merge on return) and fact-check; (4) brief pullers wired
per the profiles' standing data needs; (5) the clerk's re-presentation step
(needs met → packet flows on, sendback store resent-marking).

---

## Appendix (added 2026-10-25): THE SPLIT LADDER — resolving decider disagreement without Brian

Direction (Brian, 2026-10-25): come up with a way to resolve Altair–Meghan splits that tries not to send issues to him. Built the same day from a two-sided study (the house record + deep research into multi-agent systems, organizational practice, and practitioner builders; full study: "Resolving Decider Splits Without Escalating", research notes 2026-10-25). Status: built as machinery + protocol; the ladder itself is presented to Brian as a proposal for ruling.

WHEN IT FIRES: Altair and Meghan have the research back and still disagree. Before anything else, the split is NAMED — one of seven locus classes: weights (priorities weighed differently), research (soft/conflicting/stale), scope (research opened a new question), risk (act-now-vs-wait appetite), rules (two standing rules collide), misread (one side misread or anchored), framing (the packet was framed around the wrong problem). The class picks the route (harness/splitlog.py ROUTES).

THE LADDER (in order; a step runs only if the split survives the ones before it):
1. DECOMPOSE — break the split into sub-questions, load-bearing assumptions, and value weights; each decider answers each piece blind; re-litigate only the exact locus. Most whole-decision splits collapse here.
2. PRECEDENT — search prior decisions (the R36 ledgers, now fed) and Brian's standing priority order; if a rule or a prior ruling covers it, apply it and cite it.
3. MIND-CHANGING TEST — both deciders state in advance what evidence would flip them; the system runs exactly that check (tool, test, primary source, fresh pull); both abide by the outcome. One cycle.
4. ONE BLIND EXCHANGE — each steelmans the other; both run a key-assumptions check and a short premortem on the leading course; justifications only are exchanged; then a blind re-vote. No open thread, no third round (measured: debate's benefit concentrates in the first exchange; more rounds buy sycophancy).
5. JUDGE DIAGNOSTIC — a leftover FACTUAL point only: a small cross-family panel (families disjoint from both deciders, blind to who argued which side) issues an advisory finding; the deciders re-vote. Never a deciding vote; never on a value question.
6. REVERSIBILITY FALLBACK — still split: reversible → proceed with the least-regret course as a bounded pilot (smallest step, monitoring trigger, expiry date; the R36 outcome record judges it). Irreversible → wait / no-act.

ESCALATION TO BRIAN — only three doors: (a) irreversible and still split after the ladder; (b) two standing rules collide with no precedence covering them — his answer is recorded as a new standing rule so the class never escalates twice; (c) the mind-changing test cannot be run.

THEATER — do not build: long open-ended debate, assigned devil's-advocate personas, confidence face-offs, a single tie-breaker judge, two-agent votes or "prediction markets" (category error at n=2), the full ACH matrix.

RECORD: every split, locus, step, and resolution goes to board-splits.jsonl (harness/splitlog.py SplitLog). The morning loop reads locus counts: recurring loci are upstream faults (framing, research quality, missing standing rules), not decider faults.

FEEDING THE ARBITER: since 2026-10-25 the harness logs every ruled call automatically — ≥0.98 to atlas.board_suggestions (releases), below to atlas.board_ideas (R37 routing, DB-enforced) — and the 113 historical rulings were backfilled, so precedent (step 2) and outcome-judging (step 6) have real data to work with.
