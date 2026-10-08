#!/usr/bin/env python3
"""SuccessBrian OS employment stream: skill-fit grading + gap signals.

PURPOSE: Grade every job_tracking lead against Brian's REAL profile —
    a developing vibe coder, not a strong natural programmer (per Brian
    2026-10-04) — and record how often required skills he is
    underqualified for show up in intel. The coach reads the rollup to
    guide his learning toward what the market wants.
WHY: Brian 2026-10-04 — "my job scout/coach needs to know I'm a
    developing vibe coder and not a strong natural programmer... when it
    grades my fit. i want the scout/coach to see how often various things
    that I'm underqualified for come up in intel discoveries and help
    guide me to learning and improving into what the market is looking
    for".
CALLED BY: CLI (`python3 grade_skills.py [--limit N]`); the daily cron
    `employment-daily-scan` after extract_entities.py.
NOTES:
    - Deterministic: matches public.skill_lexicon regexes against
      title/notes/pay_range; Brian's level comes from skill_lexicon.
      No chat model — Penny's nuanced pass (extract_entities.py) merges
      additively on top of these results.
    - Idempotent: only grades rows where skill_gaps IS NULL. Re-runs are
      safe; skill_gap_signals has a UNIQUE(job_tracking_id, skill).
    - coding_fit: 'vibe_fit' | 'hand_code_heavy' | 'mixed' | NULL.
    - Gap rule (fixed 2026-10-08 per board): a skill is a gap only on
      genuine mismatch — required 'high' vs Brian developing/weak, or
      required 'stated' vs Brian weak. Developing covers basic needs.
      A freelance 'target' that is hand_code_heavy is a STRETCH, not a
      clean target — the briefing worker treats it that way.
    - DB writes go through ~/workspace/bin/kssh -> psql on k11.
"""
import argparse
import base64
import json
import os
import re
import subprocess

KSSH = os.path.expanduser("~/workspace/bin/kssh")

# Posting asks for a HIGH level of the skill.
HIGH_RE = re.compile(
    r"\bstrong\b|\bexpert\b|\bsenior\b|\bsr\.?\b|\badvanced\b|"
    r"\d+\+?\s*years?\b", re.I)
# The work itself needs hand-written production code.
HAND_RE = re.compile(
    r"strong\s+(python|javascript|typescript|java|c\+\+|go\b)|"
    r"expert\s+(python|javascript|typescript)|"
    r"production\s+code|existing\s+codebase|code\s+review|"
    r"senior\s+(python|software|full[\s\-]?stack)\s+engineer|"
    r"\b5\+?\s*years?.{0,40}(python|javascript|typescript)",
    re.I)
# The work fits vibe coding: new builds, automation, deploys, advising.
VIBE_RE = re.compile(
    r"greenfield|build\s+(a|an|the)\s+\w*\s*(system|platform|tool|app)|"
    r"automat(e|ion|ing)|workflow|consult(ing|ant)?|audit|"
    r"deploy|local\s+ai|no[\s\-]?code|low[\s\-]?code",
    re.I)


def kssh(cmd):
    p = subprocess.run(["bash", KSSH, cmd], capture_output=True, text=True,
                       timeout=180)
    if p.returncode != 0:
        raise RuntimeError("kssh failed: " + p.stderr.strip()[-300:])
    return p.stdout


def kssh_psql(db, sql):
    b64 = base64.b64encode(sql.encode()).decode()
    return kssh(
        "psql -h localhost -U successbrian -d %s -v ON_ERROR_STOP=1 -t -A "
        "-c \"$(echo %s | base64 -d)\"" % (db, b64))


def sql_lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def load_lexicon():
    # unnest() gives one row per pattern, avoiding psql's TEXT[] output
    # quoting/escaping (which double-escapes regex backslashes).
    out = kssh_psql(
        "ecosystem_central",
        "SELECT skill, unnest(patterns) AS pat, brian_level "
        "FROM public.skill_lexicon ORDER BY skill;")
    lex = {}
    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        skill, pat, level = line.split("|", 2)
        lex.setdefault(skill, {"skill": skill, "patterns": [],
                               "level": level})["patterns"].append(pat)
    return list(lex.values())


def grade_row(text, lex):
    required, gaps = [], []
    for entry in lex:
        hit = any(re.search(p, text, re.I) for p in entry["patterns"])
        if not hit:
            continue
        rlevel = "high" if HIGH_RE.search(text) else "stated"
        required.append({"skill": entry["skill"],
                         "required_level": rlevel})
        # Gap only on genuine mismatch (Brian 2026-10-08 board fix):
        # "developing" covers basic ("stated") requirements; it is only a gap
        # when the job demands "high". "weak" is a gap at any required level.
        blevel = entry["level"]
        is_gap = (rlevel == "high" and blevel in ("developing", "weak")) or \
                 (rlevel == "stated" and blevel == "weak")
        if is_gap:
            gaps.append({"skill": entry["skill"],
                         "required_level": rlevel,
                         "gap_kind": "underqualified"})
    hand = bool(HAND_RE.search(text))
    vibe = bool(VIBE_RE.search(text))
    if hand and not vibe:
        coding_fit = "hand_code_heavy"
    elif vibe and not hand:
        coding_fit = "vibe_fit"
    elif hand and vibe:
        coding_fit = "mixed"
    else:
        coding_fit = None
    return required, gaps, coding_fit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    lex = load_lexicon()
    print("lexicon skills: %d" % len(lex))

    q = ("SELECT id, track, source, coalesce(title,'') || ' ' || "
         "coalesce(notes,'') || ' ' || coalesce(pay_range,'') "
         "FROM public.job_tracking WHERE skill_gaps IS NULL ORDER BY id")
    if args.limit:
        q += " LIMIT %d" % args.limit
    q += ";"
    rows = [r for r in kssh_psql("ecosystem_central", q).strip().split("\n")
            if r.strip()]
    print("rows needing grading: %d" % len(rows))

    graded, signals = 0, 0
    upd_stmts, sig_vals = [], []
    for row in rows:
        jid, track, source, text = row.split("|", 3)
        required, gaps, coding_fit = grade_row(text or "", lex)
        upd_stmts.append(
            "UPDATE public.job_tracking SET skill_gaps = %s::jsonb, "
            "required_skills = %s::jsonb, coding_fit = %s, "
            "updated_at = now() WHERE id = %s;"
            % (sql_lit(json.dumps(gaps)), sql_lit(json.dumps(required)),
               sql_lit(coding_fit), jid))
        graded += 1
        for g in gaps:
            sig_vals.append(
                "(%s,%s,%s,%s,%s,%s)" % (
                    jid, sql_lit(g["skill"]),
                    sql_lit(g["required_level"]), sql_lit(g["gap_kind"]),
                    sql_lit(track), sql_lit(source)))
            signals += 1
        if len(upd_stmts) >= 50:
            kssh_psql("ecosystem_central", "\n".join(upd_stmts))
            upd_stmts = []
        if len(sig_vals) >= 200:
            kssh_psql(
                "ecosystem_central",
                "INSERT INTO public.skill_gap_signals (job_tracking_id, "
                "skill, required_level, gap_kind, track, source) VALUES "
                + ",".join(sig_vals) +
                " ON CONFLICT (job_tracking_id, skill) DO NOTHING;")
            sig_vals = []
    if upd_stmts:
        kssh_psql("ecosystem_central", "\n".join(upd_stmts))
    if sig_vals:
        kssh_psql(
            "ecosystem_central",
            "INSERT INTO public.skill_gap_signals (job_tracking_id, skill, "
            "required_level, gap_kind, track, source) VALUES "
            + ",".join(sig_vals) +
            " ON CONFLICT (job_tracking_id, skill) DO NOTHING;")
    print("graded %d rows, %d gap signals queued" % (graded, signals))


if __name__ == "__main__":
    main()
