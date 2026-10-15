#!/usr/bin/env python3
"""Build projects-fragment.html — clean, human-readable project display.
No ID codes, no jargon. Just goals, their phases, and what's next.
Re-run to refresh.
"""
import psycopg2, html, os, re

OUT = '/home/successbrian/dashboard-fragments/projects-fragment.html'

def esc(s):
    return html.escape(str(s or ''))
def clean(s):
    s = re.sub(r'\s*\(id \d+\)', '', str(s or ''))
    return esc(s)

CHIP = {'active':'st-live','planning':'st-proposed','pending':'st-planned',
        'passed':'st-live','failed':'st-deferred','in_progress':'st-active',
        'complete':'st-live','cancelled':'st-planned'}
PRETTY = {'active':'Active','planning':'Planning','pending':'Not started',
          'passed':'Done','failed':'Blocked','in_progress':'In progress',
          'complete':'Done','cancelled':'Cancelled'}

conn = psycopg2.connect(dbname='ecosystem_central')
cur = conn.cursor()

cur.execute("""
    SELECT g.id, g.goal_name, g.status, g.category,
           COUNT(p.id) AS nph,
           COUNT(CASE WHEN p.status IN ('complete','passed') THEN 1 END) AS ndone
    FROM successbrian_os.sbos_goals g
    LEFT JOIN successbrian_os.sbos_projects p ON p.goal_id = g.id
    GROUP BY g.id, g.goal_name, g.status, g.category
    HAVING COUNT(p.id) > 0
    ORDER BY g.id""")
goals = cur.fetchall()

parts = ['<div class="section-title"><span class="chip">🎯</span>'
         '<span class="stitle">Goals & Projects</span>'
         '<span class="sub">where everything stands, top to bottom</span></div>']

for gid, gname, gstatus, gcat, nph, ndone in goals:
    pct = int(100 * ndone / nph) if nph else 0
    chip = CHIP.get(gstatus, 'st-planned')
    parts.append('<div class="card" style="margin-bottom:14px">')
    parts.append(f'<h3>{esc(gname)}</h3>')
    if gcat:
        parts.append(f'<div class="role">{esc(gcat)}</div>')
    parts.append(f'<span class="status {chip}">{PRETTY.get(gstatus, esc(gstatus))}</span>')
    parts.append(f'<div style="margin:10px 0 4px;color:#888;font-size:.82em">'
                 f'{ndone} of {nph} phases done</div>')
    parts.append(f'<div style="background:#2a2d3a;border-radius:6px;height:8px;'
                 f'margin-bottom:10px"><div style="background:#4a9eff;height:8px;'
                 f'border-radius:6px;width:{pct}%"></div></div>')
    cur.execute("""
        SELECT phase, status, target_date, description
        FROM successbrian_os.sbos_projects WHERE goal_id=%s
        ORDER BY phase""", (gid,))
    phases = cur.fetchall()
    now_idx = next((i for i, ph in enumerate(phases) if ph[1] not in ('complete','passed')), 0)
    parts.append('<table class="data"><tr><th></th><th>Phase</th>'
                 '<th>Status</th><th>Target date</th><th>What it delivers</th></tr>')
    for i, (phase, pstatus, tdate, desc) in enumerate(phases):
        pchip = CHIP.get(pstatus, 'st-planned')
        marker = '<span style="color:#4a9eff;font-weight:700">▶ NEXT</span>' if i == now_idx else ''
        tdate_s = str(tdate) if tdate else '—'
        parts.append(f'<tr><td>{marker}</td><td>{esc(phase)}</td>'
                     f'<td><span class="status {pchip}">{PRETTY.get(pstatus, esc(pstatus))}</span></td>'
                     f'<td>{tdate_s}</td><td>{clean(desc)}</td></tr>')
    parts.append('</table></div>')

cur.execute("""
    SELECT project_name, status FROM successbrian_os.projects_registry
    WHERE sbos_goal_id IS NULL ORDER BY project_name""")
unlinked = cur.fetchall()
if unlinked:
    parts.append('<div class="section-title" style="margin-top:28px"><span class="chip">📁</span>'
                 '<span class="stitle">Waiting to be assigned</span>'
                 f'<span class="sub">{len(unlinked)} projects not tied to a goal yet</span></div>')
    parts.append('<table class="data"><tr><th>Project</th><th>Status</th></tr>')
    for pname, pstatus in unlinked:
        pchip = CHIP.get(pstatus, 'st-planned')
        parts.append(f'<tr><td>{esc(pname)}</td>'
                     f'<td><span class="status {pchip}">{PRETTY.get(pstatus, esc(pstatus))}</span></td></tr>')
    parts.append('</table>')

open(OUT, 'w').write('\n'.join(parts))
print(f'Wrote {OUT}')
