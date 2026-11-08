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
    comm_intel_queue / comm_profile_intel (NEW tables only; no
    existing table is altered).
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
    - Sender-profile intel scans are READ-ONLY against Facebook.
      Brian's requested fields are never filled by inference: every
      field carries a field_status of ok / not_exposed / not_public /
      error, with the connector command that was used. The Facebook
      connector's profile surface exposes birthdate and location when
      listed, but no followers count, no target friends count, and no
      common/mutual-friends list; those stay NULL + not_exposed.
      Interest signals require deterministic term evidence in the
      profile bio/hobbies or the person's own recent timeline posts.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import date, datetime, timezone

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
          "people.comm_intel_queue, people.comm_profile_intel")


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


# -------------------------------------------------- profile intel scan
#
# Brian's order (2026-11-08): when Messenger senders are ingested,
# pull their Facebook profile into the CRM and scan it for followers,
# friends, mutual friends, crypto/health interest signals, country,
# and birthday. The scan is READ-ONLY and evidence-bound:
#   - profile info exposes birthdate + current city/hometown when the
#     profile lists them, plus bio/hobbies/work/education;
#   - timeline fetch exposes recent posts (own posts are separated
#     from wall posts by author_id == owner_id);
#   - NO command exposes a personal profile's followers count, the
#     profile's own friends count, or a common/mutual-friends list.
#     Those fields are stored NULL with field_status=not_exposed.
#   - me friends can establish whether the sender is Brian's direct
#     Facebook friend; that is recorded as supplemental context, never
#     dressed up as a mutual-friends list.

FACEBOOK_CLI = os.environ.get("SBOS_FACEBOOK_CLI",
                              "/opt/hatch/bin/facebook-cli")
PROFILE_INFO_CMD = "facebook-cli profile info --profile-id <id-or-vanity>"
TIMELINE_CMD = "facebook-cli timeline fetch --profile-id <id>"
FRIENDS_CMD = "facebook-cli me friends --name <name>"

INTEL_THEME_RULES = {
    "crypto": {
        "bitcoin": r"\bbitcoin\b",
        "btc": r"\bbtc\b",
        "ethereum": r"\bethereum\b",
        "eth": r"\beth\b",
        "crypto": r"\bcrypt(?:o|currency|currencies)?\b",
        "blockchain": r"\bblockchain\b",
        "web3": r"\bweb3\b",
        "nft": r"\bnfts?\b",
        "non-fungible token": r"\bnon[-\s]?fungible tokens?\b",
        "solana": r"\bsolana\b",
        "xrp": r"\bxrp\b",
        "dogecoin": r"\bdogecoin\b",
        "defi": r"\bdefi\b",
        "altcoin": r"\baltcoins?\b",
        "stablecoin": r"\bstablecoins?\b",
        "crypto wallet": r"\bcrypto wallet\b",
        "digital asset": r"\bdigital assets?\b",
        "memecoin": r"\bmemecoins?\b",
        "binance": r"\bbinance\b",
        "coinbase": r"\bcoinbase\b",
    },
    "health": {
        "health": r"\bhealth(?:y|care)?\b",
        "wellness": r"\bwellness\b",
        "fitness": r"\bfitness\b",
        "workout": r"\bworkouts?\b",
        "gym": r"\bgym\b",
        "nutrition": r"\bnutrition(?:al)?\b",
        "supplements": r"\bsupplements?\b",
        "vitamins": r"\bvitamins?\b",
        "weight loss": r"\bweight[-\s]?loss\b",
        "diabetes": r"\bdiabet(?:es|ic)\b",
        "gut health": r"\bgut health\b",
        "mental health": r"\bmental health\b",
        "longevity": r"\blongevity\b",
        "biohacking": r"\bbiohacking\b",
        "yoga": r"\byoga\b",
        "meditation": r"\bmeditation\b",
        "sleep apnea": r"\bsleep apnea\b",
        "zepbound": r"\bzepbound\b",
        "glp-1": r"\bglp[-\s]?1\b",
        "keto": r"\bketo(?:genic)?\b",
        "carnivore diet": r"\bcarnivore diet\b",
        "protein": r"\bprotein\b",
        "essential oils": r"\bessential oils?\b",
        "holistic health": r"\bholistic health\b",
    },
}

_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california",
    "colorado", "connecticut", "delaware", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota",
    "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia",
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc",
}
_CA_REGIONS = {
    "alberta", "british columbia", "manitoba", "new brunswick",
    "newfoundland and labrador", "nova scotia", "ontario",
    "prince edward island", "quebec", "saskatchewan",
    "northwest territories", "nunavut", "yukon",
    "ab", "bc", "mb", "nb", "nl", "ns", "on", "pe", "qc", "sk",
    "nt", "nu", "yt",
}
_AU_REGIONS = {
    "new south wales", "victoria", "queensland", "western australia",
    "south australia", "tasmania", "australian capital territory",
    "northern territory", "nsw", "vic", "qld", "wa", "sa", "tas",
    "act", "nt",
}
# NOTE: no UK county/region inference. County names collide with
# US place names (Suffolk, Norfolk, Essex, Kent are all US places
# too), so a bare British county is NOT country evidence. Only the
# explicit constituent-country aliases in _COUNTRY_ALIASES resolve
# for the UK.
_COUNTRY_ALIASES = {
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States", "u.s.a.": "United States",
    "u.s.": "United States", "us": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom", "u.k.": "United Kingdom",
    "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "canada": "Canada", "australia": "Australia",
    "philippines": "Philippines", "nigeria": "Nigeria",
    "ghana": "Ghana", "india": "India", "germany": "Germany",
    "france": "France", "spain": "Spain", "italy": "Italy",
    "netherlands": "Netherlands", "mexico": "Mexico",
    "brazil": "Brazil", "south africa": "South Africa",
    "kenya": "Kenya", "pakistan": "Pakistan",
    "bangladesh": "Bangladesh", "indonesia": "Indonesia",
    "malaysia": "Malaysia", "singapore": "Singapore",
    "new zealand": "New Zealand", "ireland": "Ireland",
}


class FacebookConnectorError(Exception):
    def __init__(self, message, status="error"):
        super().__init__(message)
        self.status = status


class FacebookProfileClient:
    """Thin read-only runner over the sanctioned facebook-cli.

    Only the profile surface is used: profile info, timeline fetch,
    and me friends (name search, to establish direct-friend context).
    No write command exists in this class.
    """

    def __init__(self, executable=None):
        self.executable = executable or FACEBOOK_CLI

    def _run(self, args):
        if not os.path.isfile(self.executable):
            raise FacebookConnectorError(
                f"facebook-cli not found at {self.executable}",
                status="error")
        try:
            proc = subprocess.run(
                [self.executable] + args, capture_output=True,
                text=True, timeout=90)
        except (OSError, subprocess.SubprocessError) as exc:
            raise FacebookConnectorError(
                f"facebook-cli invocation failed: {exc}",
                status="error")
        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            blob = (out + " " + (proc.stderr or "")).lower()
            status = "not_public" if (
                "not accessible" in blob or "403" in blob) else "error"
            raise FacebookConnectorError(
                (proc.stderr or out or "facebook-cli failed")[:300],
                status=status)
        try:
            return json.loads(out)
        except ValueError:
            raise FacebookConnectorError(
                "facebook-cli returned non-JSON output", status="error")

    def profile_info(self, profile_ref):
        return self._run(["profile", "info", "--profile-id",
                          str(profile_ref)])

    def timeline(self, profile_id, limit=20, after=None):
        args = ["timeline", "fetch", "--profile-id", str(profile_id),
                "--limit", str(limit)]
        if after:
            args += ["--after", after]
        return self._run(args)

    def friends_by_name(self, name, limit=20, after=None):
        args = ["me", "friends", "--name", name, "--limit",
                str(limit)]
        if after:
            args += ["--after", after]
        return self._run(args)

    def find_direct_friend(self, display_name, platform_id,
                           max_pages=10):
        """Exact-ID lookup inside Brian's friends by name search.

        Returns yes only on an exact friend_id match in a fully-read
        result set; no only when the name result set is exhausted
        without the ID; unknown when paging is truncated or the
        command fails. This establishes a DIRECT friendship only —
        it is not a mutual/common-friends list.
        """
        if not display_name or not platform_id:
            return {"value": None, "status": "unknown",
                    "reason": "display name or platform id missing"}
        after = None
        pages = 0
        try:
            while pages < max_pages:
                pages += 1
                payload = self.friends_by_name(display_name,
                                               after=after)
                for row in payload.get("data") or []:
                    if str(row.get("friend_id")) == str(platform_id):
                        return {"value": True, "status": "ok",
                                "pages_read": pages}
                after = ((payload.get("paging") or {}).get("cursors")
                         or {}).get("after")
                if not after:
                    return {"value": False, "status": "ok",
                            "pages_read": pages}
            return {"value": None, "status": "unknown",
                    "reason": "name result set truncated by page cap",
                    "pages_read": pages}
        except FacebookConnectorError as exc:
            return {"value": None, "status": exc.status,
                    "reason": str(exc)[:300]}


def _profile_ref(profile):
    if profile.get("platform_id"):
        return str(profile["platform_id"])
    if profile.get("handle"):
        return profile["handle"]
    url = profile.get("profile_url") or ""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    if tail and "profile.php" not in tail:
        return tail
    return None


def fetch_facebook_surface(profile, client=None):
    """Collect the connector surface for one profile, capturing
    per-command failures instead of raising: a scan must still write
    an intel row that says WHY each field is empty."""
    client = client or FacebookProfileClient()
    surface = {"profile_info": None, "timeline": None,
               "direct_friend": {"value": None, "status": "unknown",
                                 "reason": "not attempted"},
               "errors": {}}
    ref = _profile_ref(profile)
    if not ref:
        surface["errors"]["profile_info"] = {
            "status": "error",
            "reason": "profile row has no platform_id, handle, or "
                      "usable profile_url"}
        return surface
    try:
        info = client.profile_info(ref)
        surface["profile_info"] = info
    except FacebookConnectorError as exc:
        surface["errors"]["profile_info"] = {
            "status": exc.status, "reason": str(exc)[:300]}
        info = None
    if info is not None:
        canonical_id = info.get("id") or profile.get("platform_id")
        posts = []
        after = None
        try:
            for _page in range(2):
                payload = client.timeline(canonical_id, limit=20,
                                          after=after)
                posts.extend(payload.get("posts") or [])
                after = payload.get("next_cursor")
                if not payload.get("has_next_page") or not after:
                    break
            surface["timeline"] = {"posts": posts}
        except FacebookConnectorError as exc:
            surface["errors"]["timeline"] = {
                "status": exc.status, "reason": str(exc)[:300]}
    else:
        surface["errors"]["timeline"] = dict(
            surface["errors"]["profile_info"])
    canonical_id = (info or {}).get("id") or profile.get(
        "platform_id")
    display_name = (info or {}).get("name") or profile.get(
        "display_name")
    surface["direct_friend"] = client.find_direct_friend(
        display_name, canonical_id)
    return surface


def _first_present(mapping, keys):
    for key in keys:
        value = (mapping or {}).get(key)
        if value is not None and value != "":
            return value
    return None


def _parse_birthday(raw):
    """Normalize a Facebook birthdate to ISO where possible.

    Full date -> YYYY-MM-DD; month+day -> MM-DD; year alone -> YYYY.
    Unrecognized formats are returned as the raw string so nothing
    the connector exposed is silently dropped.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = repair_text(str(raw)).strip()
    # Manual parsing (no datetime.strptime): the repo tree contains
    # a tools/calendar package that shadows the stdlib calendar
    # module strptime depends on when this file runs from the tree.
    months = {name: idx for idx, name in enumerate(
        ["january", "february", "march", "april", "may", "june",
         "july", "august", "september", "october", "november",
         "december"], start=1)}
    for full, num in list(months.items()):
        months[full[:3]] = num
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)),
                        int(m.group(3))).isoformat()
        except ValueError:
            return text
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1).lower() in months:
        try:
            return date(int(m.group(3)), months[m.group(1).lower()],
                        int(m.group(2))).isoformat()
        except ValueError:
            return text
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m and m.group(2).lower() in months:
        try:
            return date(int(m.group(3)), months[m.group(2).lower()],
                        int(m.group(1))).isoformat()
        except ValueError:
            return text
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)),
                        int(m.group(2))).isoformat()
        except ValueError:
            return text
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})", text)
    if m and m.group(1).lower() in months:
        month, day = months[m.group(1).lower()], int(m.group(2))
        try:
            date(2000, month, day)
            return f"{month:02d}-{day:02d}"
        except ValueError:
            return text
    if re.fullmatch(r"\d{4}", text):
        return text
    return text


def _country_from_location(raw):
    """Conservative country extraction from a Facebook locality.

    Only an explicit country alias or a recognized state/province/
    region segment resolves. A bare city name resolves NOTHING —
    Suffolk alone is not evidence for any one country.
    """
    if not raw:
        return None
    text = repair_text(str(raw)).strip().lower()
    parts = [p.strip(" .") for p in text.split(",") if p.strip()]
    for part in reversed(parts):
        if part in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[part]
        if part in _US_STATES:
            return "United States"
        if part in _CA_REGIONS:
            return "Canada"
        if part in _AU_REGIONS:
            return "Australia"
    if text in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[text]
    if text in _US_STATES:
        return "United States"
    if text in _CA_REGIONS:
        return "Canada"
    if text in _AU_REGIONS:
        return "Australia"
    return None


def _match_theme(text, patterns):
    found = []
    low = (text or "").lower()
    for label, pattern in patterns.items():
        if re.search(pattern, low):
            found.append(label)
    return sorted(found)


def classify_interest_signals(text_sources, own_posts_read):
    """Deterministic theme classification.

    text_sources: [{source, text, post_id?, url?}] from the profile
    bio/hobbies and the person's OWN recent posts. A theme is:
      yes     — at least one matched term, with evidence refs;
      no      — sources were readable, at least one own post was
                read, and no term matched (means: no signal in the
                scanned surface, not a claim about the person);
      unknown — no own posts were readable, so absence of terms is
                not evidence of anything.
    """
    signals = {}
    for theme, patterns in INTEL_THEME_RULES.items():
        evidence = []
        for src in text_sources:
            terms = _match_theme(src.get("text"), patterns)
            if terms:
                entry = {"source": src["source"],
                         "matched_terms": terms}
                if src.get("post_id"):
                    entry["post_id"] = src["post_id"]
                if src.get("url"):
                    entry["url"] = src["url"]
                evidence.append(entry)
        if evidence:
            status = "yes"
        elif own_posts_read > 0:
            status = "no"
        else:
            status = "unknown"
        signals[theme] = {"status": status, "evidence": evidence}
    return signals


def build_profile_intel(profile, surface):
    """Pure builder: (identity profile row, connector surface) ->
    the comm_profile_intel column values + field_status. No DB, no
    subprocess — this is the selftestable core of the scan."""
    info = surface.get("profile_info") or {}
    errors = surface.get("errors") or {}
    info_error = errors.get("profile_info")
    field_status = {}

    followers = _first_present(info, ("followers", "follower_count",
                                      "followers_count"))
    if followers is not None:
        field_status["followers"] = {
            "status": "ok", "source_command": PROFILE_INFO_CMD}
    elif info_error:
        field_status["followers"] = {
            "status": info_error["status"],
            "source_command": PROFILE_INFO_CMD,
            "reason": info_error["reason"]}
    else:
        field_status["followers"] = {
            "status": "not_exposed", "source_command": PROFILE_INFO_CMD,
            "reason": "profile info returns no followers count for a "
                      "personal profile"}

    friends_count = _first_present(info, ("friends_count",
                                          "friend_count",
                                          "total_friends"))
    if friends_count is not None:
        field_status["friends_count"] = {
            "status": "ok", "source_command": PROFILE_INFO_CMD}
    elif info_error:
        field_status["friends_count"] = {
            "status": info_error["status"],
            "source_command": PROFILE_INFO_CMD,
            "reason": info_error["reason"]}
    else:
        field_status["friends_count"] = {
            "status": "not_exposed", "source_command": PROFILE_INFO_CMD,
            "reason": "profile info returns no friends count for the "
                      "profile owner; me friends lists Brian's "
                      "friends, not the sender's"}

    mutual_raw = _first_present(info, ("mutual_friends",
                                       "common_friends"))
    mutual_friends = mutual_raw if isinstance(mutual_raw, list) \
        else None
    if mutual_friends is not None:
        field_status["mutual_friends"] = {
            "status": "ok", "source_command": PROFILE_INFO_CMD}
    elif info_error:
        field_status["mutual_friends"] = {
            "status": info_error["status"],
            "source_command": PROFILE_INFO_CMD,
            "reason": info_error["reason"]}
    else:
        field_status["mutual_friends"] = {
            "status": "not_exposed",
            "source_command": PROFILE_INFO_CMD + " / " + FRIENDS_CMD,
            "reason": "no connector command returns a common/mutual "
                      "friends list; me friends establishes only "
                      "whether the sender is Brian's direct friend"}

    direct = surface.get("direct_friend") or {}
    field_status["facebook_friend"] = {
        "status": direct.get("status", "unknown"),
        "source_command": FRIENDS_CMD,
        "value": direct.get("value"),
        "reason": direct.get(
            "reason",
            "exact friend_id match inside Brian's friends by name "
            "search" if direct.get("value") is not None else None)}

    country = None
    loc_field = None
    loc_value = None
    for key in ("current_city", "hometown"):
        if info.get(key):
            loc_field, loc_value = key, info[key]
            country = _country_from_location(loc_value)
            if country:
                break
            loc_field, loc_value = key, info[key]
    if country:
        field_status["country"] = {
            "status": "ok", "source_command": PROFILE_INFO_CMD,
            "source_field": loc_field, "source_value": loc_value,
            "basis": "explicit country or recognized state/province/"
                     "region segment in the returned locality"}
    elif info_error:
        field_status["country"] = {
            "status": info_error["status"],
            "source_command": PROFILE_INFO_CMD,
            "reason": info_error["reason"]}
    elif loc_value:
        field_status["country"] = {
            "status": "not_exposed", "source_command": PROFILE_INFO_CMD,
            "source_field": loc_field, "source_value": loc_value,
            "reason": "connector returns locality text, not a country "
                      "field, and this locality names no recognizable "
                      "country/state/province/region"}
    else:
        field_status["country"] = {
            "status": "not_public", "source_command": PROFILE_INFO_CMD,
            "reason": "profile lists no current city or hometown"}

    birthday_raw = _first_present(info, ("birthdate", "birthday",
                                         "date_of_birth"))
    birthday = _parse_birthday(birthday_raw)
    if birthday:
        field_status["birthday"] = {
            "status": "ok", "source_command": PROFILE_INFO_CMD,
            "source_value": birthday_raw}
    elif info_error:
        field_status["birthday"] = {
            "status": info_error["status"],
            "source_command": PROFILE_INFO_CMD,
            "reason": info_error["reason"]}
    else:
        field_status["birthday"] = {
            "status": "not_public", "source_command": PROFILE_INFO_CMD,
            "reason": "profile info returned no birthdate (not listed "
                      "or hidden)"}

    # Interest signals: bio + hobbies + the person's OWN posts only
    # (wall posts by other people are not the owner's themes).
    text_sources = []
    if info.get("bio"):
        text_sources.append({"source": "profile_info.bio",
                             "text": info["bio"]})
    hobbies = info.get("hobbies")
    if hobbies:
        hobby_text = " ".join(
            str(h.get("name") or h) if isinstance(h, dict) else str(h)
            for h in hobbies)
        if hobby_text.strip():
            text_sources.append({"source": "profile_info.hobbies",
                                 "text": hobby_text})
    timeline = surface.get("timeline") or {}
    posts = timeline.get("posts") or []
    owner_id = str(info.get("id") or profile.get("platform_id") or "")
    own_posts = []
    for post in posts:
        author = post.get("author_id")
        if author is not None and str(author) == owner_id:
            own_posts.append(post)
    for post in own_posts[:20]:
        caption = post.get("post_caption") or ""
        media = post.get("media_summary") or ""
        text = (caption + " " + media).strip()
        if text:
            text_sources.append({
                "source": "timeline_fetch.own_post",
                "text": text,
                "post_id": post.get("post_id"),
                "url": post.get("url")})
    signals = classify_interest_signals(text_sources, len(own_posts))
    timeline_error = errors.get("timeline")
    if timeline_error and not any(
            s["status"] == "yes" for s in signals.values()):
        field_status["interest_signals"] = {
            "status": timeline_error["status"],
            "source_command": TIMELINE_CMD,
            "reason": timeline_error["reason"],
            "own_posts_read": len(own_posts)}
    else:
        field_status["interest_signals"] = {
            "status": "ok",
            "source_command": PROFILE_INFO_CMD + " / " + TIMELINE_CMD,
            "own_posts_read": len(own_posts),
            "note": "yes requires matched-term evidence; no means no "
                    "signal in the scanned surface; unknown means no "
                    "own posts were readable"}

    return {
        "followers": followers,
        "friends_count": friends_count,
        "mutual_friends": mutual_friends,
        "country": country,
        "birthday": birthday,
        "interest_signals": signals,
        "field_status": field_status,
        "_profile_info": info,
        "_own_posts_read": len(own_posts),
        "_direct_friend": direct.get("value"),
    }


def _intel_summary(profile, intel):
    signals = intel["interest_signals"]
    tags = [f"{theme}-interest" for theme, sig in signals.items()
            if sig.get("status") == "yes"]

    def show(value, field):
        if value is not None:
            return str(value)
        status = (intel["field_status"].get(field) or {}).get(
            "status", "unknown")
        return f"unknown ({status})"

    lines = [
        f"[comm_profile_intel profile_id={profile['id']}]",
        f"Profile intel scan — {profile.get('display_name') or ''} "
        f"(facebook profile {profile.get('platform_id') or ''})",
        f"followers: {show(intel['followers'], 'followers')}; "
        f"friends: {show(intel['friends_count'], 'friends_count')}; "
        f"mutual friends: "
        f"{show(intel['mutual_friends'], 'mutual_friends')}",
        f"country: {show(intel['country'], 'country')}; "
        f"birthday: {show(intel['birthday'], 'birthday')}",
        "interests: " + "; ".join(
            f"{theme}={sig['status']}" for theme, sig in
            signals.items()),
        f"interest_tags: {', '.join(tags) if tags else '(none)'}",
        "[/comm_profile_intel]",
    ]
    return "\n".join(lines)


def _replace_intel_note(notes, profile_id, summary):
    pattern = re.compile(
        r"\[comm_profile_intel profile_id=%s\].*?"
        r"\[/comm_profile_intel\]\n?" % re.escape(str(profile_id)),
        re.DOTALL)
    base = pattern.sub("", notes or "").rstrip()
    return (base + "\n" + summary) if base else summary


def scan_profile_intel(profile_id, client=None, surface=None):
    """Run (or re-run) the intel scan for one identity profile and
    write it through to the CRM: comm_profile_intel row + a summary
    block on the person's identity_people.notes (replaced on rescan,
    never stacked) + any yes-interest tags named in that block. The
    identity_people table has no tags column, so tags live in the
    intel row's interest_signals and the note's interest_tags line —
    as data in JSONB, not prose-only."""
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM people.identity_profiles WHERE id=%s",
            (profile_id,))
        profile = cur.fetchone()
        if profile is None:
            raise ValueError(f"no identity profile {profile_id}")
        if profile["platform"] not in ("facebook", "messenger"):
            raise ValueError(
                "intel scan supports facebook/messenger profiles; "
                f"profile {profile_id} is {profile['platform']}")
        if surface is None:
            surface = fetch_facebook_surface(dict(profile),
                                             client=client)
        intel = build_profile_intel(dict(profile), surface)
        cur.execute(
            "INSERT INTO people.comm_profile_intel "
            "(profile_id, followers, friends_count, mutual_friends, "
            "country, birthday, interest_signals, field_status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
            "ON CONFLICT (profile_id) DO UPDATE SET "
            "scanned_at=now(), followers=EXCLUDED.followers, "
            "friends_count=EXCLUDED.friends_count, "
            "mutual_friends=EXCLUDED.mutual_friends, "
            "country=EXCLUDED.country, birthday=EXCLUDED.birthday, "
            "interest_signals=EXCLUDED.interest_signals, "
            "field_status=EXCLUDED.field_status, updated_at=now() "
            "RETURNING *",
            (profile_id, intel["followers"], intel["friends_count"],
             json.dumps(intel["mutual_friends"])
             if intel["mutual_friends"] is not None else None,
             intel["country"], intel["birthday"],
             json.dumps(intel["interest_signals"]),
             json.dumps(intel["field_status"])))
        row = cur.fetchone()

        info = intel.get("_profile_info") or {}
        if info.get("bio"):
            cur.execute(
                "UPDATE people.identity_profiles SET "
                "bio_current=%s, last_seen=now() WHERE id=%s",
                (info["bio"], profile_id))
            ir._snapshot_bio(cur, profile_id, info["bio"],
                             "facebook_connector:profile_info")
        if info.get("vanity_url"):
            cur.execute(
                "UPDATE people.identity_profiles SET "
                "profile_url=COALESCE(profile_url, %s) WHERE id=%s",
                (info["vanity_url"], profile_id))

        note_status = "skipped (profile has no person anchor)"
        if profile.get("person_id"):
            summary = _intel_summary(dict(profile), intel)
            cur.execute(
                "SELECT notes FROM people.identity_people WHERE id=%s",
                (profile["person_id"],))
            person = cur.fetchone()
            cur.execute(
                "UPDATE people.identity_people SET notes=%s, "
                "updated_at=now() WHERE id=%s",
                (_replace_intel_note((person or {}).get("notes"),
                                     profile_id, summary),
                 profile["person_id"]))
            note_status = "written"
        conn.commit()
    finally:
        conn.close()
    result = dict(row)
    result["crm_note"] = note_status
    print(format_profile_intel(result | {
        "display_name": profile.get("display_name"),
        "platform_id": profile.get("platform_id")}))
    return result


def pending_intel_profile_ids(limit=None):
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        sql = (
            "SELECT DISTINCT p.profile_id FROM "
            "people.comm_thread_participants p "
            "LEFT JOIN people.comm_profile_intel i "
            "ON i.profile_id = p.profile_id "
            "WHERE p.profile_id IS NOT NULL AND i.id IS NULL "
            "AND p.role <> 'owner' ORDER BY p.profile_id")
        if limit:
            sql += " LIMIT %s"
            cur.execute(sql, (limit,))
        else:
            cur.execute(sql)
        return [r["profile_id"] for r in cur.fetchall()]
    finally:
        conn.close()


def scan_pending_intel(limit=None, client=None):
    ids = pending_intel_profile_ids(limit=limit)
    results = []
    for profile_id in ids:
        try:
            results.append(scan_profile_intel(profile_id,
                                              client=client))
        except Exception as exc:  # one bad profile must not stop the queue
            print(f"  scan profile {profile_id}: FAILED "
                  f"{type(exc).__name__}: {exc}")
            results.append({"profile_id": profile_id,
                            "error": str(exc)})
    print(f"intel scans attempted: {len(ids)}; "
          f"ok: {sum(1 for r in results if 'error' not in r)}")
    return results


def get_profile_intel(profile_id):
    conn = _dict_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT i.*, p.display_name, p.platform, "
            "p.platform_id, p.handle FROM people.comm_profile_intel i "
            "JOIN people.identity_profiles p ON p.id=i.profile_id "
            "WHERE i.profile_id=%s", (profile_id,))
        return cur.fetchone()
    finally:
        conn.close()


def format_profile_intel(row):
    if row is None:
        return "profile intel: (no scan recorded)"
    signals = row.get("interest_signals") or {}
    status = row.get("field_status") or {}
    if isinstance(signals, str):
        signals = json.loads(signals)
    if isinstance(status, str):
        status = json.loads(status)

    def show(value, field):
        if value is not None:
            return str(value)
        return f"unknown ({(status.get(field) or {}).get('status', 'unknown')})"

    lines = [
        f"Profile intel — {row.get('display_name') or ''} "
        f"[profile {row['profile_id']}, "
        f"{row.get('platform') or 'facebook'} "
        f"{row.get('platform_id') or row.get('handle') or ''}]",
        f"  scanned: {row.get('scanned_at')}",
        f"  followers: {show(row.get('followers'), 'followers')}",
        f"  friends: {show(row.get('friends_count'), 'friends_count')}",
        f"  mutual friends: "
        f"{show(row.get('mutual_friends'), 'mutual_friends')}",
        f"  country: {show(row.get('country'), 'country')}",
        f"  birthday: {show(row.get('birthday'), 'birthday')}",
    ]
    for theme, sig in signals.items():
        line = f"  {theme}: {sig.get('status')}"
        ev = sig.get("evidence") or []
        if ev:
            refs = []
            for e in ev:
                ref = e.get("source", "evidence")
                if e.get("post_id"):
                    ref += f" post {e['post_id']}"
                refs.append(ref + " [" + ", ".join(
                    e.get("matched_terms") or []) + "]")
            line += " — evidence: " + "; ".join(refs)
        lines.append(line)
    return "\n".join(lines)


def show_profile_intel(profile_id):
    row = get_profile_intel(profile_id)
    if row is None:
        print(f"profile intel: no scan recorded for profile "
              f"{profile_id}")
        return None
    print(format_profile_intel(dict(row)))
    return dict(row)


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
        cur.execute("SELECT count(*) c FROM people.comm_profile_intel")
        intel_scans = cur.fetchone()["c"]
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
    print(f"profile intel scans: {intel_scans}")
    print(f"intel queue pending: {pending}")
    print("participant resolution:")
    for r in res_states:
        print(f"  {r['resolution_state']}: {r['c']}")
    return {"accounts": len(accounts), "threads": threads,
            "messages": messages, "attachments": attachments,
            "runs": runs, "intel_scans": intel_scans,
            "intel_pending": pending}


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

    # Profile-intel builder: honest field coverage on synthetic data.
    unknown_intel = build_profile_intel(
        {"id": 1, "platform_id": "111", "display_name": "Pat Example"},
        {"profile_info": {"id": "111", "name": "Pat Example",
                          "bio": "Weekend notes.",
                          "current_city": "Suffolk"},
         "timeline": {"posts": []},
         "direct_friend": {"value": None, "status": "unknown",
                           "reason": "fixture"},
         "errors": {}})
    ck("intel: followers/friends/mutual are NULL + not_exposed "
       "(connector does not expose them)",
       unknown_intel["followers"] is None
       and unknown_intel["friends_count"] is None
       and unknown_intel["mutual_friends"] is None
       and unknown_intel["field_status"]["followers"]["status"]
       == "not_exposed"
       and unknown_intel["field_status"]["friends_count"]["status"]
       == "not_exposed"
       and unknown_intel["field_status"]["mutual_friends"]["status"]
       == "not_exposed")
    ck("intel: a bare locality yields no invented country; a "
       "missing birthdate is not_public",
       unknown_intel["country"] is None
       and unknown_intel["field_status"]["country"]["status"]
       == "not_exposed"
       and unknown_intel["birthday"] is None
       and unknown_intel["field_status"]["birthday"]["status"]
       == "not_public")
    ck("intel: no readable own posts => interests unknown, "
       "never 'no'",
       unknown_intel["interest_signals"]["crypto"]["status"]
       == "unknown"
       and unknown_intel["interest_signals"]["health"]["status"]
       == "unknown")
    wall_intel = build_profile_intel(
        {"id": 2, "platform_id": "222", "display_name": "Sam Wall"},
        {"profile_info": {"id": "222", "name": "Sam Wall",
                          "bio": "General notes."},
         "timeline": {"posts": [
             {"post_id": "own1", "author_id": "222",
              "post_caption": "A quiet evening at home"},
             {"post_id": "wall1", "author_id": "999",
              "post_caption": "Bitcoin and wellness all day"}]},
         "direct_friend": {"value": False, "status": "ok"},
         "errors": {}})
    ck("intel: wall posts by others are not the owner's interest "
       "evidence",
       wall_intel["interest_signals"]["crypto"]["status"] == "no"
       and wall_intel["interest_signals"]["crypto"]["evidence"] == []
       and wall_intel["interest_signals"]["health"]["status"]
       == "no")

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

        intel_surface = {
            "profile_info": {
                "id": "42424", "name": "Renée Fournier",
                "bio": "Bitcoin educator focused on wellness and "
                       "nutrition.",
                "birthdate": "March 4, 1990",
                "current_city": "Austin, Texas",
                "vanity_url": "https://facebook.com/renee.fournier"},
            "timeline": {"posts": [
                {"post_id": "own-health",
                 "url": "https://facebook.com/posts/own-health",
                 "author_id": "42424", "owner_id": "42424",
                 "post_caption": "Morning workout and protein "
                                 "notes"},
                {"post_id": "wall-crypto", "author_id": "999",
                 "owner_id": "42424",
                 "post_caption": "Ethereum giveaway"}]},
            "direct_friend": {"value": True, "status": "ok"},
            "errors": {}}
        intel_row = scan_profile_intel(fixture_profile_id,
                                       surface=intel_surface)
        ck("intel scan writes a comm_profile_intel row",
           intel_row and intel_row["profile_id"]
           == fixture_profile_id)
        ck("intel scan: exposed country + birthday are stored",
           intel_row["country"] == "United States"
           and intel_row["birthday"] == "1990-03-04")
        ck("intel scan: unexposed counts stay NULL + not_exposed",
           intel_row["followers"] is None
           and intel_row["friends_count"] is None
           and intel_row["mutual_friends"] is None
           and intel_row["field_status"]["followers"]["status"]
           == "not_exposed")
        ck("intel scan: crypto + health are yes WITH evidence refs",
           intel_row["interest_signals"]["crypto"]["status"] == "yes"
           and intel_row["interest_signals"]["crypto"]["evidence"]
           and intel_row["interest_signals"]["health"]["status"]
           == "yes"
           and intel_row["interest_signals"]["health"]["evidence"])
        conn = _dict_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT notes FROM people.identity_people WHERE "
                "id=%s", (fixture_person_id,))
            notes = cur.fetchone()["notes"] or ""
            ck("intel scan writes the CRM summary + interest tags "
               "to the person's notes",
               "[comm_profile_intel profile_id="
               f"{fixture_profile_id}]" in notes
               and "crypto-interest" in notes
               and "health-interest" in notes)
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
                    "DELETE FROM people.identity_life_events WHERE "
                    "profile_id=%s", (fixture_profile_id,))
                cur.execute(
                    "DELETE FROM people.identity_bio_snapshots "
                    "WHERE profile_id=%s", (fixture_profile_id,))
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
    ap.add_argument("--scan-intel", nargs="?", const="pending",
                    metavar="PROFILE_ID",
                    help="scan one facebook identity profile, or "
                         "'pending' / no value for all comm "
                         "participants lacking intel")
    ap.add_argument("--scan-pending", action="store_true",
                    help="scan all comm participants lacking intel")
    ap.add_argument("--scan-limit", type=int,
                    help="cap for --scan-intel pending")
    ap.add_argument("--intel", type=int, metavar="PROFILE_ID",
                    help="print the intel card for a profile")
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
    elif args.scan_intel is not None or args.scan_pending:
        if args.scan_pending or args.scan_intel in (None, "pending"):
            scan_pending_intel(limit=args.scan_limit)
        else:
            try:
                scan_profile_intel(int(args.scan_intel))
            except ValueError:
                ap.error("--scan-intel needs a numeric PROFILE_ID "
                         "or 'pending'")
    elif args.intel:
        show_profile_intel(args.intel)
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
