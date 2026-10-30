#!/usr/bin/env python3
"""Sprawl Census — measuring the distance to R32.

R32 (Brian, 2026-10-23): the sanctioned homes are
AnythingLLM (documents), PostgreSQL (state), n8n
(automation), and CODE in repos (logic) — "not just
random files and scripts."

This census inventories the loose zones of the box,
classifies every file by the home it BELONGS in, and
measures the headline sprawl metric: how much of the
automation (crontab) runs on loose scripts outside any
repo. It changes nothing — it produces the migration
queue with numbers, so the cleanup is sized honestly
instead of vibes.

A file under a git repo counts as CODE (sanctioned).
Everything else is loose, classed:
  doc      (.md/.txt/.rst)   -> belongs in AnythingLLM
  script   (.py/.sh)         -> logic belongs in a repo;
                                recurring runs belong in n8n
  fragment (.html)           -> generated output; its
                                generator belongs in a repo
  data     (.json/.yaml/.csv/.db/.sql) -> belongs in PG
  other                      -> judged case by case
"""

import os
import subprocess
import sys
import tempfile

import psycopg2

# SBOS common routines — Batch B migration (2026-10-27): the DB
# helpers below delegate to sbos_common (tools/), the one shared
# module. sys.path gets the tools/ dir (this file lives in tools/atlas/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

DBNAME = "ecosystem_central"

DDL = """
CREATE TABLE IF NOT EXISTS atlas.sprawl_snapshots (
    id                    serial PRIMARY KEY,
    run_at                timestamptz NOT NULL DEFAULT now(),
    loose_doc             integer NOT NULL,
    loose_script          integer NOT NULL,
    loose_fragment        integer NOT NULL,
    loose_data            integer NOT NULL,
    loose_other           integer NOT NULL,
    in_repo               integer NOT NULL,
    cron_invocations      integer,
    cron_loose_invocations integer,
    cron_loose_distinct   integer,
    is_baseline           boolean NOT NULL DEFAULT false
);
"""

# "Getting too far" — the board's trip lines (Brian,
# 2026-10-23: 'the board of directors should be watching
# any sprawl that is getting too far'). Growth is measured
# against the BASELINE snapshot. The board can tighten or
# loosen these; they live here, in code, where the watch
# reads them.
SPRAWL_LIMITS = {
    "doc_growth_pct": 10,        # loose documents
    "doc_abs": 1250,             # ...or this absolute cap
    "script_growth_pct": 10,     # loose scripts
    "data_growth_pct": 25,      # loose data files
    "cron_distinct_increase": 0,  # ANY new loose cron
                                  # script trips the watch
}

HOME = os.path.expanduser("~")
REPORT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "SPRAWL_CENSUS.md")

SCAN_ROOTS = [
    ("home (top level)", HOME, 1),
    ("~/scripts", os.path.join(HOME, "scripts"), 6),
    ("~/bin", os.path.join(HOME, "bin"), 2),
    ("~/night_work", os.path.join(HOME, "night_work"), 3),
    ("~/dashboard-fragments",
     os.path.join(HOME, "dashboard-fragments"), 1),
    ("/home/agents/workspace/scripts",
     "/home/agents/workspace/scripts", 3),
    ("~/successbrian-os/tools",
     os.path.join(HOME, "successbrian-os", "tools"), 6),
]

REPO_CANDIDATES = [
    os.path.join(HOME, "successbrian-os"),
    os.path.join(HOME, "campaignsdesk"),
    os.path.join(HOME, "tradesdesk"),
    os.path.join(HOME, "dashboard-api"),
    os.path.join(HOME, "vera-repo"),
    os.path.join(HOME, "anything-llm"),
    "/home/agents/workspace",
    "/home/dealsdesk",
]

SKIP_DIRS = {".git", "node_modules", "__pycache__",
             "venv", ".venv", "dist", "build"}
MAX_PER_ROOT = 20000

EXT_CLASS = {}
for _e in (".md", ".txt", ".rst"):
    EXT_CLASS[_e] = "doc"
for _e in (".py", ".sh"):
    EXT_CLASS[_e] = "script"
for _e in (".html", ".htm"):
    EXT_CLASS[_e] = "fragment"
for _e in (".json", ".yaml", ".yml", ".csv", ".db",
           ".sqlite", ".sql"):
    EXT_CLASS[_e] = "data"


def classify(path):
    return EXT_CLASS.get(
        os.path.splitext(path)[1].lower(), "other")


def repo_roots():
    return [r for r in REPO_CANDIDATES
            if os.path.isdir(os.path.join(r, ".git"))]


def under_repo(path, roots):
    ap = os.path.abspath(path)
    return any(ap == r or ap.startswith(r + os.sep)
               for r in roots)


def scan(root, maxdepth, roots):
    counts = {}
    docs = []
    total = 0
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) \
            - base_depth
        if depth >= maxdepth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS]
        for fn in filenames:
            total += 1
            if total > MAX_PER_ROOT:
                return counts, docs, total, True
            p = os.path.join(dirpath, fn)
            if under_repo(p, roots):
                counts["in-repo"] = counts.get(
                    "in-repo", 0) + 1
                continue
            cls = classify(p)
            counts[cls] = counts.get(cls, 0) + 1
            if cls == "doc":
                try:
                    docs.append((os.path.getsize(p), p))
                except OSError:
                    pass
    return counts, docs, total, False


def cron_metric(roots):
    try:
        out = subprocess.run(
            ["crontab", "-l"], capture_output=True,
            text=True, timeout=15).stdout
    except Exception:
        return None
    scripts = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        for tok in ln.replace(";", " ").split():
            if tok.endswith((".py", ".sh")) and "/" in tok:
                scripts.append(tok.strip("\"'"))
    loose = [s for s in scripts if not under_repo(s, roots)]
    return {"total_invocations": len(scripts),
            "loose_invocations": len(loose),
            "distinct_loose_scripts": len(set(loose))}


def collect():
    """Run the census. Returns (metrics, report_text)."""
    roots = repo_roots()
    lines = ["# Sprawl Census — distance to R32", "",
             "Repos detected (CODE, sanctioned): %s"
             % (", ".join(roots) or "none"), ""]
    grand = {}
    all_docs = []
    for label, root, depth in SCAN_ROOTS:
        if not os.path.isdir(root):
            lines.append("- %s: (absent)" % label)
            continue
        counts, docs, total, capped = scan(root, depth,
                                            roots)
        all_docs.extend(docs)
        for k, v in counts.items():
            grand[k] = grand.get(k, 0) + v
        lines.append("- %s: %d files — %s%s"
                     % (label, total,
                        ", ".join("%s %d" % kv for kv
                                  in sorted(counts.items())),
                        " (CAPPED)" if capped else ""))
    cm = cron_metric(roots)
    metrics = {
        "doc": grand.get("doc", 0),
        "script": grand.get("script", 0),
        "fragment": grand.get("fragment", 0),
        "data": grand.get("data", 0),
        "other": grand.get("other", 0),
        "in_repo": grand.get("in-repo", 0),
        "cron_invocations": cm["total_invocations"]
        if cm else None,
        "cron_loose_invocations": cm["loose_invocations"]
        if cm else None,
        "cron_loose_distinct": cm["distinct_loose_scripts"]
        if cm else None,
    }
    lines.append("")
    lines.append("## Loose totals (outside any repo)")
    for k in ("doc", "script", "fragment", "data", "other"):
        if metrics[k]:
            lines.append("- %s: %d" % (k, metrics[k]))
    lines.append("- in-repo (sanctioned CODE): %d"
                 % metrics["in_repo"])
    lines.append("")
    lines.append("## Automation sprawl (crontab)")
    if cm:
        lines.append(
            "- script invocations in crontab: %d; on "
            "LOOSE scripts: %d (%d distinct scripts)"
            % (cm["total_invocations"],
               cm["loose_invocations"],
               cm["distinct_loose_scripts"]))
    else:
        lines.append("- crontab unreadable")
    lines.append("")
    lines.append("## Biggest loose documents "
                 "(AnythingLLM candidates)")
    for size, p in sorted(all_docs, reverse=True)[:12]:
        lines.append("- %8d bytes  %s" % (size, p))
    lines.append("")
    return metrics, "\n".join(lines)


def pg():
    # Batch B migration (2026-10-27): the connection comes from the one
    # shared factory — same database, host, and 'postgres' role as before.
    return sbos_common.connect(user="postgres")


def record_snapshot(conn, m, is_baseline=False):
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            "INSERT INTO atlas.sprawl_snapshots "
            "(loose_doc, loose_script, loose_fragment, "
            "loose_data, loose_other, in_repo, "
            "cron_invocations, cron_loose_invocations, "
            "cron_loose_distinct, is_baseline) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (m["doc"], m["script"], m["fragment"],
             m["data"], m["other"], m["in_repo"],
             m["cron_invocations"],
             m["cron_loose_invocations"],
             m["cron_loose_distinct"], is_baseline))
    conn.commit()


def get_baseline(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            "SELECT loose_doc, loose_script, loose_data, "
            "cron_loose_distinct, run_at FROM "
            "atlas.sprawl_snapshots ORDER BY "
            "is_baseline DESC, run_at ASC LIMIT 1")
        row = cur.fetchone()
    conn.commit()
    if not row:
        return None
    return {"doc": row[0], "script": row[1], "data": row[2],
            "cron_loose_distinct": row[3], "run_at": row[4]}


def evaluate(m, base):
    """The trip lines. Returns a list of trip strings
    (empty = sprawl within limits)."""
    trips = []
    if base is None:
        return trips
    if base["doc"]:
        growth = 100.0 * (m["doc"] - base["doc"]) / base["doc"]
        if growth > SPRAWL_LIMITS["doc_growth_pct"] \
                or m["doc"] > SPRAWL_LIMITS["doc_abs"]:
            trips.append(
                "loose documents %d (baseline %d, %+.0f%%; "
                "limit +%d%% or %d)"
                % (m["doc"], base["doc"], growth,
                   SPRAWL_LIMITS["doc_growth_pct"],
                   SPRAWL_LIMITS["doc_abs"]))
    if base["script"]:
        growth = 100.0 * (m["script"] - base["script"]) \
            / base["script"]
        if growth > SPRAWL_LIMITS["script_growth_pct"]:
            trips.append(
                "loose scripts %d (baseline %d, %+.0f%%; "
                "limit +%d%%)"
                % (m["script"], base["script"], growth,
                   SPRAWL_LIMITS["script_growth_pct"]))
    if base["data"]:
        growth = 100.0 * (m["data"] - base["data"]) \
            / base["data"]
        if growth > SPRAWL_LIMITS["data_growth_pct"]:
            trips.append(
                "loose data files %d (baseline %d, %+.0f%%; "
                "limit +%d%%)"
                % (m["data"], base["data"], growth,
                   SPRAWL_LIMITS["data_growth_pct"]))
    if base["cron_loose_distinct"] is not None \
            and m["cron_loose_distinct"] is not None \
            and m["cron_loose_distinct"] \
            > base["cron_loose_distinct"] \
            + SPRAWL_LIMITS["cron_distinct_increase"]:
        trips.append(
            "NEW loose cron scripts: %d distinct "
            "(baseline %d) — automation is landing outside "
            "n8n and the repos"
            % (m["cron_loose_distinct"],
               base["cron_loose_distinct"]))
    return trips


def file_board_item(conn, trips, m):
    """Put the trip on the board's agenda: the board
    reads Atlas open gates + tasks, so a queued
    atlas_task IS a board agenda item. Idempotent — no
    duplicate while one is open."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT node_key FROM atlas.nodes WHERE "
            "node_key = 'task:sprawl-watch' AND status IN "
            "('open', 'queued')")
        if cur.fetchone():
            return "already on the board's agenda"
    title = ("SPRAWL WATCH TRIPPED: %s. Census: "
             "SPRAWL_CENSUS.md; snapshots: "
             "atlas.sprawl_snapshots. The board proposes; "
             "the chair disposes." % "; ".join(trips))
    here = os.path.dirname(os.path.abspath(__file__))
    proc = subprocess.run(
        [sys.executable, os.path.join(here, "atlas.py"),
         "task-add", "task:sprawl-watch", title,
         "--found-by", "sprawl-watch"],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return "task filing FAILED: %s" % proc.stderr.strip()
    return "filed as task:sprawl-watch (board agenda)"


def run():
    metrics, text = collect()
    with open(REPORT_PATH, "w") as f:
        f.write(text)
    conn = pg()
    try:
        record_snapshot(conn, metrics)
    finally:
        conn.close()
    return text


def watch():
    metrics, text = collect()
    with open(REPORT_PATH, "w") as f:
        f.write(text)
    conn = pg()
    try:
        base = get_baseline(conn)
        if base is None:
            record_snapshot(conn, metrics, is_baseline=True)
            print("BASELINE SET from this census: "
                  "docs %d, scripts %d, data %d, loose "
                  "cron scripts %d"
                  % (metrics["doc"], metrics["script"],
                     metrics["data"],
                     metrics["cron_loose_distinct"]))
            return 0
        record_snapshot(conn, metrics)
        trips = evaluate(metrics, base)
        if not trips:
            print("SPRAWL WITHIN LIMITS — docs %d, "
                  "scripts %d, data %d, loose cron "
                  "scripts %d (baseline %s)"
                  % (metrics["doc"], metrics["script"],
                     metrics["data"],
                     metrics["cron_loose_distinct"],
                     base["run_at"]))
            return 0
        print("SPRAWL TRIPPED %d line(s):" % len(trips))
        for t in trips:
            print("- " + t)
        print(file_board_item(conn, trips, metrics))
        return 0
    finally:
        conn.close()


def selftest():
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    check(classify("a/b/notes.md") == "doc",
          "markdown classifies as doc")
    check(classify("x.py") == "script"
          and classify("x.sh") == "script",
          "code files classify as script")
    check(classify("f.html") == "fragment",
          "html classifies as fragment")
    check(classify("d.csv") == "data",
          "csv classifies as data")
    with tempfile.TemporaryDirectory() as td:
        os.mkdir(os.path.join(td, ".git"))
        check(under_repo(os.path.join(td, "a.py"), [td]),
              "files under a repo root are sanctioned")
        check(not under_repo("/etc/passwd", [td]),
              "files outside are loose")
    base = {"doc": 1000, "script": 4000, "data": 1000,
            "cron_loose_distinct": 13}
    calm = {"doc": 1050, "script": 4100, "data": 1200,
            "cron_loose_distinct": 13}
    check(evaluate(calm, base) == [],
          "watch: growth inside the limits stays calm")
    hot = {"doc": 1150, "script": 4100, "data": 1200,
           "cron_loose_distinct": 14}
    trips = evaluate(hot, base)
    check(len(trips) == 2,
          "watch: doc growth + a new loose cron script "
          "trip exactly 2 lines (%s)" % trips)
    check(evaluate(calm, None) == [],
          "watch: no baseline, no trips (baseline pass "
          "sets it instead)")
    if failures:
        print("SELFTEST FAILED: %d" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "selftest":
        return selftest()
    if cmd == "run":
        print(run())
        return 0
    if cmd == "watch":
        return watch()
    print("usage: sprawl_census.py [run|watch|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
