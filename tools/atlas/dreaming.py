#!/usr/bin/env python3
"""dreaming.py — Atlas nightly dreaming / consolidation pass.

Brian's order (2026-10-27): a nightly pass that scans Atlas for
duplicates, contradictions and stale/superseded nodes, like a
sleeping brain consolidating memory — but gated, honestly.

GATES (hard laws):
  * Mode lives in atlas.dream_config (single row), DEFAULT dry_run.
  * dry_run: NOTHING in atlas.nodes / atlas.edges changes.
    Everything goes to the review list (atlas.dream_review) + diary.
  * live: ONLY exact-duplicate merges auto-apply, via BI-TEMPORAL
    INVALIDATION — loser status='superseded', its original details
    preserved under 'pre_merge_details', merged details carry
    {superseded_by, dreaming_run_id, invalidated_at}, plus an edge
    loser -[superseded_by]-> winner. Rows are NEVER deleted.
  * Near-duplicates, contradictions, stale items and capture
    matches are review-only in BOTH modes.
  * Every live action is written to atlas.dream_actions.

SCAN (deterministic heuristics, confidence labelled):
  (a) Duplicates: exact = same node_type + normalized name
      (lowercase, punctuation/space-collapsed); near = same type +
      token Jaccard >= 0.8 in Python (pg_trgm exists on this DB —
      checked 2026-10-27 — but the Python path is deterministic and
      needs no extension, so it is the one used).
  (b) Contradictions: duplicate groups with conflicting status;
      plus pairs whose details jsonb disagree on a shared scalar
      key ('status','price','owner', or any shared scalar).
  (c) Stale/superseded candidates: in a duplicate group, a node
      untouched 90+ days beside a sibling touched in last 30 days.
      Captures: atlas.scattered_captures from the last 7 days whose
      title matches an existing node name -> review item only.

DIARY: rolling journal at tools/atlas/state/DREAMS_DIARY.md —
APPEND a dated section per run (diary is a journal; history is
kept on disk). The full file is embedded each run into the
AnythingLLM workspace 'successbrian-os' (the OS/Atlas home in
allm_workspaces.REGISTRY) via allm_embed.py, which replaces the
prior embedded edition — the file on disk keeps the full journal.

CLI:
  dreaming.py run [--dry-run|--live]   # mode defaults to config
  dreaming.py selftest
  dreaming.py show-config
"""
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import psycopg2.extras

DBNAME = "ecosystem_central"
DIARY_PATH = os.path.expanduser("~/successbrian-os/tools/atlas/state/DREAMS_DIARY.md")
DIARY_SLUG = "successbrian-os"
DIARY_FILENAME = "DREAMS_DIARY.md"
NEAR_THRESHOLD = 0.8

DDL = """
CREATE TABLE IF NOT EXISTS atlas.dream_config (
    id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    mode text NOT NULL DEFAULT 'dry_run' CHECK (mode IN ('dry_run','live')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    note text
);
INSERT INTO atlas.dream_config (id, mode, note)
VALUES (1, 'dry_run', 'Set 2026-10-27 by Brian order via dreaming build; dry_run is the shipped default')
ON CONFLICT (id) DO NOTHING;
CREATE TABLE IF NOT EXISTS atlas.dream_runs (
    id serial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    mode text NOT NULL,
    counts jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS atlas.dream_review (
    id serial PRIMARY KEY,
    run_id int REFERENCES atlas.dream_runs(id),
    kind text NOT NULL,
    subject_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atlas.dream_actions (
    id serial PRIMARY KEY,
    run_id int REFERENCES atlas.dream_runs(id),
    action text NOT NULL,
    subject text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    ts timestamptz NOT NULL DEFAULT now()
);
"""

def connect():
    return psycopg2.connect(dbname=DBNAME, host="localhost", user="postgres")

def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()

def get_mode(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT mode FROM atlas.dream_config WHERE id=1")
        row = cur.fetchone()
        return row[0] if row else "dry_run"

def normalize(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (name or "").lower())).strip()

def tokens(name):
    return set(normalize(name).split()) if normalize(name) else set()

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def fetch_nodes(conn, key_prefix=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if key_prefix:
            cur.execute("SELECT node_key,node_type,name,status,details,created_at,updated_at FROM atlas.nodes WHERE node_key LIKE %s ORDER BY node_type,name,node_key", (key_prefix + "%",))
        else:
            cur.execute("SELECT node_key,node_type,name,status,details,created_at,updated_at FROM atlas.nodes ORDER BY node_type,name,node_key")
        return [dict(r) for r in cur.fetchall()]

def exact_groups(nodes):
    groups = defaultdict(list)
    for n in nodes:
        if n["status"] == "superseded":
            continue
        groups[(n["node_type"], normalize(n["name"]))].append(n)
    return [g for g in groups.values() if len(g) > 1]

def near_pairs(nodes):
    by_type = defaultdict(list)
    for n in nodes:
        if n["status"] == "superseded":
            continue
        by_type[n["node_type"]].append(n)
    pairs = []
    # Token blocking: a pair with Jaccard >= 0.8 must share a token,
    # so only pairs sharing a token are candidates (exact otherwise
    # this is O(n^2) over the whole graph).
    for t, lst in by_type.items():
        cand = set()
        by_token = defaultdict(list)
        for idx, n in enumerate(lst):
            for tok in tokens(n["name"]):
                by_token[tok].append(idx)
        for idxs in by_token.values():
            for i in range(len(idxs)):
                for j in range(i+1, len(idxs)):
                    cand.add((idxs[i], idxs[j]))
        for i, j in sorted(cand):
            a, b = lst[i], lst[j]
            if normalize(a["name"]) == normalize(b["name"]):
                continue
            sim = jaccard(tokens(a["name"]), tokens(b["name"]))
            if sim >= NEAR_THRESHOLD:
                pairs.append((a, b, sim))
    return pairs

def dup_groups_all(nodes):
    """Union groups from exact + near for contradiction/stale scans."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    by_key = {n["node_key"]: n for n in nodes}
    for g in exact_groups(nodes):
        for n in g[1:]: union(g[0]["node_key"], n["node_key"])
    for a, b, _ in near_pairs(nodes):
        union(a["node_key"], b["node_key"])
    groups = defaultdict(list)
    for k in list(parent.keys()):
        groups[find(k)].append(by_key[k])
    return [g for g in groups.values() if len(g) > 1]

def find_contradictions(groups):
    items = []
    scalar_keys = ["status", "price", "owner"]
    for g in groups:
        statuses = sorted(set(n["status"] for n in g))
        if len(statuses) > 1:
            items.append({"kind": "contradiction_status", "subject_keys": [n["node_key"] for n in g],
                          "detail": {"values": {n["node_key"]: n["status"] for n in g},
                                     "explanation": f"Duplicate group carries conflicting status values: {statuses}"}})
        # details disagreements — AGGREGATED per group+key (one review
        # item quoting every distinct value). Pair-by-pair reporting
        # exploded on real data (run #6: 25,478 items from large
        # placeholder-name groups); aggregation keeps the same facts.
        by_key = {}
        for n in g:
            for k, v in (n["details"] or {}).items():
                if isinstance(v, (str, int, float, bool)):
                    by_key.setdefault(k, {}).setdefault(repr(v), []).append(n["node_key"])
        for k in sorted(by_key):
            vals = by_key[k]
            if len(vals) > 1:
                quoted = "; ".join(f"{v} (x{len(ks)}, e.g. {ks[0]})" for v, ks in sorted(vals.items()))
                items.append({"kind": "contradiction_details", "subject_keys": [n["node_key"] for n in g],
                              "detail": {"key": k, "distinct_values": {v: ks for v, ks in vals.items()},
                                         "priority_key": k in scalar_keys,
                                         "explanation": f"details['{k}'] disagrees across duplicate group: {quoted}"}})
    return items

def find_stale(groups, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    items = []
    for g in groups:
        fresh = [n for n in g if n["updated_at"] and (now - n["updated_at"]).days < 30]
        old = [n for n in g if n["updated_at"] and (now - n["updated_at"]).days >= 90]
        for o in old:
            if fresh:
                items.append({"kind": "stale_possibly_superseded", "subject_keys": [n["node_key"] for n in g],
                              "detail": {"stale_node": o["node_key"], "stale_updated_at": o["updated_at"].isoformat(),
                                         "fresh_siblings": [f["node_key"] for f in fresh],
                                         "explanation": f"{o['node_key']} not updated in 90+ days beside sibling(s) updated in last 30 days — possibly superseded"}})
    return items

def find_capture_matches(conn, nodes, key_prefix=None):
    items = []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id,title,created_at FROM atlas.scattered_captures WHERE created_at >= now() - interval '7 days' ORDER BY created_at DESC")
        caps = [dict(r) for r in cur.fetchall()]
    # N-gram lookup: a node name matches when it appears as a contiguous
    # token sequence in the capture title (or the title inside the name).
    name_dict = {}
    first_tok = defaultdict(list)
    for n in nodes:
        nn = normalize(n["name"])
        if len(nn) >= 4:
            name_dict.setdefault(nn, n)
            first_tok[nn.split()[0]].append((nn, n))
    for c in caps:
        ct = normalize(c["title"])
        if not ct: continue
        toks = ct.split()
        hit = None
        for span in range(min(6, len(toks)), 0, -1):
            for i in range(len(toks)-span+1):
                gram = " ".join(toks[i:i+span])
                if gram in name_dict:
                    hit = name_dict[gram]; break
            if hit: break
        if not hit and len(ct) >= 4:
            for nn, n in first_tok.get(toks[0], []):
                if ct in nn: hit = n; break
        if hit:
            if key_prefix and not hit["node_key"].startswith(key_prefix):
                continue
            items.append({"kind": "capture_matches_node", "subject_keys": [hit["node_key"]],
                          "detail": {"capture_id": c["id"], "capture_title": c["title"], "node_name": hit["name"],
                                     "explanation": f"Capture #{c['id']} '{c['title']}' (last 7d) matches existing node {hit['node_key']} — possible new info about a known subject; no auto-action"}})
    return items

def choose_winner(group):
    # most recently updated wins; tie-break earliest created, then node_key
    return sorted(group, key=lambda n: (n["updated_at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), ), reverse=True)[0] if False else sorted(group, key=lambda n: (-(n["updated_at"].timestamp() if n["updated_at"] else 0), n["node_key"]))[0]

def apply_exact_merges(conn, run_id, groups):
    actions = []
    with conn.cursor() as cur:
        for g in groups:
            winner = choose_winner(g)
            for loser in g:
                if loser["node_key"] == winner["node_key"]: continue
                if loser["status"] == "superseded": continue
                orig = loser["details"] or {}
                merged = dict(orig)
                merged["pre_merge_details"] = orig
                merged["superseded_by"] = winner["node_key"]
                merged["dreaming_run_id"] = run_id
                merged["invalidated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                cur.execute("UPDATE atlas.nodes SET status='superseded', details=%s::jsonb, updated_at=now() WHERE node_key=%s",
                            (json.dumps(merged), loser["node_key"]))
                cur.execute("INSERT INTO atlas.edges (from_node,to_node,edge_type,notes) VALUES (%s,%s,'superseded_by',%s) ON CONFLICT (from_node,to_node,edge_type) DO NOTHING",
                            (loser["node_key"], winner["node_key"], f"dreaming run {run_id} exact-duplicate merge"))
                detail = {"loser": loser["node_key"], "winner": winner["node_key"], "normalized_name": normalize(loser["name"]), "node_type": loser["node_type"]}
                cur.execute("INSERT INTO atlas.dream_actions (run_id,action,subject,detail) VALUES (%s,'merge_exact_duplicate',%s,%s::jsonb)",
                            (run_id, loser["node_key"], json.dumps(detail)))
                actions.append(detail)
    conn.commit()
    return actions

def write_diary(run_id, mode, counts, exact, near, reviews, actions, started, embed=True):
    os.makedirs(os.path.dirname(DIARY_PATH), exist_ok=True)
    if mode == "dry_run":
        header = "DRY-RUN — no changes applied; auto-merge stays off until Brian flips atlas.dream_config to live"
    else:
        header = "LIVE — exact-duplicate merges applied (see Actions); everything else is review-only"
    lines = []
    lines.append(f"\n## Dreaming run #{run_id} — {started.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append(f"\n**MODE: {header}**\n")
    lines.append("### What was scanned")
    lines.append(f"- Nodes scanned: {counts.get('nodes_scanned',0)}; exact-duplicate groups: {counts.get('exact_groups',0)}; near-duplicate pairs: {counts.get('near_pairs',0)}")
    lines.append(f"- Contradictions: {counts.get('contradictions',0)}; stale/possibly-superseded: {counts.get('stale',0)}; capture matches (7d): {counts.get('capture_matches',0)}")
    lines.append("\n### Exact duplicates")
    if exact:
        for g in exact:
            lines.append(f"- {', '.join(n['node_key'] for n in g)} — [{g[0]['node_type']}] \"{g[0]['name']}\"")
    else:
        lines.append("- (none)")
    if mode == "live":
        lines.append("\n### Merged this run")
        if actions:
            for a in actions: lines.append(f"- {a['loser']} superseded_by {a['winner']}")
        else: lines.append("- (none)")
    lines.append("\n### Review list")
    if reviews:
        by_kind = defaultdict(list)
        for r in reviews: by_kind[r["kind"]].append(r)
        for kind in sorted(by_kind):
            lines.append(f"\n#### {kind}")
            for r in by_kind[kind]:
                expl = r["detail"].get("explanation", json.dumps(r["detail"])[:200])
                lines.append(f"- {', '.join(r['subject_keys'])} — {expl}")
    else:
        lines.append("- (empty)")
    lines.append(f"\n### Counts\n```json\n{json.dumps(counts, indent=2, default=str)}\n```\n")
    section = "\n".join(lines)
    if not os.path.exists(DIARY_PATH):
        with open(DIARY_PATH, "w") as f:
            f.write("# Atlas Dreams Diary\n\nRolling journal of Atlas dreaming/consolidation runs. APPEND by date — each run adds a dated section; history is kept in this file. The embedded copy in AnythingLLM (workspace successbrian-os, file DREAMS_DIARY.md) is replaced each run with this full journal.\n")
    with open(DIARY_PATH, "a") as f: f.write(section + "\n")
    # embed (replace prior edition) — skipped for scoped/selftest runs:
    # the diary file is still written; embeds of the full journal take
    # 30s+ each and made selftest slow enough to drop DB connections.
    if not embed:
        return "embed skipped (scoped run; diary file written, next full run embeds)"
    embed_note = ""
    try:
        import allm_embed
        text = open(DIARY_PATH).read()
        loc = allm_embed.embed_latest(DIARY_SLUG, DIARY_FILENAME, text)
        embed_note = f"embedded to {DIARY_SLUG}: {loc}"
    except Exception as e:
        embed_note = f"embed failed (diary kept on disk): {type(e).__name__}: {e}"
    return embed_note

def run(mode_override=None, key_prefix=None, embed=True):
    conn = connect(); ensure_schema(conn)
    mode = mode_override or get_mode(conn)
    started = dt.datetime.now(dt.timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO atlas.dream_runs (mode) VALUES (%s) RETURNING id", (mode,))
        run_id = cur.fetchone()[0]
    conn.commit()
    nodes = fetch_nodes(conn, key_prefix)
    exact = exact_groups(nodes)
    near = near_pairs(nodes)
    groups_all = dup_groups_all(nodes)
    contradictions = find_contradictions(groups_all)
    stale = find_stale(groups_all)
    captures = find_capture_matches(conn, nodes, key_prefix)
    reviews = []
    for g in exact:
        reviews.append({"kind": "exact_duplicate", "subject_keys": [n["node_key"] for n in g],
                        "detail": {"name": g[0]["name"], "node_type": g[0]["node_type"], "explanation": f"Exact duplicate: {len(g)} nodes share type '{g[0]['node_type']}' + normalized name '{normalize(g[0]['name'])}'" + (" — merged in live mode" if mode=="live" else " — would merge in live mode (dry-run: no change)")}})
    for a, b, sim in near:
        reviews.append({"kind": "near_duplicate", "subject_keys": [a["node_key"], b["node_key"]],
                        "detail": {"jaccard": round(sim,3), "explanation": f"Near duplicate (token Jaccard {sim:.2f} >= 0.80): '{a['name']}' vs '{b['name']}' — review only, never auto-merged"}})
    reviews.extend(contradictions); reviews.extend(stale); reviews.extend(captures)
    # The scan's Python phases can take a minute; the DB connection
    # may have been dropped meanwhile (seen live 2026-10-27: 'SSL
    # connection has been closed unexpectedly'). Revalidate/reconnect.
    try:
        with conn.cursor() as cur: cur.execute("SELECT 1")
    except Exception:
        try: conn.close()
        except Exception: pass
        conn = connect(); ensure_schema(conn)
    actions = []
    if mode == "live":
        actions = apply_exact_merges(conn, run_id, exact)
    counts = {"nodes_scanned": len(nodes), "exact_groups": len(exact), "exact_nodes": sum(len(g) for g in exact),
              "near_pairs": len(near), "contradictions": len(contradictions), "stale": len(stale),
              "capture_matches": len(captures), "review_items": len(reviews), "actions": len(actions), "mode": mode}
    with conn.cursor() as cur:
        for r in reviews:
            cur.execute("INSERT INTO atlas.dream_review (run_id,kind,subject_keys,detail) VALUES (%s,%s,%s::jsonb,%s::jsonb)",
                        (run_id, r["kind"], json.dumps(r["subject_keys"]), json.dumps(r["detail"], default=str)))
        cur.execute("UPDATE atlas.dream_runs SET finished_at=now(), counts=%s::jsonb WHERE id=%s", (json.dumps(counts), run_id))
    conn.commit()
    conn.close()  # close BEFORE the diary embed: embeds can take 30s+ and idle connections get dropped
    embed_note = write_diary(run_id, mode, counts, exact, near, reviews, actions, started, embed=embed)
    print(f"DREAMING run #{run_id} mode={mode} counts={json.dumps(counts)} diary={DIARY_PATH} {embed_note}")
    return run_id, counts, reviews, actions

# ---------- selftest ----------
def selftest():
    fails = []; total = [0]
    def ck(cond, label):
        total[0] += 1
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond: fails.append(label)
    conn = connect(); ensure_schema(conn)
    orig_mode = get_mode(conn)
    prefix = "test:dream:"
    def cleanup(c):
        with c.cursor() as cur:
            cur.execute("DELETE FROM atlas.edges WHERE from_node LIKE %s OR to_node LIKE %s", (prefix+"%", prefix+"%"))
            cur.execute("DELETE FROM atlas.dream_review WHERE subject_keys::text LIKE %s", ("%test:dream:%",))
            cur.execute("DELETE FROM atlas.dream_actions WHERE subject LIKE %s", (prefix+"%",))
            cur.execute("DELETE FROM atlas.nodes WHERE node_key LIKE %s", (prefix+"%",))
        c.commit()
    cleanup(conn)
    # fixtures
    fixtures = [
        ("test:dream:exact-a", "project", "Dream Exact Widget", "active", {"owner":"alice"}),
        ("test:dream:exact-b", "project", "Dream Exact Widget!", "active", {"owner":"alice"}),
        ("test:dream:near-a", "project", "Dream Near Alpha Beta Gamma Delta", "active", {}),
        ("test:dream:near-b", "project", "Dream Near Alpha Beta Gamma Delta Extra", "active", {}),
        ("test:dream:contra-a", "project", "Dream Contra Widget", "active", {"price":10,"owner":"alice"}),
        ("test:dream:contra-b", "project", "Dream Contra Widget", "planned", {"price":20,"owner":"bob"}),
    ]
    with conn.cursor() as cur:
        for k,t,n,s,d in fixtures:
            cur.execute("INSERT INTO atlas.nodes (node_key,node_type,name,status,details) VALUES (%s,%s,%s,%s,%s::jsonb)", (k,t,n,s,json.dumps(d)))
    conn.commit()
    nodes = fetch_nodes(conn, prefix)
    exact = exact_groups(nodes)
    ck(any(set(n["node_key"] for n in g)=={"test:dream:exact-a","test:dream:exact-b"} for g in exact), "exact-dup pair detected")
    near = near_pairs(nodes)
    ck(any({a["node_key"],b["node_key"]}=={"test:dream:near-a","test:dream:near-b"} for a,b,_ in near), "near-dup detected (Jaccard >=0.8)")
    contras = find_contradictions(dup_groups_all(nodes))
    ck(len(contras)>=1 and any("test:dream:contra-a" in c["subject_keys"] for c in contras), "contradiction detected (status/details)")
    # snapshot fixtures
    with conn.cursor() as cur:
        cur.execute("SELECT node_key,status,details::text FROM atlas.nodes WHERE node_key LIKE %s ORDER BY node_key", (prefix+"%",))
        before = cur.fetchall()
    # dry-run scoped
    run_id_dry, counts_dry, _, _ = run(mode_override="dry_run", key_prefix=prefix, embed=False)
    conn.close(); conn = connect()  # nested run's diary embed idles this conn; it may have been dropped
    with conn.cursor() as cur:
        cur.execute("SELECT node_key,status,details::text FROM atlas.nodes WHERE node_key LIKE %s ORDER BY node_key", (prefix+"%",))
        after_dry = cur.fetchall()
    ck(before == after_dry, "dry-run run changes ZERO fixture rows")
    # live scoped
    run_id_live, counts_live, _, actions_live = run(mode_override="live", key_prefix=prefix, embed=False)
    conn.close(); conn = connect()  # reconnect after nested run (see above)
    with conn.cursor() as cur:
        cur.execute("SELECT status,details FROM atlas.nodes WHERE node_key='test:dream:exact-b'")
        row_b = cur.fetchone()
        cur.execute("SELECT status,details FROM atlas.nodes WHERE node_key='test:dream:exact-a'")
        row_a = cur.fetchone()
        # winner is most recent updated — both same time, tie-break node_key so exact-a wins, exact-b loser; accept either loser superseded
        cur.execute("SELECT count(*) FROM atlas.edges WHERE edge_type='superseded_by' AND (from_node LIKE %s)", (prefix+"%",))
        edge_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM atlas.dream_actions WHERE run_id=%s AND action='merge_exact_duplicate'", (run_id_live,))
        audit_count = cur.fetchone()[0]
    # check at least one exact fixture superseded with preserved details
    superseded_ok = False; preserved_ok = False
    with conn.cursor() as cur:
        cur.execute("SELECT status,details FROM atlas.nodes WHERE node_key LIKE %s AND status='superseded'", (prefix+"%",))
        for st, det in cur.fetchall():
            if det and det.get("superseded_by") and "pre_merge_details" in det:
                superseded_ok = True
                if det["pre_merge_details"].get("owner") in ("alice","bob") or det["pre_merge_details"]=={} or "price" in det.get("pre_merge_details",{}):
                    preserved_ok = True
    ck(superseded_ok and edge_count>=1, "live-mode run merges exact-dup fixture (loser superseded, edge exists)")
    ck(audit_count>=1, "live merge writes audit row in dream_actions")
    ck(preserved_ok, "original details preserved under pre_merge_details")
    diary_ok = os.path.exists(DIARY_PATH) and f"Dreaming run #{run_id_live}" in open(DIARY_PATH).read()
    ck(diary_ok, "diary section written")
    cleanup(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM atlas.nodes WHERE node_key LIKE %s", (prefix+"%",))
        remaining = cur.fetchone()[0]
        # restore config
        cur.execute("UPDATE atlas.dream_config SET mode=%s, updated_at=now() WHERE id=1", (orig_mode,))
    conn.commit()
    ck(remaining==0, "fixtures cleaned up (including superseded rows)")
    conn.close()
    passed = total[0]-len(fails)
    print(f"SELFTEST {'OK' if not fails else 'FAILED'}: {passed}/{total[0]} passed, {len(fails)} failure(s)")
    return 1 if fails else 0

def main(argv):
    if len(argv)>1 and argv[1]=="selftest":
        return selftest()
    if len(argv)>1 and argv[1]=="show-config":
        conn=connect(); ensure_schema(conn); print(get_mode(conn)); conn.close(); return 0
    if len(argv)>1 and argv[1]=="run":
        mode=None
        if "--dry-run" in argv: mode="dry_run"
        if "--live" in argv: mode="live"
        run(mode_override=mode); return 0
    print(__doc__); return 2

if __name__=="__main__":
    sys.exit(main(sys.argv))
