#!/usr/bin/env python3
"""roadchat.py — the travel laptop's front door to the ecosystem.

SBOS travel kit, piece #2 (Brian 2026-10-20): "software on the laptop
that is a real tight integration of tools... audio visual ready — TUI
or web chat ready — integrates with successbrian-os and dealsdesk and
other tools natively."

This is the web half (roadchat_tui.py is the terminal twin). One file,
pure Python 3 stdlib — runs on a fresh Ubuntu laptop with nothing
installed. Start it on the laptop:

    python3 roadchat.py            # http://127.0.0.1:8799

What it does:
  - Chat, streamed, against the home engines (Penny / Morpheus today;
    anything OpenAI-compatible tomorrow). On the road the ports below
    are the mouths of the link_up SSH tunnels, so "home" is local —
    the exact same code path at home and away.
  - Audio-visual ready, in the browser: microphone input via the Web
    Speech API, spoken replies via speech synthesis, and image attach
    that rides to the engine as an OpenAI image part (vision-capable
    home engines see the picture; text engines simply get the text).
  - Native tools, not links: /status renders eco_status live in the
    chat; the scorer panel runs DealsDesk's mini_node_scorer in-process
    and drops the verdict into the conversation.
  - Binds 127.0.0.1 only. On the road it is reached through the laptop
    itself; it is never a network service. (Access doctrine: the
    perimeter is Tailscale + tunnels; this page is a local console.)

Engines: name -> (port, label). Ports are localhost by design (see
above). Add a home engine by adding a line.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                   # eco_status
sys.path.insert(0, os.path.join(HERE, "..", "dealsdesk"))  # the scorer

ENGINES = {
    "penny": (11438, "Penny — Qwen2.5-7B, fast worker"),
    "morpheus": (11437, "Morpheus — Qwen2.5-14B, Altair's engine"),
}
DEFAULT_ENGINE = "morpheus"
PORT = 8799


def engine_chat(payload, engine):
    """Stream an OpenAI-compatible chat completion from an engine.
    Yields raw SSE bytes lines as they arrive."""
    port = ENGINES[engine][0]
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % port,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        for line in resp:
            yield line


_STATUS_CACHE = {"t": 0.0, "data": None}


def run_status():
    # Power doctrine (Brian 2026-10-20): the travel kit must sip. A
    # status probe spawns subprocesses (tailscale CLI, git) — never pay
    # that more than once per 10 s, however often the board asks.
    import time
    now = time.time()
    if _STATUS_CACHE["data"] is not None and now - _STATUS_CACHE["t"] < 10:
        return _STATUS_CACHE["data"]
    data = _run_status_fresh()
    _STATUS_CACHE.update(t=now, data=data)
    return data


def _run_status_fresh():
    import eco_status
    out = {"endpoints": [], "repos": [], "tailnet": None,
           "home_online": False}
    for label, port in eco_status.ENDPOINTS:
        up, ms = eco_status.probe(port)
        out["endpoints"].append({"name": label.strip(), "port": port,
                                  "up": up, "ms": ms})
    ts = eco_status.tailnet_peers()
    if ts:
        out["tailnet"] = {"self": ts[0],
                           "peers": [{"name": n, "online": o}
                                     for n, o in ts[1]]}
        # Home is up if k11-alpha is this machine or an online peer.
        if ts[0].lower() == eco_status.HOME_HOSTNAME:
            out["home_online"] = True
        out["home_online"] = out["home_online"] or any(
            n.lower() == eco_status.HOME_HOSTNAME and o for n, o in ts[1])
    if not out["home_online"]:
        out["home_online"] = any(e["up"] for e in out["endpoints"])
    home = os.path.expanduser("~")
    for repo in eco_status.REPOS:
        st = eco_status.repo_state(os.path.join(home, repo))
        if st:
            out["repos"].append({"name": repo, "branch": st[0],
                                  "dirty": st[1], "track": st[2]})
    return out


def run_score(candidate):
    import mini_node_scorer
    result = mini_node_scorer.score_candidate(dict(candidate))
    keys = ("score", "verdict", "notes", "pull_parts", "delivered_usd",
            "ram_value_usd")
    return {k: result.get(k) for k in keys}


def run_code():
    """The Code room's data: repos (from status) + the doctrine
    registries, read from the live modules — never hard-coded here."""
    import machine_classes
    import hardware_traps
    classes = [{"id": cid, "name": c["name"], "status": c["status"],
                "mission": c["mission"], "scorer": c["scorer"]}
               for cid, c in sorted(machine_classes.CLASSES.items())]
    traps = [{"id": t.get("id", "?"), "name": t.get("name", "?"),
              "kind": t.get("kind", "?"),
              "mechanism": t.get("mechanism", "")}
             for t in hardware_traps.TRAPS]
    return {"classes": classes, "traps": traps}


def run_brain(q):
    """The Brain room, v1: keyword search over the SBOS knowledge on
    this machine (docs + tool READMEs). This is the honest stand-in in
    the exact slot AnythingLLM / Altair's second brain will occupy —
    when that API is wired, this function is the only thing that
    changes. Returns up to 8 hits with file + snippet."""
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"hits": [], "note": "type at least 2 characters"}
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "successbrian-os", "docs"),
             os.path.join(home, "successbrian-os", "tools")]
    loose = [os.path.join(home, "successbrian-os")]
    hits = []

    def scan(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(400000)
        except Exception:
            return
        i = text.lower().find(q)
        if i >= 0:
            hits.append({"file": os.path.relpath(path, home),
                         "snippet": " ".join(
                             text[max(0, i - 90):i + 170].split())})

    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            if ".git" in dirpath:
                continue
            for fn in files:
                if fn.endswith(".md"):
                    scan(os.path.join(dirpath, fn))
                if len(hits) >= 8:
                    return {"hits": hits}
    for d in loose:
        for fn in os.listdir(d):
            if fn.endswith(".md"):
                scan(os.path.join(d, fn))
            if len(hits) >= 8:
                return {"hits": hits}
    return {"hits": hits}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RoadChat — SBOS travel console</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;font:15px/1.5 system-ui,sans-serif;background:#0d1117;color:#e6edf3}
  header{display:flex;gap:.6rem;align-items:center;padding:.6rem .9rem;background:#161b22;border-bottom:1px solid #30363d;flex-wrap:wrap}
  header b{font-size:1.05rem} select,button,input,textarea{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:.45rem .6rem}
  button{cursor:pointer} button:hover{border-color:#58a6ff}
  #pill{font-size:.8rem;padding:.25rem .6rem;border-radius:99px;border:1px solid #30363d}
  #log{max-width:860px;margin:0 auto;padding:1rem .9rem 7.5rem}
  .msg{margin:.7rem 0;padding:.65rem .85rem;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}
  .user{background:#1f6feb33;margin-left:12%} .assistant{background:#161b22;border:1px solid #30363d;margin-right:12%}
  .tool{background:#8957e533;border:1px solid #8957e5;font-size:.92rem}
  .msg img{max-width:100%;border-radius:8px;margin-top:.4rem}
  #bar{position:fixed;bottom:0;left:0;right:0;background:#161b22;border-top:1px solid #30363d;padding:.6rem .9rem}
  #bar div{max-width:860px;margin:0 auto;display:flex;gap:.5rem;align-items:flex-end}
  #text{flex:1;resize:none;max-height:8rem}
  #panel{max-width:860px;margin:0 auto;padding:0 .9rem;display:none}
  #board{max-width:860px;margin:0 auto;padding:.7rem .9rem 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:.5rem}
  .tile{border:1px solid #30363d;border-radius:10px;padding:.55rem .7rem;background:#161b22}
  .tile .nm{font-size:.86rem;font-weight:600;display:flex;align-items:center;gap:.45rem}
  .tile .meta{font-size:.76rem;color:#8b949e;margin-top:.15rem}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block;flex:none}
  .dot.up{background:#3fb950;box-shadow:0 0 7px #3fb95088}
  .dot.down{background:#f85149;box-shadow:0 0 7px #f8514988}
  .dot.info{background:#58a6ff;box-shadow:0 0 7px #58a6ff88}
  .dot.warn{background:#d29922;box-shadow:0 0 7px #d2992288}
  #nav{display:flex;gap:.45rem;flex-wrap:wrap;max-width:860px;margin:0 auto;padding:.55rem .9rem 0}
  #nav button.on{border-color:#58a6ff;color:#58a6ff}
  .view{display:none} .view.active{display:block}
  .boardgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:.5rem}
  .roomwrap{max-width:860px;margin:0 auto;padding:.9rem .9rem 6.5rem}
  .card{border:1px solid #30363d;border-radius:10px;padding:.7rem .9rem;margin:.6rem 0;background:#161b22}
  .card h3{margin:.1rem 0 .35rem;font-size:1rem}
  .card .sub{font-size:.8rem;color:#8b949e}
  .card p{margin:.3rem 0;font-size:.92rem}
  .planned{opacity:.75;border-style:dashed}
  #panel form{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.5rem;padding:.7rem 0}
  label{font-size:.78rem;color:#8b949e;display:flex;flex-direction:column;gap:.2rem}
  /* C64 mode — the whole point (Brian 2026-10-20): the old farts who
     follow him should think "holy shit, it's a C-64 wrapped up in
     modern Ubuntu and AI." Blue on blue, chunky mono, no apologies. */
  body.c64{background:#483AAA;color:#B8B4EF;font-family:"Courier New",monospace}
  body.c64 header,body.c64 #bar{background:#483AAA;border-color:#867ADE}
  body.c64 select,body.c64 button,body.c64 input,body.c64 textarea{background:#483AAA;color:#B8B4EF;border-color:#867ADE;font-family:inherit}
  body.c64 .msg{background:transparent;border:1px solid #867ADE;color:#B8B4EF;border-radius:0}
  body.c64 .user{background:#352879} body.c64 .tool{background:#352879;border-color:#B8B4EF}
  body.c64 #pill{border-color:#867ADE}
  body.c64 .tile{background:transparent;border-color:#867ADE;border-radius:0}
  body.c64 .tile .meta{color:#867ADE}
</style></head><body>
<header>
  <b>RoadChat</b>
  <select id="engine">
    <option value="morpheus">Morpheus · deep</option>
    <option value="penny">Penny · fast</option>
  </select>
  <span id="pill">checking ecosystem…</span>
  <button id="statusBtn" title="Ecosystem status">/status</button>
  <button id="boardBtn" title="Graphical status board">📊 board</button>
  <button id="c64Btn" title="Commodore mode">🕹 C64</button>
  <button id="scoreBtn" title="Score a listing with DealsDesk">score a listing</button>
  <label style="flex-direction:row;align-items:center;gap:.3rem"><input type="checkbox" id="speak"> speak replies</label>
  <button id="saverBtn" title="Battery saver: slow the board, rest the radios">🔋 saver: off</button>
</header>
<nav id="nav">
  <button data-view="chat" class="on">💬 Chat</button>
  <button data-view="fleet">🛰 Fleet</button>
  <button data-view="code">🛠 Code</button>
  <button data-view="brain">🧠 Brain</button>
  <button data-view="more">🏠 More rooms</button>
</nav>
<div class="view active" id="view-chat">
<section id="board" class="boardgrid" style="max-width:860px;margin:0 auto;padding:.7rem .9rem 0" title="What's up, what's not"></section>
<div id="panel"><form id="scoreForm">
  <label>Listing name<input name="name" required placeholder="M920q i7-8700T…"></label>
  <label>Price $<input name="price" type="number" step="0.01" required></label>
  <label>Shipping $<input name="shipping" type="number" step="0.01" value="0"></label>
  <label>Form factor<select name="form_factor"><option value="1l">1L mini</option><option value="sff">SFF</option><option value="tower">tower</option></select></label>
  <label>CPU<input name="cpu" placeholder="Intel Core i7-8700T" required></label>
  <label>Cores<input name="cores" type="number" value="6"></label>
  <label>RAM GB<input name="ram_gb" type="number" value="16"></label>
  <label>RAM slots<input name="sodimm_slots" type="number" value="2"></label>
  <label>RAM ceiling GB<input name="ram_ceiling_gb" type="number" value="32"></label>
  <label>Storage GB<input name="storage_gb" type="number" value="256"></label>
  <label>NVMe slots<input name="nvme_slots" type="number" value="1"></label>
  <label>NVMe lanes<select name="nvme_lanes"><option>4</option><option>2</option></select></label>
  <label>Ethernet GbE<input name="ethernet_gbe" type="number" step="0.1" value="1"></label>
  <label>Adapter included<select name="power_adapter"><option value="1">yes</option><option value="0">no</option></select></label>
  <button type="submit">score it</button>
</form></div>
<main id="log"></main>
</div>
<section class="view" id="view-fleet"><div class="roomwrap">
  <div id="boardBig" class="boardgrid"></div>
  <div id="fleetText"></div>
</div></section>
<section class="view" id="view-code"><div class="roomwrap" id="codeRoom">
  <p class="sub">loading the doctrine…</p>
</div></section>
<section class="view" id="view-brain"><div class="roomwrap">
  <form id="brainForm" style="display:flex;gap:.5rem">
    <input id="brainQ" style="flex:1" placeholder="Search the second brain (SBOS docs today — AnythingLLM slot)">
    <button type="submit">search</button>
  </form>
  <div id="brainResults"></div>
</div></section>
<section class="view" id="view-more"><div class="roomwrap">
  <div class="card planned"><h3>👥 People — the contact list</h3>
    <p>Planned. Wiring: Google Contacts import + the train-card inbox (photograph a card, it becomes a contact with a follow-up clock).</p></div>
  <div class="card planned"><h3>✉️ Comms — WhatsApp + email</h3>
    <p>Planned. Wiring: Gmail for email; WhatsApp as a Muse side channel. One river of messages, answered from here.</p></div>
  <div class="card planned"><h3>📈 Content — SEO strategy → blogging</h3>
    <p>Planned. Wiring: strategy notes in the Brain, drafts composed in Chat with the home fleet, published from the laptop.</p></div>
</div></section>
<div id="bar"><div>
  <button id="mic" title="Talk (Web Speech API)">🎤</button>
  <button id="attach" title="Attach an image">📎</button>
  <input type="file" id="file" accept="image/*" hidden>
  <textarea id="text" rows="2" placeholder="Message the ecosystem…  (/status works too)"></textarea>
  <button id="send">send</button>
</div></div>
<script>
const log=document.getElementById('log'), text=document.getElementById('text');
const engineSel=document.getElementById('engine'), pill=document.getElementById('pill');
let messages=[], pendingImage=null;
function add(cls, body, img){
  const d=document.createElement('div'); d.className='msg '+cls;
  const t=document.createElement('div'); t.textContent=body; d.appendChild(t);
  if(img){const i=document.createElement('img'); i.src=img; d.appendChild(i);}
  log.appendChild(d); d.scrollIntoView({behavior:'smooth'}); return t;
}
function tile(name, state, meta){
  const d=document.createElement('div'); d.className='tile';
  const n=document.createElement('div'); n.className='nm';
  const dot=document.createElement('span'); dot.className='dot '+state; n.appendChild(dot);
  n.appendChild(document.createTextNode(name)); d.appendChild(n);
  const m=document.createElement('div'); m.className='meta'; m.textContent=meta; d.appendChild(m);
  return d;
}
let lastStatus=null;
function renderBoard(s){
  /* THE BOARD IS INFRASTRUCTURE ONLY (Brian, 2026-10-20): machines,
     engines, links, repos — up/down facts. The agents (Altair,
     Meghan, Lyra) are a different layer; they live in the council
     (council.py), never as board tiles. Do not blur the two. */
  lastStatus=s;
  ['board','boardBig'].forEach(id=>{ const b=document.getElementById(id); if(!b) return; b.innerHTML='';
    b.appendChild(tile('k11-alpha · home', s.home_online?'up':'down', s.home_online?'the hub is alive':'the hub is not answering'));
    s.endpoints.forEach(e=>b.appendChild(tile(e.name.split('(')[0].trim(), e.up?'up':'down', e.up?('answering · '+e.ms+' ms · :'+e.port):'not answering · :'+e.port)));
    if(s.tailnet) s.tailnet.peers.forEach(p=>b.appendChild(tile(p.name, p.online?'up':'down', p.online?'on the tailnet':'offline')));
    s.repos.forEach(r=>b.appendChild(tile(r.name, r.dirty? 'warn':'info', r.branch+' · '+r.dirty+' uncommitted · '+r.track)));
  });
  const ft=document.getElementById('fleetText');
  if(ft && s.tailnet){ ft.innerHTML='';
    const c=document.createElement('div'); c.className='card';
    c.innerHTML='<h3>Tailnet</h3><p>this machine: '+s.tailnet.self+' · peers: '+
      s.tailnet.peers.map(p=>(p.online?'● ':'○ ')+p.name).join(' · ')+'</p>'+
      '<p class="sub">Inference lives on its own fabric; only jobs and answers cross. Outsiders: hard by design.</p>';
    ft.appendChild(c); }
}
async function refreshPill(){
  try{ const s=await (await fetch('/api/status')).json(); renderBoard(s);
    const down=s.endpoints.filter(e=>!e.up).length;
    pill.textContent = down? `NOT READY. — ${down} endpoint(s) down` : 'READY.';
    pill.style.borderColor = down? '#f85149' : '#3fb950';
  }catch(e){ pill.textContent='NOT READY.'; pill.style.borderColor='#f85149'; }
}
document.getElementById('boardBtn').onclick=()=>{ const b=document.getElementById('board');
  b.style.display = b.style.display==='none' ? 'grid' : 'none'; };
async function showStatus(){
  const s=await (await fetch('/api/status')).json();
  let lines=['Ecosystem status'];
  s.endpoints.forEach(e=>lines.push(`${e.up?'✓':'✗'} ${e.name} — ${e.up?e.ms+' ms':'DOWN'}`));
  if(s.tailnet){ lines.push(`tailnet (this machine: ${s.tailnet.self})`);
    s.tailnet.peers.forEach(p=>lines.push(`  ${p.online?'up ':'off'} ${p.name}`)); }
  s.repos.forEach(r=>lines.push(`git ${r.name}: ${r.branch}, ${r.dirty} uncommitted, ${r.track}`));
  add('tool', lines.join('\n'));
}
async function sendChat(){
  const body=text.value.trim(); if(!body && !pendingImage) return;
  if(body==='/status'){ text.value=''; showStatus(); return; }
  text.value='';
  const parts=[{type:'text',text:body||'(image)'}];
  if(pendingImage) parts.push({type:'image_url',image_url:{url:pendingImage}});
  messages.push({role:'user',content:parts});
  add('user', body, pendingImage); pendingImage=null;
  const out=add('assistant','');
  const payload={model:engineSel.value, messages:messages, stream:true};
  let acc='';
  try{
    const resp=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!resp.ok){ const e=await resp.json(); out.textContent='⚠ '+(e.error||resp.status); return; }
    const reader=resp.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){ const {done,value}=await reader.read(); if(done) break;
      buf+=dec.decode(value,{stream:true});
      let i; while((i=buf.indexOf('\n'))>=0){ const line=buf.slice(0,i).trim(); buf=buf.slice(i+1);
        if(!line.startsWith('data:')) continue; const data=line.slice(5).trim();
        if(data==='[DONE]') continue;
        try{ const j=JSON.parse(data); const delta=j.choices?.[0]?.delta?.content||'';
          acc+=delta; out.textContent=acc; out.parentElement.scrollIntoView({behavior:'smooth'}); }catch(e){}
      }
    }
  }catch(e){ out.textContent='⚠ engine unreachable — is link_up running? ('+e.message+')'; return; }
  messages.push({role:'assistant',content:acc});
  if(document.getElementById('speak').checked && acc){
    const u=new SpeechSynthesisUtterance(acc.slice(0,600)); speechSynthesis.speak(u);
  }
}
document.getElementById('send').onclick=sendChat;
text.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();} });
document.getElementById('statusBtn').onclick=showStatus;
const c64Btn=document.getElementById('c64Btn');
function setC64(on){ document.body.classList.toggle('c64',on);
  try{ localStorage.setItem('roadchat-c64', on?'1':''); }catch(e){} }
c64Btn.onclick=()=>{ const on=!document.body.classList.contains('c64'); setC64(on);
  if(on) add('tool','    **** SUCCESSBRIAN 64 BASIC V2 ****\nREADY.\n(ubuntu + ai under the hood — don\'t tell anyone)'); };
try{ if(localStorage.getItem('roadchat-c64')) setC64(true); }catch(e){}
const panel=document.getElementById('panel');
document.getElementById('scoreBtn').onclick=()=>{ panel.style.display=panel.style.display==='block'?'none':'block'; };
document.getElementById('scoreForm').addEventListener('submit', async e=>{
  e.preventDefault(); const f=new FormData(e.target), c={};
  for(const [k,v] of f.entries()){ c[k]=isNaN(v)||v==='' ? v : Number(v); }
  c.power_adapter = f.get('power_adapter')==='1'; c.soldered=false; c.usb32_gen2=true;
  const r=await (await fetch('/api/tools/score',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:c})})).json();
  if(r.error){ add('tool','⚠ scorer: '+r.error); return; }
  let lines=[`DealsDesk verdict: ${r.verdict} — score ${r.score} (delivered $${r.delivered_usd}, RAM value $${r.ram_value_usd})`];
  (r.pull_parts||[]).forEach(p=>lines.push('pull part: '+p));
  (r.notes||[]).forEach(n=>lines.push('· '+n));
  add('tool', lines.join('\n')); panel.style.display='none';
});
const file=document.getElementById('file');
document.getElementById('attach').onclick=()=>file.click();
file.addEventListener('change',()=>{ const f=file.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ pendingImage=r.result; add('tool','image attached — it will ride with your next message'); };
  r.readAsDataURL(f); });
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const mic=document.getElementById('mic');
if(!SR){ mic.disabled=true; mic.title='Speech recognition not supported in this browser'; }
else mic.onclick=()=>{ const rec=new SR(); rec.lang='en-US';
  rec.onresult=e=>{ text.value=e.results[0][0].transcript; }; rec.start(); };
refreshPill();
let codeLoaded=false;
async function loadCode(){
  if(codeLoaded) return; codeLoaded=true;
  const room=document.getElementById('codeRoom');
  try{ const s=await (await fetch('/api/code')).json(); room.innerHTML='';
    if(lastStatus) lastStatus.repos.forEach(r=>{ const c=document.createElement('div'); c.className='card';
      c.innerHTML='<h3>📦 '+r.name+'</h3><p class="sub">'+r.branch+' · '+r.dirty+' uncommitted · '+r.track+'</p>'; room.appendChild(c); });
    const ch=document.createElement('div'); ch.className='card';
    ch.innerHTML='<h3>Machine classes</h3>'+s.classes.map(c=>'<p><b>'+c.name+'</b> — '+c.status+'<br><span class="sub">'+c.mission+'</span></p>').join('');
    room.appendChild(ch);
    const th=document.createElement('div'); th.className='card';
    th.innerHTML='<h3>⛔ Never — the trap registry</h3>'+s.traps.map(t=>'<p><b>'+t.name+'</b> ('+t.kind+')<br><span class="sub">'+t.mechanism+'</span></p>').join('');
    room.appendChild(th);
  }catch(e){ room.innerHTML='<p class="sub">code room failed to load: '+e.message+'</p>'; }
}
function setView(name){
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active', v.id==='view-'+name));
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on', b.dataset.view===name));
  document.getElementById('bar').style.display = name==='chat' ? '' : 'none';
  if(name==='code') loadCode();
}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>setView(b.dataset.view));
document.getElementById('brainForm').addEventListener('submit', async e=>{
  e.preventDefault(); const q=document.getElementById('brainQ').value.trim(); if(!q) return;
  const out=document.getElementById('brainResults'); out.innerHTML='<p class="sub">searching…</p>';
  try{ const s=await (await fetch('/api/brain?q='+encodeURIComponent(q))).json(); out.innerHTML='';
    if(!s.hits.length){ out.innerHTML='<p class="sub">no hits in the local docs for "'+q+'". (AnythingLLM takes this slot when wired.)</p>'; return; }
    s.hits.forEach(h=>{ const c=document.createElement('div'); c.className='card';
      c.innerHTML='<h3 style="font-size:.9rem">📄 '+h.file+'</h3><p>'+h.snippet.replace(/</g,'&lt;')+'</p>'; out.appendChild(c); });
  }catch(err){ out.innerHTML='<p class="sub">brain search failed: '+err.message+'</p>'; }
});
let saver=false, pollTimer=null;
function schedulePoll(){ clearTimeout(pollTimer);
  pollTimer=setTimeout(async ()=>{ if(!document.hidden) await refreshPill(); schedulePoll(); }, saver?120000:30000); }
schedulePoll();
const saverBtn=document.getElementById('saverBtn');
function setSaver(on){ saver=on; saverBtn.textContent='🔋 saver: '+(on?'on':'off'); schedulePoll(); }
saverBtn.onclick=()=>setSaver(!saver);
if(navigator.getBattery) navigator.getBattery().then(b=>{
  const check=()=>{ if(!b.charging && b.level<=0.30 && !saver){ setSaver(true);
    add('tool','🔋 battery at '+Math.round(b.level*100)+'% and not charging — saver mode on: the board slows down and the laptop rests. Home still does the heavy lifting.'); } };
  b.addEventListener('levelchange',check); b.addEventListener('chargingchange',check); check();
});
add('assistant','**** SBOS TRAVEL CONSOLE ****\nREADY.\nYou are talking to the home fleet — pick Penny for fast, Morpheus for deep. Try /status, or score a listing.');
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            try:
                self._json(run_status())
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif self.path == "/api/code":
            try:
                self._json(run_code())
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif self.path.startswith("/api/brain"):
            try:
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                self._json(run_brain(q))
            except Exception as e:
                self._json({"error": str(e)}, 500)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/chat":
            try:
                data = self._read_json()
                engine = data.get("model", DEFAULT_ENGINE)
                if engine not in ENGINES:
                    return self._json({"error": "unknown engine"}, 400)
                payload = {"model": engine,
                           "messages": data.get("messages", []),
                           "stream": True}
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                for line in engine_chat(payload, engine):
                    self.wfile.write(line)
                    self.wfile.flush()
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                try:
                    self._json({"error": "engine unreachable: %s" % e}, 502)
                except Exception:
                    pass
            except Exception as e:
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass
        elif self.path == "/api/tools/score":
            try:
                data = self._read_json()
                self._json(run_score(data.get("candidate") or {}))
            except Exception as e:
                self._json({"error": str(e)}, 500)
        else:
            self._json({"error": "not found"}, 404)


def main():
    if "--selftest" in sys.argv:
        assert DEFAULT_ENGINE in ENGINES and "RoadChat" in PAGE
        print("selftest: OK (engines %s, port %d)"
              % (", ".join(sorted(ENGINES)), PORT))
        return 0
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("RoadChat on http://127.0.0.1:%d (Ctrl-C to stop)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
