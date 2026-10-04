#!/usr/bin/env python3
"""Map an industry the way Brian mapped the MLM industry: companies, links, intel, sources.

PURPOSE:
    For every income stream, help the entrepreneur develop the industry
    layout -- who the companies are, how they relate, what is happening
    with them over time, and which sources are worth watching. One
    "industry map" per income stream (or family of streams).

WHY:
    Brian mapped the MLM industry in Oct 2026 (companies table, links,
    intel log, intel sources, visual graph) and asked for it as code:
    every income stream deserves the same layout. Competitive research
    compounds -- a map turns scattered findings into a durable picture
    of the playing field instead of a pile of notes.

CALLED BY:
    CLI (`python3 industry_map.py <command>`) run by an agent session or
    the entrepreneur directly. A weekly cron can call `report` / feed
    `add-intel`. Importable as a library too.

NOTES:
    - CANONICAL: successbrian-os/tools/industry_map/
    - DB: successbrian_os.industry_maps + industry_companies +
      industry_company_links + industry_intel + industry_intel_sources.
      Runs against the k11 Postgres the same way tools/audience does
      (localhost psql from k11).
    - Generic schema on purpose: no entrepreneur-specific data is
      hard-coded. Brian's MLM map is seeded data, not schema.
    - status is free text; conventions: active | defunct | exited.
    - category conventions for intel: company_update | industry |
      regulatory | opportunity.
    - export-graph writes a standalone HTML file with an SVG radial map.
      Deterministic layout, no dependencies.
"""

import argparse
import datetime
import os
import subprocess
from xml.sax.saxutils import escape as _xesc

HERE = os.path.dirname(os.path.abspath(__file__))

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import pg_password

PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian"}
PG["password"] = pg_password(PG["host"], PG["dbname"], PG["user"])


def _psql(sql, variables=None, field_sep="\t"):
    """Run SQL via the psql CLI. Values go through -v variables so nothing
    is interpolated into SQL by hand."""
    env = dict(os.environ, PGPASSWORD=PG["password"])
    cmd = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", field_sep]
    for k, v in (variables or {}).items():
        cmd += ["-v", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                       env=env)
    if p.returncode != 0:
        raise RuntimeError("psql failed: " + p.stderr.strip()[-400:])
    return p.stdout


def _rows(sql, variables=None):
    return [l for l in _psql(sql, variables).split("\n") if l.strip()]


def _map_id(slug):
    rows = _rows("SELECT id FROM successbrian_os.industry_maps "
                 "WHERE slug=:'slug';", {"slug": slug})
    if not rows:
        raise SystemExit("no industry map with slug '%s'" % slug)
    return rows[0]


# ---------------------------------------------------------------- commands

def cmd_init_db(_args):
    _psql(open(os.path.join(HERE, "schema.sql")).read())
    print("industry_map schema ready")


def cmd_new_map(args):
    _psql(
        "INSERT INTO successbrian_os.industry_maps"
        " (slug, name, income_stream, description) VALUES"
        " (:'slug', :'name', :'stream', :'desc')"
        " ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name,"
        " income_stream=EXCLUDED.income_stream,"
        " description=EXCLUDED.description;",
        {"slug": args.slug, "name": args.name, "stream": args.income_stream,
         "desc": args.description or ""})
    print("industry map upserted: %s" % args.slug)


def cmd_list_maps(_args):
    rows = _rows("SELECT slug, name, income_stream FROM"
                 " successbrian_os.industry_maps ORDER BY slug;")
    if not rows:
        print("no industry maps yet -- run new-map first")
        return
    for r in rows:
        slug, name, stream = r.split("\t")
        print("%-24s %-40s [%s]" % (slug, name, stream))


def cmd_add_company(args):
    mid = _map_id(args.map)
    _psql(
        "INSERT INTO successbrian_os.industry_companies"
        " (map_id, name, sector, what_we_know, status, is_mine, my_role)"
        " VALUES (:'mid', :'name', :'sector', :'what', :'status',"
        "         :'mine'::boolean, :'role')"
        " ON CONFLICT (map_id, name) DO UPDATE SET"
        " sector=EXCLUDED.sector, what_we_know=EXCLUDED.what_we_know,"
        " status=EXCLUDED.status, is_mine=EXCLUDED.is_mine,"
        " my_role=EXCLUDED.my_role;",
        {"mid": mid, "name": args.name, "sector": args.sector or "",
         "what": args.what or "", "status": args.status or "active",
         "mine": "true" if args.mine else "false",
         "role": args.my_role or ""})
    print("company upserted: %s [%s]" % (args.name, args.map))


def cmd_list_companies(args):
    mid = _map_id(args.map)
    filt = "" if not args.status else " AND status=:'status'"
    rows = _rows(
        "SELECT name, status, is_mine FROM successbrian_os.industry_companies"
        " WHERE map_id=:'mid'" + filt + " ORDER BY name;",
        {"mid": mid, "status": args.status or ""})
    if not rows:
        print("no companies on map '%s'" % args.map)
        return
    for r in rows:
        name, status, is_mine = r.split("\t")
        mark = " *MINE*" if is_mine == "t" else ""
        print("%-32s %-12s%s" % (name, status, mark))
    print("(%d companies)" % len(rows))


def cmd_add_link(args):
    mid = _map_id(args.map)
    _psql(
        "INSERT INTO successbrian_os.industry_company_links"
        " (map_id, from_node, to_company, relationship, notes) VALUES"
        " (:'mid', :'frm', :'to', :'rel', :'notes');",
        {"mid": mid, "frm": args.frm, "to": args.to,
         "rel": args.relationship, "notes": args.notes or ""})
    print("link added: %s --(%s)--> %s" % (args.frm, args.relationship,
                                           args.to))


def cmd_add_intel(args):
    mid = _map_id(args.map)
    _psql(
        "INSERT INTO successbrian_os.industry_intel"
        " (map_id, company_name, intel_date, category, finding, source_url)"
        " VALUES (:'mid', :'company', :'ondate'::date, :'cat', :'finding',"
        "         :'url');",
        {"mid": mid, "company": args.company or "",
         "ondate": args.date or datetime.date.today().isoformat(),
         "cat": args.category or "company_update",
         "finding": args.finding, "url": args.source_url or ""})
    print("intel logged on map '%s'" % args.map)


def cmd_recent_intel(args):
    mid = _map_id(args.map)
    rows = _rows(
        "SELECT intel_date, COALESCE(company_name,''), category, finding"
        " FROM successbrian_os.industry_intel WHERE map_id=:'mid'"
        " ORDER BY intel_date DESC, id DESC LIMIT :'lim';",
        {"mid": mid, "lim": str(args.limit or 10)})
    if not rows:
        print("no intel logged on map '%s' yet" % args.map)
        return
    for r in rows:
        ondate, company, cat, finding = r.split("\t", 3)
        who = ("[%s] " % company) if company else ""
        print("%s %s%s(%s)" % (ondate, who, finding[:160], cat))


def cmd_add_source(args):
    mid = _map_id(args.map) if args.map else None
    _psql(
        "INSERT INTO successbrian_os.industry_intel_sources"
        " (map_id, name, url, source_type, focus, notes) VALUES"
        " (:%s, :'name', :'url', :'stype', :'focus', :'notes');"
        % ("mid" if mid else "NULL"),
        {"mid": mid or "", "name": args.name, "url": args.url or "",
         "stype": args.type, "focus": args.focus,
         "notes": args.notes or ""})
    print("intel source added: %s" % args.name)


def cmd_list_sources(args):
    if args.map:
        mid = _map_id(args.map)
        filt = "WHERE (map_id=:'mid' OR map_id IS NULL)"
        vars_ = {"mid": mid}
    else:
        filt, vars_ = "", {}
    rows = _rows(
        "SELECT name, source_type, focus, COALESCE(url,'') FROM"
        " successbrian_os.industry_intel_sources " + filt +
        " ORDER BY name;", vars_)
    if not rows:
        print("no intel sources recorded")
        return
    for r in rows:
        name, stype, focus, url = r.split("\t", 3)
        print("%-34s [%-16s] %s" % (name, stype, focus))
        if url:
            print("%-34s %s" % ("", url))


def cmd_report(args):
    mid = _map_id(args.map)
    name = _rows("SELECT name FROM successbrian_os.industry_maps "
                 "WHERE id=:'mid';", {"mid": mid})[0]
    print("=== %s ===" % name)
    for r in _rows(
            "SELECT status, COUNT(*) FROM successbrian_os.industry_companies"
            " WHERE map_id=:'mid' GROUP BY status ORDER BY status;",
            {"mid": mid}):
        status, n = r.split("\t")
        print("companies [%s]: %s" % (status, n))
    mine = _rows("SELECT COUNT(*) FROM successbrian_os.industry_companies"
                 " WHERE map_id=:'mid' AND is_mine;",
                 {"mid": mid})[0]
    print("my companies: %s" % mine)
    links = _rows("SELECT COUNT(*) FROM successbrian_os.industry_company_links"
                  " WHERE map_id=:'mid';", {"mid": mid})[0]
    print("links: %s" % links)
    intel = _rows("SELECT COUNT(*) FROM successbrian_os.industry_intel"
                  " WHERE map_id=:'mid';", {"mid": mid})[0]
    print("intel entries: %s" % intel)
    srcs = _rows("SELECT COUNT(*) FROM successbrian_os.industry_intel_sources"
                 " WHERE map_id=:'mid' OR map_id IS NULL;",
                 {"mid": mid})[0]
    print("intel sources: %s" % srcs)


# ------------------------------------------------------------- graph export

_PALETTE = ["#2563eb", "#16a34a", "#7c3aed", "#ea580c", "#0d9488",
            "#db2777", "#0891b2", "#65a30d"]


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def cmd_export_graph(args):
    import math
    mid = _map_id(args.map)
    mname = _rows("SELECT name FROM successbrian_os.industry_maps "
                  "WHERE id=:'mid';", {"mid": mid})[0]
    companies = []
    for r in _rows("SELECT name, what_we_know, status, is_mine FROM"
                   " successbrian_os.industry_companies"
                   " WHERE map_id=:'mid' ORDER BY is_mine DESC, name;",
                   {"mid": mid}):
        nm, what, status, is_mine = r.split("\t", 3)
        companies.append({"name": nm, "what": what, "status": status,
                          "mine": is_mine == "t"})
    links = []
    for r in _rows("SELECT from_node, to_company, relationship FROM"
                   " successbrian_os.industry_company_links"
                   " WHERE map_id=:'mid';", {"mid": mid}):
        frm, to, rel = r.split("\t", 2)
        links.append((frm, to, rel))

    W, H, CX, CY = 1400, 900, 700, 450
    R = 300
    n = max(len(companies), 1)
    pos = {}
    for i, c in enumerate(companies):
        a = 2 * math.pi * i / n - math.pi / 2
        pos[c["name"]] = (CX + R * math.cos(a), CY + R * math.sin(a))

    # satellites: link endpoints that are not companies
    sats = {}
    for frm, to, _rel in links:
        if frm not in pos and to in pos and frm not in sats:
            tx, ty = pos[to]
            dx, dy = tx - CX, ty - CY
            d = math.hypot(dx, dy) or 1
            sats[frm] = (tx + dx / d * 150, ty + dy / d * 150, to)

    parts = []
    for frm, to, rel in links:
        if frm in sats:
            x1, y1 = sats[frm][0], sats[frm][1]
        else:
            x1, y1 = pos.get(frm, (None, None))
        x2, y2 = pos.get(to, (None, None))
        if None in (x1, y1, x2, y2):
            continue
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append(
            '<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#64748b"'
            ' stroke-width="1.5"/>' % (x1, y1, x2, y2))
        parts.append(
            '<text x="%.0f" y="%.0f" text-anchor="middle" font-size="11"'
            ' fill="#334155" style="paint-order:stroke;stroke:#fff;'
            'stroke-width:4px">%s</text>' % (mx, my - 4, _xesc(rel)))
    # center node
    parts.append('<rect x="%d" y="%d" width="200" height="70" rx="12"'
                 ' fill="#f5b301"/>' % (CX - 100, CY - 35))
    parts.append('<text x="%d" y="%d" text-anchor="middle" font-size="15"'
                 ' font-weight="bold">%s</text>' % (CX, CY - 2, _xesc(mname)))
    parts.append('<text x="%d" y="%d" text-anchor="middle" font-size="12">'
                 '%d companies</text>' % (CX, CY + 20, len(companies)))

    for i, c in enumerate(companies):
        x, y = pos[c["name"]]
        color = "#f5b301" if c["mine"] else _PALETTE[i % len(_PALETTE)]
        lines = _wrap(c["what"], 30)[:3]
        h = 44 + 15 * len(lines)
        parts.append('<rect x="%.0f" y="%.0f" width="220" height="%d" rx="12"'
                     ' fill="%s"/>' % (x - 110, y - h / 2, h, color))
        parts.append('<text x="%.0f" y="%.0f" text-anchor="middle"'
                     ' font-size="14" font-weight="bold" fill="#fff">%s</text>'
                     % (x, y - h / 2 + 22, _xesc(c["name"])))
        if c["mine"]:
            parts.append('<text x="%.0f" y="%.0f" text-anchor="middle"'
                         ' font-size="11" fill="#fff">MY COMPANY -- %s</text>'
                         % (x, y - h / 2 + 38, _xesc(c["status"]).upper()))
            base = y - h / 2 + 54
        else:
            base = y - h / 2 + 40
        for j, ln in enumerate(lines):
            parts.append('<text x="%.0f" y="%.0f" text-anchor="middle"'
                         ' font-size="11" fill="#fff">%s</text>'
                         % (x, base + 15 * j, _xesc(ln)))
    for frm, (x, y, _to) in sats.items():
        parts.append('<rect x="%.0f" y="%.0f" width="180" height="52" rx="10"'
                     ' fill="#fff" stroke="#64748b" stroke-width="2"/>'
                     % (x - 90, y - 26))
        for j, ln in enumerate(_wrap(frm, 24)[:2]):
            parts.append('<text x="%.0f" y="%.0f" text-anchor="middle"'
                         ' font-size="11" font-weight="bold">%s</text>'
                         % (x, y - 4 + 15 * j, _xesc(ln)))

    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>%(title)s -- industry map</title>
<style>body{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
margin:0;padding:24px;background:#f8fafc;color:#0f172a}
.wrap{max-width:1440px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
border-radius:12px;padding:24px}
h1{margin:0 0 4px;font-size:24px}.sub{color:#475569;font-size:14px}
svg{width:100%%;height:auto;display:block}</style></head>
<body><div class="wrap"><h1>%(title)s</h1>
<p class="sub">Industry map generated %(date)s -- gold nodes are the
entrepreneur's own companies.</p>
<svg viewBox="0 0 %(W)d %(H)d" role="img">%(svg)s</svg>
</div></body></html>""" % {
        "title": _xesc(mname), "date": datetime.date.today().isoformat(),
        "W": W, "H": H, "svg": "".join(parts)}

    with open(args.out, "w") as f:
        f.write(html)
    print("graph written: %s (%d companies, %d links)" %
          (args.out, len(companies), len(links)))


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create the industry_map tables")

    p = sub.add_parser("new-map", help="scaffold the layout for an income stream")
    p.add_argument("--slug", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--income-stream", required=True)
    p.add_argument("--description", default="")

    sub.add_parser("list-maps", help="list industry maps")

    p = sub.add_parser("add-company", help="add a company to a map")
    p.add_argument("--map", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--sector", default="")
    p.add_argument("--status", default="active")
    p.add_argument("--what", default="")
    p.add_argument("--mine", action="store_true")
    p.add_argument("--my-role", default="")

    p = sub.add_parser("list-companies", help="list companies on a map")
    p.add_argument("--map", required=True)
    p.add_argument("--status", default="")

    p = sub.add_parser("add-link", help="link a node to a company")
    p.add_argument("--map", required=True)
    p.add_argument("--from", dest="frm", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--relationship", required=True)
    p.add_argument("--notes", default="")

    p = sub.add_parser("add-intel", help="log an intel finding")
    p.add_argument("--map", required=True)
    p.add_argument("--finding", required=True)
    p.add_argument("--company", default="")
    p.add_argument("--category", default="company_update")
    p.add_argument("--source-url", default="")
    p.add_argument("--date", default="")

    p = sub.add_parser("recent-intel", help="show recent intel on a map")
    p.add_argument("--map", required=True)
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("add-source", help="record an intel source")
    p.add_argument("--name", required=True)
    p.add_argument("--url", default="")
    p.add_argument("--type", required=True)
    p.add_argument("--focus", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--map", default="")

    p = sub.add_parser("list-sources", help="list intel sources")
    p.add_argument("--map", default="")

    p = sub.add_parser("report", help="map summary: counts + intel")
    p.add_argument("--map", required=True)

    p = sub.add_parser("export-graph",
                       help="write a standalone HTML radial graph of the map")
    p.add_argument("--map", required=True)
    p.add_argument("--out", required=True)

    args = ap.parse_args()
    {"init-db": cmd_init_db, "new-map": cmd_new_map,
     "list-maps": cmd_list_maps, "add-company": cmd_add_company,
     "list-companies": cmd_list_companies, "add-link": cmd_add_link,
     "add-intel": cmd_add_intel, "recent-intel": cmd_recent_intel,
     "add-source": cmd_add_source, "list-sources": cmd_list_sources,
     "report": cmd_report,
     "export-graph": cmd_export_graph}[args.cmd](args)


if __name__ == "__main__":
    main()
