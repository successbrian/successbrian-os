#!/usr/bin/env python3
"""Build unified inbox fragment — email-inbox style.
Priority-sorted, highest first. Questions (action) then reports.
"""
import psycopg2, html, json, sys
sys.path.insert(0, '/home/successbrian/successbrian-os/tools/dashboard')
import priority_judge

OUT = '/home/successbrian/dashboard-fragments/inbox-unified.html'

def esc(s):
    return html.escape(str(s or ''))

priority_judge.judge_all()

conn = psycopg2.connect(dbname='ecosystem_central')
cur = conn.cursor()
cur.execute("""
    SELECT id, question, context, options, priority, created_at
    FROM successbrian_os.pending_questions
    WHERE status = 'open' ORDER BY priority DESC, created_at DESC""")
questions = cur.fetchall()
cur.execute("""
    SELECT id, report_type, title, left(body, 220), created_at, priority
    FROM successbrian_os.reports ORDER BY priority DESC, id DESC LIMIT 25""")
reports = cur.fetchall()
cur.close(); conn.close()

PRIO = {3: ('#ff5f56', 'High'), 2: ('#ffb84d', 'Medium'), 1: ('#5a5e6e', 'Low')}

def row(kind, title, snippet, when, prio, extra=''):
    color, label = PRIO.get(prio or 1, PRIO[1])
    badge = (f'<span class="ib-badge ib-action">Needs your call</span>' if kind == 'q'
             else f'<span class="ib-badge">{esc(kind)}</span>')
    return f'''<div class="ib-row" style="border-left:3px solid {color}">
  <div class="ib-main">
    <div class="ib-subject">{esc(title)} {badge}</div>
    <div class="ib-snippet">{esc(snippet)}</div>
    {extra}
  </div>
  <div class="ib-side">
    <div class="ib-time">{esc(when)}</div>
    <div class="ib-prio" style="color:{color}">{label}</div>
  </div>
</div>'''

p = []
p.append('''<style>
.ib-wrap{max-width:760px;margin:0 auto}
.ib-title{display:flex;align-items:center;gap:10px;margin:4px 0 14px}
.ib-title .stitle{font-size:1.3em;font-weight:700;color:#fff}
.ib-row{display:flex;gap:14px;background:#161923;border:1px solid #23262f;border-radius:10px;
  padding:13px 16px;margin:0 0 8px;transition:background .15s,transform .15s}
.ib-row:hover{background:#1b1f2b;transform:translateX(2px)}
.ib-main{flex:1;min-width:0}
.ib-subject{font-size:1.02em;font-weight:600;color:#f0f1f5;line-height:1.35}
.ib-snippet{color:#8b8fa0;font-size:.88em;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ib-side{text-align:right;flex-shrink:0;min-width:74px}
.ib-time{color:#5a5e6e;font-size:.78em}
.ib-prio{font-size:.75em;font-weight:700;margin-top:4px}
.ib-badge{display:inline-block;background:#2a2d3a;color:#8cf;font-size:.68em;font-weight:700;
  padding:2px 9px;border-radius:9px;margin-left:8px;vertical-align:2px;text-transform:uppercase;letter-spacing:.4px}
.ib-badge.ib-action{background:#3a1d22;color:#ff8a80}
.ib-opts{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
.ib-opts button{background:#2a2d3a;color:#cfe3ff;border:1px solid #3a3e4d;border-radius:8px;
  padding:7px 14px;font-size:.85em;cursor:pointer;transition:background .15s}
.ib-opts button:hover{background:#3a4a6b}
.ib-sec{color:#8b8fa0;font-size:.8em;font-weight:700;text-transform:uppercase;letter-spacing:1px;
  margin:20px 0 10px}
</style>''')

p.append('<div class="ib-wrap">')
p.append('<div class="ib-title"><span class="chip">📥</span><span class="stitle">Inbox</span></div>')

for qid, question, context, options, prio, created in questions:
    when = str(created)[:16] if created else ''
    try:
        opts = json.loads(options) if isinstance(options, str) else (options or [])
    except Exception:
        opts = []
    extra = ''
    if opts:
        btns = ''.join(
            f"<button onclick=\"answerQuestion({qid},'{esc(o.get('label', o.get('text', str(o))) if isinstance(o, dict) else str(o))}')\">"
            f"{esc(o.get('label', o.get('text', str(o))) if isinstance(o, dict) else str(o))}</button>"
            for o in opts)
        extra = f'<div class="ib-opts">{btns}</div>'
    snippet = (context or '')[:220]
    p.append(row('q', question, snippet, when, prio, extra))

if reports:
    p.append('<div class="ib-sec">Reports</div>')
    for rid, rtype, title, snippet, when, rprio in reports:
        when_s = str(when)[:16] if when else ''
        p.append(row((rtype or 'report'), title, snippet or '', when_s, rprio or 1))

if not questions and not reports:
    p.append('<div class="loading">Inbox is clear.</div>')
p.append('</div>')

open(OUT, 'w').write('\n'.join(p))
print(f'Wrote {OUT}: {len(questions)} questions, {len(reports)} reports')
