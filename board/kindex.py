#!/usr/bin/env python3
"""kindex — the Knowledge Index machinery (Brian's rulings, 2026-10-25).

Implements the integration series (Intel Bridge captures #171–175,
as amended #177–179 and #182):

  * THE MASTER INDEX (successbrian_os.knowledge_index): PostgreSQL
    says what knowledge items exist, which version is current, and
    which have been superseded. Every item has ONE CANONICAL ID
    (ki:<subject-slug>), minted here, carried by the item's
    AnythingLLM document and its second-brain row. Matching across
    stores is by ID, never by title similarity.
  * RECONCILIATION (the clerk's `reconcile` job): ticket FIRST for
    every mismatch, then verify in-house, then FIX — but only the
    fix types a written SOP covers (SOP_FIXES below; anything else
    defaults to ticket / research request / board packet). A fix
    that may change or affect policy is HELD and sent to the board
    as a packet (Workflow #1). What cannot be verified becomes a
    filed RESEARCH REQUEST (Workflow #2). RECURRENCE TRIGGER: the
    third occurrence of the same mismatch kind packets the PATTERN
    to the board as an SOP question, tickets attached as evidence.
  * INTEGRITY (the clerk's `integrity` job): the plumbing watched —
    AnythingLLM registered documents whose content files are
    missing at their recorded paths; second-brain sink landing
    (expected vs landed); canonical-ID carriers present.

SOP-COVERED FIX TYPES (v1, enumerated 2026-10-25 — conservative):
  SOP-FIX-1 restore_missing_doc : index item is current, its
      AnythingLLM document is unregistered or its file is missing,
      and the index holds the document text -> re-embed it.
  SOP-FIX-2 stamp_superseded    : index item is superseded but the
      served document carries no SUPERSEDED stamp -> re-embed the
      same text with the stamp + current-truth pointer prepended.
  SOP-FIX-3 restore_id_link     : a store copy exists but does not
      carry the canonical ID -> restore the carrier (document: the
      same text with the ID line prepended; brain row: append the
      ID to its tags).
  SOP-FIX-4 restore_missing_brain : index item is current, holds a
      distilled text, and its second-brain row is missing -> write
      the row through the proper sink (tools/second_brain.py).
Everything else is NOT fixed by the clerk: it stays a ticket, a
research request, or a board packet. That default is the ruling,
not an oversight.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))
import pm_core  # noqa: E402
import allm_embed  # noqa: E402

ALLM_DB = os.path.expanduser("~/anything-llm/server/storage/anythingllm.db")
# AnythingLLM's files live under TWO roots on this box (the running
# server's storage/ and the server/storage/ the DB sits in) — a
# document counts as present if its file exists under either.
ALLM_DOC_ROOTS = [
    os.path.expanduser("~/anything-llm/storage/documents"),
    os.path.expanduser("~/anything-llm/server/storage/documents"),
]


def _doc_file(docpath):
    for root in ALLM_DOC_ROOTS:
        p = os.path.join(root, docpath)
        if os.path.exists(p):
            return p
    return None
ATLAS_PY = os.path.expanduser("~/successbrian-os/tools/atlas/atlas.py")
SECOND_BRAIN_PY = os.path.expanduser("~/successbrian-os/tools/second_brain.py")
BRAIN_BUILD_SOURCE = "knowledge-integration-build-2026-10-25"
ID_LINE = "Canonical ID: {cid} (master index: PostgreSQL successbrian_os.knowledge_index)"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS successbrian_os.knowledge_index (
        canonical_id TEXT PRIMARY KEY,
        subject TEXT NOT NULL,
        title TEXT,
        kind TEXT,
        status TEXT NOT NULL DEFAULT 'current',
        version INT NOT NULL DEFAULT 1,
        allm_workspace TEXT,
        allm_filename TEXT,
        brain_topic TEXT,
        source_capture_id INT,
        distilled TEXT,
        doc_text TEXT,
        pointer_note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS successbrian_os.knowledge_tickets (
        id SERIAL PRIMARY KEY,
        canonical_id TEXT,
        kind TEXT NOT NULL,
        subject TEXT,
        detail TEXT,
        owner TEXT NOT NULL DEFAULT 'clerk-reconcile',
        status TEXT NOT NULL DEFAULT 'open',
        raised_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        resolved_at TIMESTAMPTZ,
        resolution_note TEXT
    )""",
]


def conn():
    return pm_core.conn()


def ensure_schema(c=None):
    own = c is None
    c = c or conn()
    cur = c.cursor()
    for stmt in SCHEMA:
        cur.execute(stmt)
    c.commit()
    if own:
        c.close()


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "item"


def mint_id(subject):
    return "ki:" + slugify(subject)


def register(subject, title=None, kind=None, status="current",
             workspace=None, filename=None, brain_topic=None,
             source_capture_id=None, distilled=None, doc_text=None,
             pointer_note=None, c=None):
    """Index-first registration: mint the canonical ID and create (or
    refresh) the index row. Idempotent per subject."""
    cid = mint_id(subject)
    own = c is None
    c = c or conn()
    cur = c.cursor()
    cur.execute(
        """INSERT INTO successbrian_os.knowledge_index
           (canonical_id, subject, title, kind, status, allm_workspace,
            allm_filename, brain_topic, source_capture_id, distilled,
            doc_text, pointer_note)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (canonical_id) DO UPDATE SET
             title = COALESCE(EXCLUDED.title, knowledge_index.title),
             kind = COALESCE(EXCLUDED.kind, knowledge_index.kind),
             allm_workspace = COALESCE(EXCLUDED.allm_workspace, knowledge_index.allm_workspace),
             allm_filename = COALESCE(EXCLUDED.allm_filename, knowledge_index.allm_filename),
             brain_topic = COALESCE(EXCLUDED.brain_topic, knowledge_index.brain_topic),
             source_capture_id = COALESCE(EXCLUDED.source_capture_id, knowledge_index.source_capture_id),
             distilled = COALESCE(EXCLUDED.distilled, knowledge_index.distilled),
             doc_text = COALESCE(EXCLUDED.doc_text, knowledge_index.doc_text),
             pointer_note = COALESCE(EXCLUDED.pointer_note, knowledge_index.pointer_note),
             updated_at = now()""",
        (cid, subject, title, kind, status, workspace, filename,
         brain_topic, source_capture_id, distilled, doc_text,
         pointer_note))
    c.commit()
    if own:
        c.close()
    return cid


def get_item(c, cid):
    cur = c.cursor()
    cur.execute(
        """SELECT canonical_id, subject, title, kind, status,
                  allm_workspace, allm_filename, brain_topic,
                  source_capture_id, distilled, doc_text, pointer_note
           FROM successbrian_os.knowledge_index WHERE canonical_id=%s""",
        (cid,))
    r = cur.fetchone()
    if not r:
        return None
    cols = ["canonical_id", "subject", "title", "kind", "status",
            "allm_workspace", "allm_filename", "brain_topic",
            "source_capture_id", "distilled", "doc_text",
            "pointer_note"]
    return dict(zip(cols, r))


def mark_superseded(cid, pointer_note=None, c=None):
    own = c is None
    c = c or conn()
    cur = c.cursor()
    cur.execute(
        """UPDATE successbrian_os.knowledge_index
           SET status='superseded',
               pointer_note=COALESCE(%s, pointer_note), updated_at=now()
           WHERE canonical_id=%s""", (pointer_note, cid))
    c.commit()
    if own:
        c.close()


# ------------------------------------------------------------------
# Tickets (flag state: kind, subject, owner, raised/resolved, note)
# ------------------------------------------------------------------

def open_ticket(c, cid, kind, subject, detail, owner="clerk-reconcile"):
    """Open a ticket unless an unresolved one already exists for the
    same item+kind. Returns (ticket_id, created)."""
    cur = c.cursor()
    cur.execute(
        """SELECT id FROM successbrian_os.knowledge_tickets
           WHERE kind=%s AND COALESCE(canonical_id,'')=COALESCE(%s,'')
             AND status IN ('open','held','requested')
           ORDER BY id LIMIT 1""", (kind, cid))
    r = cur.fetchone()
    if r:
        return r[0], False
    cur.execute(
        """INSERT INTO successbrian_os.knowledge_tickets
           (canonical_id, kind, subject, detail, owner)
           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
        (cid, kind, subject, detail, owner))
    tid = cur.fetchone()[0]
    c.commit()
    return tid, True


def set_ticket(c, tid, status, note=None):
    cur = c.cursor()
    cur.execute(
        """UPDATE successbrian_os.knowledge_tickets
           SET status=%s, resolution_note=COALESCE(%s, resolution_note),
               resolved_at=CASE WHEN %s IN ('fixed','closed')
                                THEN now() ELSE resolved_at END
           WHERE id=%s""", (status, note, status, tid))
    c.commit()


def kind_count(c, kind):
    cur = c.cursor()
    cur.execute(
        "SELECT count(*) FROM successbrian_os.knowledge_tickets WHERE kind=%s",
        (kind,))
    return cur.fetchone()[0]


# ------------------------------------------------------------------
# Store readers
# ------------------------------------------------------------------

def allm_doc(workspace_slug, filename):
    """Return (registered, file_present, text)."""
    if not workspace_slug or not filename:
        return (False, False, None)
    db = sqlite3.connect(ALLM_DB)
    try:
        cur = db.cursor()
        cur.execute("SELECT id FROM workspaces WHERE slug=?",
                    (workspace_slug,))
        row = cur.fetchone()
        if not row:
            return (False, False, None)
        cur.execute(
            "SELECT docpath FROM workspace_documents "
            "WHERE workspaceId=? AND (filename=? OR filename LIKE ?)",
            (row[0], filename, filename + "-%"))
        rows = cur.fetchall()
    finally:
        db.close()
    if not rows:
        return (False, False, None)
    for (docpath,) in rows:
        p = _doc_file(docpath)
        if p:
            try:
                with open(p) as f:
                    text = json.load(f).get("pageContent", "") or ""
            except Exception:
                text = ""
            return (True, True, text)
    return (True, False, None)


def brain_row(c, topic):
    cur = c.cursor()
    cur.execute(
        "SELECT topic, tags, content FROM altair.second_brain "
        "WHERE topic=%s ORDER BY updated_at DESC LIMIT 1", (topic,))
    r = cur.fetchone()
    if not r:
        return None
    return {"topic": r[0], "tags": r[1] or [], "content": r[2] or ""}


def node_exists(c, key):
    cur = c.cursor()
    cur.execute("SELECT 1 FROM atlas.nodes WHERE node_key=%s", (key,))
    return cur.fetchone() is not None


def atlas_task(c, key, title, details):
    """File an atlas task node idempotently (Workflow #1/#2 surface)."""
    if node_exists(c, key):
        return key
    r = subprocess.run(
        ["python3", ATLAS_PY, "add-node", key, "atlas_task", title,
         "--status", "queued", "--details", json.dumps(details)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"add-node {key} failed: {r.stderr[:300]}")
    return key


# ------------------------------------------------------------------
# SOP-covered fixes
# ------------------------------------------------------------------

SOP_FIXES = {
    "restore_missing_doc": "SOP-FIX-1",
    "stamp_superseded": "SOP-FIX-2",
    "restore_id_link": "SOP-FIX-3",
    "restore_missing_brain": "SOP-FIX-4",
}


def _fix_restore_doc(item):
    allm_embed.embed_latest(item["allm_workspace"],
                            item["allm_filename"], item["doc_text"])
    reg, present, _ = allm_doc(item["allm_workspace"],
                               item["allm_filename"])
    return reg and present


def _fix_stamp_superseded(item, text):
    banner = ("# ⚠ SUPERSEDED — kept for history, do not use as current\n\n"
              f"Canonical ID: {item['canonical_id']} — the master index "
              "(PostgreSQL) marks this item SUPERSEDED.\n"
              f"Current truth: {item['pointer_note'] or 'see the master index'}\n\n"
              "---\n\n")
    allm_embed.embed_latest(item["allm_workspace"],
                            item["allm_filename"], banner + (text or ""))
    _, _, new_text = allm_doc(item["allm_workspace"],
                              item["allm_filename"])
    return bool(new_text) and "SUPERSEDED" in new_text


def _fix_doc_id_link(item, text):
    new = ID_LINE.format(cid=item["canonical_id"]) + "\n\n" + (text or "")
    allm_embed.embed_latest(item["allm_workspace"],
                            item["allm_filename"], new)
    _, _, t = allm_doc(item["allm_workspace"], item["allm_filename"])
    return bool(t) and item["canonical_id"] in t


def _fix_brain(item, via_link_only=False, c=None):
    if via_link_only:
        cur = c.cursor()
        cur.execute(
            """UPDATE altair.second_brain
               SET tags = CASE WHEN %s = ANY(tags) THEN tags
                               ELSE tags || %s END, updated_at=now()
               WHERE topic=%s""",
            (item["canonical_id"], item["canonical_id"],
             item["brain_topic"]))
        c.commit()
        row = brain_row(c, item["brain_topic"])
        return bool(row) and item["canonical_id"] in (row["tags"] or [])
    r = subprocess.run(
        ["python3", SECOND_BRAIN_PY, "--topic", item["brain_topic"],
         "--content", item["distilled"], "--category", "doctrine",
         "--confidence", "high", "--source", BRAIN_BUILD_SOURCE,
         "--verification", "brian-ruling",
         "--tags", item["canonical_id"] + ",knowledge-index"],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"second_brain.py failed: {r.stderr[:300]}")
    row = brain_row(c, item["brain_topic"])
    return bool(row)


# ------------------------------------------------------------------
# Reconcile
# ------------------------------------------------------------------

def _maybe_pattern_packet(c, kind, dry_run=False):
    """Recurrence trigger (#182): the third occurrence of a kind
    packets the pattern to the board as an SOP question."""
    total = kind_count(c, kind)
    key = f"task:reconcile-sop-pattern-{slugify(kind)}"
    if total < 3 or node_exists(c, key):
        return None
    cur = c.cursor()
    cur.execute(
        """SELECT id, subject, detail FROM successbrian_os.knowledge_tickets
           WHERE kind=%s ORDER BY id LIMIT 10""", (kind,))
    rows = cur.fetchall()
    evidence = "\n".join(f"- ticket #{r[0]} ({r[1]}): {(r[2] or '')[:200]}"
                         for r in rows)
    details = {
        "question": (
            f"SOP QUESTION from the clerk's reconciliation: the "
            f"mismatch kind '{kind}' has now occurred {total} times. "
            f"Per the recurrence trigger, the pattern — not just the "
            f"instance — goes to the board: this keeps happening; "
            f"maybe the rule itself needs fixing.\n\nEVIDENCE "
            f"(tickets):\n{evidence}"),
        "theme": "reconcile-sop-pattern",
        "found_by": "clerk-reconcile",
    }
    if dry_run:
        print(f"[dry-run] would file SOP pattern packet {key}")
        return key
    return atlas_task(c, key,
                      f"SOP pattern: '{kind}' has occurred {total} times",
                      details)


def reconcile(dry_run=False, log=print):
    ensure_schema()
    c = conn()
    summary = {"items": 0, "tickets_opened": 0, "tickets_existing": 0,
               "fixed": 0, "held": 0, "requested": 0, "ok": 0}
    cur = c.cursor()
    cur.execute("SELECT canonical_id FROM successbrian_os.knowledge_index "
                "ORDER BY canonical_id")
    cids = [r[0] for r in cur.fetchall()]
    for cid in cids:
        item = get_item(c, cid)
        summary["items"] += 1
        problems = []
        # --- document side ---
        if item["allm_filename"]:
            reg, present, text = allm_doc(item["allm_workspace"],
                                          item["allm_filename"])
            if not reg or not present:
                problems.append(("missing_doc",
                                  "document unregistered or file missing "
                                  f"({item['allm_workspace']}/{item['allm_filename']})"))
            elif item["status"] == "superseded" and "SUPERSEDED" not in text:
                problems.append(("superseded_served",
                                 "superseded item still served without a stamp"))
            elif item["status"] == "current" and "SUPERSEDED" in text[:400]:
                problems.append(("contradiction",
                                 "index says current but the document carries "
                                 "a SUPERSEDED stamp — cannot settle mechanically"))
            elif cid not in text:
                problems.append(("unlinked_doc",
                                 "document does not carry the canonical ID"))
        # --- brain side ---
        if item["brain_topic"]:
            row = brain_row(c, item["brain_topic"])
            if row is None:
                problems.append(("missing_brain",
                                 f"second-brain row '{item['brain_topic']}' missing"))
            elif cid not in (row["tags"] or []):
                problems.append(("unlinked_brain",
                                 "second-brain row does not carry the canonical ID in tags"))
        if not problems:
            summary["ok"] += 1
            cur.execute(
                """SELECT id, kind FROM successbrian_os.knowledge_tickets
                   WHERE canonical_id=%s AND status IN
                     ('open','held','requested')""", (cid,))
            for tid_, kind_ in cur.fetchall():
                if not dry_run:
                    set_ticket(c, tid_, "fixed",
                               "verified resolved on re-check: the "
                               "mismatch is no longer detected")
                    summary["fixed"] += 1
            continue
        for kind, detail in problems:
            if dry_run:
                log(f"[dry-run] {cid}: {kind} — {detail}")
                summary["tickets_opened"] += 1
                continue
            tid, created = open_ticket(c, cid, kind, item["subject"],
                                       detail)
            if created:
                summary["tickets_opened"] += 1
                _maybe_pattern_packet(c, kind)
            else:
                summary["tickets_existing"] += 1
            # --- disposition ---
            note = None
            try:
                if kind == "missing_doc" and item["doc_text"]:
                    if _fix_restore_doc(item):
                        set_ticket(c, tid, "fixed",
                                   "SOP-FIX-1: re-embedded the current "
                                   "document from the index copy; verified present.")
                        summary["fixed"] += 1
                        continue
                elif kind == "superseded_served":
                    _, _, text = allm_doc(item["allm_workspace"],
                                          item["allm_filename"])
                    if _fix_stamp_superseded(item, text):
                        set_ticket(c, tid, "fixed",
                                   "SOP-FIX-2: SUPERSEDED stamp + pointer "
                                   "prepended; verified in the served document.")
                        summary["fixed"] += 1
                        continue
                elif kind == "unlinked_doc":
                    _, _, text = allm_doc(item["allm_workspace"],
                                          item["allm_filename"])
                    if _fix_doc_id_link(item, text):
                        set_ticket(c, tid, "fixed",
                                   "SOP-FIX-3: canonical ID line restored "
                                   "at the head of the document.")
                        summary["fixed"] += 1
                        continue
                elif kind == "unlinked_brain":
                    if _fix_brain(item, via_link_only=True, c=c):
                        set_ticket(c, tid, "fixed",
                                   "SOP-FIX-3: canonical ID appended to "
                                   "the brain row's tags.")
                        summary["fixed"] += 1
                        continue
                elif kind == "missing_brain" and item["distilled"]:
                    if _fix_brain(item, c=c):
                        set_ticket(c, tid, "fixed",
                                   "SOP-FIX-4: distilled row written "
                                   "through tools/second_brain.py.")
                        summary["fixed"] += 1
                        continue
            except Exception as e:  # fix failed: ticket stays open
                note = f"fix attempt failed: {type(e).__name__}: {e}"
            if kind == "contradiction":
                key = f"task:reconcile-research-{tid}"
                atlas_task(c, key,
                           f"Research request: settle contradiction for {item['subject']}",
                           {"question": (
                               f"Reconciliation ticket #{tid}: {detail}. "
                               f"Item {cid} ('{item['title']}'). The clerk "
                               f"cannot verify which side is true from the "
                               f"house record. Research what settles it, "
                               f"then the fix follows verification."),
                            "theme": "reconcile-research",
                            "found_by": "clerk-reconcile"})
                set_ticket(c, tid, "requested",
                           note or "research request filed (contradiction "
                                   "cannot be settled mechanically)")
                summary["requested"] += 1
            else:
                set_ticket(c, tid, "open",
                           note or "no SOP-covered fix applies yet; "
                                   "ticket stands for an owner")
    c.close()
    log(f"RECONCILE {'(dry-run) ' if dry_run else ''}done: {summary}")
    return summary


# ------------------------------------------------------------------
# Integrity
# ------------------------------------------------------------------

def integrity(dry_run=False, log=print):
    ensure_schema()
    c = conn()
    db = sqlite3.connect(ALLM_DB)
    cur = db.cursor()
    cur.execute(
        """SELECT w.slug, wd.filename, wd.docpath
           FROM workspace_documents wd JOIN workspaces w
             ON w.id = wd.workspaceId""")
    rows = cur.fetchall()
    db.close()
    missing = []
    for slug, filename, docpath in rows:
        if _doc_file(docpath) is None:
            missing.append((slug, filename))
    opened = 0
    for slug, filename in missing:
        if dry_run:
            log(f"[dry-run] missing file: {slug}/{filename}")
            continue
        _, created = open_ticket(
            c, None, "missing_file", f"{slug}/{filename}",
            "AnythingLLM registers this document but its content file "
            "is missing at the recorded path.", owner="lyra")
        opened += 1 if created else 0
    cur2 = c.cursor()
    cur2.execute(
        "SELECT count(*) FROM successbrian_os.knowledge_index "
        "WHERE brain_topic IS NOT NULL")
    expected_brain = cur2.fetchone()[0]
    cur2.execute(
        """SELECT count(*) FROM successbrian_os.knowledge_index i
           WHERE i.brain_topic IS NOT NULL AND EXISTS
             (SELECT 1 FROM altair.second_brain b
              WHERE b.topic = i.brain_topic)""")
    landed_brain = cur2.fetchone()[0]
    c.close()
    log(f"INTEGRITY: allm_documents={len(rows)} missing_files={len(missing)} "
        f"missing_file_tickets_opened={opened} "
        f"brain_expected={expected_brain} brain_landed={landed_brain}")
    return {"documents": len(rows), "missing_files": len(missing),
            "tickets_opened": opened, "brain_expected": expected_brain,
            "brain_landed": landed_brain}


# ------------------------------------------------------------------
# Policy hold helper (used by repairs and future fix types)
# ------------------------------------------------------------------

def hold_for_board(c, item, fix_description, dry_run=False):
    """A fix that may change or affect policy is HELD and sent to
    the board as a packet instead of being applied (#179)."""
    tid, _ = open_ticket(c, item["canonical_id"], "policy_hold",
                         item["subject"],
                         f"held fix: {fix_description}")
    key = f"task:reconcile-policy-packet-{tid}"
    details = {
        "question": (
            f"POLICY HOLD from clerk reconciliation (ticket #{tid}). "
            f"Item {item['canonical_id']} ('{item['title']}').\n\n"
            f"Prepared fix (NOT applied): {fix_description}\n\n"
            f"The fix may change or affect policy, so per the ruling "
            f"it goes to the board for review instead of being "
            f"applied by the clerk."),
        "theme": "reconcile-policy-hold",
        "found_by": "clerk-reconcile",
    }
    if not dry_run:
        atlas_task(c, key,
                   f"Policy hold: fix for {item['subject']} needs board review",
                   details)
        set_ticket(c, tid, "held", "fix held; board packet filed")
    return key


# ------------------------------------------------------------------
# Selftest + CLI
# ------------------------------------------------------------------

def selftest():
    ensure_schema()
    c = conn()
    subj = "__kindex_selftest__"
    cid1 = register(subj, title="selftest", kind="test", c=c)
    cid2 = register(subj, title="selftest", kind="test", c=c)
    assert cid1 == cid2 == "ki:kindex-selftest", cid1
    cur = c.cursor()
    cur.execute("SELECT count(*) FROM successbrian_os.knowledge_index "
                "WHERE canonical_id=%s", (cid1,))
    assert cur.fetchone()[0] == 1
    t1, created1 = open_ticket(c, cid1, "missing_doc", subj, "test")
    t2, created2 = open_ticket(c, cid1, "missing_doc", subj, "test")
    assert created1 and not created2 and t1 == t2
    set_ticket(c, t1, "fixed", "selftest resolution")
    mark_superseded(cid1, "selftest pointer", c=c)
    item = get_item(c, cid1)
    assert item["status"] == "superseded"
    cur.execute("DELETE FROM successbrian_os.knowledge_tickets "
                "WHERE canonical_id=%s", (cid1,))
    cur.execute("DELETE FROM successbrian_os.knowledge_index "
                "WHERE canonical_id=%s", (cid1,))
    c.commit()
    c.close()
    print("KINDEX_SELFTEST_OK")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: kindex.py selftest|reconcile [--dry-run]|"
              "integrity [--dry-run]")
        return 2
    cmd = argv[0]
    dry = "--dry-run" in argv
    if cmd == "selftest":
        selftest()
    elif cmd == "reconcile":
        reconcile(dry_run=dry)
    elif cmd == "integrity":
        integrity(dry_run=dry)
    else:
        print(f"unknown command {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
