#!/usr/bin/env python3
"""Build ops-console fragment — the visual OS: cron fleet, worker heartbeats,
live activity, pipelines, scheduler health. Static fragment, deployed like
the other dashboard fragments."""
import html
import json
import subprocess
import sys
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

sys.path.insert(0, '/home/successbrian/successbrian-os/tools/scheduler')
import scheduler as sched

OUT = '/home/successbrian/dashboard-fragments/ops-console.html'


def esc(s):
    return html.escape(str(s or ''))


conn = psycopg2.connect(dbname='ecosystem_central')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 1. cron fleet
cur.execute("SELECT area, weight, COUNT(*) c FROM successbrian_os.cron_registry "
            "GROUP BY 1, 2 ORDER BY 1, 2")
fleet = cur.fetchall()
cur.execute("SELECT COUNT(*) c FROM successbrian_os.cron_registry")
total_jobs = cur.fetchone()['c']
cur.execute("SELECT COUNT(*) c FROM successbrian_os.cron_registry "
            "WHERE enriched")
enriched = cur.fetchone()['c']

# 2. worker heartbeats
cur.execute("SELECT worker_name, last_heartbeat, last_status, last_error, "
            "is_important FROM successbrian_os.worker_heartbeats "
            "ORDER BY last_heartbeat DESC")
workers = cur.fetchall()

# 3. live activity
cur.execute("SELECT event_type, source_plugin, title, event_at, acknowledged "
            "FROM successbrian_os.ecosystem_events "
            "ORDER BY event_at DESC LIMIT 20")
events = cur.fetchall()
cur.execute("SELECT COUNT(*) c FROM successbrian_os.ecosystem_events "
            "WHERE NOT acknowledged")
unack = cur.fetchone()['c']

# 4. pipelines: hard dates next 14d, overdue life_ops tasks, next podcast
cur.execute("SELECT title, event_date AS date, event_type "
            "FROM successbrian_os.life_calendar "
            "WHERE is_hard_date AND event_date BETWEEN CURRENT_DATE "
            "AND CURRENT_DATE + 14 ORDER BY event_date LIMIT 10")
hard_dates = cur.fetchall()
cur.execute("SELECT COUNT(*) c FROM life_ops.event_tasks "
            "WHERE status='pending' AND due_date < CURRENT_DATE")
overdue = cur.fetchone()['c']
cur.execute("SELECT COUNT(*) c FROM life_ops.event_tasks "
            "WHERE status='pending' AND due_date = CURRENT_DATE")
due_today = cur.fetchone()['c']
cur.execute("SELECT title, event_date AS date FROM successbrian_os.life_calendar "
            "WHERE event_type='podcast' AND event_date >= CURRENT_DATE "
            "ORDER BY event_date LIMIT 1")
podcast = cur.fetchone()
podcast_stage = []
if podcast:
    cur.execute("SELECT t.task, t.status FROM life_ops.event_tasks t "
                "JOIN successbrian_os.life_calendar c ON c.id=t.event_id "
                "WHERE c.event_type='podcast' AND c.event_date=%s "
                "ORDER BY due_date", (podcast['date'],))
    podcast_stage = cur.fetchall()

# 5. scheduler audit
audit = sched.audit()

cur.close()
conn.close()

p = []
p.append('''<style>
.ops-wrap{max-width:960px;margin:0 auto}
.ops-title{display:flex;align-items:center;gap:10px;margin:4px 0 14px}
.ops-title .stitle{font-size:1.3em;font-weight:700;color:#fff}
.ops-sec{color:#8b8fa0;font-size:.8em;font-weight:700;text-transform:uppercase;
  letter-spacing:1px;margin:22px 0 10px}
.ops-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px;margin-bottom:6px}
.ops-card{background:#161923;border:1px solid #23262f;border-radius:10px;
  padding:14px 16px}
.ops-card .num{font-size:1.7em;font-weight:700;color:#fff}
.ops-card .lbl{color:#8b8fa0;font-size:.82em;margin-top:2px}
.ops-card.good{border-left:3px solid #4caf50}
.ops-card.warn{border-left:3px solid #ffb84d}
.ops-card.bad{border-left:3px solid #ff5f56}
.ops-row{display:flex;gap:12px;background:#161923;border:1px solid #23262f;
  border-radius:10px;padding:10px 14px;margin:0 0 6px;align-items:center}
.ops-row .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#4caf50}.dot.warn{background:#ffb84d}.dot.bad{background:#ff5f56}
.dot.mute{background:#5a5e6e}
.ops-row .main{flex:1;min-width:0}
.ops-row .t{color:#f0f1f5;font-weight:600;font-size:.92em}
.ops-row .s{color:#8b8fa0;font-size:.8em;margin-top:2px}
.ops-row .side{color:#5a5e6e;font-size:.78em;text-align:right;flex-shrink:0}
.ops-note{color:#5a5e6e;font-size:.82em;margin-top:8px;font-style:italic}
</style>''')

p.append('<div class="ops-wrap">')
p.append('<div class="ops-title"><span class="chip">🖥️</span>'
         '<span class="stitle">Ops Console</span></div>')

# headline numbers
peak_min = audit.get('peak_minute')
peak_load = audit.get('peak_load')
p.append('<div class="ops-grid">')
p.append(f'<div class="ops-card good"><div class="num">{total_jobs}</div>'
         '<div class="lbl">cron jobs registered</div></div>')
p.append(f'<div class="ops-card {"good" if not audit.get("unregistered") else "warn"}">'
         f'<div class="num">{len(audit.get("unregistered", []))}</div>'
         '<div class="lbl">unregistered</div></div>')
p.append(f'<div class="ops-card {"warn" if peak_load and peak_load > 10 else "good"}">'
         f'<div class="num">:{peak_min:02d}</div>'
         f'<div class="lbl">peak minute (load {peak_load})</div></div>')
p.append(f'<div class="ops-card {"good" if len(workers) else "mute"}">'
         f'<div class="num">{len(workers)}</div>'
         '<div class="lbl">workers reporting</div></div>')
p.append(f'<div class="ops-card {"bad" if overdue else "good"}">'
         f'<div class="num">{overdue}</div>'
         '<div class="lbl">overdue life tasks</div></div>')
p.append(f'<div class="ops-card {"warn" if unack else "good"}">'
         f'<div class="num">{unack}</div>'
         '<div class="lbl">unacked events</div></div>')
p.append('</div>')

# cron fleet by area
p.append('<div class="ops-sec">Cron fleet</div>')
areas = {}
for r in fleet:
    areas.setdefault(r['area'] or 'unsorted', []).append(r)
for area in sorted(areas):
    tot = sum(r['c'] for r in areas[area])
    weights = ', '.join(f"{r['weight']}:{r['c']}" for r in areas[area])
    p.append(f'<div class="ops-row"><div class="dot ok"></div>'
             f'<div class="main"><div class="t">{esc(area)} — {tot} jobs</div>'
             f'<div class="s">{esc(weights)}</div></div></div>')
p.append(f'<div class="ops-note">{enriched} of {total_jobs} jobs enriched with '
         'purpose/upstream metadata. New crons get planner slots, per the '
         'scheduler rule.</div>')

# workers
p.append('<div class="ops-sec">Workers</div>')
if workers:
    for w in workers:
        age = w['last_heartbeat']
        dot = 'ok' if (w['last_status'] or '') == 'ok' else 'warn'
        p.append(f'<div class="ops-row"><div class="dot {dot}"></div>'
                 f'<div class="main"><div class="t">{esc(w["worker_name"])}</div>'
                 f'<div class="s">{esc(w["last_status"] or "")}'
                 f'{(" — " + esc(w["last_error"][:100])) if w["last_error"] else ""}</div></div>'
                 f'<div class="side">{esc(str(age)[:16])}</div></div>')
else:
    p.append('<div class="ops-note">No workers reporting.</div>')
p.append('<div class="ops-note">Heartbeat coverage is thin — most agents and '
         'crons do not report. Silent workers do not appear here at all.</div>')

# pipelines
p.append('<div class="ops-sec">Pipelines</div>')
if podcast:
    done = sum(1 for s in podcast_stage if s['status'] == 'done')
    tot = len(podcast_stage)
    dot = 'ok' if done == tot else ('warn' if done else 'mute')
    p.append(f'<div class="ops-row"><div class="dot {dot}"></div>'
             f'<div class="main"><div class="t">🎙️ {esc(podcast["title"])} '
             f'({esc(str(podcast["date"]))})</div>'
             f'<div class="s">{done}/{tot} prep tasks done'
             f'{f", {overdue} overdue" if overdue else ""}</div></div></div>')
for h in hard_dates:
    p.append(f'<div class="ops-row"><div class="dot warn"></div>'
             f'<div class="main"><div class="t">📌 {esc(h["title"])}</div>'
             f'<div class="s">{esc(h["event_type"])} — hard date</div></div>'
             f'<div class="side">{esc(str(h["date"]))}</div></div>')
if due_today:
    p.append(f'<div class="ops-note">{due_today} life task(s) due today, '
             f'{overdue} overdue.</div>')

# live activity
p.append('<div class="ops-sec">Live activity</div>')
for e in events:
    dot = 'warn' if not e['acknowledged'] else 'mute'
    p.append(f'<div class="ops-row"><div class="dot {dot}"></div>'
             f'<div class="main"><div class="t">{esc(e["title"])}</div>'
             f'<div class="s">{esc(e["source_plugin"])} · '
             f'{esc(e["event_type"])}</div></div>'
             f'<div class="side">{esc(str(e["event_at"])[:16])}</div></div>')

# on-demand runs of safe watcher jobs (HTMX: swap result in place)
try:
    _dash_token = open('/home/successbrian/.dash_actions_token').read().strip()
except OSError:
    _dash_token = ''
p.append('<div class="ops-sec">Run now</div>')
p.append('<div class="ops-row"><div class="dot ok"></div><div class="main">'
         '<div class="t">Watcher jobs</div>'
         '<div class="s">personal_os_watch · life_ops_watch · '
         'ops_console_rebuild</div></div>'
         '<div class="side" id="run-result"></div></div>')
p.append('<div style="display:flex;gap:8px;margin-top:8px">')
for job in ("personal_os_watch", "life_ops_watch", "ops_console_rebuild"):
    p.append(f'<button hx-post="/successbrian-os/dash-actions/api/run" '
             f'hx-vals=\'{{"job": "{job}"}}\' '
             f'hx-headers=\'{{"X-Dash-Token": "{_dash_token}"}}\' '
             f'hx-target="#run-result" hx-swap="innerHTML" '
             f'style="background:#2a2d3a;color:#cfe3ff;border:1px solid #3a3e4d;'
             f'border-radius:8px;padding:7px 14px;cursor:pointer">'
             f'{job}</button>')
p.append('</div>')

p.append('</div>')
open(OUT, 'w').write('\n'.join(p))
print(f'Wrote {OUT}: {total_jobs} jobs, {len(workers)} workers, '
      f'{len(events)} events')
