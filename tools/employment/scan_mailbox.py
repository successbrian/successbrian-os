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
    - Matching criteria (bulk-sender skip list, pay floor, AI target, etc.)
      come from public.employment_criteria (user_id='brian'), not hardcoded
      here.
    - DB writes go through ~/workspace/bin/kssh -> psql on k11; auth via
      k11 ~/.pgpass (no secrets in this file).
    - Company/pay extraction is best-effort regex; rows keep the raw
      subject so a later pass can refine them (refine, never reduce).
    - Learnings baked in 2026-10-04 (from the Project Blue Indeed match):
      pay is normalized to hourly + annual numbers so rows can be compared
      against the floor/target without a human doing the math; every lead
      gets a deterministic tiered verdict (target | fallback | below_bar)
      instead of a binary worth-eyes call; masked employer names
      ("Project Blue", "Confidential" — staffing-agency placeholders) are
      flagged as company_confidence='masked' rather than stored as if real;
      job-board *match/recommendation* emails ("matches your profile",
      "could be a match") are detected as job_board_alert leads even when
      the subject has no classic hiring keyword; Indeed profile-block
      staleness ("has not been updated in over a year", "minimum base pay:
      not provided") is captured in profile_flags because a stale profile
      makes the board's matches noisy; and a gaps checklist records what
      the posting did NOT say (company, pay, hours, Idemia fit) so a
      briefing can say what it doesn't know, not just what it saw.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess

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
PAY_AMT = r"\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*[kK]?"
PAY_PER = (r"(?:\s*(?:/|per|a|an)\s*(?:year|yr|hour|hr)|hourly|annually"
           r"|\s*a\s*year)?")
PAY_RE = re.compile(
    PAY_AMT + r"\s*[-\u2013\u2014]\s*" + PAY_AMT + PAY_PER
    + r"|" + PAY_AMT + PAY_PER, re.I)
REMOTE_RE = re.compile(r"\bremote\b", re.I)
FREELANCE_RE = re.compile(r"freelanc|consultant|consulting|contract\b|1099", re.I)
AI_RE = re.compile(r"\bAI\b|artificial intelligence|machine learning", re.I)
COMPANY_RE = re.compile(
    r"(?:opening|opportunity|position|hiring)\s*:?\s+(?:at|with|for)\s+"
    r"([A-Z][\w&.,'\" ]{2,40}?)(?:\s*[|\-–,(]|\s*$)",
)
FROM_RE = re.compile(r"^\s*(.*?)\s*<([^>]+)>\s*$")
# Job-board match/recommendation emails: "It looks like your background
# could be a match", "New jobs that match your profile", "Jobs like this".
JOBMATCH_RE = re.compile(
    r"could be a match|matches? your profile|job matches?|"
    r"new jobs (?:for|like) you|recommended jobs?|jobs? (?:you may|you'll) "
    r"like|more jobs like this", re.I)
# Known job-board sender domains (for gating JOBMATCH_RE on body text).
JOBBOARD_RE = re.compile(
    r"indeed|linkedin|glassdoor|ziprecruiter|monster|careerbuilder|"
    r"dice\.com|wellfound|hired\.com", re.I)
# Staffing-agency masked employer names: placeholders, not real companies.
MASKED_EMPLOYER_RE = re.compile(
    r"^\s*(?:project|code)[\s\-_]*[a-z0-9]+\s*$|"
    r"^\s*confidential(?:\s+employer)?\s*$|"
    r"^\s*a\s+(?:leading|top|growing|well[\s\-]known)\b", re.I)
# Schedule evidence: if none found, hours are a gap.
SCHEDULE_RE = re.compile(
    r"shift|schedule|hours|full[\s\-]time|part[\s\-]time|"
    r"mon(?:day)?\s*[-–]\s*fri|\d{1,2}\s*(?:am|pm)\s*[-–]", re.I)
# Indeed profile block staleness markers.
PROFILE_STALE_RE = re.compile(r"has not been updated in over a year", re.I)
NOPAY_RE = re.compile(r"minimum base pay[^\n]{0,60}not provided", re.I)


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


def body_lines(m):
    """Body as stripped lines (tags become newlines); for card-format
    employer extraction."""
    body = m.get("body") or ""
    text = re.sub(r"<[^>]+>", "\n", body)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


CARD_SKIP_RE = re.compile(
    r"salary|job type|work setting|benefits|united states|full[\s\-]time|"
    r"part[\s\-]time|responsive employer|view job|apply now", re.I)
CARD_NAME_RE = re.compile(r"^[A-Z][\w&.,'\- ]{1,40}$")


def company_from_card(lines, title):
    """Job-board card format: '<Role>\\n<Company>\\n<Location>'. Find the
    body line containing the role title, then take the next line that
    looks like a company name."""
    hint = JOBMATCH_RE.sub("", title or "")
    # Drop boilerplate up to the last colon/dash: "New job matches for
    # you: Customer Success Onboarding Specialist" -> the role itself.
    hint = re.split(r"[:\-–—]", hint)[-1].strip(" :-").lower()
    if not hint:
        return ""
    for i, ln in enumerate(lines[:-1]):
        # Only title-ish lines count (a sentence that merely mentions the
        # role is not the card title); the company is the next line.
        if hint in ln.lower() and len(ln) <= len(hint) + 10:
            nxt = lines[i + 1]
            if (CARD_NAME_RE.match(nxt) and not CARD_SKIP_RE.search(nxt)
                    and nxt.lower() != hint):
                return nxt
    return ""


def parse_from(frm):
    m = FROM_RE.match(frm or "")
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip()
    return (frm or "").strip(), ""


def sql_lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def parse_money(tok):
    """'$74,000' -> 74000.0 ; '$50K' -> 50000.0 ; None on junk."""
    t = tok.replace("$", "").replace(",", "").strip()
    mult = 1
    if t[-1:] in "kK":
        mult = 1000
        t = t[:-1]
    try:
        return float(t.strip()) * mult
    except (ValueError, IndexError):
        return None


def normalize_pay(snippet):
    """Best-effort pay -> {'hourly_low','hourly_high','annual_low',
    'annual_high'}. Annual assumed when the period is annual or unstated
    (salary postings dominate); hourly only when the text says so."""
    out = {"hourly_low": None, "hourly_high": None,
           "annual_low": None, "annual_high": None}
    if not snippet:
        return out
    vals = [v for v in (parse_money(t) for t in
                        re.findall(r"\$\s*[\d,]+(?:\.\d{2})?\s*[kK]?",
                                   snippet)) if v]
    if not vals:
        return out
    low, high = min(vals), max(vals)
    tl = snippet.lower()
    is_annual = bool(re.search(r"a year|per year|annually|/yr\b|yearly|"
                               r"\bsalary\b", tl))
    is_hourly = bool(re.search(r"/hr\b|per hour|/hour|an hour|hourly", tl))
    if is_hourly and not is_annual:
        out["hourly_low"], out["hourly_high"] = low, high
        out["annual_low"], out["annual_high"] = low * 2080, high * 2080
    else:
        out["annual_low"], out["annual_high"] = low, high
        out["hourly_low"], out["hourly_high"] = low / 2080, high / 2080
    return out


def company_confidence_for(company):
    """'parsed' | 'masked' (staffing placeholder) | 'none'."""
    if not company:
        return "none"
    if MASKED_EMPLOYER_RE.search(company):
        return "masked"
    return "parsed"


def profile_flags_for(text):
    """Indeed profile-block quality signals; stale profile -> noisy matches."""
    flags = []
    if PROFILE_STALE_RE.search(text):
        flags.append("profile_stale")
    if NOPAY_RE.search(text):
        flags.append("no_min_pay")
    return flags


def gaps_for(lead, text, criteria):
    """What the posting did NOT say. Briefings should name these gaps
    explicitly instead of presenting a partial picture as complete."""
    gaps = []
    if lead["company_confidence"] != "parsed":
        gaps.append("company_unknown")
    if lead["pay_annual_low"] is None:
        gaps.append("pay_unknown")
    if not SCHEDULE_RE.search(text):
        gaps.append("hours_unknown")
    if lead["verdict"] in ("target", "fallback"):
        gaps.append("idemia_fit_unconfirmed")
    if (lead["verdict"] == "fallback"
            and criteria.get("w2_replacement", {})
            .get("crew2_pay_hourly_usd") is None):
        gaps.append("crew2_pay_comparison_unverified")
    return gaps


def verdict_for(lead, criteria):
    """Tiered discovery verdict, deterministic from the criteria row:
    'target'    = meets the bar to act on (100k+ AI remote W2, or the
                  freelance AI Applied Engineer track).
    'fallback'  = remote + clears the $24/hr floor but is a lateral move
                  (below the AI/pay bar) — worth eyes, not a move.
    'below_bar' = fails the floor or isn't a remote/freelance fit.
    """
    w2 = criteria.get("w2_replacement", {})
    floor = w2.get("pay_floor_hourly_usd", 24)
    ai_target = w2.get("ai_target_annual_usd", 100000)
    if lead["track"] == "freelance_ai":
        return "target"
    if (lead["ai_role"] and lead["remote"]
            and lead["pay_annual_low"] is not None
            and lead["pay_annual_low"] >= ai_target):
        return "target"
    if (lead["remote"] and lead["pay_hourly_low"] is not None
            and lead["pay_hourly_low"] >= floor):
        return "fallback"
    return "below_bar"


def classify(msg, bulk_skips, criteria=None):
    """Return a lead dict or None."""
    criteria = criteria or {}
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
    body = body_text(msg)
    text = subject + " " + body
    h = msg.get("_id_hash") or hashlib.sha256(
        (frm + subject).encode()).hexdigest()

    # Job-board match/recommendation emails ("could be a match", "matches
    # your profile") rarely carry classic hiring keywords in the subject.
    # Trust the phrasing on the subject; on the body only when the sender
    # is a known job board (avoids newsletter false positives).
    is_jobmatch = bool(JOBMATCH_RE.search(subject)) or (
        bool(JOBMATCH_RE.search(body)) and bool(JOBBOARD_RE.search(frm)))

    # Outcome detection rides on any folder.
    if REJECTED_RE.search(text):
        status, astatus = "open", "rejected"
    elif PAUSED_RE.search(text):
        status, astatus = "open", "paused"
    elif folder == "sentitems" and SUBJECT_KW.search(subject):
        status, astatus = "open", "applied"
    elif (not SUBJECT_KW.search(subject)
            and not COMPANY_RE.search(subject) and not is_jobmatch):
        # A subject that explicitly names a hiring company ("... opening
        # at Acme Corp") is employment content even without a classic
        # hiring keyword.
        return None
    else:
        status, astatus = "open", "lead"

    if folder == "sentitems":
        source = "brian_outbound"
    elif is_bulk or is_jobmatch:
        source = "job_board_alert"
    else:
        source = "recruiter_email"

    pay_m = PAY_RE.search(text)
    pay_snippet = ""
    if pay_m:
        # Include trailing text so the pay period ("a year", "/hour")
        # stays attached to the amount for normalization.
        pay_snippet = text[pay_m.start():pay_m.end() + 40]
    pay_norm = normalize_pay(pay_snippet)
    remote = bool(REMOTE_RE.search(text))
    freelance = bool(FREELANCE_RE.search(text))
    ai_role = bool(AI_RE.search(text))
    cname, cemail = parse_from(frm)
    comp_m = COMPANY_RE.search(subject)
    if comp_m:
        company = comp_m.group(1).strip()
    else:
        # Job-board cards print "<Role>\n<Company>\n<Location>" lines.
        company = company_from_card(body_lines(msg), subject)
    conf = company_confidence_for(company)

    if freelance and ai_role:
        track = "freelance_ai"
    elif remote and not freelance:
        track = "crew2_replacement"
    else:
        track = "other"

    lead = {
        "title": subject[:200],
        "company": company[:120],
        "status": status,
        "source": source,
        "source_detail": frm[:200],
        "contact_name": cname[:120],
        "contact_email": cemail[:200],
        "pay_range": pay_m.group(0)[:60] if pay_m else "",
        "pay_hourly_low": pay_norm["hourly_low"],
        "pay_hourly_high": pay_norm["hourly_high"],
        "pay_annual_low": pay_norm["annual_low"],
        "pay_annual_high": pay_norm["annual_high"],
        "remote": remote,
        "ai_role": ai_role,
        "company_confidence": conf,
        "employment_type": "freelance" if freelance else "w2",
        "track": track,
        "application_status": astatus,
        "next_action": None,
        "message_id_hash": h,
        "notes": ("folder=" + folder) if folder else "",
    }
    lead["verdict"] = verdict_for(lead, criteria)
    lead["gaps"] = ",".join(gaps_for(lead, text, criteria))
    lead["profile_flags"] = ",".join(profile_flags_for(text))

    etype = lead["employment_type"]
    if source == "recruiter_email" and astatus == "lead":
        lead["next_action"] = "Review and reply if fit"
    elif astatus == "paused":
        lead["next_action"] = "Send updated CV + rate range when asked"
    elif lead["verdict"] == "fallback" and astatus == "lead":
        lead["next_action"] = "Fallback only: file, do not chase unless remote escape hatch needed"

    return lead


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
        lead = classify(msg, bulk_skips, criteria)
        if lead:
            leads.append(lead)

    print("scanned %d new files, %d employment leads" % (len(seen_files),
                                                         len(leads)))

    if leads:
        # Batch the upserts so no single kssh argv element exceeds the
        # kernel's max per-arg length (ARG_MAX / MAX_ARG_STRLEN).
        chunk = 40
        for i in range(0, len(leads), chunk):
            vals = []
            for l in leads[i:i + chunk]:
                vals.append(
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s)" % (
                        sql_lit(l["title"]), sql_lit(l["company"]),
                        sql_lit(l["status"]), sql_lit(l["source"]),
                        sql_lit(l["source_detail"]), sql_lit(l["contact_name"]),
                        sql_lit(l["contact_email"]), sql_lit(l["pay_range"]),
                        sql_lit(l["pay_hourly_low"]),
                        sql_lit(l["pay_hourly_high"]),
                        sql_lit(l["pay_annual_low"]),
                        sql_lit(l["pay_annual_high"]),
                        "true" if l["remote"] else "false",
                        "true" if l["ai_role"] else "false",
                        sql_lit(l["company_confidence"]),
                        sql_lit(l["employment_type"]), sql_lit(l["track"]),
                        sql_lit(l["application_status"]),
                        sql_lit(l["next_action"]),
                        sql_lit(l["message_id_hash"]), sql_lit(l["notes"]),
                        sql_lit(l["profile_flags"]), sql_lit(l["gaps"]),
                        sql_lit(l["verdict"]),
                    ))
            sql = (
                "INSERT INTO public.job_tracking (title, company, status,"
                " source, source_detail, contact_name, contact_email,"
                " pay_range, pay_hourly_low, pay_hourly_high, pay_annual_low,"
                " pay_annual_high, remote, ai_role, company_confidence,"
                " employment_type, track, application_status, next_action,"
                " message_id_hash, notes, profile_flags, gaps, verdict)"
                " VALUES " + ",".join(vals) +
                " ON CONFLICT (message_id_hash) WHERE message_id_hash"
                " IS NOT NULL DO NOTHING;"
            )
            out = kssh_psql(sql)
            print("upsert batch %d-%d done: %s" % (
                i + 1, min(i + chunk, len(leads)),
                out.strip().split("\n")[-1] if out.strip() else "ok"))

    json.dump(sorted(scanned), open(state_file, "w"))
    print("state saved: %d files scanned total" % len(scanned))


if __name__ == "__main__":
    main()
