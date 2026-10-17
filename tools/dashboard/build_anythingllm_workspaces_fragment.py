#!/usr/bin/env python3
"""Build anythingllm-workspaces-fragment.html — visual map of all AnythingLLM workspaces.

Queries every AnythingLLM instance in anythingllm_instances.json and lists each
workspace with its document count. Ready for the multi-node spread: add an entry
per instance and re-run. Plain words, no ID codes (Brian's dashboard standard).
Re-run to refresh.
"""
import json, html, urllib.request

OUT = '/home/successbrian/dashboard-fragments/anythingllm-workspaces-fragment.html'
CONFIG = '/home/successbrian/successbrian-os/tools/dashboard/anythingllm_instances.json'

def esc(s):
    return html.escape(str(s or ''))

def api(base, key, path):
    req = urllib.request.Request(base + path,
                                 headers={'Authorization': 'Bearer ' + key})
    return json.load(urllib.request.urlopen(req, timeout=30))

instances = json.load(open(CONFIG))
parts = []
total_ws, total_docs = 0, 0

parts.append('<div class="section-title"><span class="chip">🧠</span>'
             '<span class="stitle">Knowledge workspaces</span>'
             '<span class="sub">every AnythingLLM workspace, every node</span></div>')

for inst in instances:
    name = inst.get('name', 'unknown')
    base = inst.get('base_url', '').rstrip('/')
    key = open(inst['key_path']).read().strip()
    try:
        wss = api(base, key, '/api/v1/workspaces').get('workspaces', [])
    except Exception as e:
        parts.append(f'<div class="section-title" style="margin-top:24px">'
                     f'<span class="chip">⚠️</span>'
                     f'<span class="stitle">{esc(name)}</span>'
                     f'<span class="sub">unreachable right now</span></div>')
        continue
    wss = sorted(wss, key=lambda w: (w.get('name') or w.get('slug', '')).lower())
    total_ws += len(wss)
    parts.append(f'<div class="section-title" style="margin-top:24px">'
                 f'<span class="chip">🖥️</span>'
                 f'<span class="stitle">{esc(name)}</span>'
                 f'<span class="sub">{len(wss)} workspaces</span></div>')
    if not wss:
        parts.append('<div class="role">No workspaces on this node yet.</div>')
        continue
    parts.append('<table class="data"><tr><th>Workspace</th>'
                 '<th>Documents</th></tr>')
    for w in wss:
        slug = w.get('slug', '')
        wname = w.get('name') or slug
        try:
            det = api(base, key, f'/api/v1/workspace/{slug}')
            wl = det.get('workspace', [])
            docs = (wl[0].get('documents', []) if wl else []) or []
        except Exception:
            docs = None
        if docs is None:
            dcell = '—'
        else:
            total_docs += len(docs)
            dcell = str(len(docs))
        parts.append(f'<tr><td><b>{esc(wname)}</b></td><td>{dcell}</td></tr>')
    parts.append('</table>')

parts.append(f'<div class="role" style="margin-top:24px">'
             f'{total_ws} workspaces · {total_docs} documents '
             f'across {len(instances)} node{"s" if len(instances) != 1 else ""}.</div>')

open(OUT, 'w').write('\n'.join(parts))
print(f'Wrote {OUT}: {total_ws} workspaces, {total_docs} docs')
