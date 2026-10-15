# Ecosystem Needs Plan — when each workload gets its home
<!-- PURPOSE: for every major ecosystem workload, WHERE it runs now, WHAT serves it
     next, and WHEN (roadmap phase or trigger).
     WHY: the fleet roadmap covers build order; this covers workload placement —
     the two meet at the phases.
     CALLED BY: Brian, Spencer, Altair, DealsDesk (sourcing follows the needs).
     NOTES: drafted 2026-10-10 per Brian. Open questions marked [BRIAN'S CALL].
     Standing gates: scale-up spend only when making money; measure before upgrading.
     The move next year affects all physical placements — nothing big lands at
     Chaska that would have to move twice. -->

## 1. Web hosting (public apps + 100-blog network)

- **Now:** Supabase + Netlify (bolt.new stack). Per Brian 2026-10-02, the ecosystem
  cannot self-host public web apps yet — this stays until the home-lab web tier
  is ready. NETLIFY RULE (Brian 2026-10-10): free tier ONLY, never pay — if the
  free tier can't carry the load, self-host or move to another free host
  (e.g. Cloudflare Pages).
- **Next:** a custom CMS to host their own blogs (per Brian 2026-10-10). Strategy:
  start distributed — run a few here and there where they fit (Netlify free tier,
  other free hosts); eventually build a home-lab home for them, prioritizing the
  strongest performers. The winners earn the infrastructure.
- **WHEN:** CMS build is software work (no hardware phase needed — can start any
  time); the home-lab home waits for post-move (section: cross-cutting gates).

## 2. Scrapers (Vera/MSV, SearXNG, worker fleet)

- **Now:** murky. Vera's MSV pipeline showed 12 scrapers live since 2026-09-30,
  but Altair flagged zero throughput 2026-10-05 and a 2026-10-07 check found no
  scraper processes on k11-alpha. Status needs re-verification before new hardware
  is bought for it.
- **Planned homes:**
  - R630 (Brian 2026-10-10): VERA'S HOME — MSV scraping + Vera/enrichment pipeline on the Proxmox multi-role node (no more waiting on a Mantis-5 build)
  - Mantis-6/7/8 (dual-LGA2011 builds, if built): SearXNG workers, AI analysis, scraper overflow
  - SearXNG core: fix where it sits (k11-alpha) or park on the scheduler box —
    no dedicated box needed per 2026-10-07
- **Model (per 2026-10-07):** (1) SearXNG core fixed, (2) scraper worker fleet
  (dual-2011 builds or Z240s; jobs in Postgres, results to ecosystem_central),
  (3) egress/anti-block rotation across gamma, node zero, k11-alpha (3 free IPs,
  ~60k/day combined ceiling — no proxy spend until revenue).
- **WHEN:** verify current scraper status FIRST (no hardware for a pipeline that
  isn't running). Worker fleet builds with Phases 1–3 hardware; SearXNG fix is
  software work, no phase needed. [BRIAN'S CALL: are the LGA2011 builds in the
  Phase 1–3 build order, or their own sequence?]

## 3. Agent boxes (agent homes)

- **Now:** Altair on k11-alpha (Qwen3.6-35B-A3B, the heavy worker). Meghan
  (OpenClaw CEO) and other agents run where their hosts are.
- **K11-ALPHA ROLE (Brian 2026-10-10): AI inference ONLY.** Everything else on
  k11-alpha — scheduler/crons, SearXNG, scrapers, utility DBs, monitoring,
  scripts — gets homed elsewhere, with the R630 taking what it can.
  (Altair to inventory k11-alpha's services and propose the offload map.)
- **Rule (per Brian 2026-10-07):** routines/crons move OFF agent homes and k11-alpha
  onto a dedicated scheduler node — agents keep their boxes for thinking, the
  scheduler owns the timetable.
- **WHEN:** scheduler node is a near-term need (it unloads k11-alpha, which is
  carrying cron + agents + DB today). Agent homes beyond k11-alpha: as the agent
  count grows; no phase assigned yet. [BRIAN'S CALL: which physical box becomes
  the scheduler node?]

## 4. Script boxes (always-on utility runners)

- **Need:** always-on x86 nodes for hosting, scrapers, code/DB runners — the
  unglamorous workhorses. 4× HP Z240 SFF ($640) was proposed; per
  hardware-2026-10-07 the Z240 buy is still UNDECIDED (superseded by SearXNG
  being lightweight? workers = Box 3–4?).
- **WHEN:** unresolved — the Z240 question needs Brian's call before any script-box
  phase exists. The scheduler node (section 3) is the first concrete piece.
  [BRIAN'S CALL: Z240s yes/no, or do the dual-2011 builds cover it?]

## 5. Gen 8/9/10 systems (fabric + inference lanes)

- **Plan (roadmap Phase 4):** Gen8 (E5-2650 v2+, each = 2× 150B slices), Gen9
  (E5-2650 v4+, DDR4, native NVMe — ideal fabric citizens), Gen10 as they come.
- **WHEN:** Phase 4, after X79s + Echo are done. TRIGGER: measured demand from
  Phases 0–3 + revenue gate. DealsDesk already scores rack-server candidates
  (rack_server_scorer.py).

## 6. Databases

- **Now:** PostgreSQL (ecosystem_central) on k11-alpha; people.people slices on
  DL380s.
- **Open (per hardware-2026-10-07):** Echo Postgres vs DL380 #1 Postgres split —
  still undecided.
- **WHEN:** with the Echo decision (Phase 2) and DL380 provisioning (Phase 4).
  [BRIAN'S CALL: Echo Postgres vs DL380 #1 split.]

## Cross-cutting gates

- **The move next year** freezes big physical commitments at Chaska: no 42U rack,
  no home-lab web hosting, nothing that would move twice. Test-size hardware
  (X3 unit, minis) is fine.
- **Movable-first rack strategy** (Brian 2026-10-10): start with smaller rack
  systems that transport easily — RAV4-carriable, disassemble/reassemble for moves
  (open frames break down to flat posts). Era 2 rack target: TWO 20U open-frame
  4-post frames (balanced, per Brian 2026-10-10) — Frame A: 2x X79 @ 4U
  (Mantis-3/4) + 2x DL380 @ 2U + Dell R630 @ 1U + Node Echo @ 2U = 15U (5U
  free); Frame B: 2x X79 @ 4U (Mantis-1 image/video, Mantis-2 text) = 8U
  (12U free) — the content frame. Proxmox cluster spans BOTH frames (all 8
  nodes); Echo is the rack timekeeper. Both become satellite racks at Fridley.
  Either way: 4-post, adjustable depth (~30") for DL380 rails.
  RACK DISCIPLINE (Brian 2026-10-10): every U must count toward improving the
  ecosystem — no filler slots; each U earned by a workload, decided case by case.
  NETWORKING CONSTRAINT (Brian 2026-10-10): the X79s/rack servers are wired-only
  (no wifi) — both frames and any overflow must sit within easy cable reach of
  the switch. Plan switch port count for everything in/near the racks. The
  serious rack builds (42U, X5 cluster, X3 blade shelf, full DL380 rows) wait for
  the permanent home.
- **Revenue gate** applies to Phases 4–11 scale-up (except Phase 12 cluster:
  ecosystem-readiness gate).
- **Measure-first:** no hardware for a workload that isn't proven running
  (scrapers rule #1).

## What could change this

- Brian's answers to the four [BRIAN'S CALL] items above
- Move timing/location — re-homes everything physical
- Scraper status verification — could accelerate or kill section 2 hardware
- A revenue step-change — pulls forward Phases 4–11
