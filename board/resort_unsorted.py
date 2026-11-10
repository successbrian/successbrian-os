#!/usr/bin/env python3
"""resort_unsorted — drain the unsorted tray through the improved
router (2026-11-09, clerk filing-flow repair; Brian: "fix all
leaks").

Every document sitting in the AnythingLLM `unsorted` workspace is
re-routed with allm_workspaces.route_subject() (determine()'s
ruled routes first, then subject extraction). A document MOVES
only on a clear route to a live workspace — moves, never deletes
(retention doctrine); the document's stored file is untouched,
only its workspace embedding changes (add to the new home first,
then remove from unsorted, so it is never unfiled).

Intel-capture documents route on their capture (title / context /
raw + the clerk's blog match); other documents route on their
stored title / first heading + content head.

Anything the router cannot place stays in unsorted and is
reported on the HELD LIST (filename, subject, best-guess
candidates) for Brian/Altair — never force-fit.

Usage:
    python3 resort_unsorted.py [--apply] [--limit N]
Dry-run by default. --apply performs the moves and updates the
bookkeeping (capture workspace_slug, wf3_filings home, master
index row) for capture documents.
"""

import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))

import allm_workspaces as allm          # noqa: E402
import allm_embed                       # noqa: E402
import pm_core                          # noqa: E402
import scatter_clerk                    # noqa: E402

ALLM_DB = os.path.expanduser("~/anything-llm/server/storage/anythingllm.db")
DOC_ROOTS = [
    os.path.expanduser("~/anything-llm/storage/documents"),
    os.path.expanduser("~/anything-llm/server/storage/documents"),
]
BACKUP_DIR = os.path.expanduser("~/backups/clerk-filing-repair-20261109")
CAP_RE = re.compile(r"^intel-capture-(\d+)\.md-[0-9a-f-]+\.json$")
BASE_RE = re.compile(r"-[0-9a-f]{8}[0-9a-f-]*\.json$")


def base_filename(filename):
    m = BASE_RE.search(filename or "")
    return filename[:m.start()] if m else (filename or "")


def doc_text(docpath):
    for root in DOC_ROOTS:
        p = os.path.join(root, docpath)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    d = json.load(f)
                return d.get("title") or "", d.get("pageContent") or ""
            except Exception:
                return "", ""
    return "", ""


def unsorted_docs():
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        rows = db.execute(
            "SELECT wd.id, wd.filename, wd.docpath FROM "
            "workspace_documents wd JOIN workspaces w "
            "ON w.id = wd.workspaceId WHERE w.slug = 'unsorted' "
            "ORDER BY wd.id").fetchall()
        homes = {}
        for slug, fn in db.execute(
                "SELECT w.slug, wd.filename FROM workspace_documents "
                "wd JOIN workspaces w ON w.id = wd.workspaceId"):
            homes.setdefault(slug, set()).add(base_filename(fn))
    finally:
        db.close()
    return rows, homes


def total_docs():
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        return db.execute(
            "SELECT count(*) FROM workspace_documents").fetchone()[0]
    finally:
        db.close()


def route_for(conn, filename, docpath):
    """Returns (verdict_dict, subject, capture_id_or_None)."""
    m = CAP_RE.match(filename or "")
    if m:
        cid = int(m.group(1))
        cap = scatter_clerk.fetch_capture(cid)
        if cap:
            subject = scatter_clerk._wf3_subject(cap["title"])
            blog_slug = None
            try:
                ctx = scatter_clerk.match_blog(cap)
                blog_slug = (ctx or {}).get("slug")
            except Exception:
                blog_slug = None
            d = allm.route_subject(
                conn, subject,
                extra_text=(cap["context"] or "") + "\n"
                           + (cap["raw"] or "")[:4000],
                blog_slug=blog_slug)
            return d, subject, cid
    title, content = doc_text(docpath)
    head = ""
    for line in (content or "").splitlines():
        if line.startswith("# "):
            head = line[2:].strip()
            break
    subject = head or title or base_filename(filename)
    d = allm.route_subject(conn, subject, extra_text=(content or "")[:4000])
    return d, subject, None


def move(key, docpath, target):
    allm_embed._post("/api/v1/workspace/%s/update-embeddings" % target,
                     {"adds": [docpath], "deletes": []}, key)
    allm_embed._post("/api/v1/workspace/unsorted/update-embeddings",
                     {"adds": [], "deletes": [docpath]}, key)


def verify_moved(docpath, target):
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        rows = db.execute(
            "SELECT w.slug FROM workspace_documents wd JOIN "
            "workspaces w ON w.id = wd.workspaceId "
            "WHERE wd.docpath = ?", (docpath,)).fetchall()
    finally:
        db.close()
    slugs = [r[0] for r in rows]
    return target in slugs and "unsorted" not in slugs


def bookkeep_capture(cid, target, filename):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE atlas.scattered_captures SET workspace_slug = %s "
        "WHERE id = %s AND workspace_slug = 'unsorted'", (target, cid))
    cur.execute(
        "UPDATE successbrian_os.wf3_filings SET workspace_slug = %s "
        "WHERE capture_id = %s AND workspace_slug = 'unsorted'",
        (target, cid))
    c.commit()
    c.close()
    try:
        import kindex as _kx
        _kx.register(subject="intel-capture-%d" % cid,
                     workspace=target, filename=base_filename(filename),
                     source_capture_id=cid)
    except Exception as e:
        print(f"  [kindex] refresh for capture #{cid} failed: {e}")


def main():
    apply_mode = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    conn = allm.pg()
    live = allm.live_workspaces()
    rows, homes = unsorted_docs()
    before_total = total_docs()
    print(f"unsorted docs: {len(rows)}; total embedded docs: {before_total}")
    if limit:
        rows = rows[:limit]
    key = allm_embed._key()
    moves, held, skipped_home = [], [], 0
    os.makedirs(BACKUP_DIR, exist_ok=True)
    logf = open(os.path.join(BACKUP_DIR, "moves.jsonl"), "a")
    for _id, filename, docpath in rows:
        d, subject, cid = route_for(conn, filename, docpath)
        target = d.get("workspace")
        base = base_filename(filename)
        if d["verdict"] == "intake" or not target or target == "unsorted" \
                or target not in live:
            held.append({"filename": filename, "subject": subject[:160],
                         "capture_id": cid,
                         "candidates": d.get("candidates", []),
                         "why": d.get("why", "")[:200]})
            continue
        if base in homes.get(target, set()):
            skipped_home += 1
            held.append({"filename": filename, "subject": subject[:160],
                         "capture_id": cid,
                         "candidates": d.get("candidates", []),
                         "why": f"router chose '{target}' but an edition "
                                f"of this filename already lives there — "
                                f"held as a duplicate edition"})
            continue
        rec = {"filename": filename, "from": "unsorted", "to": target,
               "subject": subject[:160], "capture_id": cid,
               "why": d.get("why", "")[:240]}
        if apply_mode:
            try:
                move(key, docpath, target)
                if not verify_moved(docpath, target):
                    rec["error"] = "post-move verification failed"
                    held.append(rec)
                    continue
                if cid:
                    bookkeep_capture(cid, target, filename)
                homes.setdefault(target, set()).add(base)
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"
                held.append(rec)
                continue
        moves.append(rec)
        logf.write(json.dumps(rec) + "\n")
        logf.flush()
        print(f"{'MOVED' if apply_mode else 'WOULD MOVE'}: "
              f"{filename[:60]} -> {target}  ({subject[:60]})")
    logf.close()
    with open(os.path.join(BACKUP_DIR, "held-list.json"), "w") as f:
        json.dump(held, f, indent=1)
    after_total = total_docs()
    live_after = allm.live_workspaces()
    print(f"\n{'APPLIED' if apply_mode else 'DRY-RUN'}: "
          f"{len(moves)} moves, {len(held)} held "
          f"({skipped_home} duplicate-edition holds)")
    print(f"total embedded docs: before {before_total} -> after {after_total}")
    print(f"unsorted now: {live_after.get('unsorted')}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
