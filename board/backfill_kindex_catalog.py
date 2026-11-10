#!/usr/bin/env python3
"""Backfill the master index's catalog for embedded documents.

Leak 2 of the 2026-11-09 clerk filing-flow repair ("docs embedded
directly get NO knowledge_index row"): documents embedded before
the embed-and-index-one-act fix -- or through paths that never
registered -- have no row in successbrian_os.knowledge_index, so
the master index and the Agent Knowledge Gateway cannot see them.

For every (workspace, base filename) pair present in AnythingLLM
and lacking ANY knowledge_index row, register a catalog row
(kind 'embedded-doc') via kindex.register -- the same row shape
allm_embed.register_catalog writes from the embed path.
Idempotent: pairs already covered (curated OR catalog) are
skipped, and register() upserts by canonical id.

Usage:
    python3 backfill_kindex_catalog.py            # dry run
    python3 backfill_kindex_catalog.py --apply
"""

import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))

ALLM_DB = os.path.expanduser(
    "~/anything-llm/server/storage/anythingllm.db")
DOC_ROOTS = [
    os.path.expanduser("~/anything-llm/storage/documents"),
    os.path.expanduser("~/anything-llm/server/storage/documents"),
]
SUFFIX_RE = re.compile(
    r"(-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{12}|-[0-9a-f]{8,64})\.json$")
BARE_HEX_RE = re.compile(r"-[0-9a-f]{8,64}$")


def base_filename(filename):
    # AnythingLLM's generated forms carry a hash suffix before
    # '.json' ('name.md-<uuid>.json', 'name-<16hex>.json'):
    # strip both, leaving the name the machinery registers and
    # allm_doc matches by 'name-%'. A filename with NO hash
    # suffix ('rural-freeze-prep-v1.json', 'plain-name.md') is
    # registered exactly as stored.
    b = SUFFIX_RE.sub("", filename)
    if b != filename:
        return b
    if BARE_HEX_RE.search(filename) and not filename.endswith(
            (".md", ".txt", ".json")):
        return BARE_HEX_RE.sub("", filename)
    return filename


def doc_title(docpath, fallback):
    for root in DOC_ROOTS:
        p = os.path.join(root, docpath)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8",
                          errors="replace") as f:
                    d = json.load(f)
                pc = d.get("pageContent") or ""
                for ln in pc.splitlines():
                    if ln.startswith("# "):
                        return ln[2:].strip()[:200]
                if d.get("title"):
                    return str(d["title"])[:200]
            except Exception:
                pass
            break
    return fallback


def main():
    apply_mode = "--apply" in sys.argv
    import kindex
    _c = kindex.conn()
    _cur = _c.cursor()
    covered = set()
    _cur.execute(
        "SELECT allm_workspace, allm_filename FROM "
        "successbrian_os.knowledge_index WHERE "
        "allm_filename IS NOT NULL AND allm_workspace "
        "IS NOT NULL")
    for ws, fn in _cur.fetchall():
        covered.add((ws, fn))
    _c.close()
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    pairs = {}
    for slug, filename, docpath in db.execute(
            "SELECT w.slug, wd.filename, wd.docpath FROM "
            "workspace_documents wd JOIN workspaces w ON "
            "w.id = wd.workspaceId"):
        pairs.setdefault((slug, base_filename(filename)), docpath)
    db.close()
    todo = [(k, v) for k, v in sorted(pairs.items())
            if k not in covered]
    print("embedded (workspace, base) pairs: %d" % len(pairs))
    print("already covered by an index row: %d"
          % (len(pairs) - len(todo)))
    print("uncovered -> catalog rows to write: %d" % len(todo))
    if not apply_mode:
        for (slug, base), _dp in todo[:10]:
            print("  WOULD REGISTER %s / %s" % (slug, base))
        print("DRY RUN — pass --apply to write.")
        return 0
    # Canonical-id ownership map (slugify collisions: see
    # allm_embed.register_catalog). Loaded once; updated as
    # rows are written so collisions inside this run also
    # disambiguate deterministically.
    import hashlib
    owners = {}
    _c2 = kindex.conn()
    _cur2 = _c2.cursor()
    _cur2.execute(
        "SELECT canonical_id, allm_workspace, allm_filename "
        "FROM successbrian_os.knowledge_index WHERE "
        "allm_filename IS NOT NULL")
    for _cid, _ws, _fn in _cur2.fetchall():
        owners[_cid] = (_ws, _fn)
    _c2.close()
    done = 0
    for (slug, base), docpath in todo:
        _subj = "doc:%s/%s" % (slug, base)
        _cid = kindex.mint_id(_subj)
        if _cid in owners and owners[_cid] != (slug, base):
            _subj += " [%s]" % hashlib.sha1(
                ("%s/%s" % (slug, base)).encode()
            ).hexdigest()[:6]
            _cid = kindex.mint_id(_subj)
        owners[_cid] = (slug, base)
        kindex.register(
            subject=_subj,
            title=doc_title(docpath, base), kind="embedded-doc",
            workspace=slug, filename=base,
            pointer_note="catalog backfill: existence/location "
                         "row for a document embedded before "
                         "the embed-and-index fix (2026-11-09 "
                         "filing-flow repair)")
        done += 1
        if done % 500 == 0:
            print("  ... %d" % done)
    print("BACKFILLED %d catalog rows" % done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
