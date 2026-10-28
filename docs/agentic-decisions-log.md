# The Agentic Decisions Log

**Purpose.** This log records decisions made by the AGENTS and the SYSTEM — choices taken inside delegated space while executing Brian's directives: defaults chosen, structures picked, thresholds set, enforcement shapes designed. These are not Brian's rulings. They are the judgment calls the machinery made on the way to carrying his rulings out, and they shape the ecosystem's future just the same. Brian ordered this log kept (2026-10-28) "so you can tell me about them some day" — retrieval and narration back to Brian is the point of the document.

**The distinction.** Brian's own rulings live in the decision machinery and MEMORY. Entries here are ONLY agentic/system decisions: things no Brian ruling specified, where an agent or a piece of code had to choose. Where an entry touches one of Brian's rules, the entry is about how the rule was *implemented*, never about changing it.

**Standing rule for agents.** Any agent (or build) that makes a choice which will shape future behavior — a default, a threshold, a schema shape, an enforcement mechanism, a placement, a cadence — appends an entry here in the same pass, in the entry format below. A shaping choice left only in a chat transcript or a build report is a logging failure, the same way a Brian ruling left only in a transcript is a storage failure.

**Entry format.** Date · **Decision** (one line) · Made by · Context (what directive was being executed) · Why (the reasoning) · What it shapes (what future behavior this constrains or enables) · Reversibility (how Brian overrides it, and what overriding costs).

**Immutability.** Entries are never deleted or rewritten. A decision that is later changed is SUPERSEDED by appending a new entry that names the old one; the old entry stays as the record of what was decided at the time.

---

## Entries

### 2026-10-28 · 1. Blog-fleet honesty rule: UNKNOWN is the enforced default state
- **Made by:** CampaignsDesk blog_fleet build agent, executing Brian's blog-registration directives.
- **Context:** The fleet checklist (`blog_checklist`) needed a state model for 72 standard items across 29 blogs.
- **Decision:** States are present / missing / **unknown**, unknown is the default, and claiming present or missing REQUIRES naming the checker who verified it.
- **Why:** A checklist that defaults to "fine" manufactures false readiness. Unknown is the honest state; a named checker makes every non-unknown claim attributable.
- **What it shapes:** Every fleet readiness number from now on. Nothing in the fleet can silently look complete.
- **Reversibility:** Brian can order a different state model at any time; existing rows keep their recorded states and checker names.
- **Source:** Intel Bridge capture #442.

### 2026-10-28 · 2. Scorecard design: raw traffic metrics stay separate; value metrics are derived
- **Made by:** CampaignsDesk blog_fleet build agent.
- **Context:** `blog_scorecards` had to store blog performance under Brian's attention chain (visits → contacts → revenue).
- **Decision:** unique_visits, sessions, and pageviews are stored as SEPARATE columns (never merged into one "traffic" number); contacts/1,000 and revenue/1,000 are DERIVED from the raw columns, never stored as primary facts.
- **Why:** The three traffic metrics answer different questions (and ad networks key on different ones); merging them destroys information. Derived ratios can always be recomputed from honest raw inputs.
- **What it shapes:** All fleet reporting, ramp-stage promotion evidence, and the dual-maximization review's inputs.
- **Reversibility:** Brian can add metrics or change derivations; raw history is preserved by design.
- **Source:** Intel Bridge capture #442.

### 2026-10-28 · 3. Missed reviews read carried_forward — they never vanish
- **Made by:** CampaignsDesk blog_fleet build agent.
- **Context:** The review cadence machinery (`review_cadence` / `review_events`) needed a state for a review whose date passes unheld.
- **Decision:** An owed review reads due → **carried_forward**, indefinitely, until held. There is no expired/dropped state.
- **Why:** Direct implementation of Brian's calendar carry-forward law ("the calendar cannot forget") at the machinery's own initiative in the review layer.
- **What it shapes:** Review debt is permanent and visible; the fleet can accumulate an honest backlog instead of a silent one.
- **Reversibility:** Brian can forgive specific carried reviews explicitly; the machinery will not do it on its own.
- **Source:** Intel Bridge capture #442.

### 2026-10-28 · 4. Multi-language eligibility: machinery default = top decile by contacts; languages never assumed
- **Made by:** Multi-language layer build agent, encoding Brian's "multi-language our best stuff" directive.
- **Context:** Brian ruled that translation is earned by attention but set no threshold and no per-blog languages.
- **Decision:** Default eligibility threshold = **90th percentile (top decile) of the blog's measured articles, by CONTACTS** (threshold_pct default 90, basis default 'contacts'); per-blog language sets start EMPTY (unset — never assumed; standing facts recorded: Tagalog + English for PH-facing blogs, Spanish a standing candidate); **unmeasured articles can never be eligible**, because eligibility is computed from measured attention only.
- **Why:** Contacts sit mid-chain (visits → contacts → revenue) and prove an article converts, not just attracts. A default had to exist for the machinery to run; it is labeled everywhere (code, doc, CLI) as a MACHINERY default Brian tunes per blog in the planning package.
- **What it shapes:** Which articles get translation investment across the whole fleet, and how much.
- **Reversibility:** Fully Brian's: threshold and basis are per-blog policy fields he sets in each planning package; changing them re-computes eligibility from stored metrics.
- **Source:** Intel Bridge capture #485.

### 2026-10-28 · 5. Voice-basis enforcement: no code path records an unconsented clone
- **Made by:** Multi-language layer build agent, implementing Brian's Gina clone-consent ruling inside the edition machinery.
- **Context:** Article editions include video/audio versions in other languages, where cloned voices would be the easy path.
- **Decision:** A media edition can be recorded `present` ONLY with a named voice basis — `consented_clone` (which asserts explicit consent under the fleet clone law), `platform_voice`, or `human_narrator`. There is deliberately NO code path by which an unconsented clone can be recorded as present; text editions refuse any voice basis at all.
- **Why:** A consent rule that lives only in prose can be bypassed by the next build. Encoding it as a schema-level refusal makes the violation unrepresentable, not just discouraged.
- **What it shapes:** Every future media edition in every language across the fleet — consent is enforced by the type system of the record, not by vigilance.
- **Reversibility:** Brian can add a voice basis or relax the rule by ordering a code change; until then the refusal stands even against agent error.
- **Source:** Intel Bridge capture #485.

### 2026-10-28 · 6. Promotion state modeled on the existing article registry — no second registry
- **Made by:** Article-promotion layer build agent, encoding Brian's promotion-package directive.
- **Context:** Per-article promotion tracking needed an article identity to attach to.
- **Decision:** Promotion state lives in `campaignsdesk.article_promotion`, keyed to content_pm's EXISTING `content_items` registry (ON DELETE CASCADE). No new article registry was created; content_pm owns articles, blog_fleet stores promotion state against them.
- **Why:** Two registries for the same articles would drift apart and manufacture reconciliation work forever. One owner per entity is the fleet's standing shape.
- **What it shapes:** All future per-article layers (Hiro audio state, ML editions, anything article-scoped) inherit the same anchor and the same discipline.
- **Reversibility:** A future consolidation could re-key the tables; the no-second-registry principle would argue against it.
- **Source:** Intel Bridge capture #481.

### 2026-10-28 · 7. Mindell watch shape: 02:20 daily, flags candidates, never advances the ladder
- **Made by:** Mindell Atlas-node build agent, executing Brian's directive that the ecosystem think about the launch daily.
- **Context:** The readiness plan's trigger ladder (T0–T6) needed a daily automated watch without automating judgment.
- **Decision:** The watch runs daily at **02:20** (ahead of the 02:30 board, same slot family as sprawl-watch at 02:10); signal checks are hash+keyword watches on fetchable sources; sources that are bot-walled from alpha (Square One, and alongside it BookHype, Target, Amazon, Edelweiss, Mindell's Facebook) are classified **agent-only** rather than silently skipped; the script **FLAGS ladder-advance candidates but never advances the ladder** — confirming a trigger stays an agent/Brian judgment.
- **Why:** Automation is trustworthy for state, diffing, and filing; it is not trustworthy for deciding that a launch phase has begun. The cadence slot puts the packet in the board's hands the same morning.
- **What it shapes:** How every future launch watch in the ecosystem should be built — this is now the reference shape.
- **Reversibility:** Brian can order ladder advances manually at any time, change the slot, or authorize the script to advance specific triggers.
- **Source:** Intel Bridge capture #468.

### 2026-10-28 · 8. Atlas type inventions: `product` and `pattern` node types; Mindell as payload, not a person node
- **Made by:** Mindell node build agent and Interception Pattern registration agent, working in Atlas during today's builds.
- **Context:** Atlas had no type for a sellable product slot or for a repeatable pattern; Earl Mindell needed representing in the launch node.
- **Decision:** Two node types were introduced — `product` (prod:oliabo-prima, prod:oliabo-evoo, prod:mindell-olive-oil-bible) and `pattern` (pattern:interception hub + instance nodes). Mindell himself is carried as **payload inside the launch node, NOT as a person node**, because Atlas person nodes are harvested lead records (person:<numeric id>) and a public-figure ally is not a lead.
- **Why:** Forcing existing types would have corrupted two registries at once: products would have masqueraded as projects, and a named ally would have entered the lead pool.
- **What it shapes:** The Atlas type vocabulary every future build inherits; product slots across all programs now have a home type, and patterns are first-class graph citizens.
- **Reversibility:** Brian can order types merged or renamed; edges and payloads survive a type migration.
- **Sources:** Intel Bridge captures #468, #483.

### 2026-10-28 · 9. AMD placed WATCH-ONLY: Brian's own accumulation screen applied to his own watch request
- **Made by:** AMD watch setup agent, executing Brian's "track AMD and potentially buy it" direction.
- **Context:** The natural home for a new watch was TradesDesk's quality_accumulation sleeve, whose starter watchlist carries Brian's 2026-10-20 accumulation doctrine (valuation screen; independence from the AI capex cycle).
- **Decision:** AMD was added **watch-only**, with the doctrinal flag recorded on the entry: at P/E ~135 and +170% YTD it FAILS the sleeve's screen, so under Brian's own doctrine it is tracked, not accumulated — accumulation requires a screen pass (a real de-rating / crash-ladder moment) or Brian's deliberate owner override. The price snapshot was filed to `successbrian_os.price_intel` (row id 25, capture #467) with the standard **7-day shelf life** (checked 2026-10-28, valid_until 2026-11-04).
- **Why:** The agent's job was to place the watch inside Brian's system as his system is written — not to let enthusiasm for the company silently rewrite his accumulation rules. The flag keeps the tension visible instead of resolved by stealth.
- **What it shapes:** How future watch requests get placed when the named asset conflicts with the sleeve's doctrine: doctrine applies, flag recorded, override reserved to Brian.
- **Reversibility:** Brian's override is explicit and instant — one ruling from him moves AMD to accumulation-eligible; the entry records that this is HIS call, not the screen's.
- **Source:** Intel Bridge capture #467; price_intel row 25.

### 2026-10-28 · 10. Interception scouting initially rides existing machinery — no dedicated watch script
- **Made by:** Interception Pattern registration agent, encoding Brian's scouting mandate.
- **Context:** The mandate ("find instances happening all over") needed a working cadence the day it was ruled, before any dedicated system existed.
- **Decision:** Scouting was seated on EXISTING machinery — the daily board agenda consuming `task:interception-scout`, the clerk's capture sweep, and desk/agent discovery filed through the Intel Bridge — rather than waiting for, or improvising, a dedicated watch script. The record states this plainly as cadence honesty.
- **Why:** A mandate with no operating seat dies in the transcript; a mandate riding live machinery starts tomorrow morning. The gap (no mechanical periodic sweep) was named instead of papered over.
- **What it shapes:** Interim discovery coverage for interception candidates until the dedicated system lands.
- **Status note:** A dedicated Interception Intel Discovery System is now BUILDING on Brian's later order (2026-10-28 16:09 CDT); when it lands, its build agent must append a superseding entry here.
- **Source:** Intel Bridge capture #483.

### 2026-10-28 · 11. Hiro audio step encoded as its own article section + table; pipeline completeness gates only on the steps every article owes
- **Made by:** Hiro audio-step encode agent (Muse subagent), executing Brian's 16:04 CDT directive ("audio integration into hiro.fm is also part of the flow — after each article is written").
- **Context:** blog_fleet.py already tracked a per-article promotion package (section 'promotion', table article_promotion, scope-filtered reads). The Hiro step needed the same per-article tracking without contaminating the promotion surfaces, inside a file three sibling encodes were landing the same day.
- **Decision:** (1) The Hiro step is its own section ('article_pipeline') with its own state table (campaignsdesk.article_hiro), mirroring article_promotion's shape and unknown-default honesty discipline, rather than reusing the promotion table or the blog checklist. (2) Companion repair: the promotion layer's materialize/read/set paths are section-filtered (section='promotion'), and each setter refuses the other section's items — without this, the scope-only filters would have swept Hiro items into promotion gaps. (3) article_pipeline_state's top-level 'complete' gates on written + Hiro + promotion only; the multi-language step is READ from the ML layer's own verdicts (eligible / not_eligible / unmeasured via ml_eligible_articles / ml_gaps), never re-derived and never gating, because editions are earned downstream, not owed by every article. (4) Tracking materializes for published articles (the promotion layer's universe); ensure/set accept any content item so pre-publish tracking stays possible by hand.
- **Why:** One section per pipeline step keeps each step's gaps attributable and its machinery independently checkable; reading sibling verdicts instead of re-deriving them keeps a single source of truth per step (the same courtesy the sibling encodes extended each other all day: items carried verbatim, CHECK widened to the union, seed delete-guard).
- **What it shapes:** How every future per-article pipeline step gets added to blog_fleet: new section + own state table + section-filtered paths + a pipeline view that reads, never re-derives, sibling verdicts.
- **Reversibility:** Purely additive machinery — Brian can retire the step by ruling it out; states already recorded stay as history. The section filter on promotion paths is behavior-preserving for promotion-only data (selftest green across all four encodes).
- **Source:** Intel Bridge capture #492; campaignsdesk commit 600c477; QA checks 199 + 200 on PM project blog-fleet.
---

*Log created 2026-10-28 on Brian's order. Canonical copies: this file in the successbrian-os repo (docs/) and the embedded document of the same filename in the SuccessBrian OS AnythingLLM workspace. On update, edit the repo file and re-embed (replace-on-update) so exactly one current edition lives in the workspace.*
