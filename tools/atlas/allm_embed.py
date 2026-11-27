#!/usr/bin/env python3
"""allm_embed — the R32 embed helper.

R32 (Brian, 2026-10-23): documents belong in AnythingLLM.
Generated briefs and digests embed their canonical copy
in their owning workspace. embed_latest() uploads the new
edition and removes the previous edition of the same
filename from the workspace, so exactly ONE current copy
ever lives there — no pile-up of dated duplicates.

Used by scattered_brain.py (digest -> scattered-second-
brain) and deadline_radar.py (brief -> business-goals).
Failures raise; callers decide whether a failed embed is
fatal (generators treat it as a warning — the brief still
exists locally, and the next run retries).
"""

import json
import os
import re
import sqlite3
import sys
import urllib.request
import uuid

ALLM_DB = os.path.expanduser(
    "~/anything-llm/server/storage/anythingllm.db")
ENV = os.path.expanduser("~/successbrian-os/.env")
BASE = "http://127.0.0.1:3000"


def _key():
    with open(ENV) as f:
        for ln in f:
            if ln.startswith("ANYTHINGLLM_API_KEY="):
                return ln.split("=", 1)[1].strip()
    return None


def _old_locations(slug, filename):
    # AnythingLLM stores an upload as "<filename>-<uuid>.json";
    # update-embeddings deletes by docpath (the location the
    # upload returned), NOT by docId. Learned live
    # 2026-10-23: passing docIds silently deletes nothing.
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB,
                         uri=True)
    try:
        rows = db.execute(
            "SELECT wd.docpath FROM workspace_documents wd "
            "JOIN workspaces w ON w.id = wd.workspaceId "
            "WHERE w.slug = ? AND (wd.filename = ? OR "
            "wd.filename LIKE ?)",
            (slug, filename, filename + "-%")).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def _post(path, payload, key, timeout=60):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def register_catalog(slug, filename, title=None):
    """EMBED AND INDEX ARE ONE ACT (2026-11-09 clerk filing-flow
    repair, Intel Bridge order 'fix all leaks'): every document
    embedded through the fleet's paths is also registered in the
    master index (successbrian_os.knowledge_index) as a catalog
    row (kind 'embedded-doc'), so no embedded document is
    invisible to the index or to the Agent Knowledge Gateway.

    A catalog row asserts EXISTENCE + LOCATION only. Curated
    registrations (kindex.register with a real subject -- the
    clerk's WF3 filings, doctrine docs) remain the knowledge
    items and carry the full reconcile checks; reconcile treats
    catalog rows as existence checks only. Lazy import: kindex
    imports this module. Guarded: returns the canonical id or
    None; a failure is LOUD on stderr but never breaks the
    embed -- the daily QA check counts unindexed documents, so
    a miss cannot hide."""
    try:
        sys.path.insert(
            0, os.path.expanduser('~/successbrian-os/board'))
        import kindex as _kx
        _subj = 'doc:%s/%s' % (slug, filename)
        # Canonical ids are slugified (mint_id): two distinct
        # documents can slugify to the same id ('ECOSYSTEM-SOP'
        # vs 'ecosystem-sop', 'AGENTS.md' vs 'agents-md'). If
        # the id is already owned by a DIFFERENT (workspace,
        # filename), disambiguate deterministically so both
        # documents keep a row.
        _cid = _kx.mint_id(_subj)
        _c = _kx.conn()
        try:
            _ex = _kx.get_item(_c, _cid)
        finally:
            _c.close()
        if _ex and (_ex['allm_workspace'], _ex['allm_filename']) \
                != (slug, filename):
            import hashlib as _hl
            _subj += ' [%s]' % _hl.sha1(
                ('%s/%s' % (slug, filename)).encode()
            ).hexdigest()[:6]
        return _kx.register(
            subject=_subj,
            title=title or filename, kind='embedded-doc',
            workspace=slug, filename=filename,
            pointer_note='catalog registration: existence/'
                         'location row written by the embed '
                         'path (2026-11-09 filing-flow repair)')
    except Exception as e:
        print('[allm_embed] CATALOG REGISTRATION FAILED for '
              '%s/%s: %s: %s'
              % (slug, filename, type(e).__name__, e),
              file=sys.stderr)
        return None

MIN_EMBED_WORDS = 3


def _require_embeddable(slug, filename, text):
    """B25 (2026-11-26): refuse blank editions BEFORE anything is
    uploaded or deleted. AnythingLLM's update-embeddings deletes
    the old rows FIRST, then adds the new edition; a blank /
    whitespace-only edition fails to vectorize, so the add creates
    no row and the workspace silently LOSES the document (rolodex
    charter + heartbeat, 2026-11-25 06:29: blank uploads, old rows
    deleted, no new rows; check 503 failed at its next run).
    A refused embed raises here, the old edition stays put, and
    the caller retries with real text. The threshold is words,
    not characters: a real brief always has words; a blank
    template render has none."""
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    if len(words) < MIN_EMBED_WORDS:
        raise ValueError(
            "refusing blank embed: %s/%s has %d words "
            "(minimum %d) -- old edition left in place"
            % (slug, filename, len(words), MIN_EMBED_WORDS))


def embed_latest(slug, filename, text):
    """Upload text as filename into slug's workspace,
    replacing any prior edition. Returns the new
    document location."""
    _require_embeddable(slug, filename, text)
    key = _key()
    if not key:
        raise RuntimeError("no ANYTHINGLLM_API_KEY in .env")
    olds = _old_locations(slug, filename)
    boundary = "----embed" + uuid.uuid4().hex
    body = (
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; "
        "filename=\"%s\"\r\nContent-Type: text/markdown\r\n\r\n"
        "%s\r\n--%s--\r\n" % (boundary, filename, text, boundary)
    ).encode()
    req = urllib.request.Request(
        BASE + "/api/v1/document/upload", data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "multipart/form-data; "
                 "boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    loc = payload["documents"][0]["location"]
    _post("/api/v1/workspace/%s/update-embeddings" % slug,
          {"adds": [loc], "deletes": olds}, key)
    _title = None
    for _ln in (text or '').splitlines():
        if _ln.startswith('# '):
            _title = _ln[2:].strip()[:200]
            break
    register_catalog(slug, filename, _title)
    return loc


def _selftest():
    checks = []

    def _check(name, ok):
        checks.append((name, bool(ok)))
        print(("PASS " if ok else "FAIL ") + name)

    for label, text in [("empty", ""),
                        ("whitespace", "   \n\n  \n"),
                        ("newlines-24", "\n" * 24),
                        ("two-words", "hello world"),
                        ("placeholder-only-word",
                         "HEARTBEAT_EMPTY_PLACEHOLDER")]:
        # The placeholder is 3 words -> allowed (it vectorizes,
        # the row survives); the rest must be refused.
        try:
            _require_embeddable("probe-slug", "probe.md", text)
            allowed = True
        except ValueError:
            allowed = False
        want = (label == "placeholder-only-word")
        _check("guard %s: %s" % (
            label, "allowed" if want else "refused"),
            allowed == want)
    try:
        _require_embeddable("probe-slug", "probe.md",
                            "# Title\nSome real content here.\n")
        _check("guard real text: allowed", True)
    except ValueError:
        _check("guard real text: allowed", False)
    ok = all(o for _, o in checks)
    print("ALLM_EMBED_OK" if ok else "ALLM_EMBED_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    if len(sys.argv) == 4:
        print(embed_latest(sys.argv[1], sys.argv[2],
                           open(sys.argv[3]).read()))
    else:
        print("usage: allm_embed.py <slug> <filename> <path>")
        print("       allm_embed.py --selftest")
