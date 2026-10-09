#!/usr/bin/env python3
"""SuccessBrian OS employment stream: AI entity extraction -> people_unified.

PURPOSE: For recruiter/outbound employment emails already in
    public.job_tracking, use LOCAL models (Penny 7B first, Morpheus 14B on
    failure) to extract person/company/role/pay, then upsert people into
    people.people and hiring companies into lead_discovery.companies
    (people_unified DB), and fill gaps on the job_tracking row.
WHY: Brian 2026-10-03 - "as it discovers company names and people names, it
    populates data into people_unified. use existing tables." + "use penny
    and Morpheus models for ai support". No cloud models, no per-token cost
    (his hardware principle).
CALLED BY: CLI (`python3 extract_entities.py [--archive-dir DIR]
    [--limit N]`); runs after scan_mailbox.py, also from the daily cron.
NOTES:
    - Penny (:11438) does the extraction; Morpheus (:11437) is the fallback
      when Penny's output isn't valid JSON. Both reached via kssh -> curl
      on k11 (no port forwards, no secrets).
    - people.people dedup follows Brian's migration rule: an email match
      requires a name match to merge; mismatches go to quarantine (printed
      + saved), never silently merged.
    - Idempotent: rows already enriched (company filled + extracted_at set
      in notes) are skipped.
    - Staffing-agency placeholder employers ("Project Blue", "Confidential"
      — flagged by Penny as company_is_placeholder) are never inserted
      into lead_discovery.companies; the job_tracking row is marked
      company_confidence='masked' instead (learning 2026-10-04).
    - Extracted schedule/hours info is appended to the tracking row's notes
      and clears the hours_unknown gap the scan recorded.
    - Slow-model resilience (2026-10-09): per-row model calls are wrapped so
      one timeout can't kill the run; curl -m 240 / subprocess timeout 300
      because Penny/Morpheus on CPU can take 90s+ per extraction prompt.
      WHY: before this, a single slow Morpheus call raised an unhandled
      RuntimeError and the 600+ row enrichment backlog never drained.
"""
import argparse
import base64
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
KSSH = os.path.expanduser("~/workspace/bin/kssh")

PENNY_URL = "http://127.0.0.1:11438/v1/chat/completions"
MORPHEUS_URL = "http://127.0.0.1:11437/v1/chat/completions"

PROMPT = (
    "Extract job details from the email below. Reply with ONLY "
    "a JSON object, no other text. Keys: company (hiring company or "
    "null), company_is_placeholder (true if the company name looks like "
    "a staffing-agency placeholder such as 'Project Blue', "
    "'Confidential', or 'A leading company' — otherwise false), "
    "role (job title or null), pay (pay range string or null), "
    "location (city/state or null), remote (true/false/null), "
    "schedule (work hours/shift info or null), "
    "required_skills (array of {{\"skill\": name, \"required_level\": "
    "\"high\" if the posting demands strong/expert/senior/5+ years, else "
    "\"stated\"}} — every technical skill, tool, or domain the posting "
    "asks for), "
    "skill_gaps (array of {{\"skill\": name, \"required_level\": "
    "\"high\"/\"stated\", \"gap_kind\": \"underqualified\"}} — the "
    "subset of required_skills where the posting wants MORE than Brian "
    "has, judged against BRIAN'S PROFILE below), "
    "coding_fit (\"vibe_fit\" if the work is greenfield builds, workflow "
    "automation, local AI deploys, or consulting/audits; "
    "\"hand_code_heavy\" if it demands strong hand-written code in "
    "someone else's production codebase; \"mixed\" if both; null if the "
    "role is not technical).\n\n"
    "BRIAN'S PROFILE: {profile}\n\n"
    "Subject: {subject}\n\nBody:\n{body}"
)


def load_profile():
    """Compact skill profile from the criteria row, injected into Penny's
    prompt so fit grading knows Brian is a developing vibe coder."""
    try:
        out = kssh_psql(
            "ecosystem_central",
            "SELECT criteria->'freelance_ai'->>'coding_profile', "
            "criteria->'skills' FROM public.employment_criteria "
            "WHERE user_id='brian';").strip().split("\n")[0]
        prof, skills = out.split("|", 1)
        return (prof or "") + " Skill levels: " + skills
    except Exception:
        return ("Vibe coder, developing at hand-writing code.")


def kssh(cmd):
    p = subprocess.run(["bash", KSSH, cmd], capture_output=True, text=True,
                       timeout=300)
    if p.returncode != 0:
        raise RuntimeError("kssh failed: " + p.stderr.strip()[-300:])
    return p.stdout


def kssh_psql(db, sql):
    b64 = base64.b64encode(sql.encode()).decode()
    return kssh(
        "psql -h localhost -U successbrian -d %s -v ON_ERROR_STOP=1 -t -A "
        "-c \"$(echo %s | base64 -d)\"" % (db, b64))


def model_extract(url, subject, body, profile):
    payload = {
        "model": url.split("/")[3] if False else "local",
        "messages": [{"role": "user",
                      "content": PROMPT.format(subject=subject[:300],
                                              body=body[:1500],
                                              profile=profile[:800])}],
        "temperature": 0.1,
        "max_tokens": 600,
        "stream": False,
    }
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    out = kssh(
        "echo %s | base64 -d | curl -s -m 240 -X POST %s "
        "-H 'Content-Type: application/json' -d @-" % (b64, url))
    try:
        data = json.loads(out)
        text = data["choices"][0]["message"]["content"]
    except Exception:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        ent = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(ent, dict):
        return None
    return ent


def sql_lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def split_name(full):
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def upsert_person(ent, source_note):
    email = (ent.get("person_email") or "").strip().lower()
    if not email or "@" not in email:
        return ("skipped", "no email")
    name = (ent.get("person_name") or "").strip()
    first, last = split_name(name)

    existing = kssh_psql(
        "people_unified",
        "SELECT id, first_name, last_name FROM people.people "
        "WHERE lower(primary_email) = %s LIMIT 1;" % sql_lit(email)
    ).strip()
    tag_sql = ("tags = array(select distinct unnest("
               "coalesce(tags,'{}') || '{recruiter,employment}'))")
    extra = json.dumps({"employment": {
        "company": ent.get("company"), "role": ent.get("role"),
        "source": source_note}})
    if existing:
        pid, ef, el = existing.split("|")
        ename = (ef + " " + el).strip().lower()
        if name and ename and name.lower() != ename and ef:
            return ("quarantine",
                    "email %s: '%s' vs existing '%s'" % (email, name, ename))
        kssh_psql("people_unified",
                  "UPDATE people.people SET %s, "
                  "extra_data = coalesce(extra_data,'{}') || %s::jsonb, "
                  "occupation = coalesce(nullif(occupation,''), 'recruiter') "
                  "WHERE id = %s;" % (tag_sql, sql_lit(extra), pid))
        return ("merged", "id " + pid)
    kssh_psql("people_unified",
              "INSERT INTO people.people (first_name, last_name, "
              "primary_email, tags, occupation, source, extra_data) VALUES "
              "(%s,%s,%s,'{recruiter,employment}','recruiter',"
              "'employment_scan',%s::jsonb);"
              % (sql_lit(first), sql_lit(last), sql_lit(email),
                 sql_lit(extra)))
    return ("inserted", email)


def upsert_company(ent, contact_email, mhash=None):
    company = (ent.get("company") or "").strip()
    if not company:
        return ("skipped", "no company")
    # Staffing-agency placeholder names ("Project Blue", "Confidential")
    # are not real companies — never insert them into the companies
    # table; mark the tracking row instead.
    if ent.get("company_is_placeholder"):
        if mhash:
            kssh_psql("ecosystem_central",
                      "UPDATE public.job_tracking SET company_confidence = "
                      "'masked' WHERE message_id_hash = %s;" % sql_lit(mhash))
        return ("skipped", "placeholder employer: " + company[:40])
    existing = kssh_psql(
        "people_unified",
        "SELECT id, contact_email FROM lead_discovery.companies "
        "WHERE lower(company_name) = lower(%s) LIMIT 1;" % sql_lit(company)
    ).strip()
    if existing:
        cid, cemail = existing.split("|")
        set_email = (", contact_email = %s" % sql_lit(contact_email)
                     if contact_email and not cemail else "")
        kssh_psql("people_unified",
                  "UPDATE lead_discovery.companies SET is_hiring = true, "
                  "last_seen_at = now()%s WHERE id = %s;"
                  % (set_email, cid))
        return ("merged", "id " + cid)
    kssh_psql("people_unified",
              "INSERT INTO lead_discovery.companies (company_name, "
              "is_hiring, contact_email, source_type) VALUES (%s, true, %s,"
              " 'employment_scan');"
              % (sql_lit(company), sql_lit(contact_email or "")))
    return ("inserted", company)


def merge_skill_grades(mhash, ent, track, source):
    """Merge Penny's skill grading with the deterministic baseline from
    grade_skills.py (union by skill; Penny's required_level/gap_kind wins
    on conflict). Writes skill_gaps/required_skills/coding_fit and any new
    gap signals. Returns the coding_fit written."""
    try:
        cur = kssh_psql(
            "ecosystem_central",
            "SELECT id, coalesce(skill_gaps,'[]')::text, "
            "coalesce(required_skills,'[]')::text, coalesce(coding_fit,'') "
            "FROM public.job_tracking WHERE message_id_hash = %s;"
            % sql_lit(mhash)).strip().split("\n")[0].split("|", 3)
        jid, cur_gaps_s, cur_req_s, cur_fit = cur
    except Exception:
        return None
    try:
        cur_gaps = json.loads(cur_gaps_s)
        cur_req = json.loads(cur_req_s)
    except Exception:
        cur_gaps, cur_req = [], []
    p_gaps = ent.get("skill_gaps") or []
    p_req = ent.get("required_skills") or []
    if not isinstance(p_gaps, list):
        p_gaps = []
    if not isinstance(p_req, list):
        p_req = []

    def norm(items):
        out = {}
        for it in items:
            if isinstance(it, dict) and it.get("skill"):
                out[str(it["skill"]).lower()] = it
        return out

    req = norm(cur_req)
    req.update(norm(p_req))  # Penny's read of the full body wins
    gaps = norm(cur_gaps)
    gaps.update(norm(p_gaps))
    coding_fit = (ent.get("coding_fit") if ent.get("coding_fit") in
                  ("vibe_fit", "hand_code_heavy", "mixed")
                  else (cur_fit or None))
    if not p_gaps and not p_req and not ent.get("coding_fit"):
        return coding_fit  # Penny found nothing new; keep baseline
    kssh_psql(
        "ecosystem_central",
        "UPDATE public.job_tracking SET skill_gaps = %s::jsonb, "
        "required_skills = %s::jsonb, coding_fit = %s, updated_at = now() "
        "WHERE id = %s;" % (sql_lit(json.dumps(list(gaps.values()))),
                            sql_lit(json.dumps(list(req.values()))),
                            sql_lit(coding_fit), jid))
    new_gaps = [g for g in gaps.values()
                if str(g.get("skill", "")).lower()
                not in norm(cur_gaps)]
    if new_gaps:
        vals = ",".join(
            "(%s,%s,%s,%s,%s,%s)" % (
                jid, sql_lit(g["skill"]),
                sql_lit(g.get("required_level")), sql_lit(g.get("gap_kind")),
                sql_lit(track), sql_lit(source)) for g in new_gaps)
        kssh_psql(
            "ecosystem_central",
            "INSERT INTO public.skill_gap_signals (job_tracking_id, skill, "
            "required_level, gap_kind, track, source) VALUES " + vals +
            " ON CONFLICT (job_tracking_id, skill) DO NOTHING;")
    return coding_fit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-dir",
                    default=os.path.expanduser(
                        "~/workspace/outlook-mail-download/"
                        "archive-brian.lathe/cur"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profile = load_profile()

    rows = kssh_psql(
        "ecosystem_central",
        "SELECT message_id_hash, title FROM public.job_tracking "
        "WHERE source IN ('recruiter_email','brian_outbound') "
        "AND extracted_at IS NULL "
        "AND message_id_hash IS NOT NULL ORDER BY id;"
    ).strip().split("\n")
    rows = [r for r in rows if r.strip()]
    if args.limit:
        rows = rows[:args.limit]
    print("rows needing enrichment: %d" % len(rows))

    # Build the hash->archive-file index ONCE up front. The old code did a
    # full os.listdir + json.load over ~22k files for EVERY row, which made
    # each row take minutes (found 2026-10-03 when a 306-row backlog was
    # effectively unprocessable). One pass here, O(1) lookups below.
    h2path = {}
    files = [f for f in os.listdir(args.archive_dir) if f.endswith(".json")]
    print("indexing %d archive files..." % len(files))
    for fn in files:
        p = os.path.join(args.archive_dir, fn)
        try:
            m = json.load(open(p))
        except Exception:
            continue
        h = m.get("_id_hash") or fn[:-5]
        if h and h not in h2path:
            h2path[h] = p
    print("indexed %d messages" % len(h2path))

    stats = {"person_inserted": 0, "person_merged": 0, "company_inserted": 0,
             "company_merged": 0, "quarantine": 0, "skipped": 0,
             "penny_ok": 0, "morpheus_ok": 0, "failed": 0}
    quarantine = []

    for i, row in enumerate(rows, 1):
        mhash, title = row.split("|", 1)
        # look up the archived message body
        body, subject, from_email, header_name = "", title, "", ""
        p = h2path.get(mhash)
        if p:
            try:
                m = json.load(open(p))
                subject = m.get("subject") or title
                b = m.get("body") or ""
                body = re.sub(r"\s+", " ",
                              re.sub(r"<[^>]+>", " ", b))[:2000]
                frm = m.get("from") or ""
                fm = re.search(r"<([^>]+@[^>]+)>", frm)
                from_email = fm.group(1) if fm else ""
                hn = re.match(r"^\s*(.*?)\s*<[^>]+>\s*$", frm)
                header_name = (hn.group(1).strip().strip('"')
                               if hn else frm.strip())
            except Exception:
                pass
        if not body:
            stats["skipped"] += 1
            continue

        try:
            ent = model_extract(PENNY_URL, subject, body, profile)
        except Exception:
            ent = None
        if ent:
            stats["penny_ok"] += 1
        else:
            try:
                ent = model_extract(MORPHEUS_URL, subject, body, profile)
            except Exception:
                ent = None
            if ent:
                stats["morpheus_ok"] += 1
        if not ent:
            stats["failed"] += 1
            print("[%d/%d] extraction failed: %s" % (i, len(rows), title[:50]))
            continue
        if not (ent.get("person_email") or "").strip() and from_email:
            ent["person_email"] = from_email
        # Identity comes from the From header (authoritative). Penny's
        # person_name is only a fallback — she sometimes reads the
        # recipient's name from the greeting instead of the sender.
        if header_name:
            ent["person_name"] = header_name

        pstat, pinfo = upsert_person(ent, title[:80])
        cstat, cinfo = upsert_company(ent, ent.get("person_email"), mhash)

        schedule = (ent.get("schedule") or "").strip()
        if pstat == "inserted":
            stats["person_inserted"] += 1
        elif pstat == "merged":
            stats["person_merged"] += 1
        elif pstat == "quarantine":
            stats["quarantine"] += 1
            quarantine.append(pinfo)
        if cstat == "inserted":
            stats["company_inserted"] += 1
        elif cstat == "merged":
            stats["company_merged"] += 1

        # Skill-fit grading: Penny's nuanced read merges with the
        # deterministic grade_skills.py baseline (union; Penny wins).
        pstat_track = None
        try:
            trow = kssh_psql(
                "ecosystem_central",
                "SELECT track, source FROM public.job_tracking WHERE "
                "message_id_hash = %s;" % sql_lit(mhash)
            ).strip().split("\n")[0].split("|")
            if len(trow) == 2:
                pstat_track = trow
        except Exception:
            pass
        if pstat_track:
            coding_fit = merge_skill_grades(mhash, ent, pstat_track[0],
                                            pstat_track[1])
            if coding_fit == "hand_code_heavy":
                notes_extra.append("coding_fit: hand_code_heavy (stretch "
                                   "for a vibe coder)")

        # fill gaps on the tracking row
        sets = []
        if ent.get("company"):
            sets.append("company = %s" % sql_lit(ent["company"][:120]))
            if ent.get("company_is_placeholder"):
                sets.append("company_confidence = 'masked'")
        if ent.get("pay"):
            sets.append("pay_range = %s" % sql_lit(ent["pay"][:60]))
        notes_extra = []
        if ent.get("role"):
            notes_extra.append("role: " + ent["role"][:80])
        if schedule:
            notes_extra.append("schedule: " + schedule[:80])
        if notes_extra:
            sets.append("notes = coalesce(notes,'') || %s"
                        % sql_lit(" | " + " | ".join(notes_extra)))
        if schedule:
            # A found schedule resolves the hours_unknown gap.
            sets.append("gaps = regexp_replace(regexp_replace("
                        "coalesce(gaps,''), '(^|,)hours_unknown(,|$)', "
                        "'\\\\1'), '^,|,$', '', 'g')")
        # Always mark the row extracted so it is not reprocessed daily,
        # even when nothing new was found.
        sets.append("extracted_at = now()")
        kssh_psql("ecosystem_central",
                  "UPDATE public.job_tracking SET %s WHERE "
                  "message_id_hash = %s;" % (", ".join(sets),
                                             sql_lit(mhash)))
        print("[%d/%d] %s -> person:%s company:%s"
              % (i, len(rows), (ent.get("person_name") or "?")[:30],
                 pstat, cstat))

    print("done:", json.dumps(stats))
    if quarantine:
        print("QUARANTINE (email matched, name differed — not merged):")
        for q in quarantine:
            print("  -", q)


if __name__ == "__main__":
    main()
