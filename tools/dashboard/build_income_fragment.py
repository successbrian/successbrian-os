#!/usr/bin/env python3
"""Build income-fragment.html — all income streams, tabbed Active/Gated/Inactive.
Reads successbrian_os.income_streams. Re-run to refresh.
"""
import psycopg2, html, os

OUT = '/home/successbrian/dashboard-fragments/income-fragment.html'

def esc(s):
    return html.escape(str(s or ''))

CHIP = {'active':'st-live','gated':'st-deferred','test':'st-proposed',
        'candidate':'st-proposed','rejected':'st-planned','parked':'st-planned'}
PRETTY = {'active':'Active','gated':'Gated','test':'Testing',
          'candidate':'Candidate','rejected':'Rejected','parked':'Parked'}

conn = psycopg2.connect(dbname='ecosystem_central')
cur = conn.cursor()
cur.execute("SELECT name, type, category, status, roi_score, notes FROM successbrian_os.income_streams ORDER BY name")
rows = cur.fetchall()

buckets = {'active': [], 'gated': [], 'inactive': []}
for name, typ, cat, status, roi, notes in rows:
    if status == 'active':
        buckets['active'].append((name, typ, cat, status, roi, notes))
    elif status == 'gated':
        buckets['gated'].append((name, typ, cat, status, roi, notes))
    else:
        buckets['inactive'].append((name, typ, cat, status, roi, notes))

def card(name, typ, cat, status, roi, notes):
    chip = CHIP.get(status, 'st-planned')
    pretty = PRETTY.get(status, esc(status))
    meta = ' · '.join(x for x in [typ, cat] if x)
    h = ['<div class="card">', f'<h3>{esc(name)}</h3>']
    if meta:
        h.append(f'<div class="role">{esc(meta)}</div>')
    h.append('<div class="specs">')
    if roi is not None:
        h.append(f'<div>ROI score: {esc(roi)}</div>')
    if notes:
        h.append(f'<div>{esc(notes)}</div>')
    h.append('</div>')
    h.append(f'<span class="status {chip}">{pretty}</span>')
    h.append('</div>')
    return '\n'.join(h)

p = []
p.append('<div class="section-title"><span class="chip">💰</span>'
         '<span class="stitle">Income Streams</span>'
         f'<span class="sub">{len(rows)} streams tracked</span></div>')
p.append('<div class="tabs" style="padding:0;margin-bottom:14px">')
p.append('<button class="tab active" onclick="showIncomeTab(\'active\',this)">Active</button>')
p.append(f'<button class="tab" onclick="showIncomeTab(\'gated\',this)">Gated ({len(buckets["gated"])})</button>')
p.append(f'<button class="tab" onclick="showIncomeTab(\'inactive\',this)">Inactive ({len(buckets["inactive"])})</button>')
p.append('</div>')

for key, label in [('active','Active'), ('gated','Gated'), ('inactive','Inactive')]:
    disp = 'block' if key == 'active' else 'none'
    p.append(f'<div id="income-{key}" class="income-pane" style="display:{disp}">')
    if not buckets[key]:
        p.append('<div class="loading">Nothing here.</div>')
    else:
        p.append('<div class="grid">')
        for r in buckets[key]:
            p.append(card(*r))
        p.append('</div>')
    p.append('</div>')

p.append('''<script>
function showIncomeTab(name, btn){
  document.querySelectorAll('#tab-mlm .tab').forEach(t=>t.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.income-pane').forEach(p=>p.style.display='none');
  document.getElementById('income-'+name).style.display='block';
}
</script>''')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, 'w').write('\n'.join(p))
print(f'Wrote {OUT}: active={len(buckets["active"])} gated={len(buckets["gated"])} inactive={len(buckets["inactive"])}')
