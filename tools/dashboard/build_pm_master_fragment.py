#!/usr/bin/env python3
"""Build pm-master-fragment.html — the PM master at a glance.
Gates, project budgets, and the unified ecosystem events feed.
successbrian-os PM is the master source of record; the dashboard shows what it sees.
Re-run to refresh.
"""
import psycopg2, html

OUT = '/home/successbrian/dashboard-fragments/pm-master-fragment.html'

def esc(s):
    return html.escape(str(s or ''))

CHIP = {'passed': 'st-live', 'complete': 'st-live', 'active': 'st-live',
        'in_progress': 'st-active', 'pending': 'st-planned', 'planning': 'st-planned',
        'failed': 'st-deferred', 'blocked': 'st-deferred', 'cancelled': 'st-planned'}
PRETTY = {'passed': 'Done', 'complete': 'Done', 'active': 'Active',
          'in_progress': 'In progress', 'pending': 'Not started',
          'planning': 'Planning', 'failed': 'Blocked', 'blocked': 'Blocked',
          'cancelled': 'Cancelled'}

conn = psycopg2.connect(dbname='ecosystem_central')
cur = conn.cursor()
parts = []

# ---- Gates ----
parts.append('<div class="section-title"><span class="chip">🚦</span>'
             '<span class="stitle">Gates</span>'
             '<span class="sub">checkpoints that guard progress</span></div>')
cur.execute("""
    SELECT gate_name, status, target_date, depends_on_gate_key
    FROM successbrian_os.project_gates
    WHERE status NOT IN ('passed', 'complete', 'cancelled')
    ORDER BY target_date NULLS LAST, gate_order LIMIT 20""")
gates = cur.fetchall()
if gates:
    parts.append('<table class="data"><tr><th>Gate</th><th>Status</th>'
                 '<th>Target</th><th>Waits on</th></tr>')
    for name, status, tdate, dep in gates:
        chip = CHIP.get(status, 'st-planned')
        parts.append(f'<tr><td>{esc(name)}</td>'
                     f'<td><span class="status {chip}">{PRETTY.get(status, esc(status))}</span></td>'
                     f'<td>{esc(str(tdate)) if tdate else "—"}</td>'
                     f'<td>{esc(dep) if dep else "—"}</td></tr>')
    parts.append('</table>')
else:
    parts.append('<div class="role">No open gates — everything is through.</div>')

# ---- Budgets ----
parts.append('<div class="section-title" style="margin-top:28px"><span class="chip">💰</span>'
             '<span class="stitle">Project budgets</span>'
             '<span class="sub">master source of record</span></div>')
cur.execute("""
    SELECT budget_name, project_ref, allocated, spent, remaining, pct_used, status
    FROM successbrian_os.v_project_budget_status
    WHERE is_master AND status = 'active' ORDER BY budget_name""")
budgets = cur.fetchall()
if budgets:
    parts.append('<table class="data"><tr><th>Budget</th><th>Project</th>'
                 '<th>Allocated</th><th>Spent</th><th>Remaining</th><th>Used</th></tr>')
    for name, pref, alloc, spent, rem, pct, _st in budgets:
        parts.append(f'<tr><td>{esc(name)}</td><td>{esc(pref)}</td>'
                     f'<td>${alloc:,.2f}</td><td>${spent:,.2f}</td>'
                     f'<td>${rem:,.2f}</td><td>{pct}%</td></tr>')
    parts.append('</table>')
else:
    parts.append('<div class="role">No active project budgets.</div>')

# ---- Events feed ----
parts.append('<div class="section-title" style="margin-top:28px"><span class="chip">📡</span>'
             '<span class="stitle">Ecosystem events</span>'
             '<span class="sub">what the plugins are feeding the PM system</span></div>')
cur.execute("""
    SELECT event_at, source_plugin, title, detail
    FROM successbrian_os.ecosystem_events
    ORDER BY event_at DESC LIMIT 15""")
events = cur.fetchall()
if events:
    parts.append('<table class="data"><tr><th>When</th><th>From</th><th>Event</th></tr>')
    for when, src, title, detail in events:
        when_s = when.strftime('%m-%d %H:%M') if when else '—'
        parts.append(f'<tr><td style="white-space:nowrap">{esc(when_s)}</td>'
                     f'<td>{esc(src)}</td><td><b>{esc(title)}</b>'
                     f'{f"<div class=\"role\">{esc(detail)}</div>" if detail else ""}</td></tr>')
    parts.append('</table>')
else:
    parts.append('<div class="role">No events yet.</div>')

open(OUT, 'w').write('\n'.join(parts))
print(f'Wrote {OUT}')
