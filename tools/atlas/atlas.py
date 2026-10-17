#!/usr/bin/env python3
"""Atlas CLI - the planning graph above the PM.
Graphs, not trees. Usage:
  atlas.py add-node <key> <type> <name> [--status S] [--ref KIND:ID] [--details JSON]
  atlas.py add-edge <from> <to> <edge-type> [--notes TEXT]
  atlas.py show [--type T] [--status S]
  atlas.py impact <key>        # what breaks if this slips? (downstream)
  atlas.py depends <key>       # what does this need? (upstream)
  atlas.py edges <key>         # all edges touching a node
"""
import json, subprocess, sys, argparse

def psql(sql):
    p = subprocess.run(
        ['psql', '-h', 'localhost', '-U', 'postgres', '-d', 'ecosystem_central',
         '-t', '-A', '-F', '\t', '-v', 'ON_ERROR_STOP=1'],
        input=sql, capture_output=True, text=True,
        env={'PGPASSWORD': 'postgres', 'PATH': '/usr/bin:/bin'})
    if p.returncode != 0:
        print(p.stderr.strip(), file=sys.stderr); sys.exit(1)
    return [l for l in p.stdout.split('\n') if l]

def q(s):
    return "'" + s.replace("'", "''") + "'"

def add_node(a):
    ref_kind, ref_id = None, None
    if a.ref and ':' in a.ref:
        ref_kind, ref_id = a.ref.split(':', 1)
    det = a.details or '{}'
    psql(f"INSERT INTO atlas.nodes (node_key, node_type, name, status, details, ref_kind, ref_id) "
         f"VALUES ({q(a.key)}, {q(a.type)}, {q(a.name)}, {q(a.status)}, {q(det)}::jsonb, "
         f"{q(ref_kind) if ref_kind else 'NULL'}, {q(ref_id) if ref_id else 'NULL'}) "
         f"ON CONFLICT (node_key) DO UPDATE SET name=EXCLUDED.name, status=EXCLUDED.status, "
         f"details=EXCLUDED.details, updated_at=NOW();")
    print(f"node {a.key}")

def add_edge(a):
    psql(f"INSERT INTO atlas.edges (from_node, to_node, edge_type, notes) "
         f"VALUES ({q(a.from_)}, {q(a.to)}, {q(a.edge_type)}, {q(a.notes) if a.notes else 'NULL'}) "
         f"ON CONFLICT (from_node, to_node, edge_type) DO NOTHING;")
    print(f"edge {a.from_} -[{a.edge_type}]-> {a.to}")

def show(a):
    where = []
    if a.type: where.append(f"node_type={q(a.type)}")
    if a.status: where.append(f"status={q(a.status)}")
    w = f"WHERE {' AND '.join(where)}" if where else ""
    for line in psql(f"SELECT node_key, node_type, name, status FROM atlas.nodes {w} ORDER BY node_type, name;"):
        k, t, n, s = line.split('\t')
        print(f"{k} [{t}] {n} ({s})")

def edges(a):
    for line in psql(f"SELECT from_node, edge_type, to_node FROM atlas.edges "
                     f"WHERE from_node={q(a.key)} OR to_node={q(a.key)} ORDER BY edge_type;"):
        f, t, to = line.split('\t')
        print(f"{f} -[{t}]-> {to}")

def walk(start, direction, depth=4):
    seen, out = set(), []
    frontier = [(start, 0)]
    while frontier:
        node, d = frontier.pop(0)
        if d >= depth or node in seen: continue
        seen.add(node)
        col = 'from_node' if direction == 'down' else 'to_node'
        other = 'to_node' if direction == 'down' else 'from_node'
        for line in psql(f"SELECT {other}, edge_type FROM atlas.edges WHERE {col}={q(node)};"):
            o, et = line.split('\t')
            if o not in seen:
                out.append((d + 1, node, et, o))
                frontier.append((o, d + 1))
    return out

def impact(a):
    print(f"What breaks if '{a.key}' slips:")
    rows = walk(a.key, 'down')
    if not rows: print("  (nothing downstream recorded)"); return
    for d, f, et, o in sorted(rows):
        print(f"  {'  ' * d}{f} -[{et}]-> {o}")

def depends(a):
    print(f"What '{a.key}' needs upstream:")
    rows = walk(a.key, 'up')
    if not rows: print("  (nothing upstream recorded)"); return
    for d, f, et, o in sorted(rows):
        print(f"  {'  ' * d}{o} -[{et}]-> {f}")


def research(a):
    print("RESEARCH QUEUE - items the ecosystem should help investigate:")
    rows = psql("SELECT node_key, node_type, name, details FROM atlas.nodes WHERE status='researching' ORDER BY node_key;")
    if not rows:
        print("  (queue empty)"); return
    for line in rows:
        parts = line.split('	')
        k, t, n = parts[0], parts[1], parts[2]
        d = parts[3] if len(parts) > 3 else '{}'
        print("\n%s [%s] %s" % (k, t, n))
        try:
            det = json.loads(d or '{}')
            if det.get('note'):
                print("  note: %s" % det['note'])
        except Exception:
            pass
        for eline in psql("SELECT from_node, edge_type, to_node FROM atlas.edges WHERE from_node='%s' OR to_node='%s' ORDER BY edge_type;" % (k.replace("'", "''"), k.replace("'", "''"))):
            f, et, to = eline.split('	')
            print("  %s -[%s]-> %s" % (f, et, to))


CONSTRAIN = ("blocks", "enables", "requires", "feeds")

def walk_filtered(start, direction, edge_types, depth=6):
    seen, out = set(), []
    frontier = [(start, 0)]
    types = ",".join("'%s'" % t for t in edge_types)
    while frontier:
        node, d = frontier.pop(0)
        if d >= depth or node in seen:
            continue
        seen.add(node)
        col = "from_node" if direction == "down" else "to_node"
        other = "to_node" if direction == "down" else "from_node"
        for line in psql("SELECT %s, edge_type FROM atlas.edges WHERE %s='%s' AND edge_type IN (%s);" % (other, col, node.replace("'", "''"), types)):
            o, et = line.split("\t")
            if o not in seen:
                out.append((d + 1, node, et, o))
                frontier.append((o, d + 1))
    return out

def whatif(a):
    print("WHAT-IF: '%s' slips or fails - delay propagates downstream:" % a.key)
    rows = walk_filtered(a.key, "down", CONSTRAIN)
    if not rows:
        print("  (nothing downstream constrained)"); return
    for d, f, et, o in sorted(rows):
        print("  %s%s -[%s]-> %s" % ("  " * d, f, et, o))
    print("\n%d downstream items affected." % len({o for _, _, _, o in rows}))

def gaps(a):
    print("GAP DETECTION:")
    print("\n[1] Orphan nodes (no edges at all):")
    rows = psql("SELECT node_key, node_type, name FROM atlas.nodes n WHERE NOT EXISTS (SELECT 1 FROM atlas.edges e WHERE e.from_node=n.node_key OR e.to_node=n.node_key) ORDER BY node_type, node_key;")
    for line in rows:
        k, t, n = line.split("\t"); print("  %s [%s] %s" % (k, t, n))
    if not rows: print("  (none)")
    print("\n[2] Projects with no inventory mapped (no code/cron/model/infra/doc):")
    rows = psql("SELECT node_key, name FROM atlas.nodes WHERE node_type='project' AND status IN ('active','planned');")
    for line in rows:
        k, n = line.split("\t")
        inv = psql("SELECT count(*) FROM atlas.edges WHERE to_node='%s' AND edge_type IN ('maps-to','supports','hosts');" % k.replace("'", "''"))
        if inv and inv[0].strip() == "0":
            print("  %s %s" % (k, n))
    print("\n[3] Gates with no recorded criteria:")
    rows = psql("SELECT node_key, name FROM atlas.nodes WHERE node_type='gate' AND (details IS NULL OR details::text='{}');")
    for line in rows:
        k, n = line.split("\t"); print("  %s %s" % (k, n))
    if not rows: print("  (none)")

def critical(a):
    print("CRITICAL PATH to '%s' (longest chain of constraints):" % a.key)
    memo = {}
    def longest(node, visiting):
        if node in memo: return memo[node]
        if node in visiting: return []
        visiting = visiting | {node}
        best = []
        for line in psql("SELECT from_node FROM atlas.edges WHERE to_node='%s' AND edge_type IN ('blocks','requires','enables');" % node.replace("'", "''")):
            f = line.strip()
            if not f: continue
            path = longest(f, visiting)
            if len(path) > len(best): best = path
        memo[node] = best + [node]
        return memo[node]
    path = longest(a.key, set())
    for i, k in enumerate(path):
        print("  %d. %s" % (i + 1, k))
    print("\n%d steps deep." % len(path))

def compare(a):
    ka, kb = a.key_a, a.key_b
    ALLT = ("blocks", "enables", "requires", "feeds", "hosts", "near", "maps-to", "supports", "runs-on", "backup-for", "becomes", "documents")
    da = {o for _, _, _, o in walk_filtered(ka, "down", ALLT)} | {ka}
    db = {o for _, _, _, o in walk_filtered(kb, "down", ALLT)} | {kb}
    print("OPTION COMPARISON:")
    print("\nUnder '%s' (%d items):" % (ka, len(da)))
    for k in sorted(da - db): print("  + %s" % k)
    print("\nUnder '%s' (%d items):" % (kb, len(db)))
    for k in sorted(db - da): print("  + %s" % k)
    print("\nCommon to both (%d):" % len(da & db))
    for k in sorted(da & db): print("  = %s" % k)

def audit(a):
    import os, json as _json
    print("ATLAS SELF-AUDIT:")
    print("\n[1] Stale nodes (untouched 30+ days):")
    rows = psql("SELECT node_key, node_type, updated_at::date FROM atlas.nodes WHERE updated_at < NOW() - INTERVAL '30 days' ORDER BY updated_at LIMIT 20;")
    for line in rows: print("  %s" % line.replace("\t", " | "))
    if not rows: print("  (none)")
    print("\n[2] Doc nodes whose files are missing:")
    rows = psql("SELECT node_key, details FROM atlas.nodes WHERE node_type='doc';")
    missing = 0
    for line in rows:
        k, d = line.split("\t", 1)
        try: det = _json.loads(d or "{}")
        except Exception: continue
        path, kind = det.get("path"), det.get("kind")
        if det.get("host") == "hatch-vm":
            print("  (on Hatch VM, not verifiable from k11): %s" % k); continue
        if not path or kind not in ("repo_doc", "skill_file", "goal_doc"): continue
        base = {"repo_doc": "/home/successbrian/successbrian-os", "skill_file": "/home/successbrian", "goal_doc": "/home/hatch/workspace"}.get(kind, "")
        full = os.path.join(base, path) if not path.startswith("/") else path
        if not os.path.exists(full):
            print("  MISSING: %s -> %s" % (k, full)); missing += 1
    if not missing: print("  (all present)")
    print("\n[3] Nodes with no edges:")
    rows = psql("SELECT count(*) FROM atlas.nodes n WHERE NOT EXISTS (SELECT 1 FROM atlas.edges e WHERE e.from_node=n.node_key OR e.to_node=n.node_key);")
    print("  %s orphan nodes" % (rows[0].strip() if rows else "?"))

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest='cmd', required=True)
s = sub.add_parser('add-node'); s.add_argument('key'); s.add_argument('type'); s.add_argument('name')
s.add_argument('--status', default='planned'); s.add_argument('--ref'); s.add_argument('--details')
s = sub.add_parser('add-edge'); s.add_argument('from_', metavar='from'); s.add_argument('to'); s.add_argument('edge_type'); s.add_argument('--notes')
s = sub.add_parser('show'); s.add_argument('--type'); s.add_argument('--status')
s = sub.add_parser('edges'); s.add_argument('key')
s = sub.add_parser('impact'); s.add_argument('key')
s = sub.add_parser('depends'); s.add_argument('key')
sub.add_parser('research')
s = sub.add_parser('whatif'); s.add_argument('key')
s = sub.add_parser('gaps')
s = sub.add_parser('critical'); s.add_argument('key')
s = sub.add_parser('compare'); s.add_argument('key_a'); s.add_argument('key_b')
s = sub.add_parser('audit')
a = p.parse_args()
{'add-node': add_node, 'add-edge': add_edge, 'show': show, 'edges': edges,
 'impact': impact, 'depends': depends, 'research': research, 'whatif': whatif, 'gaps': gaps, 'critical': critical, 'compare': compare, 'audit': audit}[a.cmd](a)
