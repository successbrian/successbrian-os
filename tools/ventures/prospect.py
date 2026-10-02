#!/usr/bin/env python3
"""SuccessBrian OS venture prospector: dig ideas out of Brian's own data.

PURPOSE: Scan the database (altair.brian_learnings, altair.brian_decisions)
    and AnythingLLM workspaces for business/blog ideas Brian already recorded,
    dedupe against the ventures table, and capture the ones he approves.
WHY: Brian 2026-09-30 - "can it dig through my ideas in my database and
    anythingllm and find a bunch? can it flesh out my blog ideas?"
CALLED BY: CLI. `scan` lists candidates; `capture --ids ...` inserts them.
NOTES:
    - Read-only against AnythingLLM (SQLite directly; the API has no clean
      per-workspace document list). DB reads via psql like ideas.py.
    - Candidate ids: L<n> = brian_learnings, D<n> = brian_decisions,
      A<slug>:<docId> = AnythingLLM doc.
    - --first-pass fills a blog idea's profile from the learning text itself
      (title, angle, monetization, traffic why, effort, edge). Anything it
      can't know honestly stays blank for Brian.
"""
import argparse, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
AILLM_DB = "/home/successbrian/anything-llm/server/storage/anythingllm.db"
PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian", "password": "postgres"}

TAG_STREAM = {"BLOG": "blog_network", "networker": "mlm", "ai": "ai_clients",
              "crypto": "crypto", "health": "mlm"}
VENTURE_KEYWORDS = ["revenue stream", "consulting", "go-to-market", "monetize",
                    "monetization", "first dollar", "package the", "launch",
                    "offer", "radar", "watch", "open-source", "partner",
                    "affiliate", "channel", "publish"]
IDEA_DOC_KEYWORDS = ["idea", "business", "niche", "startup", "venture",
                     "monetiz", "blog"]
BIZ_WORKSPACES = ["blog-network", "mlm-income", "crypto-trading-yield",
                  "money-investing", "career", "trafficstreemz",
                  "contactflowcrm", "dealsdesk", "people-pipeline"]


def _psql(sql, variables=None):
    env = dict(os.environ, PGPASSWORD=PG["password"])
    cmd = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]
    for k, v in (variables or {}).items():
        cmd += ["-v", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("psql failed: " + p.stderr.strip()[-400:])
    return p.stdout


def _one(sql, variables=None):
    out = _psql(sql, variables).strip()
    return out.split("\n")[0] if out else ""


def _sqlite_json(sql):
    p = subprocess.run(["sqlite3", "-json", AILLM_DB, sql],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("sqlite3 failed: " + p.stderr.strip()[-400:])
    return json.loads(p.stdout or "[]")


def _existing_titles():
    out = _psql("SELECT lower(title) FROM successbrian_os.ventures")
    return [l.strip() for l in out.strip().split("\n") if l.strip()]


def _is_dup(title, existing):
    t = title.lower()
    return any(t in e or e in t for e in existing)


def scan_db():
    cands = []
    out = _psql("SELECT id, content FROM altair.brian_learnings ORDER BY id")
    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        lid, content = line.split("\t", 1)
        m = re.match(r"^(BLOG|\[(\w+)\])\s*:?\s*(.+)$", content.strip(),
                     re.DOTALL)
        if m:
            tag = m.group(1) if m.group(1) == "BLOG" else m.group(2)
            rest = m.group(3)
            title = re.split(r"\s+—\s+", rest, 1)[0].strip().strip("'\"")
            cands.append({"cid": "L%s" % lid, "kind": "blog",
                          "stream": TAG_STREAM.get(tag, "blog_network"),
                          "title": title[:120], "content": content})
        elif any(k in content.lower() for k in VENTURE_KEYWORDS):
            title = content.strip().split("—")[0][:120]
            cands.append({"cid": "L%s" % lid, "kind": "venture",
                          "stream": "", "title": title, "content": content})
    out = _psql("SELECT id, question FROM altair.brian_decisions ORDER BY id")
    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        did, q = line.split("\t", 1)
        if re.search(r"CMS|blog|launch|open-source|monetiz|hosting|business",
                     q, re.I):
            cands.append({"cid": "D%s" % did, "kind": "venture", "stream": "",
                          "title": q.strip()[:120], "content": q.strip()})
    return cands


def scan_anythingllm():
    cands = []
    rows = _sqlite_json(
        "SELECT w.slug, wd.docId, wd.filename, wd.metadata"
        " FROM workspace_documents wd JOIN workspaces w"
        " ON w.id = wd.workspaceId"
        " WHERE w.slug IN (%s)" % ",".join("'%s'" % s for s in BIZ_WORKSPACES))
    total = len(rows)
    for r in rows:
        meta = r.get("metadata") or ""
        if "brian_learnings" in meta or "brian_decisions" in meta:
            continue  # already covered by the DB scan
        hay = (r.get("filename") or "") + " " + meta
        if any(k in hay.lower() for k in IDEA_DOC_KEYWORDS):
            title = os.path.splitext(os.path.basename(
                r.get("filename") or r["docId"]))[0].replace("-", " ")[:120]
            cands.append({"cid": "A%s:%s" % (r["slug"], r["docId"][:8]),
                          "kind": "doc", "stream": "",
                          "title": title, "content": hay[:400]})
    return cands, total


def _first_pass_blog(content, stream):
    """Parse a BLOG:/[tag] learning into an honest first-pass profile."""
    prof = {"stream_fit": [stream] if stream else []}
    body = re.sub(r"^(BLOG|\[\w+\])\s*:?\s*", "", content.strip())
    title = re.split(r"\s+—\s+", body, 1)[0].strip().strip("'\"")
    prof["offer"] = "SEO blog: %s" % title
    rest = re.split(r"\s+—\s+", body, 1)[1] if "—" in body else ""
    why = re.search(r"50K why:\s*(.+?)(?:Monetiz\w*:|Effort|Edge:|$)", rest,
                    re.S | re.I)
    if why:
        prof["problem"] = "Traffic opportunity: %s" % why.group(1).strip()[:300]
    mon = re.search(r"Monetiz\w*:\s*(.+?)(?:Effort|Edge:|\.\s*$|$)", rest,
                    re.S | re.I)
    if mon:
        prof["revenue_model"] = mon.group(1).strip().rstrip(".")[:200]
    notes = []
    if why:
        notes.append("Traffic why: " + why.group(1).strip()[:400])
    eff = re.search(r"Effort:?\s*([SML])", content)
    if eff:
        notes.append("Effort: " + eff.group(1))
    edge = re.search(r"Edge:\s*(.+)$", content, re.S)
    if edge:
        notes.append("Edge: " + edge.group(1).strip()[:300])
    feeds = re.search(r"Feeds\s+(.+?)(?:\.|Monetiz)", content, re.S | re.I)
    if feeds:
        notes.append("Feeds: " + feeds.group(1).strip()[:200])
    prof["notes"] = "\n".join(notes)
    return prof


def cmd_scan(args):
    cands = scan_db()
    aillm = []
    aillm_total = 0
    if args.anythingllm:
        try:
            aillm, aillm_total = scan_anythingllm()
        except Exception as e:
            print("anythingllm scan skipped: %s" % e)
    cands += aillm
    existing = _existing_titles()
    fresh = [c for c in cands if not _is_dup(c["title"], existing)]
    print("%d candidates (%d already in ventures)" %
          (len(fresh), len(cands) - len(fresh)))
    for c in fresh:
        print("%-14s [%s] %s" % (c["cid"], c["kind"], c["title"]))
    if args.anythingllm:
        print("(scanned %d AnythingLLM docs in business workspaces;"
              " %d idea-like and not from the DB sync)" %
              (aillm_total, len(aillm)))


def cmd_capture(args):
    existing = _existing_titles()
    all_cands = {c["cid"]: c for c in scan_db()}
    done = 0
    for cid in args.ids:
        cid = cid.strip().upper()
        if cid.startswith("A"):
            print("skip (AnythingLLM doc capture not yet implemented): %s" % cid)
            continue
        c = all_cands.get(cid)
        if not c:
            print("candidate not found: %s" % cid)
            continue
        if _is_dup(c["title"], existing):
            print("skip (already captured): %s" % c["title"])
            continue
        streams = [c["stream"]] if c["stream"] else []
        vid = _one(
            "INSERT INTO successbrian_os.ventures"
            " (title, raw_pitch, income_streams) VALUES"
            " (:'title', :'pitch', string_to_array(:'streams', ','))"
            " RETURNING id",
            {"title": c["title"][:200], "pitch": c["content"][:2000],
             "streams": ",".join(streams)}).strip()
        profile = {}
        status = "raw"
        if args.first_pass and c["kind"] == "blog":
            profile = _first_pass_blog(c["content"], c["stream"])
            status = "fleshed"
        if profile:
            _psql("UPDATE successbrian_os.ventures SET profile=:'p'::jsonb,"
                  " status=:'st', updated_at=now() WHERE id=:id",
                  {"p": json.dumps(profile), "st": status, "id": vid})
        existing.append(c["title"].lower())
        done += 1
        print("captured #%s [%s%s]: %s" %
              (vid, c["kind"], " first-pass" if profile else "", c["title"]))
    print("%d captured" % done)


def main():
    ap = argparse.ArgumentParser(prog="prospect.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--anythingllm", action="store_true")
    p = sub.add_parser("capture")
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--first-pass", action="store_true")
    args = ap.parse_args()
    {"scan": cmd_scan, "capture": cmd_capture}[args.cmd](args)


if __name__ == "__main__":
    main()
