#!/usr/bin/env python3
"""P5 ingestion — screenshot captures -> typed graph edges (new Vera).

Runs ON k11-alpha. Cron: hourly :45 (see p5_hourly.sh + /etc/cron.d/relationship-intel-p5).

Pipeline per file:
  1. OCR via tesseract CLI (HARD dependency; verified /usr/bin/tesseract 5.3.4
     on k11-alpha 2026-10-10. Penny is text-only (qwen2.5) — there is no
     vision model on the free ladder today, so a "Penny-vision fallback" does
     not exist; tesseract absence is a hard failure, logged loudly.)
  2. Deterministic regex extraction of name/handle pairs.
  3. Penny 7B (127.0.0.1:11438, model "penny") extraction fallback ONLY when
     regex yields zero names from non-trivial OCR text.
  4. Match-or-create people.people rows (dedupe verdicts adapted from
     tools/people_migrate/migrate_oliabo_leads.py: name must also match on
     contact hits; conflicts get a new tagged row, never a silent merge).
  5. Typed edges into people.social_connections:
     platform, relation_type (friend/follower/following), connection_name,
     connection_handle, source='field_capture:<mission_id>'.
     Per-edge confidence lives on the file manifest (people.field_capture_files
     notes) because social_connections has no notes column.

GRAPH NOT TREE: tags[] are additive — existing tags are never overwritten.

File -> mission convention: filename mission<id>_<seq>.png (e.g. mission17_01.png).
No mission id in the filename -> the newest OPEN mission. No open mission ->
file goes to needs_review/, no edges fabricated.

Intake: /home/successbrian/captures_intake/ (populated by the dumb Hatch pipe,
p5_pipe.sh). Processed files move to intake/processed/.

Usage:
  p5_ingest.py --cron            # process everything new in the intake dir
  p5_ingest.py --once FILE       # process one file (e2e / manual)
  p5_ingest.py --mission-id N --once FILE

Stdlib + psycopg2 only. Auth via ~/.pgpass.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
INTAKE_DIR = os.environ.get("P5_INTAKE_DIR", "/home/successbrian/captures_intake")
TESSERACT = "/usr/bin/tesseract"
PENNY_URL = "http://127.0.0.1:11438/v1/chat/completions"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# UI chrome that shows up in friends/followers screenshots — never a name.
NOISE_WORDS = {
    "friends", "followers", "following", "search", "follow", "message", "messages",
    "like", "likes", "comment", "comments", "share", "add friend", "people",
    "photos", "home", "menu", "cancel", "done", "see all", "see more",
    "mutual friends", "mutual", "suggested", "suggestions", "requests",
    "notifications", "profile", "timeline", "about", "groups", "events",
    "marketplace", "watch", "gaming", "memories", "saved", "pages",
    "settings", "help", "logout", "log out", "sign in", "sign up",
    "years", "year", "months", "month", "weeks", "week", "days", "day",
    "hours", "hour", "hrs", "mins", "min", "ago", "yesterday", "today",
    "public", "private", "only me", "edit", "delete", "report", "block",
    "unfriend", "unfollow", "poke", "wave",
}
HANDLE_RE = re.compile(r"@([A-Za-z0-9_][A-Za-z0-9_.]{1,29})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’.\-]*")
MISSION_FN_RE = re.compile(r"mission(\d+)", re.IGNORECASE)


def log(msg):
    print(msg, flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _conn(dbname):
    return psycopg2.connect(host="localhost", dbname=dbname, user="successbrian")


def _norm_name(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def tesseract_available():
    return os.path.isfile(TESSERACT) and os.access(TESSERACT, os.X_OK)


def ocr_image(path):
    """tesseract stdout to text. Raises if tesseract is missing."""
    if not tesseract_available():
        raise RuntimeError(
            "tesseract not found at %s — hard dependency, no vision fallback "
            "exists on the model ladder (Penny is text-only)" % TESSERACT)
    r = subprocess.run([TESSERACT, path, "stdout", "-l", "eng"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("tesseract failed on %s: %s" % (path, r.stderr.strip()[:200]))
    return r.stdout


def is_noise_line(line):
    low = line.strip().lower()
    if not low or low in NOISE_WORDS:
        return True
    if re.fullmatch(r"[\d\s,.\-+()x×]+", low):  # counts, timestamps
        return True
    return False


def extract_deterministic(text):
    """Regex-first name/handle extraction. Returns [(name, handle_or_None)]."""
    pairs = []
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if is_noise_line(line) or len(line) > 80:
            continue
        m = HANDLE_RE.search(line)
        handle = m.group(1) if m else None
        name_part = HANDLE_RE.sub(" ", line).strip(" -|·•")
        words = [w for w in WORD_RE.findall(name_part)
                 if w.lower() not in NOISE_WORDS]
        name = None
        if 2 <= len(words) <= 4 and all(w[0].isupper() or w[0] == "'" for w in words
                                        if w[0].isalpha()):
            # Title-case run: likely a display name.
            name = " ".join(words)
        elif len(words) == 1 and handle and words[0].lower() == handle.lower().replace("_", " ").replace(".", " "):
            name = None  # handle-only row; name unknown
        key = (name or "", (handle or "").lower())
        if (name or handle) and key not in seen:
            seen.add(key)
            pairs.append((name, handle))
    return pairs


def penny_extract(text):
    """Penny 7B fallback: OCR text -> name/handle pairs. Only called when
    regex found nothing."""
    prompt = (
        "You are extracting a friends/followers list from OCR text of a "
        "screenshot. Return ONLY lines of the form: Full Name | @handle "
        "(one per person). If only a handle is visible, use: ? | @handle. "
        "Skip UI words (Friends, Follow, Search, Like, menu items). "
        "No commentary, no numbering.\n\nOCR TEXT:\n" + text[:4000])
    body = json.dumps({
        "model": "penny",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(PENNY_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)
        content = out["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"penny fallback failed: {e}")
        return []
    pairs = []
    for line in content.splitlines():
        line = line.strip().strip("-*•0123456789. ")
        if "|" not in line:
            continue
        name_s, handle_s = [p.strip() for p in line.split("|", 1)]
        handle = handle_s.lstrip("@") or None
        name = None if name_s in ("?", "", "Unknown") else name_s
        if name or handle:
            pairs.append((name, handle))
    return pairs


def split_name(full):
    full = (full or "").strip()
    if not full:
        return "", ""
    parts = full.split()
    return parts[0], " ".join(parts[1:])


def add_tags(cur, person_id, new_tags):
    if not new_tags:
        return
    cur.execute(
        "UPDATE people.people SET tags = ("
        " SELECT array_agg(DISTINCT t) FROM unnest("
        "   COALESCE(tags, '{}') || %s::text[]) t)"
        " WHERE id = %s AND NOT (COALESCE(tags, '{}') @> %s::text[])",
        (list(new_tags), person_id, list(new_tags)),
    )


def match_or_create(cur, name, handle, platform, mission_id):
    """Exact-match-or-create. Handle hits are name-verified (migrate_oliabo
    verdict logic): conflict -> new tagged row, never a silent merge.
    Returns (person_id, confidence, how)."""
    first, last = split_name(name or "")
    if handle:
        cur.execute(
            "SELECT person_id, username, handle FROM people.social_profiles "
            "WHERE lower(handle) = lower(%s) OR lower(username) = lower(%s) "
            "ORDER BY id LIMIT 5",
            (handle, handle),
        )
        for prof_pid, prof_user, prof_handle in cur.fetchall():
            if not prof_pid:
                continue
            cur.execute("SELECT first_name, last_name FROM people.people WHERE id = %s",
                        (prof_pid,))
            prow = cur.fetchone()
            stored = _norm_name(((prow[0] or "") + " " + (prow[1] or "")).strip()) if prow else ""
            given = _norm_name(name or "")
            if not given or not stored or given == stored:
                add_tags(cur, prof_pid, ["field_capture"])
                return prof_pid, 0.9, "handle_match"
            # conflict: same handle, different name on record -> separate row
            log(f"handle conflict @{handle}: OCR name '{name}' vs stored '{stored}' "
                "-> new tagged row")
    if name:
        # Index-safe: hits idx_people_name_lower_concat
        # (btree on lower(first_name)||' '||lower(last_name)). The naive
        # regexp_replace version seq-scans 211M rows (caught in e2e 2026-10-10).
        cur.execute(
            "SELECT id FROM people.people "
            "WHERE (lower(first_name) || ' ' || lower(last_name)) = %s "
            "ORDER BY id LIMIT 3",
            (_norm_name(name),),
        )
        rows = cur.fetchall()
        if rows:
            add_tags(cur, rows[0][0], ["field_capture"])
            return rows[0][0], 0.75, "name_match"
    cur.execute(
        "INSERT INTO people.people (first_name, last_name, source, tags, extra_data) "
        "VALUES (%s, %s, 'field_capture', %s, %s) RETURNING id",
        (first, last,
         ["field_capture"],
         json.dumps({"platform": platform, "handle": handle,
                     "captured_from": "field_capture:%s" % mission_id})),
    )
    return cur.fetchone()[0], 0.6, "created"


def edge_exists(cur, target_pid, name, handle, relation_type, mission_id):
    cur.execute(
        "SELECT id FROM people.social_connections "
        "WHERE person_id = %s AND relation_type = %s "
        "AND source LIKE 'field_capture:%%' "
        "AND (COALESCE(connection_handle, '') = COALESCE(%s, '') "
        "     OR COALESCE(connection_name, '') = COALESCE(%s, '')) "
        "LIMIT 1",
        (target_pid, relation_type, handle or "", name or ""),
    )
    return cur.fetchone() is not None


def mission_for_file(cur, filename):
    """(mission_row_or_None, mission_id_or_None). mission_row: full row tuple."""
    m = MISSION_FN_RE.search(filename)
    if m:
        cur.execute(
            "SELECT mission_id, target_person_id, target_name, what_to_capture, "
            "platform, relation_type, status FROM people.field_capture_missions "
            "WHERE mission_id = %s",
            (int(m.group(1)),),
        )
        row = cur.fetchone()
        if row:
            return row, row[0]
    cur.execute(
        "SELECT mission_id, target_person_id, target_name, what_to_capture, "
        "platform, relation_type, status FROM people.field_capture_missions "
        "WHERE status IN ('requested', 'open', 'requested_backup') "
        "ORDER BY mission_id DESC LIMIT 1"
    )
    row = cur.fetchone()
    return (row, row[0]) if row else (None, None)


def already_processed(cur, digest):
    cur.execute("SELECT file_id FROM people.field_capture_files WHERE sha256 = %s",
                (digest,))
    return cur.fetchone() is not None


def process_file(path, mission_override=None):
    filename = os.path.basename(path)
    digest = sha256_file(path)
    with _conn("people_unified") as c:
        with c.cursor() as cur:
            if already_processed(cur, digest):
                log(f"skip (already processed): {filename}")
                return "duplicate"
            if mission_override:
                cur.execute(
                    "SELECT mission_id, target_person_id, target_name, what_to_capture, "
                    "platform, relation_type, status "
                    "FROM people.field_capture_missions WHERE mission_id = %s",
                    (mission_override,),
                )
                mrow = cur.fetchone()
                mission_id = mission_override
            else:
                mrow, mission_id = mission_for_file(cur, filename)
            if not mrow:
                log(f"no open mission for {filename} -> needs_review")
                review_dir = os.path.join(INTAKE_DIR, "needs_review")
                os.makedirs(review_dir, exist_ok=True)
                shutil.move(path, os.path.join(review_dir, filename))
                cur.execute(
                    "INSERT INTO people.field_capture_files "
                    "(mission_id, filename, sha256, status, notes) "
                    "VALUES (NULL, %s, %s, 'needs_review', %s)",
                    (filename, digest,
                     "no open mission and no mission id in filename; not ingested"),
                )
                c.commit()
                return "needs_review"
            (mid, target_pid, target_name, what, platform,
             relation_type, mstatus) = mrow
            try:
                text = ocr_image(path)
            except RuntimeError as e:
                log(f"OCR failed: {e}")
                cur.execute(
                    "INSERT INTO people.field_capture_files "
                    "(mission_id, filename, sha256, status, notes) "
                    "VALUES (%s, %s, %s, 'ocr_failed', %s)",
                    (mid, filename, digest, str(e)[:500]),
                )
                c.commit()
                return "ocr_failed"

            pairs = extract_deterministic(text)
            used_penny = False
            if not pairs and len(text.strip()) >= 20:
                log(f"regex found nothing in {filename}; trying Penny fallback")
                pairs = penny_extract(text)
                used_penny = True

            edges = 0
            confidences = []
            for name, handle in pairs:
                pid, conf, how = match_or_create(cur, name, handle, platform, mid)
                confidences.append(conf)
                if edge_exists(cur, target_pid, name, handle, relation_type, mid):
                    continue
                cur.execute(
                    "INSERT INTO people.social_connections "
                    "(person_id, platform, connection_name, connection_handle, "
                    " connection_url, relation_type, source) "
                    "VALUES (%s, %s, %s, %s, NULL, %s, %s)",
                    (target_pid, platform, name, handle, relation_type,
                     "field_capture:%s" % mid),
                )
                edges += 1

            avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
            notes = (f"mission {mid} target={target_name} ({target_pid}); "
                     f"ocr_chars={len(text)} names={len([p for p in pairs if p[0]])} "
                     f"handles={len([p for p in pairs if p[1]])} "
                     f"avg_match_confidence={avg_conf} penny_fallback={used_penny}")
            cur.execute(
                "INSERT INTO people.field_capture_files "
                "(mission_id, filename, sha256, ocr_chars, names_found, "
                " handles_found, edges_created, penny_fallback, status, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'processed', %s)",
                (mid, filename, digest, len(text),
                 len([p for p in pairs if p[0]]),
                 len([p for p in pairs if p[1]]),
                 edges, used_penny, notes),
            )
            c.commit()
    proc_dir = os.path.join(INTAKE_DIR, "processed")
    os.makedirs(proc_dir, exist_ok=True)
    shutil.move(path, os.path.join(proc_dir, filename))
    log(f"processed {filename}: {len(pairs)} extracted, {edges} edges "
        f"(mission {mid}, avg_conf={avg_conf if pairs else 0})")
    return "processed"


def run_cron():
    os.makedirs(INTAKE_DIR, exist_ok=True)
    files = sorted(
        f for f in os.listdir(INTAKE_DIR)
        if os.path.splitext(f)[1].lower() in IMG_EXTS
        and os.path.isfile(os.path.join(INTAKE_DIR, f))
    )
    if not files:
        log("intake empty; nothing to do")
        return
    counts = {}
    for f in files:
        try:
            res = process_file(os.path.join(INTAKE_DIR, f))
        except Exception as e:
            log(f"ERROR on {f}: {e}")
            res = "error"
        counts[res] = counts.get(res, 0) + 1
    log(f"cron done: {counts}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="P5 field capture ingestion")
    ap.add_argument("--cron", action="store_true", help="process the intake dir")
    ap.add_argument("--once", metavar="FILE", help="process a single file")
    ap.add_argument("--mission-id", type=int, help="override mission for --once")
    ap.add_argument("--intake-dir", help="override intake dir (testing)")
    args = ap.parse_args(argv)
    if args.intake_dir:
        global INTAKE_DIR
        INTAKE_DIR = args.intake_dir
    if args.once:
        print(process_file(args.once, mission_override=args.mission_id))
    elif args.cron:
        run_cron()
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
