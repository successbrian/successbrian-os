#!/usr/bin/env python3
"""mindell_node_seed.py — build record for the Mindell opportunity node.

Brian's directive (2026-10-28 15:53 CDT): the Mindell Olive Oil Bible
launch window "is a huge atlas node that the ecosystem needs to
start thinking and mapping daily how we can align with it, improve
it, etc". This script creates that hub node and its typed edges in
Atlas, idempotently, using the write path that works (psycopg2 via
sbos_common — atlas.py add-node/add-edge are broken since the
2026-10-27 Batch B migration: pg_lines tries to fetch rows from an
INSERT with no RETURNING). The SQL shapes below are atlas.py's own
(add_node / add_edge verbatim semantics).

Nodes created:
  launch:mindell-olive-oil-bible  (project — the launch: convention)
  prod:mindell-olive-oil-bible    (product — the book itself)
  prod:oliabo-prima               (product — INTERNAL slot)
  prod:oliabo-evoo                (product — INTERNAL slot)
  cron:mindell-watch              (cron_job — the daily cadence)

Earl Mindell is recorded in the hub node's payload, NOT as a
person node: atlas person nodes are harvested lead records
(person:<numeric id> from public.people). Mindell is a public-
figure named ally, not a harvested contact — forcing that type
would misclassify him. (Task instruction, 2026-10-28.)

Re-running is safe: nodes upsert (add_node semantics), edges
ON CONFLICT DO NOTHING (add_edge semantics).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

HUB = "launch:mindell-olive-oil-bible"
BOOK = "prod:mindell-olive-oil-bible"
PRIMA = "prod:oliabo-prima"
EVOO = "prod:oliabo-evoo"
CRON = "cron:mindell-watch"

OPEN_ITEMS = [
    {"id": "package-and-go", "opened": "2026-10-28", "state": "open",
     "title": "Longevity-olive planning package completed + Brian's PP12 launch go "
              "(blog is Stage 0 registered today; nothing launches without the package)"},
    {"id": "author-hub", "opened": "2026-10-28", "state": "open",
     "title": "Author hub page drafted (Mindell backlist / Bible-franchise map) — "
              "BUILD NOW per readiness plan; backlist search demand exists today"},
    {"id": "olive-library", "opened": "2026-10-28", "state": "open",
     "title": "Olive substance library deepened (polyphenols, oleocanthal, quality "
              "testing, dosing) — the blog's core cluster, ranks with or without the book"},
    {"id": "phenolic-tracker-magnet", "opened": "2026-10-28", "state": "open",
     "title": "Phenolic tracker + Olive-Oil Quality Checklist lead magnet built "
              "(the blog's unique data source + moment-fitted capture)"},
    {"id": "crm-segment-plumbing", "opened": "2026-10-28", "state": "open",
     "title": "ContactFlowCRM segment 'longevity-olive / mindell-tour' created and "
              "capture plumbing tested end to end before the window, not during it"},
    {"id": "recap-template", "opened": "2026-10-28", "state": "open",
     "title": "Appearance-recap template ready (24-48h SLA during the T5 wave; "
              "missed windows carry forward as recaps per the calendar law)"},
    {"id": "watch-t2", "opened": "2026-10-28", "state": "open",
     "title": "T2 signal watch: Square One announcement and/or pre-order pages open "
              "(expected ~3-5 months before pub date)"},
]

HUB_DETAILS = {
    "kind": "opportunity_node",
    "summary": (
        "OPPORTUNITY HUB — Earl Mindell's 'Olive Oil Bible' launch window. "
        "Brian (2026-10-28): 'a huge atlas node that the ecosystem needs to "
        "start thinking and mapping daily how we can align with it, improve "
        "it, etc'. The longevity-olive blog (>$100K worldwide, flows "
        "privately to Oliabo) is the capture surface; the daily mapping "
        "cadence (cron:mindell-watch) keeps this node's state, signals and "
        "open items current and files board tasks when the window moves."),
    "directive": "Brian, 2026-10-28 15:53 CDT — daily thinking/mapping node (mindell_watch.py).",
    "ally": {
        "name": "Earl Mindell",
        "stance": ("NAMED ALLY of the longevity-olive blog (Brian's ruling, "
                   "2026-10-28 15:37 CDT). Allyship is a positioning stance "
                   "ONLY — no relationship, contact, partnership or "
                   "endorsement is on record, and none may be implied."),
        "born": "1940-01-20",
        "known_for": "The Vitamin Bible franchise (50+ books)",
        "promotion_expectation": ("Brian (2026-10-28): 'mindell may not travel, "
                                  "but he's going to promote this book heavy' — "
                                  "plan for promotion-heavy / travel-light: "
                                  "podcast & talk-radio guest wave, publisher "
                                  "push, industry channels."),
        "channels": ["drearlmindell.com", "facebook.com/drearlmindell",
                     "health podcast / talk-radio circuit",
                     "Square One Publishers publicity"],
        "graph_note": ("Recorded in this payload, not as a person node: atlas "
                       "person nodes are harvested lead records "
                       "(person:<numeric id>); Mindell is a public-figure "
                       "ally, not a harvested contact."),
    },
    "book": {
        "listed_title": "Dr. Earl Mindell's Olive Oil Bible for Wellness & Longevity",
        "insider_title": "The Olive Bible (Brian's insider short form)",
        "publisher": "Square One Publishers",
        "format": "paperback",
        "price_usd": 12.95,
        "listed_pub_date": "2027-05-18",
        "public_state": ("LISTED in public retail/bibliographic metadata "
                         "(BookHype, Target — verified 2026-10-28) but NOT "
                         "announced: no publisher release, no pre-order page, "
                         "no media kit found. Listed != announced; the "
                         "no-scoop ally rule binds in full."),
    },
    "trigger_ladder": {
        "current": "T1",
        "updated": "2026-10-28",
        "rungs": {
            "T0": {"signal": "insider / rumor", "state": "passed (2026-10-28)"},
            "T1": {"signal": "bibliographic + retail metadata live",
                   "state": "LIVE"},
            "T2": {"signal": "publisher announcement + pre-orders open",
                   "state": "watch — expected ~3-5 months out"},
            "T3": {"signal": "media kit + booking announcements",
                   "state": "watch — ~1-3 months out"},
            "T4": {"signal": "publication day",
                   "state": "listed 2027-05-18 (metadata dates can shift)"},
            "T5": {"signal": "appearance wave (promotion-heavy / travel-light)",
                   "state": "future — pub week through ~+8 weeks"},
            "T6": {"signal": "tail / evergreen franchise cycle",
                   "state": "future"},
        },
    },
    "downstream_internal": {
        "project": "proj:oliabo",
        "product_slots": [
            {"node": PRIMA, "name": "Oliabo PRIMA", "price_on_record_usd": 110},
            {"node": EVOO, "name": "Oliabo EVOO", "price_on_record_usd": 39.99},
        ],
        "naming_rule": ("INTERNAL ONLY — Oliabo, PRIMA and EVOO are never "
                        "named on the blog; captured audience flows to them "
                        "privately in follow-up (longevity-olive charter "
                        "targeting map, capture #463)."),
    },
    "competitor_internal": {
        "name": "Dr. Steven Gundry / Gundry MD",
        "stance": ("Nameless competitor — generic comparison + SEO "
                   "interception of his fans' searches; never named on the "
                   "blog (Brian's ruling, 2026-10-28)."),
    },
    "readiness_plan": {
        "workspace_slug": "longevity-olive-blog",
        "workspace_node": "allm:longevity-olive-blog",
        "doc": "mindell-olive-bible-readiness-plan.md",
        "local_copy": ("hatch-vm:~/workspace/research_notes/"
                       "mindell-olive-bible-readiness-20261028/"
                       "mindell-olive-bible-readiness-plan.md"),
        "captures": [464, 465],
    },
    "tracker": {
        "system": "Muse tracked program (Goals tab)",
        "goal_id": "goal_eb6ef82a330f",
        "title": "Mindell Olive Oil Bible launch readiness",
    },
    "daily_cadence": {
        "script": "successbrian-os/tools/atlas/mindell_watch.py",
        "cron": "20 2 * * * — daily 02:20 local, ahead of the 02:30 board "
                "(same board-feeding slot pattern as sprawl-watch, 02:10 Mon-Sat)",
        "board_task_key": "task:mindell-mapping",
        "note_doc": "mindell-daily-mapping.md (longevity-olive-blog workspace; "
                    "allm_embed replace-prior-edition; dated sections accumulate)",
        "snapshots_table": "atlas.mindell_snapshots",
    },
    "open_items": OPEN_ITEMS,
    "last_daily_run": None,
    "days_to_pub_at_build": 202,
}

NODES = [
    (HUB, "project",
     "Mindell 'Olive Oil Bible' launch window — opportunity hub",
     "active", HUB_DETAILS, "muse_goal", "goal_eb6ef82a330f"),
    (BOOK, "product",
     "Dr. Earl Mindell's Olive Oil Bible for Wellness & Longevity "
     "(Square One, listed 2027-05-18)",
     "listed-unannounced",
     {"publisher": "Square One Publishers", "format": "paperback",
      "price_usd": 12.95, "listed_pub_date": "2027-05-18",
      "insider_title": "The Olive Bible",
      "public_state": ("Listed in retail/bibliographic metadata "
                       "(BookHype, Target) 2026-10-28; NOT announced — "
                       "no publisher release, pre-order page or media kit."),
      "author": "Earl Mindell (named ally of the longevity-olive blog; "
                "stance only, no relationship on record)"},
     None, None),
    (PRIMA, "product", "Oliabo PRIMA (internal product slot)", "active",
     {"price_on_record_usd": 110,
      "source": "Brian's Oliabo record via captures #456/#463",
      "visibility": "INTERNAL ONLY — never named on any blog",
      "parent_project": "proj:oliabo"},
     None, None),
    (EVOO, "product", "Oliabo EVOO (internal product slot)", "active",
     {"price_on_record_usd": 39.99,
      "source": "Brian's Oliabo record via captures #456/#463",
      "visibility": "INTERNAL ONLY — never named on any blog",
      "parent_project": "proj:oliabo"},
     None, None),
    (CRON, "cron_job", "mindell-watch — daily Mindell mapping pass", "active",
     {"schedule": "20 2 * * * (daily 02:20 local)",
      "script": "/home/successbrian/successbrian-os/tools/atlas/mindell_watch.py",
      "log": "/home/successbrian/logs/mindell-watch.log",
      "maintains": HUB},
     None, None),
]

EDGES = [
    (HUB, "asset:blog/longevity-olive", "feeds",
     "The launch window feeds the longevity-olive blog's capture play — "
     "the blog is the capture surface for the Mindell audience."),
    (HUB, "allm:longevity-olive-blog", "about",
     "Workspace holds the blog charter + the readiness plan "
     "(mindell-olive-bible-readiness-plan.md) + the daily mapping note."),
    (HUB, BOOK, "about",
     "The opportunity's object: Mindell's forthcoming book "
     "(listed, unannounced — no-scoop rule binds)."),
    (HUB, "proj:oliabo", "feeds",
     "INTERNAL wiring only: captured audience flows privately to "
     "Oliabo in follow-up; Oliabo is never named on the blog."),
    (HUB, PRIMA, "feeds",
     "INTERNAL slot (charter targeting map, capture #463): the Gundry-"
     "mechanism coverage points at this product's space. Never named "
     "on the blog."),
    (HUB, EVOO, "feeds",
     "INTERNAL slot (charter targeting map, capture #463): the Gundry-"
     "mechanism coverage points at this product's space. Never named "
     "on the blog."),
    ("proj:oliabo", PRIMA, "contains", None),
    ("proj:oliabo", EVOO, "contains", None),
    ("asset:blog/longevity-olive", HUB, "supports",
     "The blog is the instrument that works the launch window "
     "(author hub, olive library, recap machinery)."),
    (CRON, HUB, "supports",
     "Daily mapping pass maintains this node's state, files board "
     "tasks, and writes the dated mapping note."),
]


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
        conn.commit()
        cur.execute(
            "SELECT from_node, edge_type, to_node FROM atlas.edges WHERE "
            "from_node=%s OR to_node=%s ORDER BY edge_type, from_node",
            (HUB, HUB))
        print("\nVERIFY — edges touching %s:" % HUB)
        for f, t, to in cur.fetchall():
            print("  %s -[%s]-> %s" % (f, t, to))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
