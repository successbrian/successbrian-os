#!/usr/bin/env python3
"""Ingestion engine: read everything, propose what to build.

PURPOSE
    Read the founder's accumulated content -- second brain, AnythingLLM
    library, markdown files, agent chat sessions -- and surface the income
    streams, audiences, marketing campaigns, and ideas hiding in it. The
    pipeline proposes; the entrepreneur decides. Accepted income streams
    land in ventures, accepted audiences in the audience builder, accepted
    campaigns in campaigns.

WHY
    A founder's notes already contain their next five businesses; they just
    cannot see them for the volume. This reads it all, cheaply, on the
    founder's own hardware, and turns "I wrote that down somewhere" into
    reviewable candidates.

CALLED BY
    - The entrepreneur (or their agent) on import: point it at existing
      content and watch it propose the business hiding inside.
    - A scheduled job: re-ingest periodically so the system keeps getting
      smarter as new content lands.

SOURCES
    second_brain : the second-brain table (Postgres public.second_brain,
                   or a SQLite .db export when ref ends in .db).
    anythingllm  : a directory of AnythingLLM document JSONs
                   (storage/documents/.../*.json).
    markdown     : a directory of .md files, chunked by ## headings.
    chat         : agent chat session exports (.json transcripts or .md).

EXTRACTION
    Deterministic code owns ingest/chunk/dedupe/store/review. The reading
    step goes through extract.py --via sonic (local llama.cpp, default),
    env (any OpenAI-compatible endpoint), or dry (no model, pipeline test).

NOTES
    - Nothing is created in ventures/audiences/campaigns until `accept`.
    - Re-running `run` on a source only adds what is new (dedupe on
      kind + title; rejected stays rejected).
    - Scores are deterministic heuristics to sort the review queue, not
      judgments. The entrepreneur decides.
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import pg_password  # noqa: E402

from ingest.extract import extract  # noqa: E402

PG = {"host": os.environ.get("SBOS_PGHOST", "localhost"),
      "dbname": os.environ.get("SBOS_PGDATABASE", "ecosystem_central"),
      "user": os.environ.get("SBOS_PGUSER", "successbrian")}

_PG_PASSWORD = None


def _pg_password():
    global _PG_PASSWORD
    if _PG_PASSWORD is None:
        _PG_PASSWORD = pg_password(PG["host"], PG["dbname"], PG["user"])
    return _PG_PASSWORD


def _psql(sql, variables=None, field_sep="\t"):
    env = dict(os.environ, PGPASSWORD=_pg_password())
    cmd = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
           "-v", "ON_ERROR_STOP=1", "-X", "-q", "-t", "-A",
           "-F", field_sep, "-P", "null="]
    for k, v in (variables or {}).items():
        cmd += ["-v", "%s=%s" % (k, v)]
    # NOTE: SQL goes via stdin, not -c: this psql build (pg_wrapper) does
    # :'var' substitution on stdin but NOT on -c strings (found 2026-10-11).
    out = subprocess.run(cmd, input=sql, capture_output=True, text=True,
                         env=env)
    if out.returncode != 0:
        raise RuntimeError("psql failed: %s" % out.stderr.strip())
    return out.stdout


def _rows(sql, variables=None):
    return [l for l in _psql(sql, variables).splitlines() if l.strip()]


# ---------------------------------------------------------------- readers

def read_second_brain(ref, limit):
    """ref: Postgres table (public.second_brain) or a SQLite .db path."""
    chunks = []
    if ref.endswith(".db"):
        con = sqlite3.connect(ref)
        try:
            cols = [r[1] for r in
                    con.execute("PRAGMA table_info(learnings)")]
            topic_c = "topic" if "topic" in cols else cols[0]
            rows = con.execute(
                "SELECT %s, content FROM learnings ORDER BY id DESC LIMIT %d"
                % (topic_c, limit))
            for topic, content in rows:
                if content:
                    chunks.append(("second_brain:%s" % topic,
                                   "%s\n\n%s" % (topic, content)))
        finally:
            con.close()
        return chunks
    # NOTE: the table name cannot go through -v variables; it comes from the
    # registered source ref, which the operator controls. Quoted defensively.
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", ref):
        raise SystemExit("unsafe table ref '%s'" % ref)
    rows = _rows("SELECT topic, category, content FROM " + ref +
                 " ORDER BY id DESC LIMIT " + str(int(limit)) + ";")
    for r in rows:
        parts = r.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        topic, cat, content = parts[0], parts[1], parts[2]
        chunks.append(("second_brain:%s" % topic,
                       "TOPIC: %s\nCATEGORY: %s\n\n%s"
                       % (topic, cat, content)))
    return chunks


def read_anythingllm(ref, limit):
    """ref: directory of AnythingLLM document JSONs."""
    chunks = []
    for root, _dirs, files in os.walk(ref):
        for f in sorted(files):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(root, f)) as fh:
                    d = json.load(fh)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            text = d.get("pageContent")
            if not text or not isinstance(text, str):
                continue
            title = d.get("title") or f
            chunks.append(("anythingllm:%s" % title, text))
            if len(chunks) >= limit:
                return chunks
    return chunks


def read_markdown(ref, limit):
    """ref: directory of .md files; chunked by ## headings."""
    chunks = []
    for root, _dirs, files in os.walk(ref):
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    text = fh.read()
            except Exception:
                continue
            parts = re.split(r"(?m)^##\s+", text)
            for i, part in enumerate(parts):
                part = part.strip()
                if len(part) < 200:
                    continue
                label = "%s#%d" % (f, i) if i else f
                chunks.append(("markdown:%s" % label, part))
                if len(chunks) >= limit:
                    return chunks
    return chunks


def read_chat(ref, limit):
    """ref: a chat export file or a directory of them (.json/.md)."""
    paths = []
    if os.path.isdir(ref):
        for root, _dirs, files in os.walk(ref):
            for f in sorted(files):
                if f.endswith((".json", ".md")):
                    paths.append(os.path.join(root, f))
    elif os.path.isfile(ref):
        paths = [ref]
    chunks = []
    for path in paths:
        label = "chat:%s" % os.path.basename(path)
        try:
            with open(path) as fh:
                raw = fh.read()
        except Exception:
            continue
        text = raw
        if path.endswith(".json"):
            try:
                d = json.loads(raw)
                msgs = d if isinstance(d, list) else d.get("messages", d)
                bits = []
                for m in msgs if isinstance(msgs, list) else []:
                    if isinstance(m, dict):
                        c = m.get("content") or m.get("text") or ""
                        r = m.get("role") or m.get("speaker") or ""
                        if c:
                            bits.append("[%s] %s" % (r, c))
                if bits:
                    text = "\n".join(bits)
            except Exception:
                pass
        if len(text.strip()) >= 200:
            chunks.append((label, text))
        if len(chunks) >= limit:
            break
    return chunks


READERS = {"second_brain": read_second_brain, "anythingllm": read_anythingllm,
           "markdown": read_markdown, "chat": read_chat}


# ---------------------------------------------------------------- scoring

def _score(kind, evidence):
    s = 30 + len(evidence) // 40
    if kind in ("income_stream", "audience", "campaign"):
        s += 10
    return max(0, min(95, s))


def _slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60] or "candidate"


# ---------------------------------------------------------------- commands

def cmd_init_db(_args):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "schema.sql")) as f:
        _psql(f.read())
    print("ingest schema ready")


def cmd_add_source(args):
    if args.kind not in READERS:
        raise SystemExit("unknown source kind '%s'" % args.kind)
    _psql("INSERT INTO successbrian_os.ingest_sources (kind, ref)"
          " VALUES (:'kind', :'ref')"
          " ON CONFLICT (kind, ref) DO NOTHING;",
          {"kind": args.kind, "ref": args.ref})
    print("source registered: %s %s" % (args.kind, args.ref))


def cmd_run(args):
    if args.kind not in READERS:
        raise SystemExit("unknown source kind '%s'" % args.kind)
    cmd_add_source(args)  # idempotent register
    chunks = READERS[args.kind](args.ref, args.limit)
    print("read %d chunks from %s %s" % (len(chunks), args.kind, args.ref))
    if not chunks:
        return
    cands = extract(chunks, via=args.via, batch_size=args.batch)
    print("extracted %d candidates (%s)" % (len(cands), args.via))
    added = 0
    for c in cands:
        dup = _psql(
            "SELECT 1 FROM successbrian_os.ingest_candidates"
            " WHERE kind=:'kind' AND lower(title)=lower(:'title')"
            " AND status != 'rejected' LIMIT 1;",
            {"kind": c["kind"], "title": c["title"]}).strip()
        if dup:
            continue
        _psql(
            "INSERT INTO successbrian_os.ingest_candidates"
            " (source_kind, source_ref, kind, title, summary, evidence, score)"
            " VALUES (:'sk', :'sr', :'kind', :'title', :'summary',"
            " :'evidence', :score);",
            {"sk": args.kind, "sr": args.ref, "kind": c["kind"],
             "title": c["title"], "summary": c["summary"],
             "evidence": c["evidence"],
             "score": _score(c["kind"], c["evidence"])})
        added += 1
    _psql("UPDATE successbrian_os.ingest_sources"
          " SET last_ingested_at=now() WHERE kind=:'kind' AND ref=:'ref';",
          {"kind": args.kind, "ref": args.ref})
    print("stored %d new candidates (dedupe skipped %d)"
          % (added, len(cands) - added))


def cmd_review(args):
    filt, vars_ = "", {}
    if args.kind:
        filt, vars_ = "AND kind=:'kind'", {"kind": args.kind}
    rows = _rows(
        "SELECT id, kind, score, title, left(summary, 100)"
        " FROM successbrian_os.ingest_candidates"
        " WHERE status='proposed' " + filt +
        " ORDER BY score DESC, id LIMIT 50;", vars_)
    if not rows:
        print("no proposed candidates -- run ingest first")
        return
    for r in rows:
        cid, kind, score, title, summary = r.split("\t")
        print("#%-4s [%s] (%s) %s -- %s" % (cid, score, kind, title, summary))


def cmd_show(args):
    rows = _rows(
        "SELECT kind, title, summary, evidence, score, status,"
        " source_kind, source_ref"
        " FROM successbrian_os.ingest_candidates WHERE id=:%s;" % int(args.id))
    if not rows:
        raise SystemExit("no candidate #%s" % args.id)
    kind, title, summary, evidence, score, status, sk, sr = \
        rows[0].split("\t")
    print("#%s [%s] score=%s status=%s\n%s\n\nSUMMARY\n%s\n\nEVIDENCE\n%s\n"
          "SOURCE\n%s %s" % (args.id, kind, score, status, title,
                              summary, evidence, sk, sr))


def cmd_accept(args):
    rows = _rows(
        "SELECT kind, title, summary FROM successbrian_os.ingest_candidates"
        " WHERE id=:%s AND status='proposed';" % int(args.id))
    if not rows:
        raise SystemExit("no proposed candidate #%s" % args.id)
    kind, title, summary = rows[0].split("\t")
    if kind == "income_stream":
        _psql("INSERT INTO successbrian_os.ventures"
              " (title, raw_pitch, status, income_streams)"
              " VALUES (:'t', :'s', 'raw', ARRAY[:'t']);",
              {"t": title, "s": summary})
        print("accepted -> ventures: %s" % title)
    elif kind == "audience":
        slug = _slugify(title)
        _psql("INSERT INTO successbrian_os.audiences"
              " (slug, name, who_they_are)"
              " VALUES (:'slug', :'t', :'s')"
              " ON CONFLICT (slug) DO NOTHING;",
              {"slug": slug, "t": title, "s": summary})
        print("accepted -> audiences: %s (%s)" % (title, slug))
    elif kind == "campaign":
        if not args.audience:
            raise SystemExit("campaigns need --audience <slug>")
        aid = _psql("SELECT id FROM successbrian_os.audiences"
                    " WHERE slug=:'s';",
                    {"s": args.audience}).strip()
        if not aid:
            raise SystemExit("unknown audience slug '%s'" % args.audience)
        slug = _slugify(title)
        _psql("INSERT INTO successbrian_os.campaigns"
              " (audience_id, slug, name, goal)"
              " VALUES (:'aid', :'slug', :'t', :'s')"
              " ON CONFLICT (audience_id, slug) DO NOTHING;",
              {"aid": aid, "slug": slug, "t": title, "s": summary})
        print("accepted -> campaigns: %s/%s" % (args.audience, slug))
    else:
        print("accepted (idea -- agent handles it): %s" % title)
    _psql("UPDATE successbrian_os.ingest_candidates SET status='accepted'"
          " WHERE id=:%s;" % int(args.id))


def cmd_reject(args):
    _psql("UPDATE successbrian_os.ingest_candidates SET status='rejected'"
          " WHERE id=:%s AND status='proposed';" % int(args.id))
    print("rejected #%s" % args.id)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ingest.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init_db")

    p = sub.add_parser("add_source")
    p.add_argument("--kind", required=True,
                   choices=sorted(READERS),
                   help="second_brain|anythingllm|markdown|chat")
    p.add_argument("--ref", required=True,
                   help="table name, directory, .db path, or file")

    p = sub.add_parser("run")
    p.add_argument("--kind", required=True, choices=sorted(READERS))
    p.add_argument("--ref", required=True)
    p.add_argument("--via", default="sonic", choices=["sonic", "env", "dry"],
                   help="extraction backend (default: sonic)")
    p.add_argument("--limit", type=int, default=200,
                   help="max chunks to read (default 200)")
    p.add_argument("--batch", type=int, default=10,
                   help="chunks per model call (default 10)")

    p = sub.add_parser("review")
    p.add_argument("--kind", default=None,
                   choices=["income_stream", "audience", "campaign", "idea"])

    p = sub.add_parser("show")
    p.add_argument("--id", required=True)

    p = sub.add_parser("accept")
    p.add_argument("--id", required=True)
    p.add_argument("--audience", default=None,
                   help="audience slug (required for campaigns)")

    p = sub.add_parser("reject")
    p.add_argument("--id", required=True)

    args = ap.parse_args(argv)
    {"init_db": cmd_init_db, "add_source": cmd_add_source, "run": cmd_run,
     "review": cmd_review, "show": cmd_show, "accept": cmd_accept,
     "reject": cmd_reject}[args.cmd](args)


if __name__ == "__main__":
    main()
