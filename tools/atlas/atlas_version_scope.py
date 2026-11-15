#!/usr/bin/env python3
"""atlas_version_scope.py — ATLAS VERSION-SCOPE TOOL (Phase 1, 2026-11-15).

Brian's ruling, 2026-11-15 08:43 CST: "as we define what V1 of
succesbrian os is, we need to start scoping things into V2 and V3 ...
and this needs to happen for all my vibe coded projects -- build tools
into atlas to help us manage this for vibe coding (including successbrian
os itself)".

The practice this tools: defining a product's V1 is simultaneously an
act of scoping V2/V3 — anything deliberately left out of V1 is parked in
a named later version, never dropped, never floating. This module is the
ONE interface to that ledger (written once, importable + CLI, in the
sbos_common spirit).

Store (DDL: tools/atlas/2026-11-15_version_scope.sql): dedicated tables
in the atlas schema — atlas.version_scope_projects / _items / _moves —
linked to the project's Atlas node. Dedicated tables, not Atlas
nodes/edges, because scope is a ledger: items carry status + ruling
source, and moves between versions keep append-only history; the graph
keeps structure + pointers. A project's scope is UNKNOWN until Brian
rules it or a ruled record states it — this tool never invents scope.

Scope state (computed, never stored):
  unknown  — no scope items at all
  partial  — some items, but at least one of v1/v2/v3 has no live item
  defined  — v1, v2 and v3 each carry at least one non-ruled_out item
scope-gaps lists every project that is not 'defined', with what is
missing — the gap list the planner rotation works from.

Part-of projects (Brian, 2026-11-15 09:21 CST: "road chat is part of
successbrian os (not separate)"): a component of another project is
registered with part_of = the parent project_key. It is NOT a
standalone project: scope-gaps excludes it (its undefined scope is
the parent's business, recorded in the parent's note), and
list-projects / show-scope display it as part of the parent. The row
is kept — history matters; the correction re-homes the registration,
never erases it.

Priority (Brian, 2026-11-15 09:22 CST: "traffic streemz is a
marketing skin and it's super high priority"): projects carry a
priority — normal | high | super_high. scope-gaps surfaces
super_high first, clearly flagged. Priority is ruled separately
from scope and never implies scope items.

Project removal (Brian, 2026-11-15 09:33 CST: "hashrate harbor is a
blog"): a registration that turns out not to be a project at all is
removed with remove-project. Removal is never silent and never a
plain DELETE: the verb refuses a project that still carries scope
items or still has part-of children, and writes an append-only row
to atlas.version_scope_project_events (event 'project_removed',
carrying the ruling source + reason) BEFORE the project row goes.
(version_scope_moves is item-level — item_id is a NOT NULL FK — so
project-level events get their own audit table.)

Definition sheet (Brian, 2026-11-15 09:39 CST: "income projects
defined. audiences defined. ideas on how we'll market it definied...
etc etc ... all the steps needed to vet and sort them"): version
scope alone does not make a project "defined" — every registered
project also carries a standard DEFINITION SHEET, the project-level
counterpart of the blog fleet's 12-part planning package. The
standard set is FIXED (DEFINITION_ITEMS below, mirroring
blog_fleet.py's STANDARD_ITEMS discipline): the same 10 items for
every project, seeded to every registered project, each item
UNKNOWN until the record actually settles it. A cell is DEFINED
only with a citable source in Brian's record (detail + source are
required — set-definition refuses an uncited fill); a plausible
inference stays UNKNOWN. version_scope is DERIVED from the scope
tables (defined exactly when the project carries ruled v1 items),
never hand-set. sort_verdict is Brian's ruling only — the sheet
seeds it UNKNOWN everywhere. Store: atlas
.version_scope_definition_items + _definition_moves (append-only
change history, same pattern as scope moves). DDL:
tools/atlas/2026-11-15_version_scope_definitions.sql. QA checks
713 (definition coverage) and 714 (definition source discipline)
guard the sheet.

PHASE B — the project vetting engine (Brian, 2026-11-15 09:50 CST:
"just like we have a blog vetting system, we need a vibe code
project vetting system"). The definition sheet is the MARK; this
engine crunches CANDIDATES against it, mirroring the blog
candidate engine: candidates live in
atlas.version_scope_project_candidates, crunches append to
atlas.version_scope_project_candidate_crunches (never duplicate),
a grade reads the mark LIVE from the definition tables, and the
engine NEVER registers a candidate and NEVER sets a disposition —
a disposition is recorded only from a Brian ruling, with his words
as the source. A crunch works three evidence sources in order:
(a) RECORD DIG (Atlas/PM/blog registry on alpha + seed/supplied
evidence from Brian's record, cited), (b) ASSET INSPECTION (the
candidate's folder on alpha; README/title text are CLAIMS, never
facts), (c) MODEL SYNTHESIS for income/audience/marketing/edge via
the fleet's shared packet caller under the blog engine's tier
discipline (Morpheus-class synthesis; the grade's verdict
narrative is a smarter-engine job by design; overflow UP only;
endpoints are env config; provenance names the actual serving
engine). Evidence discipline: no evidence = UNKNOWN / EVIDENCE
MISSING; numbers are never invented; model claims not tied to
evidence land in unsupported_mentions and NEVER raise an item's
state. The crunch PROPOSES per-item fills on the crunch record —
candidates have no registered sheet and the engine never writes
one. QA check 715 (vetting-engine selftest) guards the engine.

Usage (CLI):
  atlas_version_scope.py register-project --key KEY --name "Name" \
      [--note "..."] [--source "..."]
  atlas_version_scope.py add-item --project KEY --version v1|v2|v3|none \
      --item ITEM_KEY --name "Name" --summary "one line" \
      --source "Brian ruling / record ref" [--status in_scope|parked|done|ruled_out]
  atlas_version_scope.py move-item --project KEY --item ITEM_KEY \
      --to v1|v2|v3 --source "..." [--reason "..."]
  atlas_version_scope.py set-status --project KEY --item ITEM_KEY \
      --status in_scope|parked|done|ruled_out
  atlas_version_scope.py set-part-of --project KEY --part-of PARENT_KEY
  atlas_version_scope.py set-priority --project KEY \
      --priority normal|high|super_high
  atlas_version_scope.py remove-project --project KEY \
      [--source "..."] [--reason "..."]
  atlas_version_scope.py show-scope --project KEY
  atlas_version_scope.py scope-gaps
  atlas_version_scope.py list-projects
  atlas_version_scope.py import-json FILE   (register project + items)
  atlas_version_scope.py seed-definitions   (materialize the 10 standard
      definition rows for every project + refresh derived version_scope)
  atlas_version_scope.py set-definition --project KEY --item ITEM_KEY \
      --state defined|unknown [--detail "..."] [--source "..."]
  atlas_version_scope.py show-definition --project KEY
  atlas_version_scope.py definition-gaps
  atlas_version_scope.py sort-projects [--with-candidates]
  atlas_version_scope.py add-candidate --key KEY --name "Name" \
      [--priority normal|high|super_high] [--goal REF] \
      [--seed-file seed.json]
  atlas_version_scope.py crunch --candidate KEY \
      [--evidence-file dig.json] [--no-model]
  atlas_version_scope.py grade --candidate KEY [--no-model]
  atlas_version_scope.py show-candidate --candidate KEY
  atlas_version_scope.py list-candidates
  atlas_version_scope.py set-disposition --candidate KEY \
      --disposition registered|parked|merged|dropped \
      --source "Brian's ruling, quoted"
  atlas_version_scope.py selftest
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

USER = "postgres"
CORE_VERSIONS = ("v1", "v2", "v3")
STATUSES = ("in_scope", "parked", "moved", "done", "ruled_out")
PRIORITIES = ("normal", "high", "super_high")
PRIORITY_RANK = {"super_high": 0, "high": 1, "normal": 2}
PRIORITY_LABEL = {"super_high": "SUPER HIGH PRIORITY", "high": "HIGH PRIORITY"}


def pg_rows(sql, params=None):
    return sbos_common.pg_rows(sql, params, user=USER)


def pg_one(sql, params=None):
    rows = pg_rows(sql, params)
    return rows[0] if rows else None


def pg_exec(sql, params=None):
    return sbos_common.pg_exec(sql, params, user=USER)


# ---------------------------------------------------------------- store

def ensure_node(project_key, display_name):
    """Link the project to its Atlas node proj:<key>; create the node
    (additive, type 'project') only if it does not exist yet."""
    node_key = "proj:%s" % project_key
    row = pg_one("SELECT node_key FROM atlas.nodes WHERE node_key=%s", (node_key,))
    if not row:
        pg_exec(
            "INSERT INTO atlas.nodes (node_key, node_type, name, status, details) "
            "VALUES (%s, 'project', %s, 'planned', %s::jsonb)",
            (node_key, display_name,
             json.dumps({"version_scope_registry": True})))
    return node_key


def register_project(key, name, note="", source=""):
    node_key = ensure_node(key, name)
    pg_exec(
        "INSERT INTO atlas.version_scope_projects "
        "(project_key, display_name, atlas_node_key, scope_note, registered_source) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (project_key) DO UPDATE SET "
        "display_name=EXCLUDED.display_name, atlas_node_key=EXCLUDED.atlas_node_key, "
        "scope_note=CASE WHEN EXCLUDED.scope_note <> '' THEN EXCLUDED.scope_note "
        "ELSE atlas.version_scope_projects.scope_note END, updated_at=NOW()",
        (key, name, node_key, note, source))
    return node_key


def add_item(project, version, item_key, name, summary, source, status="in_scope"):
    if status not in STATUSES:
        raise SystemExit("bad status: %s" % status)
    pg_exec(
        "INSERT INTO atlas.version_scope_items "
        "(project_key, version_label, item_key, name, summary, status, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (project_key, item_key) DO UPDATE SET "
        "version_label=EXCLUDED.version_label, name=EXCLUDED.name, "
        "summary=EXCLUDED.summary, status=EXCLUDED.status, "
        "source=EXCLUDED.source, updated_at=NOW()",
        (project, version, item_key, name, summary, status, source))


def move_item(project, item_key, to_version, source="", reason=""):
    row = pg_one(
        "SELECT id, version_label FROM atlas.version_scope_items "
        "WHERE project_key=%s AND item_key=%s", (project, item_key))
    if not row:
        raise SystemExit("no such item: %s/%s" % (project, item_key))
    item_id, from_version = row
    if from_version == to_version:
        raise SystemExit("item %s is already in %s" % (item_key, to_version))
    pg_exec(
        "UPDATE atlas.version_scope_items SET version_label=%s, updated_at=NOW() "
        "WHERE id=%s", (to_version, item_id))
    pg_exec(
        "INSERT INTO atlas.version_scope_moves "
        "(item_id, project_key, item_key, from_version, to_version, reason, source) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (item_id, project, item_key, from_version, to_version, reason, source))
    return from_version


def set_status(project, item_key, status):
    if status not in STATUSES:
        raise SystemExit("bad status: %s" % status)
    n = pg_exec(
        "UPDATE atlas.version_scope_items SET status=%s, updated_at=NOW() "
        "WHERE project_key=%s AND item_key=%s", (status, project, item_key))
    if not n:
        raise SystemExit("no such item: %s/%s" % (project, item_key))


def set_part_of(project, parent):
    if project == parent:
        raise SystemExit("a project cannot be part of itself")
    prow = pg_one(
        "SELECT part_of FROM atlas.version_scope_projects "
        "WHERE project_key=%s", (parent,))
    if not prow:
        raise SystemExit("no such parent project: %s" % parent)
    if prow[0]:
        raise SystemExit("parent %s is itself part of %s — no chains"
                         % (parent, prow[0]))
    n = pg_exec(
        "UPDATE atlas.version_scope_projects SET part_of=%s, updated_at=NOW() "
        "WHERE project_key=%s", (parent, project))
    if not n:
        raise SystemExit("no such project: %s" % project)


def set_priority(project, priority):
    if priority not in PRIORITIES:
        raise SystemExit("bad priority: %s" % priority)
    n = pg_exec(
        "UPDATE atlas.version_scope_projects SET priority=%s, updated_at=NOW() "
        "WHERE project_key=%s", (priority, project))
    if not n:
        raise SystemExit("no such project: %s" % project)


def remove_project(project, source="", reason=""):
    """Remove a project registration that should never have been one
    (e.g. a blog registered as a project). Guarded + audited: refuses
    while the project carries scope items or has part-of children;
    writes the 'project_removed' event BEFORE deleting the row."""
    row = pg_one(
        "SELECT display_name FROM atlas.version_scope_projects "
        "WHERE project_key=%s", (project,))
    if not row:
        raise SystemExit("no such project: %s" % project)
    n_items = pg_one(
        "SELECT count(*) FROM atlas.version_scope_items "
        "WHERE project_key=%s", (project,))[0]
    if n_items:
        raise SystemExit(
            "project %s still carries %d scope item(s) — refusing to "
            "remove; rule the items out first" % (project, n_items))
    kids = pg_rows(
        "SELECT project_key FROM atlas.version_scope_projects "
        "WHERE part_of=%s", (project,))
    if kids:
        raise SystemExit(
            "project %s is the part-of parent of %s — re-home them first"
            % (project, ", ".join(k[0] for k in kids)))
    pg_exec(
        "INSERT INTO atlas.version_scope_project_events "
        "(project_key, event, detail, source) "
        "VALUES (%s, 'project_removed', %s, %s)",
        (project, reason, source))
    pg_exec(
        "DELETE FROM atlas.version_scope_projects WHERE project_key=%s",
        (project,))
    return row[0]


def gap_projects():
    """(key, name, state, missing, priority) for every project that is
    not 'defined' and NOT part of another project — part-of projects
    are scoped inside their parent, never standalone gaps. Ordered:
    super_high priority first, then high, then normal, then key."""
    out = []
    for key, name, _node, _note, part_of, priority in list_projects():
        if part_of:
            continue
        state, _counts, missing = project_state(key)
        if state != "defined":
            out.append((key, name, state, missing, priority or "normal"))
    out.sort(key=lambda r: (PRIORITY_RANK.get(r[4], 2), r[0]))
    return out


def project_state(project):
    """(state, counts-by-version, missing list) computed live."""
    rows = pg_rows(
        "SELECT version_label, status, count(*) FROM atlas.version_scope_items "
        "WHERE project_key=%s GROUP BY 1, 2", (project,))
    counts = {}
    total = 0
    for version, status, n in rows:
        total += n
        if status != "ruled_out":
            counts[version] = counts.get(version, 0) + n
    if total == 0:
        return "unknown", counts, ["no scope items at all — scope not yet defined"]
    missing = ["%s has no live items" % v for v in CORE_VERSIONS
               if counts.get(v, 0) == 0]
    return ("defined" if not missing else "partial"), counts, missing


def list_projects():
    return pg_rows(
        "SELECT project_key, display_name, atlas_node_key, scope_note, "
        "part_of, priority "
        "FROM atlas.version_scope_projects ORDER BY project_key")


# ------------------------------------------------------- definition sheet
# The standard definition set — FIXED, in this order, the same 10 items
# for every registered project (Brian, 2026-11-15 09:39 CST). Mirrors
# blog_fleet.py's STANDARD_ITEMS discipline: seeded to every project,
# each item UNKNOWN until the record settles it, filled only from the
# settled record with the source cited on the cell.
DEFINITION_ITEMS = [
    ("what_it_is", "What it is",
     "What the project is + its kind/placement (product / marketing "
     "skin / internal desk / template / plugin-part-of / game / tool), "
     "from Brian's record."),
    ("income_model", "Income model",
     "How it makes money: what is sold, at what price, who pays — "
     "price/payer/mechanism must be ON RECORD. A settled 'none — "
     "internal, never sold' also defines it; paywall furniture with "
     "no recorded price does not."),
    ("audience", "Audience",
     "The named audience/segment it serves, on record."),
    ("marketing_ideas", "Marketing ideas",
     "How it will be marketed — its blog or marketing asset, "
     "channels, skin tie-ins — ideas ON RECORD (a ruled blog counts; "
     "a ruled-out blog is recorded as such; nothing is invented)."),
    ("unique_edge", "Unique edge",
     "Its unique data source / unfair advantage / differentiator, on "
     "record (the blogs' pp03 discipline: no evidence = UNKNOWN)."),
    ("version_scope", "Version scope",
     "DERIVED, never hand-set: defined exactly when the project "
     "carries ruled v1 items in this registry."),
    ("build_state", "Build state",
     "Code state on record: exists / partial / finished / not "
     "started / existence unknown."),
    ("hosting", "Hosting",
     "Hosting settled on record (Brian's launch law: no launch "
     "without reliable hosting + finished code)."),
    ("lifecycle_status", "Lifecycle status",
     "Active / on hold / tentative-exit / under research / parked — "
     "ONLY where Brian's record states it; unstated = UNKNOWN, never "
     "'active' by default."),
    ("sort_verdict", "Sort verdict",
     "Where the project lands after vetting (build-next / develop / "
     "park / merge / drop) — Brian's ruling only; UNKNOWN until he "
     "rules it."),
]
DEFINITION_KEYS = [k for k, _t, _r in DEFINITION_ITEMS]
DEFINITION_TITLES = {k: t for k, t, _r in DEFINITION_ITEMS}
DEFINITION_STATES = ("defined", "unknown")
DERIVED_SOURCE = ("derived by atlas_version_scope.py from "
                  "atlas.version_scope_items")


def definition_rows(project):
    return pg_rows(
        "SELECT item_key, state, detail, source FROM "
        "atlas.version_scope_definition_items WHERE project_key=%s",
        (project,))


def defined_count(project):
    row = pg_one(
        "SELECT count(*) FROM atlas.version_scope_definition_items "
        "WHERE project_key=%s AND state='defined'", (project,))
    return row[0] if row else 0


def _set_definition_row(project, item, state, detail, source):
    """Write one definition cell; append the change to
    _definition_moves when anything actually changed. Returns True
    when a change was written."""
    old = pg_one(
        "SELECT state, detail, source FROM "
        "atlas.version_scope_definition_items "
        "WHERE project_key=%s AND item_key=%s", (project, item))
    if old and (old[0], old[1], old[2]) == (state, detail, source):
        return False
    pg_exec(
        "INSERT INTO atlas.version_scope_definition_items "
        "(project_key, item_key, state, detail, source) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (project_key, item_key) DO UPDATE SET "
        "state=EXCLUDED.state, detail=EXCLUDED.detail, "
        "source=EXCLUDED.source, updated_at=NOW()",
        (project, item, state, detail, source))
    pg_exec(
        "INSERT INTO atlas.version_scope_definition_moves "
        "(project_key, item_key, from_state, to_state, detail, source) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (project, item, old[0] if old else "", state, detail, source))
    return True


def set_definition(project, item, state, detail="", source=""):
    if item not in DEFINITION_KEYS:
        raise SystemExit("bad definition item: %s" % item)
    if item == "version_scope":
        raise SystemExit(
            "version_scope is derived from the scope tables — it "
            "cannot be hand-set (seed-definitions refreshes it)")
    if state not in DEFINITION_STATES:
        raise SystemExit("bad definition state: %s" % state)
    prow = pg_one(
        "SELECT count(*) FROM atlas.version_scope_projects "
        "WHERE project_key=%s", (project,))
    if not prow or not prow[0]:
        raise SystemExit("no such project: %s" % project)
    if state == "defined" and (not detail.strip() or not source.strip()):
        raise SystemExit(
            "a defined cell must carry a detail + a source citation — "
            "an uncited fill is exactly what this sheet exists to "
            "prevent")
    _set_definition_row(project, item, state, detail, source)


def derive_version_scope(project):
    """version_scope is DEFINED exactly when the project carries
    ruled v1 items in this registry; derived live, never hand-set."""
    n = pg_one(
        "SELECT count(*) FROM atlas.version_scope_items "
        "WHERE project_key=%s AND version_label='v1' "
        "AND status<>'ruled_out'", (project,))[0]
    if n:
        _set_definition_row(
            project, "version_scope", "defined",
            "%d ruled v1 item(s) live in this registry — the "
            "project's version scope is defined where v1 items are "
            "ruled" % n, DERIVED_SOURCE)
    else:
        _set_definition_row(
            project, "version_scope", "unknown", "", DERIVED_SOURCE)
    return n


def seed_definitions():
    """Materialize any missing standard definition rows (at UNKNOWN)
    for every registered project, then refresh the derived
    version_scope cell for each. Idempotent. Returns
    (project_count, new_rows_made)."""
    keys = [r[0] for r in list_projects()]
    made = 0
    for key in keys:
        for item in DEFINITION_KEYS:
            made += pg_exec(
                "INSERT INTO atlas.version_scope_definition_items "
                "(project_key, item_key) VALUES (%s, %s) "
                "ON CONFLICT (project_key, item_key) DO NOTHING",
                (key, item)) or 0
        derive_version_scope(key)
    return len(keys), made


def definition_gaps():
    """(key, name, defined_n, missing_keys, priority, part_of) for
    every registered project, worst-first: most missing items first,
    then priority, then key. Part-of projects keep their own sheets —
    their definition is the parent's business too, but the sheet is
    where that shows."""
    out = []
    for key, name, _node, _note, part_of, priority in list_projects():
        rows = {r[0]: r[1] for r in definition_rows(key)}
        missing = [k for k in DEFINITION_KEYS
                   if rows.get(k) != "defined"]
        out.append((key, name, len(DEFINITION_KEYS) - len(missing),
                    missing, priority or "normal", part_of))
    out.sort(key=lambda r: (-len(r[3]), PRIORITY_RANK.get(r[4], 2),
                            r[0]))
    return out


def sort_projects():
    """The sorting view: projects ordered by priority (super_high
    first) then definition completeness (defined-count desc), then
    key. (key, name, defined_n, priority, part_of)."""
    out = []
    for key, name, _node, _note, part_of, priority in list_projects():
        out.append((key, name, defined_count(key),
                    priority or "normal", part_of))
    out.sort(key=lambda r: (PRIORITY_RANK.get(r[3], 2), -r[2], r[0]))
    return out


# ---------------------------------------------------------------- CLI

def cmd_register_project(a):
    node = register_project(a.key, a.name, a.note or "", a.source or "")
    print("registered %s (atlas node %s)" % (a.key, node))


def cmd_add_item(a):
    add_item(a.project, a.version, a.item, a.name, a.summary or "",
             a.source or "", a.status)
    print("item %s/%s -> %s (%s)" % (a.project, a.item, a.version, a.status))


def cmd_move_item(a):
    frm = move_item(a.project, a.item, a.to, a.source or "", a.reason or "")
    print("moved %s/%s: %s -> %s (history kept)" % (a.project, a.item, frm, a.to))


def cmd_set_status(a):
    set_status(a.project, a.item, a.status)
    print("status %s/%s = %s" % (a.project, a.item, a.status))


def cmd_set_part_of(a):
    set_part_of(a.project, a.part_of)
    print("part-of %s -> %s" % (a.project, a.part_of))


def cmd_set_priority(a):
    set_priority(a.project, a.priority)
    print("priority %s = %s" % (a.project, a.priority))


def cmd_remove_project(a):
    name = remove_project(a.project, a.source or "", a.reason or "")
    print("removed project %s — %s (removal recorded in "
          "version_scope_project_events)" % (a.project, name))


def cmd_show_scope(a):
    proj = pg_one(
        "SELECT display_name, atlas_node_key, scope_note, part_of, priority "
        "FROM atlas.version_scope_projects WHERE project_key=%s", (a.project,))
    if not proj:
        raise SystemExit("no such project: %s" % a.project)
    state, counts, missing = project_state(a.project)
    if proj[3]:
        parent = pg_one(
            "SELECT display_name FROM atlas.version_scope_projects "
            "WHERE project_key=%s", (proj[3],))
        parent_name = parent[0] if parent else proj[3]
        print("%s — %s [part of %s — scoped there, not separately]"
              % (a.project, proj[0], parent_name))
        if proj[2]:
            print("  note: %s" % proj[2])
        print("  no separate scope is kept here — see: show-scope "
              "--project %s" % proj[3])
        return
    print("%s — %s [scope: %s]" % (a.project, proj[0], state))
    if proj[4] and proj[4] != "normal":
        print("  priority: %s" % PRIORITY_LABEL.get(proj[4], proj[4]))
    if proj[2]:
        print("  note: %s" % proj[2])
    items = pg_rows(
        "SELECT version_label, item_key, name, summary, status, source "
        "FROM atlas.version_scope_items WHERE project_key=%s "
        "ORDER BY version_label, item_key", (a.project,))
    cur = None
    for version, ikey, name, summary, status, source in items:
        if version != cur:
            cur = version
            print(" %s:" % ("RULED OUT (no version home)" if version == "none" else version))
        print("   - [%s] %s — %s" % (status, name, summary))
        if source:
            print("     source: %s" % source)
    moves = pg_rows(
        "SELECT item_key, from_version, to_version, reason, source, "
        "to_char(moved_at, 'YYYY-MM-DD HH24:MI') FROM atlas.version_scope_moves "
        "WHERE project_key=%s ORDER BY id", (a.project,))
    if moves:
        print(" moves:")
        for ikey, frm, to, reason, source, when in moves:
            print("   - %s: %s -> %s (%s)%s" % (ikey, frm, to, when,
                  (" — " + reason) if reason else ""))
    if missing:
        print(" gaps: %s" % "; ".join(missing))


def cmd_scope_gaps(a):
    gaps = gap_projects()
    for key, name, state, missing, priority in gaps:
        flag = (" [%s]" % PRIORITY_LABEL[priority]
                if priority in PRIORITY_LABEL else "")
        print("GAP %s — %s [scope: %s]%s: %s"
              % (key, name, state, flag, "; ".join(missing)))
    print("scope gaps: %d project(s) not fully defined" % len(gaps))


def cmd_list_projects(a):
    rows = list_projects()
    names = {r[0]: r[1] for r in rows}
    for key, name, node, _note, part_of, priority in rows:
        if part_of:
            print("%s — %s [part of %s — scoped there, not separately; node %s]"
                  % (key, name, names.get(part_of, part_of), node))
            continue
        state, counts, _m = project_state(key)
        cs = " ".join("%s=%d" % (v, counts.get(v, 0)) for v in CORE_VERSIONS)
        flag = ("; %s" % PRIORITY_LABEL[priority]
                if priority in PRIORITY_LABEL else "")
        print("%s — %s [scope: %s; %s%s; node %s]"
              % (key, name, state, cs, flag, node))


def cmd_import_json(a):
    with open(a.file) as f:
        data = json.load(f)
    register_project(data["project_key"], data["display_name"],
                     data.get("note", ""), data.get("source", ""))
    for it in data.get("items", []):
        add_item(data["project_key"], it["version"], it["item_key"], it["name"],
                 it.get("summary", ""), it.get("source", ""),
                 it.get("status", "in_scope"))
    print("imported %s: %d item(s)" % (data["project_key"], len(data.get("items", []))))


def cmd_seed_definitions(a):
    nproj, made = seed_definitions()
    total = pg_one(
        "SELECT count(*) FROM atlas.version_scope_definition_items")[0]
    defined = pg_one(
        "SELECT count(*) FROM atlas.version_scope_definition_items "
        "WHERE state='defined'")[0]
    print("seeded definitions: %d project(s), %d new row(s); "
          "%d cells total, %d defined" % (nproj, made, total, defined))


def cmd_set_definition(a):
    set_definition(a.project, a.item, a.state,
                   a.detail or "", a.source or "")
    print("definition %s/%s = %s" % (a.project, a.item, a.state))


def cmd_show_definition(a):
    proj = pg_one(
        "SELECT display_name, scope_note, part_of, priority "
        "FROM atlas.version_scope_projects WHERE project_key=%s",
        (a.project,))
    if not proj:
        raise SystemExit("no such project: %s" % a.project)
    rows = {r[0]: (r[1], r[2], r[3]) for r in definition_rows(a.project)}
    n = sum(1 for k in DEFINITION_KEYS
            if rows.get(k, ("unknown", "", ""))[0] == "defined")
    head = "%s — %s [definition: %d/%d defined" % (
        a.project, proj[0], n, len(DEFINITION_KEYS))
    if proj[3] and proj[3] != "normal":
        head += "; %s" % PRIORITY_LABEL.get(proj[3], proj[3])
    if proj[2]:
        head += "; part of %s" % proj[2]
    print(head + "]")
    for item in DEFINITION_KEYS:
        state, detail, source = rows.get(item, ("unknown", "", ""))
        print("  [%s] %s" % (state, item))
        if detail:
            print("      %s" % detail)
        if source:
            print("      source: %s" % source)
    moves = pg_one(
        "SELECT count(*) FROM atlas.version_scope_definition_moves "
        "WHERE project_key=%s", (a.project,))[0]
    if moves:
        print("  history: %d definition change(s) recorded" % moves)


def cmd_definition_gaps(a):
    gaps = definition_gaps()
    total = defined = 0
    for key, name, n, missing, priority, part_of in gaps:
        total += len(DEFINITION_KEYS)
        defined += n
        flag = (" [%s]" % PRIORITY_LABEL[priority]
                if priority in PRIORITY_LABEL else "")
        home = " (part of %s)" % part_of if part_of else ""
        print("DEFGAP %s — %s [defined %d/%d]%s%s: missing %s"
              % (key, name, n, len(DEFINITION_KEYS), flag, home,
                 ", ".join(missing) if missing else "nothing"))
    print("definition gaps: %d cells across %d project(s), "
          "%d defined, %d unknown"
          % (total, len(gaps), defined, total - defined))


def cmd_sort_projects(a):
    rows = sort_projects()
    names = {r[0]: r[1] for r in list_projects()}
    if not getattr(a, "with_candidates", False):
        for key, name, n, priority, part_of in rows:
            flag = (" [%s]" % PRIORITY_LABEL[priority]
                    if priority in PRIORITY_LABEL else "")
            home = (" (part of %s)"
                    % names.get(part_of, part_of)) if part_of else ""
            print("SORT %s — %s%s%s: defined %d/%d"
                  % (key, name, flag, home, n, len(DEFINITION_KEYS)))
        return
    # One list for Brian to sort: graded/crunched candidates
    # interleaved with registered projects, marked as candidates.
    entries = []
    for key, name, n, priority, part_of in rows:
        flag = (" [%s]" % PRIORITY_LABEL[priority]
                if priority in PRIORITY_LABEL else "")
        home = (" (part of %s)"
                % names.get(part_of, part_of)) if part_of else ""
        entries.append(
            (PRIORITY_RANK.get(priority, 2), -n, key,
             "SORT %s — %s%s%s: defined %d/%d"
             % (key, name, flag, home, n, len(DEFINITION_KEYS))))
    for crow in pg_rows(
            "SELECT candidate_key, display_name, priority, state "
            "FROM atlas.version_scope_project_candidates"):
        ckey, cname, cpri, cstate = crow
        n = candidate_defined_count(ckey)
        flag = (" [%s]" % PRIORITY_LABEL[cpri]
                if cpri in PRIORITY_LABEL else "")
        if n is None:
            line = ("SORT %s — %s%s [CANDIDATE — not registered]: "
                    "not crunched" % (ckey, cname, flag))
            entries.append((PRIORITY_RANK.get(cpri, 2), 1, ckey,
                            line))
        else:
            g = (get_candidate(ckey) or {}).get("last_grade") or {}
            verdict = (" — grade: %s" % g["verdict"]
                       if g.get("verdict") else "")
            line = ("SORT %s — %s%s [CANDIDATE — not registered]: "
                    "proposed defined %d/%d%s"
                    % (ckey, cname, flag, n, len(DEFINITION_KEYS),
                       verdict))
            entries.append((PRIORITY_RANK.get(cpri, 2), -n, ckey,
                            line))
    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    for _r, _n, _k, line in entries:
        print(line)


def cmd_add_candidate(a):
    seed = {}
    if a.seed_file:
        seed = json.loads(open(a.seed_file).read())
    cand = add_candidate(a.key, a.name, a.priority, a.goal or "",
                          seed)
    print("candidate %s — %s (state %s, priority %s)"
          % (cand["key"], cand["name"], cand["state"],
             cand["priority"]))


def cmd_crunch(a):
    supplied = None
    if a.evidence_file:
        supplied = json.loads(
            open(a.evidence_file).read()).get("entries")
    cid = crunch_candidate(a.candidate, use_model=not a.no_model,
                           supplied=supplied)
    print("crunch #%d recorded for %s" % (cid, a.candidate))
    print_candidate(a.candidate)


def cmd_grade(a):
    g = grade_candidate(a.candidate, use_model=not a.no_model)
    print(json.dumps(g, indent=1, default=str))


def cmd_show_candidate(a):
    print_candidate(a.candidate)


def cmd_list_candidates(a):
    rows = pg_rows(
        "SELECT candidate_key, display_name, state, priority, "
        "disposition, last_grade FROM "
        "atlas.version_scope_project_candidates "
        "ORDER BY candidate_key")
    if not rows:
        print("(no candidates)")
    for key, name, state, priority, disp, grade in rows:
        verdict = (grade or {}).get("verdict", "")
        print("CANDIDATE %s — %s: state %s, priority %s%s%s"
              % (key, name, state, priority,
                 (", disposition %s" % disp) if disp else "",
                 (", grade %s" % verdict) if verdict else ""))


def cmd_set_disposition(a):
    cand = set_disposition(a.candidate, a.disposition,
                           a.source or "")
    print("disposition recorded for %s: %s (source: %s)"
          % (cand["key"], cand["disposition"],
             cand["disposition_source"]))


# ---------------------------------------------------------------- selftest

# ------------------------------------------------------------------
# Phase B — project vetting engine (candidates + crunches + grade).
# Mirrors the blog candidate engine's discipline; see the module
# docstring. The engine NEVER registers and NEVER sets a
# disposition on its own.
# ------------------------------------------------------------------

CANDIDATE_STATES = ("candidate", "crunched", "graded")
DISPOSITIONS = ("registered", "parked", "merged", "dropped")
MODEL_ITEMS = ("income_model", "audience", "marketing_ideas",
               "unique_edge")
# Verdict thresholds — machinery defaults, labeled as such in every
# grade; Brian-correctable, never presented as his rulings.
READY_MIN_DEFINED = 8
DEVELOPABLE_MIN_DEFINED = 5
PACKET_CHAR_BUDGET = 12000
ASSET_ROOT = os.environ.get(
    "VS_ASSET_ROOT", os.path.expanduser("~/vibecoder-projects"))
# Model seats — endpoints are CONFIG ONLY (env), mirroring the blog
# candidate engine. Morpheus-class does the synthesis; the smarter
# seats are the overflow chain AND the verdict-narrative seat.
VS_MORPHEUS_URL = os.environ.get("VS_VETTING_MORPHEUS_URL",
                                 sbos_common.MORPHEUS_URL)
VS_MORPHEUS_MODEL = os.environ.get("VS_VETTING_MORPHEUS_MODEL",
                                   sbos_common.MORPHEUS_MODEL)
VS_OVERFLOW_CHAIN = (("sonic", sbos_common.SONIC_URL,
                      sbos_common.SONIC_MODEL),)
QUEUE_DEPTH_MAX = int(os.environ.get("VS_QUEUE_DEPTH_MAX", "5"))
QUEUE_WAIT_MAX_S = int(os.environ.get("VS_QUEUE_WAIT_MAX_S", "900"))
PRICE_RE = re.compile(r"\$\s?\d|/\s?mo\b|per month|per year|price",
                      re.I)
# Substantive differentiator language only — a bare "only" (as in
# "stated plan only") or "first" must never define an edge.
EDGE_RE = re.compile(r"unique|differentiator|unfair advantage|"
                     r"data source|moat|proprietary", re.I)
PAYER_RE = re.compile(
    r"subscriber|subscription|customer|user pays|advertiser|fee|"
    r"commission|sale|sells|paid", re.I)

_CAND_COLS = ("candidate_key, display_name, state, priority, "
              "goal_ref, seed_evidence, disposition, "
              "disposition_source, last_grade, last_worked_at")


def get_candidate(key):
    row = pg_one(
        "SELECT " + _CAND_COLS + " FROM "
        "atlas.version_scope_project_candidates "
        "WHERE candidate_key = %s", (key,))
    if not row:
        return None
    return {"key": row[0], "name": row[1], "state": row[2],
            "priority": row[3], "goal_ref": row[4],
            "seed_evidence": row[5] or {}, "disposition": row[6],
            "disposition_source": row[7], "last_grade": row[8],
            "last_worked_at": row[9]}


def add_candidate(key, name, priority="normal", goal_ref="",
                  seed_evidence=None):
    if priority not in PRIORITIES:
        raise SystemExit("priority must be one of %s"
                         % (", ".join(PRIORITIES)))
    if get_candidate(key):
        raise SystemExit("candidate %s already exists" % key)
    if pg_one("SELECT 1 FROM atlas.version_scope_projects "
              "WHERE project_key = %s", (key,)):
        raise SystemExit(
            "%s is already a REGISTERED project — candidates are "
            "for ideas not yet in the roster" % key)
    pg_exec(
        "INSERT INTO atlas.version_scope_project_candidates "
        "(candidate_key, display_name, priority, goal_ref, "
        "seed_evidence) VALUES (%s, %s, %s, %s, %s::jsonb)",
        (key, name, priority, goal_ref,
         json.dumps(seed_evidence or {})))
    return get_candidate(key)


def set_disposition(key, disposition, source):
    """Record a disposition — Brian's ruling only, his words as the
    source. The engine records; it never decides."""
    cand = get_candidate(key)
    if not cand:
        raise SystemExit("no such candidate: %s" % key)
    if disposition not in DISPOSITIONS:
        raise SystemExit("disposition must be one of %s"
                         % (", ".join(DISPOSITIONS)))
    if not source:
        raise SystemExit(
            "refusing to record a disposition without Brian's "
            "ruling as the source — dispositions are his rulings, "
            "recorded with his words")
    pg_exec(
        "UPDATE atlas.version_scope_project_candidates SET "
        "disposition = %s, disposition_source = %s, "
        "updated_at = NOW() WHERE candidate_key = %s",
        (disposition, source, key))
    return get_candidate(key)


def _morpheus_backed_up():
    """The fleet's standing overflow signal (mirrors the blog
    candidate engine): queued depth / oldest wait in
    successbrian_os.morpheus_queue. An unreadable queue is NOT a
    backup signal."""
    try:
        row = pg_one(
            "SELECT count(*), COALESCE(EXTRACT(EPOCH FROM "
            "(NOW() - MIN(created_at))), 0) FROM "
            "successbrian_os.morpheus_queue WHERE status = "
            "'queued'")
        depth, wait = int(row[0]), int(row[1])
        return (depth >= QUEUE_DEPTH_MAX or wait >= QUEUE_WAIT_MAX_S,
                {"queue_depth": depth, "oldest_wait_s": wait})
    except Exception as e:
        return False, {"queue_signal_error": str(e)[:120]}


def call_packet(prompt, max_tokens=500, tier="morpheus",
                model_url=None):
    """One model packet through the fleet's shared caller
    (sbos_common.llm_chat) under the blog engine's tier discipline.
    Returns (result, seat_note); result carries provenance naming
    the ACTUAL serving engine. Overflow runs UP only."""
    prompt = prompt[:PACKET_CHAR_BUDGET]
    if tier == "smart":
        seats = list(VS_OVERFLOW_CHAIN)
        signal = {"work_tier": "smart"}
        if not seats:
            return None, "no smarter-engine seat configured"
    else:
        home = ("morpheus", model_url or VS_MORPHEUS_URL,
                VS_MORPHEUS_MODEL)
        backed, signal = _morpheus_backed_up()
        signal = dict(signal or {})
        signal["work_tier"] = "morpheus"
        signal["backed_up"] = backed
        seats = (list(VS_OVERFLOW_CHAIN) + [home]) if backed \
            else ([home] + list(VS_OVERFLOW_CHAIN))
    errors = []
    for engine, url, model in seats:
        t0 = time.time()
        try:
            text, _u = sbos_common.llm_chat(
                prompt=prompt, url=url, model=model,
                max_tokens=max_tokens, temperature=0.2, timeout=240)
            return {"text": text, "engine": engine,
                    "endpoint": url, "model": model,
                    "latency_s": round(time.time() - t0, 2),
                    "queue_signal": signal}, None
        except Exception as e:
            errors.append("%s: %s" % (engine, str(e)[:120]))
    return None, "; ".join(errors)


def dig_record(cand):
    """Stage (a) — the alpha-side record dig: Atlas nodes/edges,
    PM registry, the version-scope registry itself, the blog
    registry (same database, campaignsdesk schema), and Intel
    Bridge captures mentioning the candidate. Each sub-dig fails
    soft and records its own error honestly."""
    key, name = cand["key"], cand["name"]
    dig = {}
    node = "proj:%s" % key
    try:
        r = pg_one("SELECT node_type, name FROM atlas.nodes "
                   "WHERE node_key = %s", (node,))
        dig["atlas_node"] = ({"node_key": node, "type": r[0],
                              "name": r[1]} if r else None)
        dig["edges_in"] = [
            {"type": e[0], "from": e[1]} for e in pg_rows(
                "SELECT edge_type, from_node FROM atlas.edges "
                "WHERE to_node = %s LIMIT 20", (node,))]
        dig["edges_out"] = [
            {"type": e[0], "to": e[1]} for e in pg_rows(
                "SELECT edge_type, to_node FROM atlas.edges "
                "WHERE from_node = %s LIMIT 20", (node,))]
    except Exception as e:
        dig["atlas_error"] = str(e)[:160]
    try:
        dig["pm_project"] = bool(pg_one(
            "SELECT 1 FROM successbrian_os.pm_projects "
            "WHERE project_key = %s", (key,)))
    except Exception as e:
        dig["pm_error"] = str(e)[:160]
    dig["registered_project"] = bool(pg_one(
        "SELECT 1 FROM atlas.version_scope_projects "
        "WHERE project_key = %s", (key,)))
    try:
        rows = pg_rows(
            "SELECT slug, status, promoted_thing FROM "
            "campaignsdesk.blogs WHERE slug ILIKE %s "
            "OR promoted_thing ILIKE %s",
            ("%%%s%%" % key, "%%%s%%" % name))
        dig["blogs"] = [{"slug": b[0], "status": b[1],
                         "promoted_thing": b[2]} for b in rows]
    except Exception as e:
        dig["blogs_error"] = str(e)[:160]
        dig["blogs"] = []
    try:
        dig["captures"] = [
            {"id": c[0], "title": c[1]} for c in pg_rows(
                "SELECT id, title FROM atlas.scattered_captures "
                "WHERE context ILIKE %s ORDER BY id DESC LIMIT 5",
                ("%%%s%%" % name,))]
    except Exception as e:
        dig["captures_error"] = str(e)[:160]
        dig["captures"] = []
    try:
        rows = pg_rows(
            "SELECT name, kind FROM people.companies "
            "WHERE lower(name) = lower(%s)", (name,),
            dbname="people_unified")
        dig["company_match"] = [{"name": c[0], "kind": c[1]}
                                for c in rows]
    except Exception as e:
        dig["company_error"] = str(e)[:160]
        dig["company_match"] = []
    return dig


def inspect_assets(cand):
    """Stage (b) — asset inspection on alpha. Folder presence, file
    counts and stack markers are OBSERVATIONS; title/README text
    are CLAIMS and are labeled as such everywhere they surface."""
    names = []
    seed_folder = (cand["seed_evidence"] or {}).get("folder")
    for nm in (seed_folder, cand["name"], cand["key"]):
        if nm and nm not in names:
            names.append(nm)
    found = None
    if os.path.isdir(ASSET_ROOT):
        try:
            lower_map = {e.lower(): e
                         for e in os.listdir(ASSET_ROOT)}
        except Exception:
            lower_map = {}
        for nm in names:
            real = lower_map.get(nm.lower())
            if real:
                found = os.path.join(ASSET_ROOT, real)
                break
    if not found:
        return {"found": False, "root": ASSET_ROOT,
                "searched": names}
    files, top = 0, []
    markers = {}
    claims = []
    for root, dirs, fnames in os.walk(found):
        dirs[:] = [d for d in dirs
                   if d not in ("node_modules", ".git")]
        files += len(fnames)
        if files > 5000:
            break
    try:
        top = sorted(os.listdir(found))[:40]
    except Exception:
        top = []
    pkg = os.path.join(found, "package.json")
    if os.path.isfile(pkg):
        markers["package.json"] = True
        try:
            pj = json.loads(open(pkg).read())
            markers["package_name"] = pj.get("name")
            deps = dict(pj.get("dependencies") or {})
            deps.update(pj.get("devDependencies") or {})
            markers["deps"] = sorted(deps)[:20]
            if pj.get("homepage"):
                markers["homepage"] = pj["homepage"]
        except Exception:
            pass
    idx = os.path.join(found, "index.html")
    if os.path.isfile(idx):
        markers["index.html"] = True
        try:
            m = re.search(r"<title>([^<]*)</title>",
                          open(idx).read())
            if m:
                claims.append({"kind": "title",
                               "text": m.group(1).strip()})
        except Exception:
            pass
    for extra in ("vercel.json", "netlify.toml", "CNAME",
                  "wrangler.toml", "Dockerfile"):
        if os.path.isfile(os.path.join(found, extra)):
            markers[extra] = True
    for rm in ("README.md", "readme.md"):
        rp = os.path.join(found, rm)
        if os.path.isfile(rp):
            try:
                lines = [ln.strip() for ln in open(rp)
                         if ln.strip()][:5]
                if lines:
                    claims.append({"kind": "readme",
                                   "text": " / ".join(lines)[:300]})
            except Exception:
                pass
            break
    if os.path.isdir(os.path.join(found, "supabase")):
        markers["supabase"] = True
    return {"found": True, "path": found,
            "folder": os.path.basename(found), "file_count": files,
            "top_level": top, "markers": markers, "claims": claims}


def _evidence_pool(cand, dig, insp, supplied):
    """Flatten seed + supplied + dig + inspection findings into a
    numbered evidence pool. Origins are kept: model 'defined'
    proposals may only stand on record-origin evidence, never on
    inspection claims."""
    pool = []

    def add(kind, text, source, origin, **extra):
        if not text:
            return
        e = {"id": "E%d" % (len(pool) + 1), "kind": kind,
             "text": str(text)[:600], "source": source,
             "origin": origin}
        e.update(extra)
        pool.append(e)

    for e in (cand["seed_evidence"] or {}).get("entries", []):
        add(e.get("kind", "record"), e.get("text"),
            e.get("source", "seed evidence"), "seed",
            **{k: v for k, v in e.items()
               if k not in ("kind", "text", "source")})
    for e in supplied or []:
        add(e.get("kind", "record"), e.get("text"),
            e.get("source", "supplied evidence"), "supplied",
            **{k: v for k, v in e.items()
               if k not in ("kind", "text", "source")})
    if dig.get("atlas_node"):
        add("record", "Has its own Atlas node %s (%s)"
            % (dig["atlas_node"]["node_key"],
               dig["atlas_node"]["type"]),
            "Atlas dig, atlas_version_scope.py crunch", "dig")
    for b in dig.get("blogs") or []:
        add("record", "Blog %s is %s in the blog registry "
            "(promoted thing: %s)"
            % (b["slug"], b["status"], b["promoted_thing"]),
            "campaignsdesk.blogs via alpha dig", "dig")
    if insp.get("found"):
        add("inspection",
            "Asset folder exists: %s (%d files observed)"
            % (insp["path"], insp["file_count"]),
            "asset inspection, atlas_version_scope.py crunch",
            "inspection")
        for c in insp.get("claims") or []:
            add("claim", "Asset %s claim: %s" % (c["kind"],
                                                c["text"]),
                "asset inspection — CLAIM, not a fact",
                "inspection")
    return pool


def _entry_mentions(entry, cand):
    t = entry["text"].lower()
    return cand["key"].lower() in t or cand["name"].lower() in t


def _assemble_items(cand, dig, insp, pool):
    """Deterministic per-item proposals from the evidence pool.
    Record evidence only; inspection observations may define
    build_state/hosting; claims never define anything."""
    items = {}

    def put(key, state, detail, source, evidence, missing):
        items[key] = {"state": state, "detail": detail,
                      "source": source, "evidence": evidence,
                      "missing": missing}

    rec = [e for e in pool if e["origin"] in ("seed", "supplied",
                                              "dig")]
    # Entries that say a thing is NOT settled must never define it.
    NEG = ("no price", "price unrecorded", "not on record",
           "no pricing", "unsettled", "blocked on", "not settled",
           "no audience", "no unique", "no differentiator",
           "unknown")

    def clean(e):
        return not any(n in e["text"].lower() for n in NEG)
    # what_it_is — an entry flagged as describing the thing wins;
    # otherwise the best record description, rulings first
    kind_rank = {"ruling": 0, "record": 1, "workup": 2,
                 "folder_evidence": 3, "classification": 1}
    desc = [e for e in rec if e.get("describes")]
    if not desc:
        desc = sorted(
            [e for e in rec if e["kind"] in kind_rank
             and not e.get("not_a_project")],
            key=lambda e: kind_rank.get(e["kind"], 9))
    cls = [e for e in rec if e.get("not_a_project")]
    if cls:
        put("what_it_is", "defined",
            "Classified on the record as NOT a standalone "
            "project: " + cls[0]["text"], cls[0]["source"],
            [cls[0]["id"]], [])
    elif desc:
        put("what_it_is", "defined", desc[0]["text"],
            desc[0]["source"], [desc[0]["id"]], [])
    else:
        put("what_it_is", "unknown", "",
            "crunch — no record description found",
            [], ["a description of the thing in Brian's record "
                 "(asset claims alone do not define it)"])
    # income_model — price/payer/mechanism on record only
    inc = [e for e in rec if e["kind"] in ("ruling", "record",
                                           "workup")
           and PRICE_RE.search(e["text"])
           and PAYER_RE.search(e["text"])
           and _entry_mentions(e, cand) and clean(e)]
    if inc:
        put("income_model", "defined", inc[0]["text"],
            inc[0]["source"], [inc[0]["id"]], [])
    else:
        put("income_model", "unknown", "",
            "crunch — no price/payer/mechanism on record", [],
            ["a price, a payer, and a mechanism on record — "
             "nothing may be invented"])
    # audience — an entry that names THIS candidate's audience
    aud = [e for e in rec if e.get("audience_for") == cand["key"]]
    aud += [e for e in rec if e["kind"] in ("ruling", "record")
            and "audience" in e["text"].lower()
            and _entry_mentions(e, cand) and clean(e)
            and e not in aud]
    if aud:
        put("audience", "defined", aud[0]["text"],
            aud[0]["source"], [aud[0]["id"]], [])
    else:
        put("audience", "unknown", "",
            "crunch — no audience named for this candidate", [],
            ["the named audience/segment this serves, on record"])
    # marketing_ideas — a ruled/registered blog or recorded channel
    blogs = dig.get("blogs") or []
    mkt_e = [e for e in rec if e["kind"] in ("ruling", "record",
                                             "workup")
             and ("blog" in e["text"].lower()
                  or "marketing" in e["text"].lower())
             and _entry_mentions(e, cand)]
    if blogs:
        put("marketing_ideas", "defined",
            "Own blog in the fleet registry: "
            + "; ".join("%s (%s)" % (b["slug"], b["status"])
                        for b in blogs)
            + (". " + mkt_e[0]["text"] if mkt_e else ""),
            "campaignsdesk.blogs dig"
            + ("; " + mkt_e[0]["source"] if mkt_e else ""),
            [e["id"] for e in mkt_e[:1]], [])
    elif mkt_e:
        put("marketing_ideas", "defined", mkt_e[0]["text"],
            mkt_e[0]["source"], [mkt_e[0]["id"]], [])
    else:
        put("marketing_ideas", "unknown", "",
            "crunch — no marketing idea on record", [],
            ["a marketing idea on record (its blog/asset, "
             "channels, tie-ins)"])
    # unique_edge — Brian's-record differentiator only
    edge = [e for e in rec if e["kind"] in ("ruling", "record")
            and EDGE_RE.search(e["text"])
            and _entry_mentions(e, cand) and clean(e)]
    if edge:
        put("unique_edge", "defined", edge[0]["text"],
            edge[0]["source"], [edge[0]["id"]], [])
    else:
        put("unique_edge", "unknown", "",
            "crunch — no differentiator on Brian's record", [],
            ["its unique data source / unfair advantage, on "
             "record (asset title claims do not count)"])
    # version_scope — candidates are unregistered by definition
    put("version_scope", "unknown", "",
        "derived — candidates carry no ruled version items", [],
        ["registration + Brian's v1 ruling (the engine never "
         "registers)"])
    # build_state — inspection observation
    if insp.get("found"):
        mk = insp.get("markers") or {}
        stack = [s for s in ("package.json", "index.html",
                             "supabase") if mk.get(s)]
        put("build_state", "defined",
            "Exists as code: %d files in %s (markers: %s). "
            "Observed by asset inspection %s; title/README text "
            "treated as claims. Finished/deployed state NOT "
            "evidenced."
            % (insp["file_count"], insp["path"],
               ", ".join(stack) or "none",
               time.strftime("%Y-%m-%d")),
            "asset inspection, atlas_version_scope.py crunch",
            [], [])
    else:
        bs = [e for e in rec if e["kind"] in ("record", "workup",
                                              "classification")]
        if bs and re.search(r"not buildable|fragment|files only|"
                            r"does not exist|no folder",
                            bs[0]["text"], re.I):
            put("build_state", "defined", bs[0]["text"],
                bs[0]["source"], [bs[0]["id"]], [])
        else:
            put("build_state", "unknown", "",
                "crunch — no asset folder found, no build state "
                "on record", [],
                ["the code state, from inspection or the record"])
    # hosting — inspection traces only
    traces = [t for t in ("vercel.json", "netlify.toml", "CNAME",
                          "wrangler.toml", "homepage")
              if (insp.get("markers") or {}).get(t)]
    if traces:
        put("hosting", "defined",
            "Hosting traces in the asset folder: %s"
            % ", ".join(traces),
            "asset inspection, atlas_version_scope.py crunch",
            [], [])
    else:
        put("hosting", "unknown", "",
            "crunch — no hosting trace or ruling found", [],
            ["hosting settled on record (Brian's launch law: no "
             "launch without reliable hosting + finished code)"])
    # lifecycle_status — only entries tagged as lifecycle rulings
    life = [e for e in rec if e["kind"] == "lifecycle"]
    if life:
        put("lifecycle_status", "defined", life[0]["text"],
            life[0]["source"], [life[0]["id"]], [])
    else:
        put("lifecycle_status", "unknown", "",
            "crunch — no lifecycle statement by Brian about "
            "this candidate", [],
            ["a lifecycle statement from Brian (active / on hold "
             "/ parked / under research) — never assumed"])
    # sort_verdict — Brian's ruling only, never proposed
    put("sort_verdict", "unknown", "",
        "Brian's ruling only — the engine never proposes it", [],
        ["Brian's sort verdict after vetting"])
    return items


def _validate_model_proposal(item_key, prop, pool_by_id, cand):
    """A model 'defined' proposal stands ONLY on cited record
    evidence that actually carries the item. Returns (ok, reason).
    """
    ids = prop.get("evidence_ids") or []
    cited = [pool_by_id[i] for i in ids if i in pool_by_id]
    if not cited:
        return False, "cites no evidence from the pool"
    if any(e["origin"] == "inspection" for e in cited):
        return False, "rests on asset claims, not record evidence"
    texts = " ".join(e["text"] for e in cited)
    if item_key == "income_model":
        if not (PRICE_RE.search(texts) and PAYER_RE.search(texts)):
            return False, ("cited evidence carries no price + "
                           "payer/mechanism — income stays UNKNOWN")
    if item_key in ("audience", "marketing_ideas", "unique_edge"):
        if not any(_entry_mentions(e, cand) for e in cited):
            return False, ("cited evidence does not concern this "
                           "candidate (family/umbrella-level "
                           "evidence does not define the member)")
    if item_key == "unique_edge":
        if not any(e["kind"] in ("ruling", "record")
                   for e in cited):
            return False, ("edge must come from Brian's record, "
                           "not folder claims or workups")
        if not EDGE_RE.search(texts):
            return False, ("cited evidence states no "
                           "differentiator — edge stays UNKNOWN")
    return True, "stands on cited record evidence"


_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b")


def _unsupported_names(text, pool):
    pool_text = " ".join(e["text"] for e in pool).lower()
    out = []
    for m in _NAME_RE.findall(text or ""):
        if m.lower() not in pool_text and m not in out:
            out.append(m)
    return out


def crunch_candidate(key, use_model=True, model_url=None,
                     supplied=None):
    cand = get_candidate(key)
    if not cand:
        raise SystemExit("no such candidate: %s" % key)
    dig = dig_record(cand)
    insp = inspect_assets(cand)
    pool = _evidence_pool(cand, dig, insp, supplied)
    items = _assemble_items(cand, dig, insp, pool)
    pool_by_id = {e["id"]: e for e in pool}
    unsupported = []
    packets = {"created": 0, "served": 0, "served_by": [],
               "endpoints": [], "latencies_s": []}
    model_stage = {"status": "skipped", "items": {}}
    if use_model:
        model_stage["status"] = "ran"
        ev_text = "\n".join(
            "[%s] (%s, %s) %s" % (e["id"], e["kind"], e["origin"],
                                  e["text"]) for e in pool)
        reqs = {k: r for k, _t, r in DEFINITION_ITEMS}
        for item_key in MODEL_ITEMS:
            req = reqs[item_key]
            prompt = (
                "You are the synthesis seat of a project vetting "
                "engine. Assess ONE definition item for a "
                "candidate project, using ONLY the evidence "
                "below. No evidence = the item stays UNKNOWN. "
                "Never invent numbers, prices, or audiences.\n\n"
                "Candidate: %s (%s)\nItem: %s — %s\n\nEvidence:\n"
                "%s\n\nReply with ONLY a JSON object: "
                "{\"state\": \"defined\" or \"unknown\", "
                "\"detail\": \"one or two plain sentences\", "
                "\"evidence_ids\": [\"E1\"]}"
                % (cand["name"], key, item_key, req, ev_text))
            packets["created"] += 1
            res, note = call_packet(prompt, max_tokens=400,
                                    model_url=model_url)
            if res is None:
                model_stage["items"][item_key] = {
                    "status": "unserved", "note": note}
                model_stage["status"] = "off-path"
                continue
            packets["served"] += 1
            packets["served_by"].append(
                "%s:%s" % (item_key, res["engine"]))
            packets["endpoints"].append(res["endpoint"])
            packets["latencies_s"].append(res["latency_s"])
            prop = None
            m = re.search(r"\{.*\}", res["text"], re.S)
            if m:
                try:
                    prop = json.loads(m.group(0))
                except Exception:
                    prop = None
            if not prop:
                model_stage["items"][item_key] = {
                    "status": "unparseable",
                    "engine": res["engine"]}
                continue
            entry = {"status": "proposed",
                     "engine": res["engine"],
                     "model": res["model"],
                     "endpoint": res["endpoint"],
                     "latency_s": res["latency_s"],
                     "proposal": prop}
            for nm in _unsupported_names(prop.get("detail", ""),
                                         pool):
                unsupported.append(
                    {"item": item_key, "mention": nm,
                     "reason": "named in model synthesis, absent "
                               "from the evidence pool"})
            if prop.get("state") == "defined" and \
                    items[item_key]["state"] != "defined":
                ok, why = _validate_model_proposal(
                    item_key, prop, pool_by_id, cand)
                if ok:
                    items[item_key] = {
                        "state": "defined",
                        "detail": prop.get("detail", ""),
                        "source": "model synthesis in crunch "
                                  "(%s) — %s"
                                  % (res["engine"], why),
                        "evidence": prop.get("evidence_ids"),
                        "missing": []}
                    entry["applied"] = True
                else:
                    entry["applied"] = False
                    entry["downgraded"] = why
                    unsupported.append(
                        {"item": item_key,
                         "mention": prop.get("detail", "")[:200],
                         "reason": "model proposed DEFINED; "
                                   "downgraded — " + why})
            model_stage["items"][item_key] = entry
    stages = {"dig": dig, "inspection": insp, "model": model_stage,
              "evidence_pool": pool}
    balance = {"goal_ref": cand["goal_ref"],
               "priority": cand["priority"],
               "packets_created": packets["created"],
               "packets_served": packets["served"],
               "served_by": packets["served_by"],
               "endpoints": packets["endpoints"],
               "latencies_s": packets["latencies_s"]}
    cid = pg_one(
        "INSERT INTO "
        "atlas.version_scope_project_candidate_crunches "
        "(candidate_key, stages, items, unsupported_mentions, "
        "balance) VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, "
        "%s::jsonb) RETURNING id",
        (key, json.dumps(stages), json.dumps(items),
         json.dumps(unsupported), json.dumps(balance)))[0]
    pg_exec(
        "UPDATE atlas.version_scope_project_candidates SET "
        "state = 'crunched', last_worked_at = NOW(), "
        "updated_at = NOW() WHERE candidate_key = %s", (key,))
    return cid


def latest_crunch(key):
    row = pg_one(
        "SELECT id, stages, items, unsupported_mentions, balance "
        "FROM atlas.version_scope_project_candidate_crunches "
        "WHERE candidate_key = %s ORDER BY id DESC LIMIT 1",
        (key,))
    if not row:
        return None
    return {"id": row[0], "stages": row[1] or {},
            "items": row[2] or {},
            "unsupported": row[3] or [], "balance": row[4] or {}}


def grade_candidate(key, use_model=True):
    cand = get_candidate(key)
    if not cand:
        raise SystemExit("no such candidate: %s" % key)
    crunch = latest_crunch(key)
    if not crunch:
        raise SystemExit("candidate %s has not been crunched — "
                         "grade needs a crunch first" % key)
    # The mark is read LIVE from the Phase A tables — never a
    # hardcoded copy.
    mark = [r[0] for r in pg_rows(
        "SELECT DISTINCT item_key FROM "
        "atlas.version_scope_definition_items")]
    if not mark:
        raise SystemExit("definition standard not seeded — run "
                         "seed-definitions first")
    order = {k: i for i, (k, _t, _r) in enumerate(DEFINITION_ITEMS)}
    mark.sort(key=lambda k: order.get(k, 99))
    items = crunch["items"]
    parts = {}
    for k in mark:
        it = items.get(k) or {"state": "unknown", "detail": "",
                              "source": "", "evidence": [],
                              "missing": ["not covered by the "
                                          "latest crunch"]}
        parts[k] = {"state": it["state"],
                    "evidence": it.get("evidence") or [],
                    "missing": it.get("missing") or []}
    defined_n = sum(1 for p in parts.values()
                    if p["state"] == "defined")
    two_q = {
        "defined_income_path": {
            "state": "pass" if parts.get("income_model", {})
            .get("state") == "defined" else "fail",
            "evidence": (parts.get("income_model") or {})
            .get("evidence") or [],
            "missing": (parts.get("income_model") or {})
            .get("missing") or []},
        "defined_audience": {
            "state": "pass" if parts.get("audience", {})
            .get("state") == "defined" else "fail",
            "evidence": (parts.get("audience") or {})
            .get("evidence") or [],
            "missing": (parts.get("audience") or {})
            .get("missing") or []}}
    pool = (crunch["stages"] or {}).get("evidence_pool") or []
    cls = [e for e in pool if e.get("not_a_project")]
    placement = [e for e in pool if e.get("kind") == "placement"]
    pubname = [e for e in pool if e.get("kind") == "public_name"]
    gaps = [k for k, p in parts.items() if p["state"] != "defined"
            and k != "sort_verdict"]
    brian_only = []
    reasons = []
    if cls:
        verdict = "NOT A PROJECT"
        reasons.append(cls[0]["text"])
        if cls[0].get("successor"):
            reasons.append("Successor on record: %s"
                           % cls[0]["successor"])
        brian_only.append(
            "Disposition (park / merge / drop) — Brian's ruling, "
            "recorded with his words; the engine never sets it")
    else:
        folded = any(e.get("fold_into_registration")
                     for e in placement)
        if folded:
            brian_only.append(
                "Registration as a standalone project — %s"
                % placement[0]["text"])
        else:
            if placement:
                brian_only.append("Placement — %s"
                                  % placement[0]["text"])
            brian_only.append(
                "Registration itself — the engine never "
                "registers; Brian's ruling only")
        if pubname:
            brian_only.append("Public name — %s"
                              % pubname[0]["text"])
        q_pass = (two_q["defined_income_path"]["state"] == "pass"
                  and two_q["defined_audience"]["state"] == "pass")
        if q_pass and defined_n >= READY_MIN_DEFINED and \
                len(brian_only) == 1:
            verdict = "READY TO REGISTER"
            reasons.append(
                "Both Two Questions pass and %d of %d items are "
                "defined on evidence; only Brian's registration "
                "ruling remains (thresholds are machinery "
                "defaults, not Brian's rulings)"
                % (defined_n, len(mark)))
        elif q_pass or defined_n >= DEVELOPABLE_MIN_DEFINED:
            verdict = "DEVELOPABLE"
            if q_pass:
                reasons.append("Both Two Questions pass; the "
                               "remaining distance is named gaps "
                               "and Brian's rulings, not invention")
            else:
                reasons.append(
                    "%d of %d items defined, but the Two "
                    "Questions do not both pass — income path: %s; "
                    "audience: %s"
                    % (defined_n, len(mark),
                       two_q["defined_income_path"]["state"],
                       two_q["defined_audience"]["state"]))
        else:
            verdict = "THIN"
            reasons.append(
                "Only %d of %d items defined and the Two "
                "Questions do not both pass (income path: %s; "
                "audience: %s) — the evidence is not there yet"
                % (defined_n, len(mark),
                   two_q["defined_income_path"]["state"],
                   two_q["defined_audience"]["state"]))
        if gaps:
            reasons.append("Open gaps: " + ", ".join(gaps))
    grade = {"mark_items": mark, "parts": parts,
             "defined_count": defined_n,
             "two_questions": two_q, "verdict": verdict,
             "reasons": reasons, "named_gaps": gaps,
             "brian_only_rulings": brian_only,
             "crunch_id": crunch["id"],
             "thresholds": "machinery defaults (READY >= %d "
                           "defined + both Two Questions; "
                           "DEVELOPABLE >= %d defined or both Two "
                           "Questions) — labeled, Brian-correctable"
                           % (READY_MIN_DEFINED,
                              DEVELOPABLE_MIN_DEFINED),
             "verdict_narrative": None}
    if use_model and not cls:
        prompt = (
            "You are the senior grader for a project vetting "
            "engine. The deterministic grade is FIXED below — "
            "states and verdict are computed from evidence by "
            "code and you must NOT change, soften, or contradict "
            "them. Write the verdict narrative (max 200 words) "
            "in plain language for the project's owner, grounded "
            "only in the grade.\n\nCandidate: %s\nGrade: %s"
            % (cand["name"], json.dumps(
                {k: grade[k] for k in ("verdict", "reasons",
                                       "two_questions",
                                       "named_gaps",
                                       "defined_count")},
                indent=1)[:6000]))
        res, note = call_packet(prompt, max_tokens=450,
                                tier="smart")
        if res is not None:
            grade["verdict_narrative"] = {
                "text": res["text"], "engine": res["engine"],
                "model": res["model"], "endpoint": res["endpoint"],
                "latency_s": res["latency_s"],
                "label": "model narrative — the deterministic "
                         "grade above is the grade"}
        else:
            grade["narrative_note"] = ("no smarter-engine seat "
                                       "served: %s" % note)
    pg_exec(
        "UPDATE atlas.version_scope_project_candidates SET "
        "last_grade = %s::jsonb, state = 'graded', "
        "last_worked_at = NOW(), updated_at = NOW() "
        "WHERE candidate_key = %s", (json.dumps(grade), key))
    return grade


def candidate_defined_count(key):
    """Proposed-defined count from the latest grade (or crunch):
    the candidate's completeness for the shared sort view."""
    cand = get_candidate(key)
    if not cand:
        return None
    if cand["last_grade"]:
        return cand["last_grade"].get("defined_count")
    crunch = latest_crunch(key)
    if crunch:
        return sum(1 for v in crunch["items"].values()
                   if v.get("state") == "defined")
    return None


def print_candidate(key):
    cand = get_candidate(key)
    if not cand:
        raise SystemExit("no such candidate: %s" % key)
    print("%s — %s" % (cand["key"], cand["name"]))
    print("  state: %s | priority: %s | goal: %s"
          % (cand["state"], cand["priority"],
             cand["goal_ref"] or "-"))
    print("  disposition: %s%s"
          % (cand["disposition"] or "(none — Brian's ruling only)",
             (" — " + cand["disposition_source"])
             if cand["disposition"] else ""))
    n = pg_one(
        "SELECT count(*) FROM "
        "atlas.version_scope_project_candidate_crunches "
        "WHERE candidate_key = %s", (key,))[0]
    print("  crunches: %d" % n)
    crunch = latest_crunch(key)
    if crunch:
        print("  latest crunch #%d items:" % crunch["id"])
        for k, _t, _r in DEFINITION_ITEMS:
            it = crunch["items"].get(k) or {}
            print("    %-18s %s" % (k, it.get("state", "unknown")))
        if crunch["unsupported"]:
            print("  unsupported mentions: %d (never raise a "
                  "state)" % len(crunch["unsupported"]))
    g = cand["last_grade"]
    if g:
        print("  grade: %s (%d defined)"
              % (g.get("verdict"), g.get("defined_count", 0)))
        print("  two questions: income path %s | audience %s"
              % (g["two_questions"]["defined_income_path"]
                 ["state"],
                 g["two_questions"]["defined_audience"]["state"]))
        for r in g.get("brian_only_rulings") or []:
            print("  brian-only: %s" % r)
    return cand


def selftest():
    ok = []

    def check(label, cond):
        ok.append((label, bool(cond)))
        print("  [ok] %s" % label if cond else "  [FAIL] %s" % label)

    P1, P2 = "selftest-vs-proj", "selftest-vs-empty"
    P3, P4 = "selftest-vs-child", "selftest-vs-plain"
    P5 = "selftest-vs-removed"
    P6, P7 = "selftest-vs-defs", "selftest-vs-defs-empty"
    try:
        register_project(P1, "Selftest VS Project", source="selftest")
        check("register project + atlas node linked",
              pg_one("SELECT atlas_node_key FROM atlas.version_scope_projects "
                     "WHERE project_key=%s", (P1,))[0] == "proj:%s" % P1)
        add_item(P1, "v1", "alpha", "Alpha", "v1 item", "selftest")
        add_item(P1, "v2", "beta", "Beta", "v2 item", "selftest")
        add_item(P1, "v3", "gamma", "Gamma", "v3 item", "selftest")
        state, counts, _ = project_state(P1)
        check("state defined with v1/v2/v3 items",
              state == "defined" and counts == {"v1": 1, "v2": 1, "v3": 1})
        frm = move_item(P1, "beta", "v1", source="selftest", reason="pulled forward")
        row = pg_one("SELECT version_label FROM atlas.version_scope_items "
                     "WHERE project_key=%s AND item_key='beta'", (P1,))
        mv = pg_one("SELECT from_version, to_version FROM atlas.version_scope_moves "
                    "WHERE project_key=%s AND item_key='beta'", (P1,))
        check("move v2->v1 applied + history kept",
              frm == "v2" and row[0] == "v1" and mv == ("v2", "v1"))
        register_project(P2, "Selftest VS Empty", source="selftest")
        state2, _c, missing2 = project_state(P2)
        check("scope-less project reads unknown + gaps named",
              state2 == "unknown" and len(missing2) == 1)
        register_project(P3, "Selftest VS Child", source="selftest")
        set_part_of(P3, P1)
        prow = pg_one("SELECT part_of FROM atlas.version_scope_projects "
                      "WHERE project_key=%s", (P3,))
        check("part-of recorded on the child row", prow[0] == P1)
        register_project(P4, "Selftest VS Plain", source="selftest")
        set_priority(P2, "super_high")
        gap_keys = [g[0] for g in gap_projects()]
        check("part-of project excluded from scope gaps",
              P3 not in gap_keys)
        check("standalone unknown projects still in scope gaps",
              P2 in gap_keys and P4 in gap_keys)
        check("super-high-priority gap surfaces before normal gaps",
              gap_keys.index(P2) < gap_keys.index(P4))
        register_project(P5, "Selftest VS Removed", source="selftest")
        remove_project(P5, source="selftest", reason="selftest removal")
        check("remove-project deletes the project row",
              pg_one("SELECT count(*) FROM atlas.version_scope_projects "
                     "WHERE project_key=%s", (P5,))[0] == 0)
        ev = pg_one("SELECT event, source FROM "
                    "atlas.version_scope_project_events "
                    "WHERE project_key=%s", (P5,))
        check("removal recorded in project events with its source",
              ev == ("project_removed", "selftest"))
        register_project(P5, "Selftest VS Removed", source="selftest")
        add_item(P5, "v1", "keepme", "Keep Me", "item blocks removal",
                 "selftest")
        refused = False
        try:
            remove_project(P5, source="selftest")
        except SystemExit:
            refused = True
        check("remove-project refuses a project carrying scope items",
              refused)
        # ---- definition sheet ----
        register_project(P6, "Selftest VS Defs", source="selftest")
        register_project(P7, "Selftest VS Defs Empty", source="selftest")
        seed_definitions()
        rows6 = {r[0]: r[1] for r in definition_rows(P6)}
        check("definition seed materializes the 10 standard rows "
              "(all unknown)",
              len(rows6) == len(DEFINITION_KEYS)
              and set(rows6.values()) == {"unknown"})
        set_definition(P6, "what_it_is", "defined",
                       "selftest thing", "selftest source")
        row = pg_one(
            "SELECT state, detail, source FROM "
            "atlas.version_scope_definition_items "
            "WHERE project_key=%s AND item_key='what_it_is'", (P6,))
        check("set-definition round-trips with detail + source",
              row == ("defined", "selftest thing", "selftest source"))
        mv = pg_one(
            "SELECT to_state FROM atlas.version_scope_definition_moves "
            "WHERE project_key=%s AND item_key='what_it_is'", (P6,))
        check("definition change kept in moves history",
              bool(mv) and mv[0] == "defined")
        refused = False
        try:
            set_definition(P6, "audience", "defined",
                           "a detail with no source", "")
        except SystemExit:
            refused = True
        check("set-definition refuses a defined cell without a source",
              refused)
        refused = False
        try:
            set_definition(P6, "version_scope", "defined", "x", "y")
        except SystemExit:
            refused = True
        check("version_scope cannot be hand-set (derived only)",
              refused)
        rows6 = {r[0]: r[1] for r in definition_rows(P6)}
        check("derived version_scope unknown with no v1 items",
              rows6["version_scope"] == "unknown")
        add_item(P6, "v1", "defcheck", "Def Check",
                 "v1 item for derivation", "selftest")
        derive_version_scope(P6)
        rows6 = {r[0]: r[1] for r in definition_rows(P6)}
        check("derived version_scope defined once a v1 item exists",
              rows6["version_scope"] == "defined")
        gaps = {g[0]: g[3] for g in definition_gaps()}
        check("definition-gaps counts missing items correctly",
              len(gaps[P7]) == len(DEFINITION_KEYS)
              and len(gaps[P6]) == len(DEFINITION_KEYS) - 2)
        srt = [s[0] for s in sort_projects()]
        check("sort puts super-high priority ahead of completeness "
              "(P2 super-high/0-defined before P6 normal/2-defined)",
              srt.index(P2) < srt.index(P6))
        check("sort orders same-priority projects by completeness",
              srt.index(P6) < srt.index(P7))

        # --- Phase B: vetting engine (scratch candidate) ---
        P8 = "selftest-vs-cand"
        pg_exec("DELETE FROM "
                "atlas.version_scope_project_candidates "
                "WHERE candidate_key = %s", (P8,))
        cand = add_candidate(
            P8, "Selftest VS Cand", seed_evidence={"entries": [
                {"kind": "ruling",
                 "text": "Selftest VS Cand is a disposable "
                         "vetting harness widget (fixture)",
                 "source": "selftest fixture"},
                {"kind": "record",
                 "text": "Selftest VS Cand is recorded as a "
                         "stated plan only, nothing more on "
                         "record",
                 "source": "selftest fixture"}]})
        check("candidate added at state candidate",
              cand["state"] == "candidate")
        saved_chain = VS_OVERFLOW_CHAIN
        globals()["VS_OVERFLOW_CHAIN"] = ()
        try:
            cid1 = crunch_candidate(
                P8, use_model=True,
                model_url="http://127.0.0.1:59998/v1/")
        finally:
            globals()["VS_OVERFLOW_CHAIN"] = saved_chain
        cr = latest_crunch(P8)
        check("crunch appended",
              cr is not None and cr["id"] == cid1)
        check("model stage honestly off-path with dead seats",
              cr["stages"]["model"]["status"] == "off-path")
        check("what_it_is defined from seed ruling evidence",
              cr["items"]["what_it_is"]["state"] == "defined")
        check("income UNKNOWN with no price on record",
              cr["items"]["income_model"]["state"] == "unknown")
        check("a disclaimer 'only' never defines unique_edge",
              cr["items"]["unique_edge"]["state"] == "unknown")
        check("engine never proposes sort_verdict",
              cr["items"]["sort_verdict"]["state"] == "unknown")
        check("candidate state advanced to crunched",
              get_candidate(P8)["state"] == "crunched")
        g = grade_candidate(P8, use_model=False)
        check("grade returns a worded verdict",
              g["verdict"] in ("READY TO REGISTER", "DEVELOPABLE",
                               "THIN", "NOT A PROJECT"))
        check("Two Questions gate reads the items",
              g["two_questions"]["defined_income_path"]["state"]
              == "fail")
        check("grade read the mark live from definition tables",
              "income_model" in g["mark_items"])
        check("candidate state advanced to graded",
              get_candidate(P8)["state"] == "graded")
        cid2 = crunch_candidate(P8, use_model=False)
        n_cr = pg_one(
            "SELECT count(*) FROM "
            "atlas.version_scope_project_candidate_crunches "
            "WHERE candidate_key = %s", (P8,))[0]
        check("re-crunch appends, never duplicates",
              cid2 != cid1 and n_cr == 2)
        try:
            set_disposition(P8, "parked", "")
            check("disposition without Brian's words refused",
                  False)
        except SystemExit:
            check("disposition without Brian's words refused",
                  True)
        set_disposition(P8, "parked",
                        "Brian (selftest fixture): park it")
        check("disposition recorded with its source",
              get_candidate(P8)["disposition"] == "parked")
        pg_exec("DELETE FROM "
                "atlas.version_scope_project_candidates "
                "WHERE candidate_key = %s", (P8,))
        n_left = pg_one(
            "SELECT count(*) FROM "
            "atlas.version_scope_project_candidate_crunches "
            "WHERE candidate_key = %s", (P8,))[0]
        check("scratch candidate + crunches fully removed",
              get_candidate(P8) is None and n_left == 0)
    finally:
        for pk in (P3, P4, P2, P1, P5, P6, P7):
            pg_exec("DELETE FROM atlas.version_scope_projects "
                    "WHERE project_key=%s", (pk,))
        pg_exec("DELETE FROM atlas.version_scope_project_events "
                "WHERE project_key LIKE 'selftest-vs-%'")
        pg_exec("DELETE FROM atlas.version_scope_definition_moves "
                "WHERE project_key LIKE 'selftest-vs-%'")
        pg_exec("DELETE FROM atlas.nodes WHERE node_key IN "
                "(%s, %s, %s, %s, %s, %s, %s)",
                ("proj:%s" % P1, "proj:%s" % P2, "proj:%s" % P3,
                 "proj:%s" % P4, "proj:%s" % P5, "proj:%s" % P6,
                 "proj:%s" % P7))
    left = pg_one("SELECT count(*) FROM atlas.version_scope_projects "
                  "WHERE project_key LIKE 'selftest-vs-%'")
    check("cleanup: no selftest rows remain", left[0] == 0)
    failed = [label for label, passed in ok if not passed]
    if failed:
        print("SELFTEST FAIL: %s" % "; ".join(failed))
        sys.exit(1)
    print("SELFTEST PASS")


def main():
    p = argparse.ArgumentParser(description="Atlas version-scope tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("register-project")
    sp.add_argument("--key", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--note")
    sp.add_argument("--source")
    sp.set_defaults(fn=cmd_register_project)

    sp = sub.add_parser("add-item")
    sp.add_argument("--project", required=True)
    sp.add_argument("--version", required=True)
    sp.add_argument("--item", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--summary")
    sp.add_argument("--source")
    sp.add_argument("--status", default="in_scope")
    sp.set_defaults(fn=cmd_add_item)

    sp = sub.add_parser("move-item")
    sp.add_argument("--project", required=True)
    sp.add_argument("--item", required=True)
    sp.add_argument("--to", required=True)
    sp.add_argument("--source")
    sp.add_argument("--reason")
    sp.set_defaults(fn=cmd_move_item)

    sp = sub.add_parser("set-status")
    sp.add_argument("--project", required=True)
    sp.add_argument("--item", required=True)
    sp.add_argument("--status", required=True)
    sp.set_defaults(fn=cmd_set_status)

    sp = sub.add_parser("set-part-of")
    sp.add_argument("--project", required=True)
    sp.add_argument("--part-of", required=True)
    sp.set_defaults(fn=cmd_set_part_of)

    sp = sub.add_parser("set-priority")
    sp.add_argument("--project", required=True)
    sp.add_argument("--priority", required=True, choices=PRIORITIES)
    sp.set_defaults(fn=cmd_set_priority)

    sp = sub.add_parser("remove-project")
    sp.add_argument("--project", required=True)
    sp.add_argument("--source")
    sp.add_argument("--reason")
    sp.set_defaults(fn=cmd_remove_project)

    sp = sub.add_parser("show-scope")
    sp.add_argument("--project", required=True)
    sp.set_defaults(fn=cmd_show_scope)

    sp = sub.add_parser("scope-gaps")
    sp.set_defaults(fn=cmd_scope_gaps)

    sp = sub.add_parser("list-projects")
    sp.set_defaults(fn=cmd_list_projects)

    sp = sub.add_parser("import-json")
    sp.add_argument("file")
    sp.set_defaults(fn=cmd_import_json)

    sp = sub.add_parser("seed-definitions")
    sp.set_defaults(fn=cmd_seed_definitions)

    sp = sub.add_parser("set-definition")
    sp.add_argument("--project", required=True)
    sp.add_argument("--item", required=True)
    sp.add_argument("--state", required=True, choices=DEFINITION_STATES)
    sp.add_argument("--detail")
    sp.add_argument("--source")
    sp.set_defaults(fn=cmd_set_definition)

    sp = sub.add_parser("show-definition")
    sp.add_argument("--project", required=True)
    sp.set_defaults(fn=cmd_show_definition)

    sp = sub.add_parser("definition-gaps")
    sp.set_defaults(fn=cmd_definition_gaps)

    sp = sub.add_parser("sort-projects")
    sp.add_argument("--with-candidates", action="store_true")
    sp.set_defaults(fn=cmd_sort_projects)

    sp = sub.add_parser("add-candidate")
    sp.add_argument("--key", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--priority", default="normal",
                    choices=PRIORITIES)
    sp.add_argument("--goal")
    sp.add_argument("--seed-file")
    sp.set_defaults(fn=cmd_add_candidate)

    sp = sub.add_parser("crunch")
    sp.add_argument("--candidate", required=True)
    sp.add_argument("--evidence-file")
    sp.add_argument("--no-model", action="store_true")
    sp.set_defaults(fn=cmd_crunch)

    sp = sub.add_parser("grade")
    sp.add_argument("--candidate", required=True)
    sp.add_argument("--no-model", action="store_true")
    sp.set_defaults(fn=cmd_grade)

    sp = sub.add_parser("show-candidate")
    sp.add_argument("--candidate", required=True)
    sp.set_defaults(fn=cmd_show_candidate)

    sp = sub.add_parser("list-candidates")
    sp.set_defaults(fn=cmd_list_candidates)

    sp = sub.add_parser("set-disposition")
    sp.add_argument("--candidate", required=True)
    sp.add_argument("--disposition", required=True,
                    choices=DISPOSITIONS)
    sp.add_argument("--source")
    sp.set_defaults(fn=cmd_set_disposition)

    sp = sub.add_parser("selftest")
    sp.set_defaults(fn=lambda a: selftest())

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
