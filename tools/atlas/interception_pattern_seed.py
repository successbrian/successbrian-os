#!/usr/bin/env python3
"""interception_pattern_seed.py — build record for the Interception
Pattern framework registration in Atlas.

Brian's directive (2026-10-28 16:08 CDT): "the mindell/gundry thing
to oliabo prima and evoo — and other things like it, like the dead
docs cassettes to higher ideals docs rocks that made me money with
seo in the past... this is a framework we can find and repeat over
and over."

This script registers, idempotently, using the write path that works
(psycopg2 via sbos_common — atlas.py add-node/add-edge are broken
since the 2026-10-27 Batch B migration; SQL shapes are atlas.py's
own add_node / add_edge semantics):

  pattern:interception                    (pattern — framework hub)
  pattern:interception/eo-doterra-yl      (pattern — instance 2)
  pattern:interception/docs-rocks-1997    (pattern — instance 3, origin)
  task:interception-scout                 (atlas_task — board mandate)

Instance 1 (Mindell/Gundry -> Oliabo PRIMA+EVOO) is NOT duplicated:
its home is the existing hub launch:mindell-olive-oil-bible; the
pattern links to it (contains) and it links back (implements).

"Interception Pattern" is a DESCRIPTIVE label only — Brian has not
named this framework; the name is his to give. That is recorded in
the hub payload and the doctrine doc (CampaignsDesk workspace,
interception-pattern-doctrine.md).

Re-running is safe: nodes upsert (add_node semantics), edges
ON CONFLICT DO NOTHING (add_edge semantics). The scout task insert
mirrors mindell_watch.file_board_task: skipped while a task with
the key is open/queued (the open task is the carry-forward).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

HUB = "pattern:interception"
MINDELL = "launch:mindell-olive-oil-bible"
EO = "pattern:interception/eo-doterra-yl"
DOCS = "pattern:interception/docs-rocks-1997"
SCOUT = "task:interception-scout"

HUB_DETAILS = {
    "kind": "repeatable_framework",
    "label_status": ("DESCRIPTIVE LABEL ONLY — 'the Interception Pattern' "
                     "is Spencer's descriptive label (2026-10-28). Brian "
                     "has NOT named this framework; the name is his to "
                     "give. Never present the label as Brian's coinage."),
    "directive": ("Brian, 2026-10-28 16:08 CDT: 'the mindell/gundry thing "
                  "to oliabo prima and evoo — and other things like it, "
                  "like the dead docs cassettes to higher ideals docs "
                  "rocks that made me money with seo in the past... this "
                  "is a framework we can find and repeat over and over'"),
    "thesis": ("Brian, 2026-10-28 15:54 CDT: 'we have a unique advantage "
               "to capture easy pickings seo bait and switch funded by "
               "high dollar marketing that should flow to us like crazy "
               "and get thousands of daily unique hits'"),
    "program": ("Brian, 2026-10-28 15:57 CDT: find what SEO searches "
                "their high-dollar marketing spends are going to create; "
                "figure out which ones are low-hanging fruit; dominate "
                "those; be ready for the thousands of daily leads — "
                "automation direct to capture, nurture and close."),
    "mechanics": {
        "a_demand": ("An outside promoter's spend/activity creates "
                     "predictable search demand (book launches, media "
                     "tours, product promotions, viral tape campaigns, "
                     "ad campaigns). Brian does not pay to create it."),
        "b_position": ("Brian's content is PRE-POSITIONED ranking on "
                       "the GENERIC searches that demand creates — "
                       "peacetime positioning, launch-window "
                       "harvesting."),
        "c_honesty": ("Coverage stays honest: genuinely aligned for "
                      "NAMED allies (stance only, never a claimed "
                      "relationship); genuinely generic for NAMELESS "
                      "competitors (never named)."),
        "d_downstream": ("Captured attention flows PRIVATELY to "
                         "Brian's downstream (CRM segment -> nurture "
                         "-> the product/program that fits). The "
                         "downstream is never the public identity of "
                         "the capturing content."),
    },
    "instance_criteria": [
        "A promoter with real spend/reach creating PREDICTABLE search demand",
        "A generic search surface Brian can legitimately rank on",
        "A private downstream that genuinely serves the captured intent",
        "A timing window (known dates or standing demand)",
        "A naming treatment per the competitor/ally law (named ally = stance only; nameless competitor = generic interception), ruled by Brian one at a time",
    ],
    "instances": [
        {"node": MINDELL, "n": 1, "state": "live — launch window",
         "play": "Mindell (named ally) / Gundry (nameless competitor) "
                 "olive-oil demand -> longevity-olive blog -> Oliabo "
                 "PRIMA + EVOO (private, internal only)"},
        {"node": EO, "n": 2, "state": "registered — Stage 0 blog",
         "play": "doTERRA + Young Living category demand -> Essential "
                 "Oils Everyday blog -> Zilara (private, internal only)"},
        {"node": DOCS, "n": 3, "state": "historical — ORIGIN (1997)",
         "play": "Dead Doctors Don't Lie cassette wave -> Higher "
                 "Ideals 'Docs Rocks' (Brian's 1997 money)"},
    ],
    "scouting": {
        "task": SCOUT,
        "mandate": ("Standing: desks surface candidate instances "
                    "scored on the five criteria, filed as proposals; "
                    "Brian rules ONE AT A TIME (candidate law, "
                    "2026-10-28); a scout finding never auto-executes "
                    "— no registration, content, outreach or spend."),
        "cadence_honesty": ("Rides EXISTING machinery today: the "
                            "daily board agenda (atlas_task nodes), "
                            "the clerk's capture sweep, desk/agent "
                            "discovery via the Intel Bridge. NO "
                            "dedicated interception watch script "
                            "exists; a mechanical periodic sweep "
                            "(interception_watch.py on the sprawl/"
                            "mindell watch pattern) is new code, built "
                            "only on Brian's order."),
    },
    "doctrine_doc": {"workspace": "campaignsdesk",
                     "doc": "interception-pattern-doctrine.md"},
    "pm_project": "interception-pattern",
    "registered": "2026-10-28",
}

EO_DETAILS = {
    "kind": "interception_instance",
    "instance_n": 2,
    "pattern": HUB,
    "state": "registered — the capturing blog is Stage 0 (registered "
             "2026-10-28, batch 7); nothing published",
    "capture_surface": "asset:blog/essential-oils-everyday",
    "audience_band": "generic health, under-$100K (counterpart to "
                     "longevity-olive's over-$100K band)",
    "demand_creators": ["doTERRA", "Young Living"],
    "competitor_ruling": ("Brian, 2026-10-28 15:48 CDT: 'doterra and "
                          "young living would be competitive — we "
                          "want to grab their markets into zilara.'"),
    "naming_treatment": ("Competitors RULED; the on-page NAMING "
                         "sub-decision is still Brian's to make — "
                         "charter default until he rules: GENERIC-ONLY "
                         "coverage (target the specific oils/rival "
                         "product spaces generically, from the real "
                         "goDesana catalog)."),
    "editorial_doctrine": ("Hole-finding engine (capture #466): "
                           "evidenced gaps in the rivals' models "
                           "(proprietary-blend opacity, premium "
                           "pricing, unanswered searches) met by the "
                           "counters designed into Paula's line — "
                           "full-label transparency; formulator story "
                           "told generically (formulator NEVER named "
                           "publicly — naming her identifies the "
                           "downstream); honest budget value, prices "
                           "as numbers."),
    "downstream_internal": {
        "project": "proj:zilara",
        "visibility": ("INTERNAL ONLY — Zilara is never the blog's "
                       "public identity; flow is private follow-up."),
    },
}

DOCS_DETAILS = {
    "kind": "interception_instance",
    "instance_n": 3,
    "pattern": HUB,
    "state": "historical — the ORIGIN instance (1997)",
    "brian_words": ("Brian, 2026-10-28 15:56 CDT: 'it's how I made "
                    "HUGE money in 1997 with Higher Ideals selling "
                    "docs rocks when everyone was mailing out dead "
                    "doctors don't lie tapes'"),
    "demand_creator": ("The 'Dead Doctors Don't Lie' cassette wave — "
                       "tapes mailed out at scale by others; their "
                       "distribution created the demand."),
    "capture_offer": ("Higher Ideals 'Docs Rocks' — Brian's phrasing. "
                      "No product details are on record; none are "
                      "invented here."),
    "mechanics_note": ("The 1997 shape of the pattern: somebody "
                       "else's mailing created the audience; Brian's "
                       "positioned offer captured it. The 2026 "
                       "framework is this play digitized (tapes -> "
                       "searches; positioned offer -> pre-positioned "
                       "content; downstream -> CRM)."),
    "lineage": ("Paula Scarcella was Brian's downline in Higher "
                "Ideals in 1997-98 (Brian, 2026-10-23, on record). "
                "She is today founder/CEO of Zilara (Green Organics, "
                "LLC) — the private downstream of Instance 2. The "
                "human thread runs from the origin instance into the "
                "live fleet."),
}

NODES = [
    (HUB, "pattern",
     "The Interception Pattern — repeatable capture framework "
     "(descriptive label; unnamed by Brian)",
     "active", HUB_DETAILS, None, None),
    (EO, "pattern",
     "Interception instance 2 — Essential Oils Everyday blog: "
     "doTERRA / Young Living demand -> Zilara (private)",
     "registered", EO_DETAILS, None, None),
    (DOCS, "pattern",
     "Interception instance 3 (ORIGIN, historical, 1997) — Dead "
     "Doctors Don't Lie cassette wave -> Higher Ideals 'Docs Rocks'",
     "historical", DOCS_DETAILS, None, None),
]

EDGES = [
    (HUB, MINDELL, "contains",
     "Instance 1 — the live citizen. Its own hub holds the trigger "
     "ladder, readiness plan and daily mapping cadence; not "
     "duplicated here."),
    (HUB, EO, "contains",
     "Instance 2 — doTERRA/Young Living demand intercepted by the "
     "Essential Oils Everyday blog, flowing privately to Zilara."),
    (HUB, DOCS, "contains",
     "Instance 3 — the 1997 origin instance (historical)."),
    (MINDELL, HUB, "implements",
     "The Mindell/Gundry -> Oliabo PRIMA/EVOO play is the pattern's "
     "first live implementation."),
    (EO, HUB, "implements",
     "The EO blog's doTERRA/YL interception is an implementation of "
     "the pattern."),
    (DOCS, HUB, "implements",
     "The 1997 Docs Rocks play is the pattern's origin "
     "implementation — the framework is this play, repeated."),
    (EO, "asset:blog/essential-oils-everyday", "about",
     "The instance's capture surface (blog asset node; its R38 "
     "markets/captures_for edges to proj:zilara already exist)."),
    (EO, "proj:zilara", "feeds",
     "INTERNAL wiring only: captured audience flows privately to "
     "Zilara in follow-up; Zilara is never the blog's public "
     "identity."),
    (DOCS, "proj:zilara", "about",
     "LINEAGE: Paula Scarcella — Brian's downline in Higher Ideals "
     "(1997-98) — is founder/CEO of Zilara, Instance 2's private "
     "downstream. The human thread from the origin instance to the "
     "live fleet."),
    (HUB, "allm:campaignsdesk", "about",
     "The framework doctrine document lives in the CampaignsDesk "
     "workspace (interception-pattern-doctrine.md); CampaignsDesk "
     "owns blogging and this framework's scouting."),
]

SCOUT_NAME = (
    "INTERCEPTION SCOUT — standing mandate: surface candidate "
    "instances of the Interception Pattern (pattern:interception) "
    "scored on its five criteria (real promoter spend creating "
    "predictable search demand; a generic surface Brian can rank "
    "on; a genuine private downstream; a timing window; a naming "
    "treatment per the competitor/ally law). File each candidate "
    "as a proposal (Intel Bridge capture / board item) for Brian — "
    "ONE AT A TIME, his ruling before the next (candidate law). "
    "NEVER auto-execute: no blog registration, content, outreach "
    "or spend follows from a scout finding. Cadence: this mandate "
    "rides the board agenda + clerk sweep + desk discovery; no "
    "dedicated watch script exists (new code only on Brian's "
    "order). Doctrine: campaignsdesk workspace, "
    "interception-pattern-doctrine.md.")

SCOUT_DETAILS = {"about": HUB, "found_by": "interception-pattern-seed "
                 "(Brian directive 2026-10-28 16:08 CDT)",
                 "model": "sonic"}


def main():
    conn = sbos_common.connect(user="postgres")
    try:
        cur = conn.cursor()
        for key, ntype, name, status, details, ref_kind, ref_id in NODES:
            cur.execute(
                "INSERT INTO atlas.nodes (node_key, node_type, name, status, "
                "details, ref_kind, ref_id) VALUES (%s, %s, %s, %s, %s::jsonb, "
                "%s, %s) ON CONFLICT (node_key) DO UPDATE SET "
                "name=EXCLUDED.name, status=EXCLUDED.status, "
                "details=EXCLUDED.details, updated_at=NOW()",
                (key, ntype, name, status, json.dumps(details),
                 ref_kind, ref_id))
            print("node %s" % key)
        for frm, to, etype, notes in EDGES:
            cur.execute(
                "INSERT INTO atlas.edges (from_node, to_node, edge_type, "
                "notes) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (from_node, to_node, edge_type) DO NOTHING",
                (frm, to, etype, notes))
            print("edge %s -[%s]-> %s" % (frm, etype, to))
        # Scout task — mindell_watch.file_board_task semantics:
        # skip while an open/queued task with the key exists.
        cur.execute(
            "SELECT node_key FROM atlas.nodes WHERE node_key=%s AND "
            "status IN ('open', 'queued')", (SCOUT,))
        if cur.fetchone():
            print("task %s already on the board's agenda (open)" % SCOUT)
        else:
            cur.execute(
                "INSERT INTO atlas.nodes (node_key, node_type, name, "
                "status, details) VALUES (%s, 'atlas_task', %s, "
                "'queued', %s::jsonb) ON CONFLICT (node_key) DO UPDATE "
                "SET name=EXCLUDED.name, status=EXCLUDED.status, "
                "details=EXCLUDED.details, updated_at=NOW()",
                (SCOUT, SCOUT_NAME, json.dumps(SCOUT_DETAILS)))
            print("task %s filed (board agenda)" % SCOUT)
        cur.execute(
            "INSERT INTO atlas.edges (from_node, to_node, edge_type) "
            "VALUES (%s, %s, 'about') ON CONFLICT DO NOTHING",
            (SCOUT, HUB))
        print("edge %s -[about]-> %s" % (SCOUT, HUB))
        conn.commit()
        cur.execute(
            "SELECT from_node, edge_type, to_node FROM atlas.edges WHERE "
            "from_node LIKE 'pattern:interception%%' OR to_node LIKE "
            "'pattern:interception%%' OR from_node=%s ORDER BY from_node, "
            "edge_type, to_node", (SCOUT,))
        print("\nVERIFY — edges touching the pattern family:")
        for f, t, to in cur.fetchall():
            print("  %s -[%s]-> %s" % (f, t, to))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
