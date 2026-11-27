#!/usr/bin/env python3
"""rolodex_workspace_guard — B25 (2026-11-26).

LOSS MECHANISM (diagnosed this cycle, Intel Bridge capture #3462):
AnythingLLM's /v1/workspace/:slug/update-embeddings deletes the
old rows FIRST, then adds the new edition; a blank/whitespace-only
edition fails to vectorize, so the add creates no row and the
workspace silently LOSES the document. Twice in ~2 weeks the
rolodex workspace lost docs this way (heartbeat 2026-11-19 17:57,
charter + heartbeat 2026-11-25 06:29 — blank uploads, old rows
deleted, no new rows; check 503 failed at its next run).
Event-log proof: anythingllm.db event_logs 300247-300252
(upload -> removed -> "added" for both docs; the "added" event
counts attempts, not landed rows).

GUARD (two layers):
  1. allm_embed.embed_latest refuses blank text BEFORE upload /
     delete, so no writer can feed the non-atomic replace a
     blank edition again (any workspace, not just rolodex).
  2. This watcher: counts the three named rolodex docs; a missing
     doc is re-embedded from its canonical source in
     ~/builds-in/rolodex/ (blank-guarded) and the repair logged,
     so a loss is caught within the hour instead of at the next
     daily check-503 run. Runs hourly from cron (--repair).

Usage:
  rolodex_workspace_guard.py --check     read-only; exit 0 iff 3/3
  rolodex_workspace_guard.py --repair    check + re-embed missing
  rolodex_workspace_guard.py --selftest  temp-DB probes, no live touch
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ALLM_DB = os.path.expanduser(
    "~/anything-llm/server/storage/anythingllm.db")
SRC_DIR = os.path.expanduser("~/builds-in/rolodex")
LOG_PATH = os.path.expanduser("~/logs/rolodex-guard.log")
SLUG = "rolodex"

# The three named docs check 503 counts. The work-order filename
# is dated; the charter/heartbeat names are stable.
NAMED = [
    "rolodex-charter.md",
    "meghan-ceo-rolodex-work-order-2026-11-09.md",
    "rolodex-heartbeat-latest.md",
]


def present(db_path=ALLM_DB):
    """filename -> row count in the rolodex workspace (read-only)."""
    db = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        out = {}
        for fn in NAMED:
            row = db.execute(
                "SELECT count(*) FROM workspace_documents wd "
                "JOIN workspaces w ON w.id = wd.workspaceId "
                "WHERE w.slug = ? AND (wd.filename = ? OR "
                "wd.filename LIKE ?)",
                (SLUG, fn, fn + "-%")).fetchone()
            out[fn] = row[0] if row else 0
        return out
    finally:
        db.close()


def _log(msg):
    ts = datetime.now(timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z")
    line = "%s %s\n" % (ts, msg)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass
    print(line, end="")


def repair(db_path=ALLM_DB, embed_fn=None, src_dir=SRC_DIR):
    """Re-embed each missing named doc from its canonical source.
    Returns (repaired, still_missing). embed_fn defaults to
    allm_embed.embed_latest (blank-guarded since B25)."""
    if embed_fn is None:
        import allm_embed
        embed_fn = allm_embed.embed_latest
    counts = present(db_path)
    missing = [fn for fn in NAMED if counts.get(fn, 0) == 0]
    repaired = []
    still = []
    for fn in missing:
        src = os.path.join(src_dir, fn)
        if not os.path.exists(src):
            _log("GUARD REPAIR SKIP %s: no canonical source %s"
                 % (fn, src))
            still.append(fn)
            continue
        try:
            text = open(src).read()
            embed_fn(SLUG, fn, text)
            repaired.append(fn)
            _log("GUARD REPAIRED %s from %s" % (fn, src))
        except Exception as exc:
            _log("GUARD REPAIR FAILED %s: %s" % (fn, exc))
            still.append(fn)
    return repaired, still


def _selftest():
    import tempfile
    checks = []

    def _check(name, ok):
        checks.append((name, bool(ok)))
        print(("PASS " if ok else "FAIL ") + name)

    # 1. present() against a temp DB with 1 of 3 docs.
    tmp = tempfile.mkdtemp(prefix="rolodex-guard-")
    db_path = os.path.join(tmp, "t.db")
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE workspaces (id INTEGER PRIMARY KEY, "
               "slug TEXT)")
    db.execute("CREATE TABLE workspace_documents (id INTEGER "
               "PRIMARY KEY, workspaceId INTEGER, filename TEXT, "
               "docpath TEXT)")
    db.execute("INSERT INTO workspaces VALUES (1, 'rolodex')")
    db.execute("INSERT INTO workspace_documents VALUES "
               "(1, 1, 'rolodex-charter.md-abc.json', "
               "'custom-documents/rolodex-charter.md-abc.json')")
    db.commit()
    db.close()
    counts = present(db_path)
    _check("present counts 1/3 on temp DB",
           counts.get("rolodex-charter.md") == 1
           and counts.get("rolodex-heartbeat-latest.md") == 0
           and counts.get(
               "meghan-ceo-rolodex-work-order-2026-11-09.md") == 0)

    # 2. repair() with a stub embed inserts the missing rows.
    def _stub_embed(slug, filename, text):
        assert slug == SLUG
        assert len(text.strip()) > 0
        d2 = sqlite3.connect(db_path)
        d2.execute(
            "INSERT INTO workspace_documents "
            "(workspaceId, filename, docpath) VALUES (1, ?, ?)",
            (filename + "-stub.json",
             "custom-documents/" + filename + "-stub.json"))
        d2.commit()
        d2.close()
        return "stub-loc"

    # Stub sources: temp dir with real-named non-blank files.
    src = os.path.join(tmp, "src")
    os.makedirs(src)
    for fn in NAMED:
        with open(os.path.join(src, fn), "w") as f:
            f.write("# %s\nReal guard selftest content.\n" % fn)
    repaired, still = repair(db_path, _stub_embed, src)
    _check("repair restores the 2 missing docs",
           sorted(repaired) == sorted([
               "meghan-ceo-rolodex-work-order-2026-11-09.md",
               "rolodex-heartbeat-latest.md"]) and not still)
    counts = present(db_path)
    _check("present counts 3/3 after stub repair",
           all(counts.get(fn, 0) >= 1 for fn in NAMED))

    # 3. Canonical sources on disk exist and are non-blank.
    import allm_embed
    ok_src = True
    for fn in NAMED:
        p = os.path.join(SRC_DIR, fn)
        if not os.path.exists(p):
            ok_src = False
            break
        try:
            allm_embed._require_embeddable(SLUG, fn, open(p).read())
        except ValueError:
            ok_src = False
            break
    _check("canonical sources exist and pass blank guard", ok_src)

    # 4. A blank source is refused by the repair path.
    with open(os.path.join(src, NAMED[0]), "w") as f:
        f.write("\n\n\n")
    try:
        allm_embed._require_embeddable(SLUG, NAMED[0], "\n\n\n")
        _check("blank source refused by guard", False)
    except ValueError:
        _check("blank source refused by guard", True)

    ok = all(o for _, o in checks)
    print("ROLODEX_GUARD_OK" if ok else "ROLODEX_GUARD_FAIL")
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    if "--repair" in argv:
        counts = present()
        n = sum(1 for fn in NAMED if counts.get(fn, 0) >= 1)
        if n == len(NAMED):
            print("ROLODEX_GUARD_OK 3/3 present, nothing to repair")
            return 0
        repaired, still = repair()
        counts = present()
        n = sum(1 for fn in NAMED if counts.get(fn, 0) >= 1)
        if n == len(NAMED):
            print("ROLODEX_GUARD_OK %d/3 after repair %s"
                  % (n, repaired))
            return 0
        print("ROLODEX_GUARD_FAIL %d/3 still missing %s"
              % (n, still))
        return 1
    # Default: --check (read-only).
    counts = present()
    n = sum(1 for fn in NAMED if counts.get(fn, 0) >= 1)
    missing = [fn for fn in NAMED if counts.get(fn, 0) == 0]
    if n == len(NAMED):
        print("ROLODEX_GUARD_OK 3/3 present")
        return 0
    print("ROLODEX_GUARD_MISSING %d/3 missing %s" % (n, missing))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
