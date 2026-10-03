#!/usr/bin/env python3
"""SuccessBrian OS employment stream: mailbox scan -> public.job_tracking.

PURPOSE: Mine mailbox archives for employment intel (recruiter outreach,
    job-board alerts, Brian's applications, outcomes) and upsert it into
    public.job_tracking. Deterministic classification, no chat model.
WHY: Brian 2026-10-03 - "you can run scans that feed Intel into the
    database... the ecosystem [should] scrape and seek out Intel regularly
    too and keep learning and growing daily."
CALLED BY: CLI (`python3 scan_mailbox.py [--archive-dir DIR]`); the daily
    cron `employment-daily-scan` for the incremental pass.
NOTES:
    - Archive format: one JSON per message (outlook_download.py output) with
      subject/from/to/date/body/_folder/_id_hash keys.
    - Dedupes on message_id_hash; re-runs are safe (INSERT .. ON CONFLICT
      DO NOTHING). A local state file skips already-scanned files.
    - Matching criteria (bulk-sender skip list etc.) come from
      public.employment_criteria (user_id='brian'), not hardcoded here.
    - DB writes go through ~/workspace/bin/kssh -> psql on k11; auth via
      k11 ~/.pgpass (no secrets in this file).
    - Company/pay extraction is best-effort regex; rows keep the raw
      subject so a later pass can refine them (refine, never reduce).
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KSSH = os.path.expanduser("~/workspace/bin/kssh")

SUBJECT_KW = re.compile(
    r"recruiter|hiring|job opportunity|job opening|now hiring|urgent hiring|"
    r"interview|offer letter|career opportunity|we are hiring|open position",
    re.I,
)
REJECTED_RE = re.compile(
    r"move forward with other candidates|no longer under consideration|"
    r"decided to pursue other|not selected|unfortunately.*position.*filled",
    re.I,
)
PAUSED_RE = re.compile(
    r"no further demand|on hold|position.*paused|search.*reactivat|"
    r"hiring freeze", re.I,
)
# Entertainment-news false positives ("celebrity exit interview").
SKIP_RE = re.compile(r"exit interview|celebrity|eastenders", re.I)
# Bulk-style subjects even from non-bulk senders.
BULK_SUBJECT_RE = re.compile(r"job alerts?\b|\bis hiring\b", re.I)
PAY_RE = re.compile(
    r"\$\s*[\d,]+(?:\.\d{2})?\s*(?:/hr|per hour|/hour|an hour)\b|"
    r"\$\s*\d+\s*[kK]\b|"
    r"\$\s*\d+\s*[kK]\s*[-\u2013]\s*\$\s*\d+\s*[kK]\b|"
    r"\$\s*\d{2,3},\d{3}\b"
)
REMOTE_RE = re.compile(r"\bremote\b", re.I)
FREELANCE_RE = re.compile(r"freelanc|consultant|consulting|contract\b|1099", re.I)
AI_RE = re.compile(r"\bAI\b|artificial intelligence|machine learning", re.I)
COMPANY_RE = re.compile(
    r"(?:opening|opportunity|position|hiring)\s+(?:at|with|for)\s+"
    r"([A-Z][\w&.,'\" ]{2,40}?)(?:\s*[|\-–,(]|\s*$)",
)
FROM_RE = re.compile(r"^\s*(.*?)\s*<([^>]+)>\s*$")


def kssh_psql(sql):
    """Run SQL on k11 via kssh; returns stdout."""
    b64 = base64.b64encode(sql.encode()).decode()
    cmd = ["bash", KSSH, "psql -h localhost -U successbrian "
           "-d ecosystem_central -v ON_ERROR_STOP=1 -t -A -c "
           "\"$(echo %s | base64 -d)\"" % b64]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError("kssh psql failed: " + p.stderr.strip()[-500:])
    return p.stdout


def load_criteria():
    out = kssh_psql(
        "SELECT criteria FROM public.employment_criteria "
        "WHERE user_id='brian';"
    ).strip()
    return json.loads(out.split("\n")[0]) if out else {}


def body_text(m):
    body = m.get("body") or ""
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", text)


def parse_from(frm):
    m = FROM_RE.match(frm or "")
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip()
    return (frm or "").strip(), ""


def sql_lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def classify(msg, bulk_skips):
    """Return a lead dict or None."""
    subject = (msg.get("subject") or "").strip()
    if not subject:
        return None
    if SKIP_RE.search(subject):
        return None
    frm = msg.get("from") or ""
    frm_l = frm.lower()
    is_bulk = any(s in frm_l for s in bulk_skips) or bool(
        BULK_SUBJECT_RE.search(subject))
    folder = msg.get("_folder") or ""
    text = subject + " " + body_text(msg)
    h = msg.get("_id_hash") or hashlib.sha256(
        (frm + subject).encode()).hexdigest()

    # Outcome detection rides on any folder.
    if REJECTED_RE.search(text):
        status, astatus = "open", "rejected"
    elif PAUSED_RE.search(text):
        status, astatus = "open", "paused"
    elif folder == "sentitems" and SUBJECT_KW.search(subject):
        status, astatus = "open", "applied"
    elif not SUBJECT_KW.search(subject):
        return None
    else:
        status, astatus = "open", "lead"

    if folder == "sentitems":
        source = "brian_outbound"
    elif is_bulk:
        source = "job_board_alert"
    else:
        source = "recruiter_email"

    pay_m = PAY_RE.search(text)
    remote = bool(REMOTE_RE.search(text))
    freelance = bool(FREELANCE_RE.search(text))
    cname, cemail = parse_from(frm)
    comp_m = COMPANY_RE.search(subject)
    company = comp_m.group(1).strip() if comp_m else ""

    if freelance and AI_RE.search(text):
        track = "freelance_ai"
    elif remote and not freelance:
        track = "crew2_replacement"
    else:
        track = "other"

    etype = "freelance" if freelance else "w2"
    next_action = None
    if source == "recruiter_email" and astatus == "lead":
        next_action = "Review and reply if fit"
    elif astatus == "paused":
        next_action = "Send updated CV + rate range when asked"

    return {
        "title": subject[:200],
        "company": company[:120],
        "status": status,
        "source": source,
        "source_detail": frm[:200],
        "contact_name": cname[:120],
        "contact_email": cemail[:200],
        "pay_range": pay_m.group(0)[:60] if pay_m else "",
        "remote": remote,
        "employment_type": etype,
        "track": track,
        "application_status": astatus,
        "next_action": next_action,
        "message_id_hash": h,
        "notes": ("folder=" + folder) if folder else "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-dir",
                    default=os.path.expanduser(
                        "~/workspace/outlook-mail-download/"
                        "archive-brian.lathe/cur"))
    ap.add_argument("--limit", type=int, default=0,
                    help="max files to scan (0 = all)")
    args = ap.parse_args()

    arch = args.archive_dir
    state_file = os.path.join(os.path.dirname(arch.rstrip("/")),
                              ".scan-state.json")
    scanned = set()
    if os.path.exists(state_file):
        scanned = set(json.load(open(state_file)))

    criteria = load_criteria()
    bulk_skips = [s.lower() for s in
                  criteria.get("bulk_senders_skip", [])]

    files = sorted(f for f in os.listdir(arch) if f.endswith(".json"))
    if args.limit:
        files = files[:args.limit]
    leads, seen_files = [], []
    for fn in files:
        path = os.path.join(arch, fn)
        try:
            msg = json.load(open(path))
        except Exception:
            continue
        h = msg.get("_id_hash") or fn[:-5]
        if h in scanned:
            continue
        scanned.add(h)
        seen_files.append(h)
        lead = classify(msg, bulk_skips)
        if lead:
            leads.append(lead)

    print("scanned %d new files, %d employment leads" % (len(seen_files),
                                                         len(leads)))

    if leads:
        vals = []
        for l in leads:
            vals.append("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)" % (
                sql_lit(l["title"]), sql_lit(l["company"]),
                sql_lit(l["status"]), sql_lit(l["source"]),
                sql_lit(l["source_detail"]), sql_lit(l["contact_name"]),
                sql_lit(l["contact_email"]), sql_lit(l["pay_range"]),
                "true" if l["remote"] else "false",
                sql_lit(l["employment_type"]), sql_lit(l["track"]),
                sql_lit(l["application_status"]), sql_lit(l["next_action"]),
                sql_lit(l["message_id_hash"]), sql_lit(l["notes"]),
            ))
        sql = (
            "INSERT INTO public.job_tracking (title, company, status, source,"
            " source_detail, contact_name, contact_email, pay_range, remote,"
            " employment_type, track, application_status, next_action,"
            " message_id_hash, notes) VALUES "
            + ",".join(vals) +
            " ON CONFLICT (message_id_hash) WHERE message_id_hash IS NOT NULL"
            " DO NOTHING;"
        )
        out = kssh_psql(sql)
        print("upsert done:", out.strip().split("\n")[-1] if out.strip() else "ok")

    json.dump(sorted(scanned), open(state_file, "w"))
    print("state saved: %d files scanned total" % len(scanned))


if __name__ == "__main__":
    main()
