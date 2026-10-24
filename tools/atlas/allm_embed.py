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
import sqlite3
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


def embed_latest(slug, filename, text):
    """Upload text as filename into slug's workspace,
    replacing any prior edition. Returns the new
    document location."""
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
    return loc


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4:
        print(embed_latest(sys.argv[1], sys.argv[2],
                           open(sys.argv[3]).read()))
    else:
        print("usage: allm_embed.py <slug> <filename> <path>")
