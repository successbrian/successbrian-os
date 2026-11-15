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
  atlas_version_scope.py selftest
"""
import argparse
import json
import os
import sys

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


# ---------------------------------------------------------------- selftest

def selftest():
    ok = []

    def check(label, cond):
        ok.append((label, bool(cond)))
        print("  [ok] %s" % label if cond else "  [FAIL] %s" % label)

    P1, P2 = "selftest-vs-proj", "selftest-vs-empty"
    P3, P4 = "selftest-vs-child", "selftest-vs-plain"
    P5 = "selftest-vs-removed"
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
    finally:
        for pk in (P3, P4, P2, P1, P5):
            pg_exec("DELETE FROM atlas.version_scope_projects "
                    "WHERE project_key=%s", (pk,))
        pg_exec("DELETE FROM atlas.version_scope_project_events "
                "WHERE project_key LIKE 'selftest-vs-%'")
        pg_exec("DELETE FROM atlas.nodes WHERE node_key IN "
                "(%s, %s, %s, %s, %s)",
                ("proj:%s" % P1, "proj:%s" % P2, "proj:%s" % P3,
                 "proj:%s" % P4, "proj:%s" % P5))
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

    sp = sub.add_parser("selftest")
    sp.set_defaults(fn=lambda a: selftest())

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
