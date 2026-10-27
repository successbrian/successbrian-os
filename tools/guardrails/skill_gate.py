#!/usr/bin/env python3
"""skill_gate.py — Skill/MCP supply-chain gate (Brian's order 2026-10-27).

WHY
    The fleet adopts external skills and MCP servers (Hermes profiles
    carry skill dirs; the OS has tools/mcp). Skill ecosystems now carry
    real supply-chain risk — malicious skills, prompt injection — so
    adoption must be scan -> pin -> register, and drift must be
    detectable after the fact. This module is that gate.

THE ADOPTION FLOW (the documented flow; `adopt` runs it in one command)
    1. SCAN   — look at what is actually on disk. Nothing is registered
                that was not found on disk; unknowns stay unregistered.
    2. PIN    — hash the skill directory / MCP server file (sha256,
                deterministic — see hash_path) and store that hash as
                pinned_ref: the exact bytes that were adopted.
    3. REGISTER — insert a row in successbrian_os.skill_registry
                (kind, name, location_path, content_hash = pinned_ref,
                adopted_at, scan_verdict='registered').
    4. DRIFT-SCAN — on a weekly cron (Sun 04:20), `scan` re-hashes every
                registered location: hash matches pin -> 'clean',
                differs -> 'drift', path gone -> 'missing'. Drift is
                data, not a crash: scan exits 0 and reports the names.

HONEST SCOPE — WHAT "SCAN" MEANS HERE
    This pass does hash-pinning and drift detection ONLY. It does NOT
    do behavioural scanning (no static analysis of skill instructions
    for prompt-injection patterns, no sandbox execution, no signature
    verification against an upstream publisher). Behavioural scanning
    is a documented TODO, not a claim this module makes. Wording in
    this module and its doc says 'pin' for the adoption hash and
    'drift-scan' for the weekly re-hash — never 'vetted' or 'safe'.

SECRETS
    MCP discovery reads server NAMES and file paths only. Hermes
    config files are never parsed for values here (the fleet's Hermes
    configs define no mcp_servers sections as of 2026-10-27 — verified
    by key inspection, values never printed). If a future config format
    carries credentials, they must never enter the registry, this
    module's output, or any file it writes.

ENUMERATION RULES (what counts as a skill under a root)
    * Every directory containing a SKILL.md is one skill; its name is
      its path relative to the root (e.g. 'apple/apple-notes').
    * A non-hidden top-level entry of a skills root whose subtree
      contains no SKILL.md is registered as-is (a loose file or an
      unpackaged skill dir).
    * Hidden entries (any path component starting with '.'), .git and
      __pycache__ are skipped: Hermes bookkeeping (.curator_backups,
      .hub, .usage.json) is not a live skill.
    * For a non-skills root (e.g. the OS repo), only SKILL.md parents
      are enumerated.
    Known gap, on the record: a loose file sitting INSIDE a category
    dir next to packaged skills (e.g. a DESCRIPTION.md beside skill
    subdirs) is not pinned separately.

STATE HOME: PostgreSQL, successbrian_os.skill_registry in
ecosystem_central (migration: 2026-10-27_skill_registry.sql beside
this file). LOGIC HOME: this file, in the repo. Idempotent: register
re-runs add 0 rows; ensure_schema can run any number of times.

RUN
    python3 skill_gate.py register [--root <dir>]...
    python3 skill_gate.py scan
    python3 skill_gate.py list [--verdict v] [--limit n]
    python3 skill_gate.py show <name>
    python3 skill_gate.py adopt <path> [--kind skill|mcp] [--source-url u]
    python3 skill_gate.py selftest
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import tempfile

import psycopg2

DBNAME = "ecosystem_central"
HOME = os.path.expanduser("~")
OS_REPO = os.path.join(HOME, "successbrian-os")
MCP_DIRS = [os.path.join(OS_REPO, "tools", "mcp"),
            os.path.join(HOME, "mcp-servers")]
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS successbrian_os.skill_registry (
    id              serial PRIMARY KEY,
    name            text NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('skill', 'mcp')),
    source_url      text,
    pinned_ref      text,
    content_hash    text,
    location_path   text NOT NULL,
    adopted_at      timestamptz NOT NULL DEFAULT now(),
    last_scanned_at timestamptz,
    scan_verdict    text NOT NULL DEFAULT 'registered'
                    CHECK (scan_verdict IN
                        ('registered', 'clean', 'drift', 'missing')),
    notes           text,
    UNIQUE (kind, name, location_path)
);
"""


def conn():
    return psycopg2.connect(dbname=DBNAME, host="localhost")


def ensure_schema(cur):
    cur.execute(SCHEMA_SQL)


# ---------------------------------------------------------------- hashing

def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_path(path):
    """Deterministic sha256 for a file or a directory.

    File: sha256 of its bytes. Directory: sha256 over the sorted list
    of (relative path, sha256(file bytes)) for every file under it,
    skipping __pycache__/.git/node_modules and hidden components.
    Same input -> same hash, across runs and machines.
    """
    if os.path.isfile(path):
        return _file_sha256(path)
    entries = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS
                             and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, path)
            if "__pycache__" in rel.split(os.sep):
                continue
            try:
                fh = _file_sha256(full)
            except OSError:
                fh = hashlib.sha256(b"<unreadable>").hexdigest()
            entries.append((rel, fh))
    entries.sort()
    h = hashlib.sha256()
    for rel, fh in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(fh.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


# ------------------------------------------------------------ enumeration

def _hidden(relpath):
    return any(part.startswith(".")
               for part in relpath.split(os.sep) if part not in (".", ""))


def enumerate_skills(root):
    """Return [(name, path)] for skills under root per the rules in
    the module docstring. root itself may be a single skill dir."""
    root = os.path.abspath(root)
    found = []
    if os.path.isfile(root):
        return [(os.path.basename(root), root)]
    if os.path.isfile(os.path.join(root, "SKILL.md")):
        return [(os.path.basename(root), root)]
    leaves = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS
                             and not d.startswith("."))
        if "SKILL.md" in filenames:
            leaves.append(dirpath)
    for leaf in leaves:
        found.append((os.path.relpath(leaf, root), leaf))
    # Orphan top-level entries (skills roots only): no SKILL.md beneath.
    if os.path.basename(root) == "skills":
        leaf_set = list(leaves)
        for entry in sorted(os.listdir(root)):
            if entry.startswith("."):
                continue
            full = os.path.join(root, entry)
            if any(l == full or l.startswith(full + os.sep)
                   for l in leaf_set):
                continue
            found.append((entry, full))
    return sorted(found)


def default_skill_roots():
    roots = []
    prof = os.path.join(HOME, ".hermes", "profiles")
    if os.path.isdir(prof):
        for name in sorted(os.listdir(prof)):
            cand = os.path.join(prof, name, "skills")
            if os.path.isdir(cand):
                roots.append(cand)
    if os.path.isdir(OS_REPO):
        roots.append(OS_REPO)
    return roots


_FASTMCP_RE = re.compile(r"""FastMCP\(\s*["']([^"']+)["']""")


def enumerate_mcp_servers():
    """[(name, path)] for MCP server files on disk. Names and paths
    only — file contents are read solely to find a FastMCP("name")
    declaration; no config values are ever extracted."""
    out = []
    for d in MCP_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("__"):
                continue
            full = os.path.join(d, fn)
            name = os.path.splitext(fn)[0]
            try:
                with open(full, "r", errors="replace") as f:
                    head = f.read(20000)
                m = _FASTMCP_RE.search(head)
                if m:
                    name = m.group(1)
            except OSError:
                pass
            out.append((name, full))
    return sorted(out)


# --------------------------------------------------------------- registry

def register_one(cur, kind, name, path, source_url=None, notes=None):
    """Insert one row. Returns True if a new row was created."""
    digest = hash_path(path)
    cur.execute(
        """INSERT INTO successbrian_os.skill_registry
             (name, kind, source_url, pinned_ref, content_hash,
              location_path, last_scanned_at, scan_verdict, notes)
           VALUES (%s, %s, %s, %s, %s, %s, now(), 'registered', %s)
           ON CONFLICT (kind, name, location_path) DO NOTHING
           RETURNING id""",
        (name, kind, source_url, digest, digest, path, notes))
    return cur.fetchone() is not None


def do_register(roots, include_mcp=True):
    stats = {"new": 0, "existing": 0, "by_kind": {}, "by_root": {}}
    with conn() as c, c.cursor() as cur:
        ensure_schema(cur)
        for root in roots:
            if not os.path.exists(root):
                print(f"  skip (missing root): {root}")
                continue
            items = enumerate_skills(root)
            n_new = 0
            for name, path in items:
                if register_one(cur, "skill", name, path,
                                notes=f"root:{root}"):
                    stats["new"] += 1
                    n_new += 1
                else:
                    stats["existing"] += 1
            stats["by_root"][root] = (len(items), n_new)
            stats["by_kind"]["skill"] = stats["by_kind"].get("skill", 0) \
                + len(items)
        if include_mcp:
            items = enumerate_mcp_servers()
            n_new = 0
            for name, path in items:
                if register_one(cur, "mcp", name, path,
                                notes="mcp server file on disk"):
                    stats["new"] += 1
                    n_new += 1
                else:
                    stats["existing"] += 1
            stats["by_root"]["<mcp-discovery>"] = (len(items), n_new)
            stats["by_kind"]["mcp"] = len(items)
    return stats


def do_scan(location_prefix=None):
    """Re-hash registered locations; update verdicts. Returns
    (counts_dict, drifted_names, missing_names)."""
    counts = {"clean": 0, "drift": 0, "missing": 0, "total": 0}
    drifted, missing = [], []
    with conn() as c, c.cursor() as cur:
        ensure_schema(cur)
        if location_prefix:
            cur.execute(
                """SELECT id, name, content_hash, location_path
                     FROM successbrian_os.skill_registry
                    WHERE location_path LIKE %s ORDER BY id""",
                (location_prefix + "%",))
        else:
            cur.execute(
                """SELECT id, name, content_hash, location_path
                     FROM successbrian_os.skill_registry ORDER BY id""")
        rows = cur.fetchall()
        for rid, name, pinned, path in rows:
            counts["total"] += 1
            if not os.path.exists(path):
                verdict = "missing"
                missing.append(name)
            elif hash_path(path) == pinned:
                verdict = "clean"
            else:
                verdict = "drift"
                drifted.append(name)
            counts[verdict] += 1
            cur.execute(
                """UPDATE successbrian_os.skill_registry
                      SET scan_verdict=%s, last_scanned_at=now()
                    WHERE id=%s""", (verdict, rid))
    return counts, drifted, missing


# ------------------------------------------------------------------- CLI

def cmd_register(args):
    roots = args.root if args.root else default_skill_roots()
    include_mcp = not args.root and not args.no_mcp
    print(f"register: {len(roots)} root(s), mcp discovery: "
          f"{'on' if include_mcp else 'off'}")
    stats = do_register(roots, include_mcp=include_mcp)
    for root, (total, n_new) in stats["by_root"].items():
        print(f"  {root}: {total} found, {n_new} new")
    print(f"register done: {stats['new']} new, "
          f"{stats['existing']} already registered; "
          f"by kind (found): {stats['by_kind']}")
    return 0


def cmd_scan(args):
    counts, drifted, missing = do_scan()
    print(f"scan: {counts['total']} registered — "
          f"{counts['clean']} clean, {counts['drift']} drift, "
          f"{counts['missing']} missing")
    for label, names in (("DRIFT", drifted), ("MISSING", missing)):
        for n in names[:100]:
            print(f"  {label}: {n}")
        if len(names) > 100:
            print(f"  {label}: … and {len(names) - 100} more")
    return 0  # drift is a report, not a crash


def cmd_list(args):
    with conn() as c, c.cursor() as cur:
        ensure_schema(cur)
        if args.verdict:
            cur.execute(
                """SELECT kind, name, scan_verdict, location_path
                     FROM successbrian_os.skill_registry
                    WHERE scan_verdict=%s ORDER BY kind, name, location_path
                    LIMIT %s""", (args.verdict, args.limit))
        else:
            cur.execute(
                """SELECT kind, name, scan_verdict, location_path
                     FROM successbrian_os.skill_registry
                    ORDER BY kind, name, location_path LIMIT %s""",
                (args.limit,))
        rows = cur.fetchall()
        cur.execute("SELECT count(*) FROM successbrian_os.skill_registry")
        total = cur.fetchone()[0]
    print(f"{total} registered (showing {len(rows)}):")
    for kind, name, verdict, path in rows:
        print(f"  [{kind}] {name} — {verdict} — {path}")
    return 0


def cmd_show(args):
    with conn() as c, c.cursor() as cur:
        ensure_schema(cur)
        cur.execute(
            """SELECT name, kind, source_url, pinned_ref, content_hash,
                      location_path, adopted_at, last_scanned_at,
                      scan_verdict, notes
                 FROM successbrian_os.skill_registry
                WHERE name=%s OR name LIKE %s OR location_path LIKE %s
                ORDER BY kind, location_path""",
            (args.name, "%/" + args.name, "%" + args.name + "%"))
        rows = cur.fetchall()
    if not rows:
        print(f"no registry entry matching '{args.name}'")
        return 0
    for r in rows:
        print(f"name:         {r[0]}")
        print(f"kind:         {r[1]}")
        print(f"source_url:   {r[2]}")
        print(f"pinned_ref:   {r[3]}")
        print(f"content_hash: {r[4]}")
        print(f"location:     {r[5]}")
        print(f"adopted_at:   {r[6]}")
        print(f"last_scanned: {r[7]}")
        print(f"verdict:      {r[8]}")
        print(f"notes:        {r[9]}")
        print("---")
    print(f"{len(rows)} match(es)")
    return 0


def cmd_adopt(args):
    path = os.path.abspath(args.path)
    if not os.path.exists(path):
        print(f"adopt: path does not exist: {path}")
        return 1
    name = args.name or os.path.basename(path.rstrip("/"))
    print("adoption flow (scan -> pin -> register; drift-scan follows "
          "on the weekly cron):")
    print(f"  1. scan: found on disk at {path}")
    digest = hash_path(path)
    print(f"  2. pin: sha256 = {digest} (hash-pin only — no behavioural "
          f"scan in this pass; see module docstring TODO)")
    with conn() as c, c.cursor() as cur:
        ensure_schema(cur)
        is_new = register_one(cur, args.kind, name, path,
                              source_url=args.source_url,
                              notes="adopted via skill_gate adopt")
    print(f"  3. register: {'new row in skill_registry' if is_new else 'already registered (idempotent, nothing changed)'}")
    print(f"  4. drift-scan: weekly cron will re-hash and flag drift")
    print(f"adopted: [{args.kind}] {name} pinned at {digest}")
    return 0


# --------------------------------------------------------------- selftest

def cmd_selftest(args):
    checks = []

    def check(label, ok):
        checks.append((label, bool(ok)))
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")

    fixture = tempfile.mkdtemp(prefix="skill_gate_selftest_")
    try:
        # a skills-shaped root so orphan enumeration applies
        root = os.path.join(fixture, "skills")
        skill_dir = os.path.join(root, "fixskill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("# fixture skill\n")
        helper = os.path.join(skill_dir, "helper.txt")
        with open(helper, "w") as f:
            f.write("helper v1\n")
        with open(os.path.join(root, "loose.md"), "w") as f:
            f.write("loose top-level file\n")

        h1 = hash_path(skill_dir)
        h2 = hash_path(skill_dir)
        check("hash deterministic across two computations", h1 == h2)

        stats = do_register([root], include_mcp=False)
        check("register fixture root adds 2 entries",
              stats["new"] == 2)

        stats2 = do_register([root], include_mcp=False)
        check("re-register is idempotent (0 new)", stats2["new"] == 0)

        counts, drifted, missing = do_scan(location_prefix=root)
        check("scan after register: all clean",
              counts["clean"] == 2 and counts["drift"] == 0
              and counts["missing"] == 0)

        with open(helper, "a") as f:
            f.write("tampered\n")
        counts, drifted, missing = do_scan(location_prefix=root)
        check("modified file flags drift",
              counts["drift"] == 1 and "fixskill" in drifted)

        with open(helper, "w") as f:
            f.write("helper v1\n")
        counts, drifted, missing = do_scan(location_prefix=root)
        check("restored file scans clean again", counts["clean"] == 2)

        shutil.rmtree(skill_dir)
        counts, drifted, missing = do_scan(location_prefix=root)
        check("deleted dir flags missing",
              counts["missing"] == 1 and "fixskill" in missing)
    finally:
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """DELETE FROM successbrian_os.skill_registry
                    WHERE location_path LIKE %s""", (fixture + "%",))
            cur.execute(
                """SELECT count(*) FROM successbrian_os.skill_registry
                    WHERE location_path LIKE %s""", (fixture + "%",))
            remaining = cur.fetchone()[0]
        shutil.rmtree(fixture, ignore_errors=True)
        check("fixture registry rows removed (self-cleaning)",
              remaining == 0)

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    if passed == total:
        print(f"SELFTEST OK: {passed}/{total} PASS")
        return 0
    print(f"SELFTEST FAIL: {passed}/{total} PASS")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill/MCP supply-chain gate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register")
    p.add_argument("--root", action="append", default=None,
                   help="skills root to enumerate (repeatable); "
                        "default: all Hermes profile skills dirs + OS repo")
    p.add_argument("--no-mcp", action="store_true",
                   help="skip MCP server discovery (default mode only)")
    p.set_defaults(fn=cmd_register)

    p = sub.add_parser("scan")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("list")
    p.add_argument("--verdict", default=None,
                   choices=["registered", "clean", "drift", "missing"])
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show")
    p.add_argument("name")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("adopt")
    p.add_argument("path")
    p.add_argument("--kind", default="skill", choices=["skill", "mcp"])
    p.add_argument("--name", default=None)
    p.add_argument("--source-url", default=None)
    p.set_defaults(fn=cmd_adopt)

    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
