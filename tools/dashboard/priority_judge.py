#!/usr/bin/env python3
"""Priority judge — deterministic, zero tokens.
Assigns priority 1-3 to new inbox items so they land correctly sorted.
Runs inside the inbox builder before rendering.
Rules:
  Questions: 3 = blocking/urgent/decision-needed, 2 = normal, 1 = FYI.
  Reports: by type — decision/action types = 3, time-relevant = 2, informational = 1.
"""
import psycopg2, re

# report_type -> priority
REPORT_PRIO = {
    # 3: needs a decision or action
    'hardware-decision': 3, 'triage': 3, 'audit': 3, 'agent-audit': 3,
    'vetting': 3, 'plan': 3, 'launch_checklist': 3,
    # 2: useful, time-relevant
    'hardware-compare': 2, 'hardware-comparison': 2, 'hardware-pricing': 2,
    'hardware-specs': 2, 'competitive-analysis': 2, 'evaluation': 2,
    'research': 2, 'mlgs-research': 2, 'substack-research': 2,
    'model-tier': 2, 'industry-map': 2, 'project-survey': 2,
    'dealsdesk-investigation': 2, 'k11-cleanup': 2, 'cleanup-survey': 2,
    # 1: informational
    'digest': 1, 'substack_draft': 1, 'blog_draft': 1,
    'content-analysis': 1, 'wealth_study': 1, 'chicago-tardis': 1,
}
DEFAULT_REPORT_PRIO = 1

Q_HIGH = re.compile(r'\b(urgent|blocking|blocked|down|failed|broken|decision needed|need.*decision|approve|approval)\b', re.I)
Q_LOW = re.compile(r'\b(fyi|for info|informational|heads up)\b', re.I)

def judge_question(question):
    q = question or ''
    if Q_HIGH.search(q):
        return 3
    if Q_LOW.search(q):
        return 1
    return 2

def judge_all():
    conn = psycopg2.connect(dbname='ecosystem_central')
    cur = conn.cursor()
    # ensure column
    cur.execute("ALTER TABLE successbrian_os.reports ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 1")
    # judge unjudged reports (priority IS NULL or 0... default is 1, so judge where never judged)
    # Use a judged flag via priority=0 meaning unjudged? Simpler: judge all NULLs.
    # Backfill: set priority by type for rows where priority = 1 (default) AND type maps higher.
    # To avoid clobbering manual priorities, only touch rows still at default 1 where rule says higher,
    # plus any NULLs.
    cur.execute("SELECT id, report_type, priority FROM successbrian_os.reports WHERE priority IS NULL OR priority = 1")
    n = 0
    for rid, rtype, prio in cur.fetchall():
        want = REPORT_PRIO.get((rtype or '').strip(), DEFAULT_REPORT_PRIO)
        if want != (prio or 1):
            cur.execute("UPDATE successbrian_os.reports SET priority = %s WHERE id = %s", (want, rid))
            n += 1
    # judge questions with NULL priority
    cur.execute("SELECT id, question FROM successbrian_os.pending_questions WHERE priority IS NULL AND status = 'open'")
    m = 0
    for qid, q in cur.fetchall():
        cur.execute("UPDATE successbrian_os.pending_questions SET priority = %s WHERE id = %s",
                    (judge_question(q), qid))
        m += 1
    conn.commit()
    print(f'judged: {n} reports, {m} questions')
    cur.close(); conn.close()

if __name__ == '__main__':
    judge_all()
