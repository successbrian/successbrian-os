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
a = p.parse_args()
{'add-node': add_node, 'add-edge': add_edge, 'show': show, 'edges': edges,
 'impact': impact, 'depends': depends, 'research': research}[a.cmd](a)
