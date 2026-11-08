#!/usr/bin/env python3
"""
comm_ingest — SuccessBrian OS core communication-ingestion module
(Messenger + Instagram slice).

PURPOSE: Ingest Brian's own Messenger and Instagram message history
    from Meta's official "Export your information" (DYI) downloads
    into the one common ingestion store — a normalized message
    envelope in PostgreSQL, counterparties resolved through the
    identity layer by person, raw payloads preserved exactly.

WHY: Brian's order (2026-11-08): ingest ALL Facebook Messenger
    threads (at least 5 Messenger accounts) and ALL Instagram DM
    threads (one account, @successbrian), written to the CRM by
    person; when ingestion is verified complete the original content
    can be deleted; fake or gone accounts are dealt with case by case
    as intel items. Standing frame: his 2026-10-25 common-ingestion
    ruling — per-channel collector -> normalized envelope in
    PostgreSQL (person joined on phone/email/handle; channel; thread;
    direction; timestamp; raw payload preserved) -> dedupe -> CRM
    thread by person. Design source: RECON.md (builds/messenger-ingest
    on the Hatch side), which established the hybrid export-first
    route: the Messenger and Instagram-Messages connectors are barred
    by their own governing docs from bulk mirror/dump use and stay in
    their narrow-read lane; the official export is the history pipe.

CALLED BY: agents, from the repo tree:
    python3 tools/ecosystem_intel/comm_ingest.py <flag>
    State lives in PostgreSQL database people_unified, schema people,
    tables comm_accounts / comm_threads / comm_thread_participants /
    comm_messages / comm_attachments / comm_ingest_runs /
    comm_intel_queue (NEW tables only; no existing table is altered).
    DB access goes through sbos_common with an explicit
    dbname="people_unified". Counterparty resolution reuses
    identity_resolution (same directory): platform+platform_id exact,
    handle_norm, and name-only lookups capped at CANDIDATE — the
    identity engine's rules, not a second matcher.

NOTES:
    - Raw payloads are preserved EXACTLY as exported in
      comm_messages.raw_payload. Meta's DYI JSON carries Latin-1
      mojibake; the repair (encode latin-1 -> decode utf-8, where
      safe) applies ONLY to the readable fields (text, display names,
      titles). The raw payload keeps the original bytes' text.
    - DYI message records normally carry NO platform message ID, so
      the dedupe key is a content hash and is marked as such
      (dedupe_kind='content_hash'). If a future format carries an ID
      (message_id / mid), it is used and marked 'platform_id'.
    - Cross-account dedupe: the same thread can appear in two of
      Brian's own accounts' exports (group chats). Dedupe is enforced
      on (platform_thread_id, dedupe_key) across accounts; the second
      account keeps its thread row and run provenance, not duplicate
      messages.
    - Anonymized counterparties ("Facebook user" / "Instagram User")
      and other gone/unresolvable participants route to
      comm_intel_queue with thread evidence. Nothing auto-resolves
      there; Brian rules case by case.
    - The secure-storage (E2EE) download format is UNKNOWN until
      Brian produces one. The ingest boundary is source-shaped (a
      source yields thread dicts -> the same store writer), so a
      second parser slots in without touching the store. Route value
      'secure_storage' exists in the schema for it. NOTHING about
      that format is invented here.
    - "Verified complete" is a gate, not a vibe (RECON §5):
      --verify runs the machine-runnable checks (manifest
      reconciliation, timestamp range, delta report). The human
      spot-check and sign-off stay Brian's: --mark-verified records
      his ruling; --verify alone never sets it.
    - Nothing here connects an account, sends anything, or deletes
      anything. Export ZIPs extracted for ingest are KEPT (hashed in
      the run record) as the audit copy, per the RECON retention
      recommendation.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
import sbos_common  # noqa: E402
import identity_resolution as ir  # noqa: E402

DBNAME = "people_unified"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "comm_ingest_schema.sql")
STAGING_DIR = os.path.expanduser("~/comm-ingest-staging")

# Names Meta substitutes for deleted / anonymized counterparties.
ANONYMIZED_NAMES = {
    "facebook user", "instagram user", "facebookgebruiker",
    "utilisateur facebook", "usuario de facebook",
}
MESSAGE_FILE_RE = re.compile(r"^message_(\d+)\.json$")
FOLDER_SEGMENTS = {"inbox", "message_requests", "archived_threads",
                   "filtered_messages", "spam", "pending", "priority"}


# ------------------------------------------------------------------ db

def _conn():
    return sbos_common.connect(dbname=DBNAME)


def _dict_conn():
    import psycopg2.extras
    conn = _conn()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def init_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        sql = fh.read()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
    print("schema applied: people.comm_accounts, people.comm_threads, "
          "people.comm_thread_participants, people.comm_messages, "
          "people.comm_attachments, people.comm_ingest_runs, "
          "people.comm_intel_queue")


# ------------------------------------------------------- text repair

def repair_text(value):
    """Repair Meta DYI mojibake: UTF-8 bytes mislabeled as Latin-1.

    The standard fix — encode latin-1, decode utf-8 — applied only
    when both steps succeed and the result differs. Strings that are
    already correct (e.g. containing real emoji, which are not
    Latin-1 encodable) are returned untouched.
    """
    if not isinstance(value, str) or not value:
        return value
    try:
        raw = value.encode("latin-1")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    try:
        fixed = raw.decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value
    return fixed if fixed != value else value


def _norm_name(value):
    return ir.normalize_name(repair_text(value) or "")


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ts_from_ms(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0,
                                      tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


# ------------------------------------------------------------- accounts

def register_account(platform, account_kind, label, owner_display_name=None,
                     handle=None, account_platform_id=None,
                     identity_profile_id=None, notes=None):
    platform = {"messenger": "messenger", "facebook": "messenger",
                "instagram": "instagram"}.get(str(platform).lower())
    if platform not in ("messenger", "instagram"):
        raise ValueError("platform must be messenger or instagram")
    if account_kind not in ("profile", "page"):
        raise ValueError("account_kind must be profile or page")
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO people.comm_accounts "
            "(platform, account_kind, identity_profile_id, label, "
            "account_platform_id, handle, owner_display_name, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (label) DO UPDATE SET "
            "account_kind=EXCLUDED.account_kind, "
            "identity_profile_id=COALESCE("
            "EXCLUDED.identity_profile_id, "
            "people.comm_accounts.identity_profile_id), "
            "account_platform_id=COALESCE("
            "EXCLUDED.account_platform_id, "
            "people.comm_accounts.account_platform_id), "
            "handle=COALESCE(EXCLUDED.handle, people.comm_accounts.handle), "
            "owner_display_name=COALESCE(EXCLUDED.owner_display_name, "
            "people.comm_accounts.owner_display_name), "
            "notes=COALESCE(EXCLUDED.notes, people.comm_accounts.notes), "
            "updated_at=now() RETURNING *",
            (platform, account_kind, identity_profile_id, label,
             account_platform_id, ir.normalize_handle(handle),
             repair_text(owner_display_name), notes))
        row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    print(f"account registered: [{row['id']}] {row['label']} "
          f"({row['platform']}/{row['account_kind']}, "
          f"state={row['ingest_state']})")
    return dict(row)


def _get_account(cur, account_ref):
    cur.execute("SELECT * FROM people.comm_accounts WHERE label=%s",
                (account_ref,))
    row = cur.fetchone()
    if row is None and str(account_ref).isdigit():
        cur.execute("SELECT * FROM people.comm_accounts WHERE id=%s",
                    (int(account_ref),))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"no comm account registered as {account_ref!r} "
                         "(register it with --register-account first)")
    return row


# ------------------------------------------- counterparty resolution
#
# RECON §5 rules, executed through the identity layer — no second
# matcher lives here.
#   1. platform + platform_id exact -> resolved
#   2. platform + handle_norm exact -> resolved
#   3. name-only -> the identity engine's cap applies: at best a
#      CANDIDATE (a unique name match links to that profile as a
#      candidate; multiple/no match mints a candidate profile +
#      anchor in the identity layer for the enrichment queue)
#   4. anonymized / gone -> comm_intel_queue, never force-merged

# For Messenger exports the counterparty's Facebook user ID resolves
# against identity profiles stored under either spelling of the
# surface; the FB friends layer lives under 'facebook'.
_RESOLUTION_PLATFORMS = {
    "messenger": ("facebook", "messenger"),
    "instagram": ("instagram",),
}


def resolve_counterparty(cur, platform, participant_platform_id=None,
                         handle=None, display_name=None):
    """Return (profile_id, resolution_state).

    profile_id is None when the participant must go to the intel
    queue instead (anonymized) — the caller handles queueing.
    """
    name = repair_text(display_name)
    name_norm = _norm_name(display_name)
    if name_norm in ANONYMIZED_NAMES or not name_norm:
        return None, "gone"
    platforms = _RESOLUTION_PLATFORMS.get(platform, (platform,))

    if participant_platform_id:
        for plat in platforms:
            cur.execute(
                "SELECT id FROM people.identity_profiles "
                "WHERE platform=%s AND platform_id=%s",
                (plat, str(participant_platform_id)))
            hit = cur.fetchone()
            if hit:
                return hit["id"], "resolved"

    handle_norm = ir.normalize_handle(handle)
    if handle_norm:
        for plat in platforms:
            cur.execute(
                "SELECT id FROM people.identity_profiles "
                "WHERE platform=%s AND handle_norm=%s "
                "ORDER BY (platform_id IS NOT NULL) DESC, id LIMIT 1",
                (plat, handle_norm))
            hit = cur.fetchone()
            if hit:
                return hit["id"], "candidate"

    # Name-only: unique exact-name profile -> candidate link to it;
    # otherwise mint a candidate profile + person anchor in the
    # identity layer (the enrichment queue picks it up by breadth).
    matches = []
    if name_norm:
        for plat in platforms:
            cur.execute(
                "SELECT id, display_name FROM people.identity_profiles "
                "WHERE platform=%s AND display_name IS NOT NULL",
                (plat,))
            for row in cur.fetchall():
                if _norm_name(row["display_name"]) == name_norm:
                    matches.append(row["id"])
    if len(matches) == 1:
        return matches[0], "candidate"

    plat0 = platforms[0]
    cur.execute(
        "INSERT INTO people.identity_people (display_name, name_norm, "
        "notes) VALUES (%s, %s, %s) RETURNING id",
        (name, name_norm,
         f"candidate anchor minted by comm_ingest ({platform} export)"))
    person_id = cur.fetchone()["id"]
    cur.execute(
        "INSERT INTO people.identity_profiles "
        "(person_id, platform, platform_id, handle, handle_norm, "
        "display_name, source) VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (person_id, plat0,
         str(participant_platform_id) if participant_platform_id else None,
         handle, handle_norm, name,
         f"comm_ingest:{platform}_export"))
    return cur.fetchone()["id"], "candidate"


# ------------------------------------------------- export discovery
#
# The ingest boundary is source-shaped: a source yields thread dicts
# (metadata + participants + raw message records) and the store
# writer below persists them. The DYI parser is the first source.
# The secure-storage (E2EE) download format is UNKNOWN until Brian
# produces one — when it exists, a second source function slots in
# here and reuses the same writer; nothing about its format is
# assumed in this module.

def prepare_export_root(path):
    """Return (root_dir, export_sha256, is_zip).

    ZIPs are extracted to a kept staging dir (the audit copy, hashed
    in the run record). Directories are used in place; their hash is
    taken over the sorted message JSON files.
    """
    if os.path.isdir(path):
        h = hashlib.sha256()
        found = 0
        for dirpath, _dirs, files in os.walk(path):
            for fname in sorted(files):
                if MESSAGE_FILE_RE.match(fname):
                    h.update(_sha256_file(
                        os.path.join(dirpath, fname)).encode())
                    found += 1
        if not found:
            raise ValueError(f"no message_<n>.json files under {path}")
        return path, h.hexdigest(), False
    if zipfile.is_zipfile(path):
        digest = _sha256_file(path)
        root = os.path.join(STAGING_DIR, digest[:16])
        if not os.path.isdir(root):
            os.makedirs(root, exist_ok=True)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(root)
        return root, digest, True
    raise ValueError(f"{path} is neither an export directory nor a ZIP")


def _folder_of(rel_parts):
    for seg in rel_parts:
        if seg in FOLDER_SEGMENTS:
            return seg
    return "inbox"


def _folder_suffix_id(folder_name):
    m = re.search(r"_(\d{5,})$", folder_name or "")
    return m.group(1) if m else None


def dyi_thread_sources(root):
    """Yield thread dicts from a Meta DYI export tree.

    Structure: <root>/.../messages/<folder>/<thread_dir>/message_<n>.json
    with media files beside the JSON. Works for both the Facebook
    (your_facebook_activity) and Instagram (your_instagram_activity)
    layouts, which share the per-thread JSON shape.
    """
    thread_dirs = {}
    for dirpath, _dirs, files in os.walk(root):
        parts = [f for f in files if MESSAGE_FILE_RE.match(f)]
        if not parts:
            continue
        rel = os.path.relpath(dirpath, root)
        if "messages" not in rel.split(os.sep):
            continue
        thread_dirs[dirpath] = sorted(
            parts, key=lambda f: int(MESSAGE_FILE_RE.match(f).group(1)))
    for dirpath in sorted(thread_dirs):
        rel = os.path.relpath(dirpath, root)
        rel_parts = rel.split(os.sep)
        messages = []
        title = thread_type_raw = thread_path = None
        participants = []
        source_files = []
        for fname in thread_dirs[dirpath]:
            fpath = os.path.join(dirpath, fname)
            source_files.append(os.path.relpath(fpath, root))
            with open(fpath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if title is None:
                title = payload.get("title")
            if thread_type_raw is None:
                thread_type_raw = payload.get("thread_type")
            if thread_path is None:
                thread_path = payload.get("thread_path")
            for part in payload.get("participants") or []:
                nm = part.get("name") if isinstance(part, dict) else part
                if nm and nm not in participants:
                    participants.append(nm)
            messages.extend(payload.get("messages") or [])
        yield {
            "thread_dir": dirpath,
            "root": root,
            "folder": _folder_of(rel_parts),
            "folder_name": os.path.basename(dirpath),
            "platform_thread_id": thread_path or rel.replace(os.sep, "/"),
            "title": repair_text(title),
            "thread_type_raw": thread_type_raw,
            "participants_raw": participants,
            "messages_raw": messages,
            "source_files": source_files,
        }


def _classify_thread(thread_type_raw, participant_count, folder):
    if folder == "marketplace":
        return "marketplace"
    raw = str(thread_type_raw or "").lower()
    if "group" in raw or participant_count > 2:
        return "group"
    if participant_count == 2 or "regular" in raw:
        return "one_to_one"
    return "unknown"


_ATTACHMENT_KEYS = (("photos", "photo"), ("videos", "video"),
                    ("files", "file"), ("audio_files", "audio"))


def _message_shape(raw, platform_thread_id):
    """Normalize one raw DYI message record.

    Returns dict with kind/text/attachments/repaired display fields;
    the caller keeps `raw` itself untouched for raw_payload.
    """
    sender_raw = raw.get("sender_name") or ""
    content_raw = raw.get("content")
    attachments = []
    for key, kind in _ATTACHMENT_KEYS:
        for item in raw.get(key) or []:
            if isinstance(item, dict) and item.get("uri"):
                attachments.append({"kind": kind, "uri": item["uri"]})
    sticker = raw.get("sticker")
    if isinstance(sticker, dict) and sticker.get("uri"):
        attachments.append({"kind": "sticker", "uri": sticker["uri"]})

    raw_type = str(raw.get("type") or "")
    if raw_type in ("Call",) or raw.get("call_duration") is not None \
            or raw.get("missed_call"):
        kind = "call"
    elif raw_type in ("Subscribe", "Unsubscribe"):
        kind = "system"
    elif any(a["kind"] == "photo" for a in attachments):
        kind = "photo"
    elif any(a["kind"] == "video" for a in attachments):
        kind = "video"
    elif any(a["kind"] == "audio" for a in attachments):
        kind = "audio"
    elif any(a["kind"] == "file" for a in attachments):
        kind = "file"
    elif raw.get("share"):
        kind = "share"
    elif content_raw:
        kind = "text"
    elif raw.get("reactions"):
        kind = "reaction"
    else:
        kind = "system" if raw_type else "text"

    pid = raw.get("message_id") or raw.get("mid")
    ts_ms = raw.get("timestamp_ms")
    if pid:
        dedupe_key, dedupe_kind = str(pid), "platform_id"
    else:
        first_uri = attachments[0]["uri"] if attachments else ""
        basis = "|".join([str(platform_thread_id), str(ts_ms),
                          sender_raw, content_raw or "", first_uri])
        dedupe_key = "sha256:" + _sha256_bytes(basis.encode("utf-8"))
        dedupe_kind = "content_hash"
    return {
        "sender_raw": sender_raw,
        "sender_name": repair_text(sender_raw),
        "timestamp_ms": ts_ms,
        "sent_at": _ts_from_ms(ts_ms),
        "kind": kind,
        "text": repair_text(content_raw) if content_raw else None,
        "attachments": attachments,
        "platform_message_id": str(pid) if pid else None,
        "dedupe_key": dedupe_key,
        "dedupe_kind": dedupe_kind,
    }


# -------------------------------------------------------- store write

def _queue_intel(cur, platform, display_name, participant_platform_id,
                 reason, evidence):
    """Add a pending intel-queue row unless an identical pending one
    (same reason + thread) already exists. Returns row id or None."""
    thread_ref = (evidence or {}).get("platform_thread_id")
    cur.execute(
        "SELECT id FROM people.comm_intel_queue WHERE status='pending' "
        "AND reason=%s AND evidence->>'platform_thread_id'=%s "
        "AND display_name_snapshot IS NOT DISTINCT FROM %s",
        (reason, thread_ref, display_name))
    hit = cur.fetchone()
    if hit:
        return None
    cur.execute(
        "INSERT INTO people.comm_intel_queue "
        "(platform, participant_platform_id, display_name_snapshot, "
        "reason, evidence) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (platform, participant_platform_id, display_name, reason,
         json.dumps(evidence or {})))
    return cur.fetchone()["id"]


def _resolve_attachment_file(root, thread_dir, uri):
    """Find an attachment's file inside the export; return
    (stored_path, sha256, bytes) or (None, None, None)."""
    candidates = [os.path.join(root, uri),
                  os.path.join(thread_dir, os.path.basename(uri))]
    # DYI uris are relative to the ZIP root, which may sit one level
    # above the tree we were handed (e.g. root IS the activity dir).
    parent = os.path.dirname(os.path.abspath(root))
    candidates.append(os.path.join(parent, uri))
    for cand in candidates:
        if os.path.isfile(cand):
            return cand, _sha256_file(cand), os.path.getsize(cand)
    return None, None, None


def ingest_export(path, account_ref, route="dyi_export",
                  requested_range="All time"):
    root, export_sha256, _is_zip = prepare_export_root(path)
    conn = _dict_conn()
    totals = {"threads": 0, "messages_seen": 0, "inserted": 0,
              "duplicated": 0, "attachments": 0, "intel_queued": 0}
    try:
        cur = conn.cursor()
        account = _get_account(cur, account_ref)
        platform = account["platform"]
        owner_norm = _norm_name(account.get("owner_display_name"))
        owner_profile_id = account.get("identity_profile_id")

        cur.execute(
            "INSERT INTO people.comm_ingest_runs "
            "(account_id, route, export_file, export_sha256, "
            "requested_range) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (account["id"], route, os.path.abspath(path), export_sha256,
             requested_range))
        run_id = cur.fetchone()["id"]

        for src in dyi_thread_sources(root):
            totals["threads"] += 1
            ttype = _classify_thread(src["thread_type_raw"],
                                     len(src["participants_raw"]),
                                     src["folder"])
            cur.execute(
                "INSERT INTO people.comm_threads "
                "(account_id, platform, platform_thread_id, thread_type, "
                "title, folder, ingest_source, completeness) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'export_loaded') "
                "ON CONFLICT (account_id, platform, platform_thread_id) "
                "DO UPDATE SET title=COALESCE(EXCLUDED.title, "
                "people.comm_threads.title), updated_at=now() "
                "RETURNING id",
                (account["id"], platform, src["platform_thread_id"],
                 ttype, src["title"], src["folder"], route))
            thread_id = cur.fetchone()["id"]

            suffix_id = _folder_suffix_id(src["folder_name"])
            # Participants from the export header, plus any sender who
            # appears in messages but not the header (removed members).
            names = list(src["participants_raw"])
            for raw in src["messages_raw"]:
                sn = raw.get("sender_name")
                if sn and sn not in names:
                    names.append(sn)
            sender_profiles = {}
            for raw_name in names:
                name = repair_text(raw_name)
                name_norm = _norm_name(raw_name)
                is_owner = bool(owner_norm) and name_norm == owner_norm
                if is_owner:
                    profile_id, state = owner_profile_id, (
                        "resolved" if owner_profile_id else "unknown")
                    role = "owner"
                    part_pid = account.get("account_platform_id")
                else:
                    role = "counterparty" if ttype == "one_to_one" \
                        else "participant"
                    part_pid = suffix_id if (
                        ttype == "one_to_one"
                        and name_norm not in ANONYMIZED_NAMES) else None
                    profile_id, state = resolve_counterparty(
                        cur, platform, part_pid, None, name)
                    if state == "gone":
                        qid = _queue_intel(
                            cur, platform, name, part_pid,
                            "anonymized_counterparty",
                            {"platform_thread_id":
                             src["platform_thread_id"],
                             "account": account["label"],
                             "folder_name": src["folder_name"],
                             "thread_title": src["title"]})
                        if qid:
                            totals["intel_queued"] += 1
                pkey = part_pid or ("name:" + name_norm)
                cur.execute(
                    "INSERT INTO people.comm_thread_participants "
                    "(thread_id, profile_id, participant_platform_id, "
                    "participant_key, display_name_snapshot, role, "
                    "resolution_state) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (thread_id, participant_key) DO UPDATE "
                    "SET profile_id=COALESCE(EXCLUDED.profile_id, "
                    "people.comm_thread_participants.profile_id), "
                    "resolution_state=EXCLUDED.resolution_state",
                    (thread_id, profile_id, part_pid, pkey, name, role,
                     state))
                sender_profiles[name_norm] = (profile_id, state)

            for raw in src["messages_raw"]:
                totals["messages_seen"] += 1
                shape = _message_shape(raw, src["platform_thread_id"])
                s_norm = _norm_name(raw.get("sender_name"))
                s_profile, s_state = sender_profiles.get(
                    s_norm, (None, "unknown"))
                if owner_norm and s_norm == owner_norm:
                    direction = "out"
                elif s_state == "gone" or not s_norm:
                    direction = "unknown"
                else:
                    direction = "in"
                # Cross-account dedupe: same platform thread + same
                # dedupe key already stored under another account.
                cur.execute(
                    "SELECT m.id FROM people.comm_messages m "
                    "JOIN people.comm_threads t ON t.id=m.thread_id "
                    "WHERE t.platform=%s AND t.platform_thread_id=%s "
                    "AND m.dedupe_key=%s LIMIT 1",
                    (platform, src["platform_thread_id"],
                     shape["dedupe_key"]))
                if cur.fetchone():
                    totals["duplicated"] += 1
                    continue
                cur.execute(
                    "INSERT INTO people.comm_messages "
                    "(thread_id, platform_message_id, dedupe_key, "
                    "dedupe_kind, sender_profile_id, "
                    "sender_name_snapshot, direction, sent_at, kind, "
                    "text, raw_payload, source_file) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s) ON CONFLICT (thread_id, dedupe_key) "
                    "DO NOTHING RETURNING id",
                    (thread_id, shape["platform_message_id"],
                     shape["dedupe_key"], shape["dedupe_kind"],
                     s_profile, shape["sender_name"], direction,
                     shape["sent_at"], shape["kind"], shape["text"],
                     json.dumps(raw, ensure_ascii=False),
                     src["source_files"][0] if src["source_files"]
                     else None))
                mrow = cur.fetchone()
                if mrow is None:
                    totals["duplicated"] += 1
                    continue
                totals["inserted"] += 1
                for att in shape["attachments"]:
                    stored, sha, size = _resolve_attachment_file(
                        root, src["thread_dir"], att["uri"])
                    cur.execute(
                        "INSERT INTO people.comm_attachments "
                        "(message_id, kind, source_uri, stored_path, "
                        "sha256, bytes) VALUES (%s, %s, %s, %s, %s, %s)",
                        (mrow["id"], att["kind"], att["uri"], stored,
                         sha, size))
                    totals["attachments"] += 1
            cur.execute(
                "UPDATE people.comm_threads SET "
                "message_count=(SELECT count(*) FROM people.comm_messages "
                "WHERE thread_id=%s), "
                "first_message_at=(SELECT min(sent_at) FROM "
                "people.comm_messages WHERE thread_id=%s), "
                "last_message_at=(SELECT max(sent_at) FROM "
                "people.comm_messages WHERE thread_id=%s), "
                "updated_at=now() WHERE id=%s",
                (thread_id, thread_id, thread_id, thread_id))

        cur.execute(
            "UPDATE people.comm_ingest_runs SET threads_seen=%s, "
            "messages_seen=%s, messages_inserted=%s, "
            "messages_duplicated=%s, attachments_seen=%s WHERE id=%s",
            (totals["threads"], totals["messages_seen"],
             totals["inserted"], totals["duplicated"],
             totals["attachments"], run_id))
        cur.execute(
            "UPDATE people.comm_accounts SET ingest_state="
            "CASE WHEN ingest_state='verified_complete' THEN "
            "ingest_state ELSE 'export_loaded' END, updated_at=now() "
            "WHERE id=%s", (account["id"],))
        conn.commit()
    finally:
        conn.close()
    print(f"ingest run {run_id}: {totals['threads']} threads, "
          f"{totals['messages_seen']} messages seen, "
          f"{totals['inserted']} inserted, {totals['duplicated']} "
          f"duplicated, {totals['attachments']} attachments, "
          f"{totals['intel_queued']} intel items queued")
    return {"run_id": run_id, **totals}


# ------------------------------------------------------------ reports

def show_stats():
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT label, platform, account_kind, ingest_state "
                    "FROM people.comm_accounts ORDER BY id")
        accounts = cur.fetchall()
        cur.execute("SELECT count(*) c FROM people.comm_threads")
        threads = cur.fetchone()["c"]
        cur.execute("SELECT count(*) c FROM people.comm_messages")
        messages = cur.fetchone()["c"]
        cur.execute("SELECT count(*) c FROM people.comm_attachments")
        attachments = cur.fetchone()["c"]
        cur.execute("SELECT count(*) c FROM people.comm_intel_queue "
                    "WHERE status='pending'")
        pending = cur.fetchone()["c"]
        cur.execute("SELECT count(*) c FROM people.comm_ingest_runs")
        runs = cur.fetchone()["c"]
        cur.execute(
            "SELECT resolution_state, count(*) c FROM "
            "people.comm_thread_participants GROUP BY 1 ORDER BY 1")
        res_states = cur.fetchall()
    finally:
        conn.close()
    print("comm accounts:")
    if not accounts:
        print("  (none registered)")
    for a in accounts:
        print(f"  {a['label']} — {a['platform']}/{a['account_kind']} "
              f"[{a['ingest_state']}]")
    print(f"threads: {threads}")
    print(f"messages: {messages}")
    print(f"attachments: {attachments}")
    print(f"ingest runs: {runs}")
    print(f"intel queue pending: {pending}")
    print("participant resolution:")
    for r in res_states:
        print(f"  {r['resolution_state']}: {r['c']}")
    return {"accounts": len(accounts), "threads": threads,
            "messages": messages, "attachments": attachments,
            "runs": runs, "intel_pending": pending}


def show_queue(limit=50):
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, platform, display_name_snapshot, reason, "
            "evidence, created_at FROM people.comm_intel_queue "
            "WHERE status='pending' ORDER BY created_at LIMIT %s",
            (limit,))
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        print("intel queue: empty")
    for r in rows:
        ev = r["evidence"] or {}
        print(f"  [#{r['id']}] {r['reason']} — "
              f"{r['display_name_snapshot']} ({r['platform']}) "
              f"thread={ev.get('platform_thread_id')} "
              f"account={ev.get('account')}")
    return [dict(r) for r in rows]


def verify_account(account_ref):
    """Machine-runnable half of the RECON verified-complete gate:
    manifest reconciliation against the latest ingest run's export,
    timestamp-range proof, and a delta report. Never sets
    verified_complete_at — Brian's spot-check + sign-off do that
    (--mark-verified)."""
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        account = _get_account(cur, account_ref)
        cur.execute(
            "SELECT * FROM people.comm_ingest_runs WHERE account_id=%s "
            "ORDER BY created_at DESC LIMIT 1", (account["id"],))
        run = cur.fetchone()
        if run is None:
            print(f"verify {account['label']}: NO INGEST RUN — FAIL")
            return {"ok": False, "reason": "no ingest run"}
        export_file = run["export_file"]
        if not export_file or not os.path.exists(export_file):
            print(f"verify {account['label']}: export file "
                  f"{export_file} no longer present — cannot "
                  "reconcile (UNKNOWN, not a pass)")
            return {"ok": False, "reason": "export missing"}
        root, digest, _z = prepare_export_root(export_file)
        hash_ok = (digest == run["export_sha256"])
        src_threads = {}
        src_keys = set()
        src_ts = []
        for src in dyi_thread_sources(root):
            keys = set()
            for raw in src["messages_raw"]:
                shape = _message_shape(raw, src["platform_thread_id"])
                keys.add(shape["dedupe_key"])
                src_keys.add(shape["dedupe_key"])
                if shape["sent_at"]:
                    src_ts.append(shape["sent_at"])
            src_threads[src["platform_thread_id"]] = keys
        cur.execute(
            "SELECT id, platform_thread_id FROM people.comm_threads "
            "WHERE account_id=%s", (account["id"],))
        db_threads = {r["platform_thread_id"]: r["id"]
                      for r in cur.fetchall()}
        deltas = []
        missing_msgs = 0
        for ptid, keys in src_threads.items():
            if ptid not in db_threads:
                deltas.append(f"thread {ptid} in export, absent in DB")
                missing_msgs += len(keys)
                continue
            cur.execute(
                "SELECT dedupe_key FROM people.comm_messages "
                "WHERE thread_id=%s", (db_threads[ptid],))
            db_keys = {r["dedupe_key"] for r in cur.fetchall()}
            gone = keys - db_keys
            if gone:
                cur.execute(
                    "SELECT count(*) c FROM people.comm_messages m "
                    "JOIN people.comm_threads t ON t.id=m.thread_id "
                    "WHERE t.platform=%s AND t.platform_thread_id=%s "
                    "AND m.dedupe_key = ANY(%s)",
                    (account["platform"], ptid, list(gone)))
                elsewhere = cur.fetchone()["c"]
                unexplained = len(gone) - elsewhere
                if unexplained:
                    deltas.append(
                        f"thread {ptid}: {unexplained} export messages "
                        "unexplained (not in DB under any account)")
                    missing_msgs += unexplained
        for ptid in db_threads:
            if ptid not in src_threads:
                deltas.append(f"thread {ptid} in DB, not in this "
                              "export (delta or earlier source — "
                              "review, not auto-fail)")
        cur.execute(
            "SELECT min(sent_at) mn, max(sent_at) mx FROM "
            "people.comm_messages m JOIN people.comm_threads t "
            "ON t.id=m.thread_id WHERE t.account_id=%s",
            (account["id"],))
        rng = cur.fetchone()
        src_range = (min(src_ts), max(src_ts)) if src_ts else (None, None)
        range_note = (f"source {src_range[0]}..{src_range[1]}; "
                      f"db {rng['mn']}..{rng['mx']}")
        ok = hash_ok and not missing_msgs and not any(
            "absent in DB" in d for d in deltas)
        print(f"verify {account['label']}: export hash "
              f"{'OK' if hash_ok else 'MISMATCH'}; "
              f"{len(src_threads)} source threads; "
              f"{len(src_keys)} source messages; {range_note}")
        for d in deltas:
            print(f"  delta: {d}")
        print(f"verify {account['label']}: machine checks "
              f"{'PASS' if ok else 'FAIL'} — human spot-check + "
              "Brian sign-off still required before "
              "verified_complete")
        return {"ok": ok, "deltas": deltas, "hash_ok": hash_ok}
    finally:
        conn.close()


def mark_verified(account_ref, by="brian"):
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        account = _get_account(cur, account_ref)
        cur.execute(
            "UPDATE people.comm_accounts SET "
            "ingest_state='verified_complete', "
            "verified_complete_at=now(), updated_at=now() WHERE id=%s",
            (account["id"],))
        cur.execute(
            "UPDATE people.comm_ingest_runs SET verified_by=%s, "
            "verified_at=now() WHERE id=(SELECT id FROM "
            "people.comm_ingest_runs WHERE account_id=%s ORDER BY "
            "created_at DESC LIMIT 1)", (by, account["id"]))
        cur.execute(
            "UPDATE people.comm_threads SET completeness='verified' "
            "WHERE account_id=%s", (account["id"],))
        conn.commit()
    finally:
        conn.close()
    print(f"{account_ref}: marked verified_complete (sign-off: {by})")


# ------------------------------------------------------------ selftest

def selftest():
    import shutil
    import tempfile
    checks = []

    def ck(name, ok):
        checks.append((name, bool(ok)))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    # Pure-logic checks.
    ck("mojibake repair fixes mangled UTF-8",
       repair_text("RenÃ©e Fournier") == "Renée Fournier")
    ck("mojibake repair leaves correct text untouched",
       repair_text("Hello 🎉") == "Hello 🎉"
       and repair_text("plain ascii") == "plain ascii")
    shape = _message_shape({"sender_name": "A", "timestamp_ms": 5,
                            "content": "x"}, "inbox/t1")
    ck("ID-less record dedupes on content hash, marked as such",
       shape["dedupe_kind"] == "content_hash"
       and shape["dedupe_key"].startswith("sha256:"))
    shape2 = _message_shape({"sender_name": "A", "timestamp_ms": 5,
                             "content": "x", "message_id": "m-1"},
                            "inbox/t1")
    ck("record with a platform ID dedupes on it",
       shape2["dedupe_kind"] == "platform_id"
       and shape2["dedupe_key"] == "m-1")

    # DB fixture: a synthetic DYI-shaped export.
    init_schema()
    tmp = tempfile.mkdtemp(prefix="comm-ingest-selftest-")
    conn = _dict_conn()
    fixture_person_id = fixture_profile_id = None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO people.identity_people (display_name, "
            "name_norm, notes) VALUES ('Renée Fournier', %s, "
            "'comm_ingest selftest fixture') RETURNING id",
            (ir.normalize_name("Renée Fournier"),))
        fixture_person_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO people.identity_profiles (person_id, "
            "platform, platform_id, display_name, source) VALUES "
            "(%s, 'facebook', '42424', 'Renée Fournier', "
            "'comm_ingest_selftest') RETURNING id",
            (fixture_person_id,))
        fixture_profile_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    def build_export(root, with_group):
        tdir = os.path.join(root, "your_facebook_activity", "messages",
                            "inbox", "renee_fournier_42424")
        os.makedirs(os.path.join(tdir, "photos"), exist_ok=True)
        with open(os.path.join(tdir, "photos", "photo1.jpg"),
                  "wb") as fh:
            fh.write(b"fake-jpeg")
        payload = {
            "participants": [{"name": "Brian Lathe"},
                             {"name": "RenÃ©e Fournier"}],
            "title": "RenÃ©e Fournier",
            "thread_type": "Regular",
            "thread_path": "inbox/renee_fournier_42424",
            "messages": [
                {"sender_name": "Brian Lathe",
                 "timestamp_ms": 1700000100000,
                 "content": "Hello RenÃ©e, call tomorrow",
                 "type": "Generic"},
                {"sender_name": "RenÃ©e Fournier",
                 "timestamp_ms": 1700000200000,
                 "content": "Hi Brian!",
                 "photos": [{
                     "uri": "your_facebook_activity/messages/inbox/"
                            "renee_fournier_42424/photos/photo1.jpg",
                     "creation_timestamp": 1700000200}],
                 "type": "Generic"},
                {"sender_name": "Brian Lathe",
                 "timestamp_ms": 1700000300000,
                 "call_duration": 65, "type": "Call"},
            ],
        }
        with open(os.path.join(tdir, "message_1.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        if with_group:
            gdir = os.path.join(root, "your_facebook_activity",
                                "messages", "inbox", "weekendcrew_99999")
            os.makedirs(gdir, exist_ok=True)
            gpayload = {
                "participants": [{"name": "Brian Lathe"},
                                 {"name": "Facebook user"},
                                 {"name": "Sam Poe"}],
                "title": "Weekend crew",
                "thread_type": "RegularGroup",
                "thread_path": "inbox/weekendcrew_99999",
                "messages": [
                    {"sender_name": "Sam Poe",
                     "timestamp_ms": 1700000400000,
                     "content": "trail on Saturday?",
                     "type": "Generic"},
                ],
            }
            with open(os.path.join(gdir, "message_1.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(gpayload, fh, ensure_ascii=False)

    export_a = os.path.join(tmp, "exportA")
    export_b = os.path.join(tmp, "exportB")
    build_export(export_a, with_group=True)
    build_export(export_b, with_group=False)
    try:
        register_account("messenger", "profile", "selftest-msgr-a",
                         owner_display_name="Brian Lathe")
        register_account("messenger", "profile", "selftest-msgr-b",
                         owner_display_name="Brian Lathe")
        res_a = ingest_export(export_a, "selftest-msgr-a")
        ck("fixture ingest: 2 threads, 4 messages inserted",
           res_a["threads"] == 2 and res_a["inserted"] == 4)

        conn = _dict_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT m.text, m.raw_payload, m.kind, m.direction "
                "FROM people.comm_messages m JOIN people.comm_threads "
                "t ON t.id=m.thread_id JOIN people.comm_accounts a "
                "ON a.id=t.account_id WHERE a.label='selftest-msgr-a' "
                "AND m.kind='text' ORDER BY m.sent_at LIMIT 1")
            m1 = cur.fetchone()
            ck("readable text is mojibake-repaired",
               m1["text"] == "Hello Renée, call tomorrow")
            raw_content = (m1["raw_payload"] or {}).get("content")
            ck("raw_payload preserves the original mangled text",
               raw_content == "Hello RenÃ©e, call tomorrow")
            cur.execute(
                "SELECT count(*) c FROM people.comm_messages m "
                "JOIN people.comm_threads t ON t.id=m.thread_id "
                "JOIN people.comm_accounts a ON a.id=t.account_id "
                "WHERE a.label='selftest-msgr-a' AND m.kind='call'")
            ck("call marker stored as kind=call",
               cur.fetchone()["c"] == 1)
            cur.execute(
                "SELECT at.sha256, at.bytes FROM people.comm_attachments at "
                "JOIN people.comm_messages m ON m.id=at.message_id "
                "JOIN people.comm_threads t ON t.id=m.thread_id "
                "JOIN people.comm_accounts a ON a.id=t.account_id "
                "WHERE a.label='selftest-msgr-a'")
            att = cur.fetchone()
            ck("attachment stored with sha256 of the real file",
               att and att["sha256"] == _sha256_bytes(b"fake-jpeg")
               and att["bytes"] == 9)
            cur.execute(
                "SELECT profile_id, resolution_state FROM "
                "people.comm_thread_participants p JOIN "
                "people.comm_threads t ON t.id=p.thread_id JOIN "
                "people.comm_accounts a ON a.id=t.account_id WHERE "
                "a.label='selftest-msgr-a' AND "
                "p.display_name_snapshot='Renée Fournier'")
            part = cur.fetchone()
            ck("counterparty with a known platform ID resolves "
               "exactly through the identity layer",
               part and part["profile_id"] == fixture_profile_id
               and part["resolution_state"] == "resolved")
            cur.execute(
                "SELECT resolution_state FROM "
                "people.comm_thread_participants p JOIN "
                "people.comm_threads t ON t.id=p.thread_id JOIN "
                "people.comm_accounts a ON a.id=t.account_id WHERE "
                "a.label='selftest-msgr-a' AND "
                "p.display_name_snapshot='Sam Poe'")
            ck("name-only counterparty is a CANDIDATE, never "
               "auto-resolved",
               cur.fetchone()["resolution_state"] == "candidate")
            cur.execute(
                "SELECT resolution_state FROM "
                "people.comm_thread_participants p JOIN "
                "people.comm_threads t ON t.id=p.thread_id JOIN "
                "people.comm_accounts a ON a.id=t.account_id WHERE "
                "a.label='selftest-msgr-a' AND "
                "p.display_name_snapshot='Facebook user'")
            ck("anonymized counterparty marked gone, not merged",
               cur.fetchone()["resolution_state"] == "gone")
            cur.execute(
                "SELECT count(*) c FROM people.comm_intel_queue "
                "WHERE status='pending' AND "
                "reason='anonymized_counterparty' AND "
                "evidence->>'platform_thread_id'="
                "'inbox/weekendcrew_99999'")
            ck("anonymized counterparty routed to the intel queue",
               cur.fetchone()["c"] == 1)
        finally:
            conn.close()

        res_b = ingest_export(export_b, "selftest-msgr-b")
        ck("same thread in a second account's export dedupes on "
           "message identity (0 inserted, 3 duplicated)",
           res_b["inserted"] == 0 and res_b["duplicated"] == 3)
        res_a2 = ingest_export(export_a, "selftest-msgr-a")
        ck("re-ingesting the same export is idempotent",
           res_a2["inserted"] == 0 and res_a2["duplicated"] == 4)
        ver = verify_account("selftest-msgr-a")
        ck("verify: manifest reconciliation passes on the fixture",
           ver["ok"])
    finally:
        # Cleanup: every artefact the fixture made is deleted.
        conn = _dict_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM people.comm_ingest_runs WHERE "
                "export_file LIKE %s", (tmp + "%",))
            cur.execute(
                "DELETE FROM people.comm_accounts WHERE label IN "
                "('selftest-msgr-a', 'selftest-msgr-b')")
            cur.execute(
                "DELETE FROM people.comm_intel_queue WHERE "
                "evidence->>'platform_thread_id'="
                "'inbox/weekendcrew_99999'")
            cur.execute(
                "SELECT id, person_id FROM people.identity_profiles "
                "WHERE source='comm_ingest:messenger_export' AND "
                "display_name='Sam Poe'")
            for row in cur.fetchall():
                cur.execute(
                    "DELETE FROM people.identity_profiles WHERE id=%s",
                    (row["id"],))
                if row["person_id"]:
                    cur.execute(
                        "DELETE FROM people.identity_people WHERE "
                        "id=%s AND NOT EXISTS (SELECT 1 FROM "
                        "people.identity_profiles WHERE person_id=%s)",
                        (row["person_id"], row["person_id"]))
            if fixture_profile_id:
                cur.execute(
                    "DELETE FROM people.identity_profiles WHERE id=%s",
                    (fixture_profile_id,))
            if fixture_person_id:
                cur.execute(
                    "DELETE FROM people.identity_people WHERE id=%s",
                    (fixture_person_id,))
            conn.commit()
        finally:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _n, ok in checks if ok)
    print(f"selftest: {passed}/{len(checks)}")
    return passed == len(checks)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="SBOS communication ingestion (Messenger + "
                    "Instagram, export-first)")
    ap.add_argument("--init-schema", action="store_true")
    ap.add_argument("--register-account", action="store_true")
    ap.add_argument("--platform", help="messenger | instagram")
    ap.add_argument("--kind", default="profile",
                    help="profile | page (for --register-account)")
    ap.add_argument("--label", help="account label")
    ap.add_argument("--owner-name")
    ap.add_argument("--handle")
    ap.add_argument("--account-platform-id")
    ap.add_argument("--identity-profile-id", type=int)
    ap.add_argument("--notes")
    ap.add_argument("--ingest-export",
                    help="path to a DYI export ZIP or extracted dir")
    ap.add_argument("--account",
                    help="comm account label (or id) the export "
                         "belongs to")
    ap.add_argument("--route", default="dyi_export",
                    choices=["dyi_export", "secure_storage",
                             "connector_read"])
    ap.add_argument("--range", default="All time",
                    dest="requested_range")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--queue", action="store_true")
    ap.add_argument("--verify", metavar="ACCOUNT")
    ap.add_argument("--mark-verified", metavar="ACCOUNT")
    ap.add_argument("--by", default="brian")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.init_schema:
        init_schema()
    elif args.register_account:
        if not (args.platform and args.label):
            ap.error("--register-account needs --platform and --label")
        register_account(args.platform, args.kind, args.label,
                         owner_display_name=args.owner_name,
                         handle=args.handle,
                         account_platform_id=args.account_platform_id,
                         identity_profile_id=args.identity_profile_id,
                         notes=args.notes)
    elif args.ingest_export:
        if not args.account:
            ap.error("--ingest-export needs --account <label>")
        ingest_export(args.ingest_export, args.account,
                      route=args.route,
                      requested_range=args.requested_range)
    elif args.stats:
        show_stats()
    elif args.queue:
        show_queue()
    elif args.verify:
        result = verify_account(args.verify)
        sys.exit(0 if result["ok"] else 1)
    elif args.mark_verified:
        mark_verified(args.mark_verified, by=args.by)
    elif args.selftest:
        sys.exit(0 if selftest() else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
