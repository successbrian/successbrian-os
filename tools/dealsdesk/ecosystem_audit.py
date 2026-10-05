#!/usr/bin/env python3
"""ecosystem_audit.py — daily audit of the ecosystem against DealsDesk.

PURPOSE: Brian 2026-10-01: audit the ecosystem daily against DealsDesk —
         demand gaps, need coverage by builds, OS integration drift, and the
         outside tool landscape. Findings land in dealsdesk.audit_log;
         'act' severity also goes to the outbox (Brian's digest).
WHY:     Closes the loop: telemetry in, priorities out. A need must never
         spawn duplicate work when a build already covers it (build_solves),
         and demand the fleet actually feels must become a tracked need.
CALLED BY: ecosystem-audit.timer (daily 07:00 America/Chicago).
NOTES:   Brian approved auto-creating needs from demand gaps (2026-10-01).
         Never purchases; never changes priorities. Proposes only.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/ecosystem_audit.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/ecosystem_audit.py (k11-alpha; systemd timers).

"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [audit] %(message)s")
LOG = logging.getLogger("audit")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


findings = []  # (leg, finding, severity, detail)


def log(leg, finding, severity, detail=""):
    findings.append((leg, finding, severity, detail))


def leg_demand():
    """Model capacity gaps -> tracked needs (auto-create per Brian)."""
    rows = psql("""SELECT model_codename, gap_tokens_day, instances_needed,
                          instances_current, COALESCE(growth_rate_pct,0)
                   FROM successbrian_os.model_capacity
                   WHERE gap_tokens_day > 0 ORDER BY gap_tokens_day DESC""")
    for r in rows:
        codename, gap, need, cur, growth = (r + ["", "", "", "", "0"])[:5]
        dup = psql(f"""SELECT id FROM successbrian_os.ecosystem_needs
                       WHERE status='open' AND title ILIKE '%{esc(codename)}%' LIMIT 1""")
        if dup:
            continue
        if "--dry-run" not in sys.argv:
            psql(f"""INSERT INTO successbrian_os.ecosystem_needs
                     (category, title, description, priority, status, identified_by, dealsdesk_action)
                     VALUES ('compute',
                             '{esc(codename)} demand gap: {gap} tokens/day unserved',
                             '{esc(f"instances {cur}/{need}, growth {growth}%")}',
                             2, 'open', 'dealsdesk-audit', 'evaluate')""", write=True)
        sev = "act" if float(growth or 0) > 20 else "watch"
        log("demand", f"demand gap: {codename}",
            sev, f"{gap} tokens/day unserved, instances {cur}/{need}, growth {growth}%")
    LOG.info("leg demand: %d gaps", len(rows))


def leg_coverage():
    """Open needs with no build covering them -> triage, not duplicate work."""
    rows = psql("""SELECT DISTINCT ON (n.title) n.id, n.title
                   FROM successbrian_os.ecosystem_needs n
                   WHERE n.status = 'open'
                     AND NOT EXISTS (SELECT 1 FROM dealsdesk.build_solves s
                                     WHERE s.need_id = n.id)
                   ORDER BY n.title, n.id""")
    for nid, title in rows:
        log("coverage", f"uncovered need: {title}", "watch",
            f"need {nid} has no build_solves link — triage: link to a build, plan one, or drop")
    LOG.info("leg coverage: %d uncovered", len(rows))


def leg_integration():
    """New OS repo inputs? OS needs asking DealsDesk with no coverage?"""
    try:
        r = subprocess.run(
            ["git", "-C", "/home/successbrian/successbrian-os", "log",
             "--since=24 hours ago", "--oneline"],
            capture_output=True, text=True, timeout=30)
        commits = [l for l in r.stdout.strip().split("\n") if l.strip()]
    except Exception as e:
        commits = []
        LOG.error("git log failed: %s", e)
    if commits:
        log("integration", f"{len(commits)} successbrian-os commits in 24h", "info",
            "; ".join(commits[:8]))
    rows = psql("""SELECT DISTINCT ON (n.title) n.id, n.title
                   FROM successbrian_os.ecosystem_needs n
                   WHERE n.dealsdesk_action IS NOT NULL AND n.status != 'fulfilled'
                     AND NOT EXISTS (SELECT 1 FROM dealsdesk.build_solves s
                                     WHERE s.need_id = n.id)
                   ORDER BY n.title, n.id""")
    for nid, title in rows:
        log("integration", f"dealsdesk_action unaddressed: {title}", "watch",
            f"need {nid} asks DealsDesk for action but no build covers it")
    LOG.info("leg integration: %d commits, %d unaddressed", len(commits), len(rows))


def leg_landscape():
    """Weekly outside-tool scan due? (price scouting, inventory, budget tools)."""
    rows = psql("""SELECT MAX(created_at) FROM dealsdesk.audit_log WHERE leg='landscape'""")
    last = rows[0][0] if rows and rows[0][0] else ""
    due = psql("""SELECT (MAX(created_at) IS NULL OR MAX(created_at) < NOW() - INTERVAL '7 days')
                  FROM dealsdesk.audit_log WHERE leg='landscape'""")
    if due and due[0][0] == "t":
        log("landscape", "weekly landscape scan due", "watch",
            "price-scouting / inventory+build-mgmt / budget-planning tools: what's new, what to borrow")
    LOG.info("leg landscape: last=%s", last or "never")


def main():
    dry = "--dry-run" in sys.argv
    leg_demand()
    leg_coverage()
    leg_integration()
    leg_landscape()
    new = 0
    for leg, finding, severity, detail in findings:
        if dry:
            LOG.info("dry [%s/%s] %s", leg, severity, finding)
            continue
        ok = psql(f"""INSERT INTO dealsdesk.audit_log (leg, finding, severity, detail)
                      VALUES ('{esc(leg)}','{esc(finding)}','{severity}','{esc(detail)}')
                      ON CONFLICT (audit_date, leg, finding) DO NOTHING
                      RETURNING id""", write=True)
        # psql write returns True/False; count via separate check is overkill — log it
        new += 1
    # notify on 'act' (dedupe: one per finding per day via notified flag)
    if not dry:
        acts = psql("""SELECT id, finding, detail FROM dealsdesk.audit_log
                       WHERE audit_date = CURRENT_DATE AND severity='act' AND notified=FALSE
                       ORDER BY id LIMIT 3""")
        for aid, finding, detail in acts:
            msg = f"DEALSDESK AUDIT: {finding}. {detail}"
            psql(f"""INSERT INTO public.successbrian_outbox (agent, message_text, priority)
                     VALUES ('dealsdesk', '{esc(msg)}', 2)""", write=True)
            psql(f"UPDATE dealsdesk.audit_log SET notified=TRUE WHERE id={aid}", write=True)
            LOG.info("notified act: %s", finding)
    LOG.info("audit done: %d findings", len(findings))


if __name__ == "__main__":
    main()
