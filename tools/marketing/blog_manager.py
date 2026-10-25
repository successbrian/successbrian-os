#!/usr/bin/env python3
"""Blog manager — coded control of the free Wix blogs (Wix Blog v3 API).

Brian's ask (2026-10-24): "are you able to code in a blog page manager
or no" -> "Build the blog manager". This module is the engine: it lives
in SuccessBrian OS beside web_chain.py (the OS owns machinery + state;
the desks own the work — CampaignsDesk drives this through a thin
client, code/blog_client.py, and never holds a Wix credential).

What it does:
  * Talks to the Wix Blog v3 REST API (www.wixapis.com/blog/v3) with
    the account API key (env WIX_API_KEY, minted 2026-10-24 as
    'sbos-blog-manager') + the site's metaSiteId (env WIX_SITE_ID).
  * Converts plain markdown articles into Wix Ricos rich content
    deterministically (headings, paragraphs, bold/italic/links,
    blockquotes, bullet + numbered lists) — no model in the loop.
  * Creates DRAFT posts, publishes drafts, lists posts/drafts, deletes
    test drafts, and keeps the registry table
    successbrian_os.marketing_blog_posts in step (PostgreSQL is the
    state home, per R32).

Approval law (Brian, stands since 2026-10-22): building drafts is
internal work; PUBLISHING a post is an outward act and needs Brian's
explicit go for that post. The `draft` verb therefore never publishes
unless --publish is passed by a caller carrying that approval.

Env (~/successbrian-os/.env or process env):
  WIX_API_KEY    account API key (secret; never printed by this tool)
  WIX_SITE_ID    metaSiteId of the site (SuccessBrian OS site:
                 cf0092ec-184e-4a60-ae44-2a29fe13fdd4)
  WIX_ACCOUNT_ID optional; sent as wix-account-id header when set
  WIX_MEMBER_ID  optional author member id for created drafts

CLI:
  init
  status                      config presence (never prints the key)
  list [--drafts]             remote posts (or drafts) from Wix
  draft --title T --file F.md [--source S] [--publish]
  publish --draft-id ID
  delete-draft --draft-id ID
  sync                        reconcile registry with remote state
  selftest [--live]           offline checks; --live adds a real
                              list + create/delete test-draft round trip
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "pm"))
import pm_core  # noqa: E402

API_BASE = "https://www.wixapis.com/blog/v3"
ENV_PATH = os.path.expanduser("~/successbrian-os/.env")


# ---------------------------------------------------------------- env

def load_env():
    """Read ~/successbrian-os/.env (KEY=value lines) without overriding
    real process environment variables."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def config():
    load_env()
    key = os.environ.get("WIX_API_KEY", "").strip()
    # Wix keys are long and can arrive with stray whitespace/newlines
    # from the one-time copy; the token itself contains no spaces.
    key = re.sub(r"\s+", "", key)
    return {
        "api_key": key or None,
        "site_id": os.environ.get("WIX_SITE_ID", "").strip() or None,
        "account_id": os.environ.get("WIX_ACCOUNT_ID", "").strip() or None,
        "member_id": os.environ.get("WIX_MEMBER_ID", "").strip() or None,
    }


def have_config():
    c = config()
    return bool(c["api_key"] and c["site_id"])


# ---------------------------------------------------------------- api

class WixError(RuntimeError):
    pass


def api(method, path, body=None, cfg=None):
    cfg = cfg or config()
    if not cfg["api_key"] or not cfg["site_id"]:
        raise WixError("Wix config missing (WIX_API_KEY / WIX_SITE_ID)")
    url = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", cfg["api_key"])
    req.add_header("wix-site-id", cfg["site_id"])
    req.add_header("Content-Type", "application/json")
    if cfg["account_id"]:
        req.add_header("wix-account-id", cfg["account_id"])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise WixError("Wix API %s %s -> HTTP %s: %s"
                       % (method, path, e.code, detail))
    except urllib.error.URLError as e:
        raise WixError("Wix API %s %s failed: %s" % (method, path, e))


def list_posts(cfg=None, limit=50):
    """Published posts via the v3 query endpoint."""
    out = api("POST", "/posts/query",
              {"query": {"paging": {"limit": limit}}}, cfg)
    return out.get("posts", [])


def list_drafts(cfg=None, limit=50):
    """Draft posts via the v3 query endpoint."""
    out = api("POST", "/draft-posts/query",
              {"query": {"paging": {"limit": limit}}}, cfg)
    return out.get("draftPosts", [])


def create_draft(title, ricos, cfg=None, excerpt=None, publish=False):
    cfg = cfg or config()
    draft = {"title": title, "richContent": ricos}
    if excerpt:
        draft["excerpt"] = excerpt
    if cfg["member_id"]:
        draft["memberId"] = cfg["member_id"]
    out = api("POST", "/draft-posts",
              {"draftPost": draft, "publish": bool(publish)}, cfg)
    return out.get("draftPost", out)


def publish_draft(draft_id, cfg=None):
    out = api("POST", "/draft-posts/%s/publish" % draft_id, {}, cfg)
    return out.get("postId")


def delete_draft(draft_id, cfg=None):
    api("DELETE", "/draft-posts/%s" % draft_id, None, cfg)
    return True


# ------------------------------------------------------- md -> ricos

class _Ids:
    """Deterministic short node ids (Ricos examples carry ids)."""

    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        x, out = self.n, ""
        while x:
            x, r = divmod(x, 36)
            out = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + out
        return "n" + out.rjust(5, "0")


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _inline_plain(text):
    """Bold/italic pass over a link-free segment -> list of TEXT nodes."""
    nodes = []

    def add(txt, decorations):
        if txt:
            nodes.append({"type": "TEXT",
                          "textData": {"text": txt,
                                       "decorations": decorations}})

    # Split on bold markers first, then italic within each piece.
    tokens = []
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            tokens.append((text[pos:m.start()], []))
        tokens.append((m.group(1), [{"type": "BOLD"}]))
        pos = m.end()
    if pos < len(text):
        tokens.append((text[pos:], []))
    for txt, deco in tokens:
        p = 0
        for m in _ITALIC_RE.finditer(txt):
            if m.start() > p:
                add(txt[p:m.start()], list(deco))
            add(m.group(1), list(deco) + [{"type": "ITALIC"}])
            p = m.end()
        if p < len(txt):
            add(txt[p:], list(deco))
    return nodes


def _inline(text):
    """Parse **bold**, *italic*, [label](url) into TEXT nodes."""
    nodes = []
    # Links first (their labels may themselves carry bold/italic).
    pos = 0
    for m in _LINK_RE.finditer(text):
        if m.start() > pos:
            nodes.extend(_inline_plain(text[pos:m.start()]))
        label, url = m.group(1), m.group(2)
        deco = [{"type": "LINK",
                 "linkData": {"link": {"url": url, "target": "BLANK"}}}]
        for sn in _inline_plain(label):
            sn["textData"]["decorations"] = (
                sn["textData"]["decorations"] + deco)
            nodes.append(sn)
        pos = m.end()
    if pos < len(text):
        nodes.extend(_inline_plain(text[pos:]))
    if not nodes:
        nodes = [{"type": "TEXT",
                  "textData": {"text": text, "decorations": []}}]
    return nodes


def _para(text, ids):
    return {"type": "PARAGRAPH", "id": ids.next(),
            "nodes": _inline(text), "paragraphData": {}}


def md_to_ricos(md):
    """Convert markdown to a Wix Ricos document ({'nodes': [...]}).

    Supports #/##/### headings, paragraphs, > blockquotes, - bullets,
    1. numbered lists, and inline bold/italic/links. Anything else is
    passed through as plain paragraph text — deterministic, no model.
    """
    ids = _Ids()
    nodes = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0

    def collect_list(start, ordered):
        items = []
        j = start
        pat = re.compile(r"^\d+\.\s+" if ordered else r"^[-*]\s+")
        while j < len(lines) and pat.match(lines[j].strip()):
            txt = pat.sub("", lines[j].strip())
            items.append({"type": "LIST_ITEM", "id": ids.next(),
                          "nodes": [_para(txt, ids)]})
            j += 1
        node = {"type": "ORDERED_LIST" if ordered else "BULLETED_LIST",
                "id": ids.next(), "nodes": items}
        return node, j

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if m:
            nodes.append({"type": "HEADING", "id": ids.next(),
                          "nodes": _inline(m.group(2)),
                          "headingData": {"level": len(m.group(1))}})
            i += 1
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            nodes.append({"type": "BLOCKQUOTE", "id": ids.next(),
                          "nodes": [_para(" ".join(quote_lines), ids)],
                          "blockquoteData": {"indentation": 1}})
            continue
        if re.match(r"^[-*]\s+", stripped):
            node, i = collect_list(i, ordered=False)
            nodes.append(node)
            continue
        if re.match(r"^\d+\.\s+", stripped):
            node, i = collect_list(i, ordered=True)
            nodes.append(node)
            continue
        # Plain paragraph: gather until a blank line or a block starter.
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or re.match(r"^(#{1,3}\s|>|[-*]\s|\d+\.\s)", nxt):
                break
            para.append(nxt)
            i += 1
        nodes.append(_para(" ".join(para), ids))
    return {"nodes": nodes}


# ------------------------------------------------------------- registry

DDL = """
CREATE SCHEMA IF NOT EXISTS successbrian_os;
CREATE TABLE IF NOT EXISTS successbrian_os.marketing_blog_posts (
  id          bigserial PRIMARY KEY,
  site_id     text NOT NULL,
  draft_id    text,
  post_id     text,
  title       text NOT NULL,
  status      text NOT NULL DEFAULT 'draft'
              CHECK (status IN ('draft','published','deleted')),
  source      text,
  url         text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (site_id, draft_id)
);
"""


def cmd_init(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    return "registry ready: successbrian_os.marketing_blog_posts"


def _record(conn, cfg, draft_post, status, source=None):
    draft_id = draft_post.get("id")
    title = draft_post.get("title", "(untitled)")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO successbrian_os.marketing_blog_posts
                 (site_id, draft_id, title, status, source)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (site_id, draft_id) DO UPDATE
                 SET title = EXCLUDED.title, status = EXCLUDED.status,
                     updated_at = now()
               RETURNING id""",
            (cfg["site_id"], draft_id, title, status, source))
        rid = cur.fetchone()[0]
    conn.commit()
    return rid


# ---------------------------------------------------------------- cli

def cmd_status(_conn):
    c = config()
    return ("WIX_API_KEY: %s\nWIX_SITE_ID: %s\nWIX_ACCOUNT_ID: %s\n"
            "WIX_MEMBER_ID: %s"
            % ("set" if c["api_key"] else "MISSING",
               c["site_id"] or "MISSING",
               "set" if c["account_id"] else "not set (optional)",
               "set" if c["member_id"] else "not set (optional)"))


def cmd_list(_conn, drafts=False):
    rows = list_drafts() if drafts else list_posts()
    kind = "draft" if drafts else "post"
    if not rows:
        return "no %ss returned by Wix" % kind
    out = []
    for r in rows:
        out.append("- [%s] %s" % (r.get("id"), r.get("title", "(untitled)")))
    return "%d %s(s):\n%s" % (len(rows), kind, "\n".join(out))


def cmd_draft(conn, title, path, source=None, publish=False):
    with open(path) as fh:
        md = fh.read()
    ricos = md_to_ricos(md)
    cfg = config()
    draft_post = create_draft(title, ricos, cfg)
    status = "draft"
    post_id = None
    if publish:
        post_id = publish_draft(draft_post["id"], cfg)
        status = "published"
    rid = _record(conn, cfg, draft_post, status, source)
    msg = "draft created: registry #%s, wix draft id %s" % (rid,
                                                           draft_post["id"])
    if post_id:
        msg += ", published as post %s" % post_id
        with conn.cursor() as cur:
            cur.execute("UPDATE successbrian_os.marketing_blog_posts "
                        "SET post_id = %s WHERE id = %s", (post_id, rid))
        conn.commit()
    return msg


def cmd_publish(conn, draft_id):
    cfg = config()
    post_id = publish_draft(draft_id, cfg)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE successbrian_os.marketing_blog_posts
                  SET post_id = %s, status = 'published', updated_at = now()
                WHERE site_id = %s AND draft_id = %s""",
            (post_id, cfg["site_id"], draft_id))
    conn.commit()
    return "published: draft %s -> post %s" % (draft_id, post_id)


def cmd_delete_draft(conn, draft_id):
    cfg = config()
    delete_draft(draft_id, cfg)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE successbrian_os.marketing_blog_posts
                  SET status = 'deleted', updated_at = now()
                WHERE site_id = %s AND draft_id = %s""",
            (cfg["site_id"], draft_id))
    conn.commit()
    return "draft deleted at Wix: %s" % draft_id


def cmd_sync(conn):
    cfg = config()
    seen = 0
    for d in list_drafts(cfg):
        _record(conn, cfg, d, "draft", source="sync")
        seen += 1
    for p in list_posts(cfg):
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO successbrian_os.marketing_blog_posts
                     (site_id, post_id, title, status, source)
                   VALUES (%s, %s, %s, 'published', 'sync')
                   ON CONFLICT DO NOTHING""",
                (cfg["site_id"], p.get("id"), p.get("title", "(untitled)")))
        conn.commit()
        seen += 1
    return "sync complete: %d remote item(s) reconciled" % seen


# ------------------------------------------------------------ selftest

def selftest(live=False):
    results = []

    def check(name, cond, note=""):
        results.append((name, bool(cond), note))

    # Converter: structure of a representative article.
    md = ("# Title line\n\nIntro with **bold** and *italic* and a "
          "[link](https://example.com/x).\n\n## Section\n\n"
          "- first\n- second\n\n1. one\n2. two\n\n> a quoted line\n")
    doc = md_to_ricos(md)
    types = [n["type"] for n in doc["nodes"]]
    check("heading node", "HEADING" in types)
    check("paragraph node", "PARAGRAPH" in types)
    check("bulleted list", "BULLETED_LIST" in types)
    check("ordered list", "ORDERED_LIST" in types)
    check("blockquote", "BLOCKQUOTE" in types)
    para = next(n for n in doc["nodes"] if n["type"] == "PARAGRAPH")
    decos = [d["type"] for t in para["nodes"]
             for d in t["textData"]["decorations"]]
    check("bold decoration", "BOLD" in decos)
    check("italic decoration", "ITALIC" in decos)
    check("link decoration", "LINK" in decos)
    li = next(n for n in doc["nodes"] if n["type"] == "BULLETED_LIST")
    check("list items wrap paragraphs",
          li["nodes"][0]["nodes"][0]["type"] == "PARAGRAPH")
    check("deterministic conversion",
          json.dumps(md_to_ricos(md)) == json.dumps(doc))

    # Registry round trip inside a rolled-back transaction.
    conn = pm_core.conn()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(
                """INSERT INTO successbrian_os.marketing_blog_posts
                     (site_id, draft_id, title, status)
                   VALUES ('selftest-site', 'selftest-draft', 'T', 'draft')
                   ON CONFLICT (site_id, draft_id) DO NOTHING""")
            cur.execute("SELECT count(*) FROM "
                        "successbrian_os.marketing_blog_posts "
                        "WHERE site_id = 'selftest-site'")
            check("registry round trip", cur.fetchone()[0] >= 1)
    finally:
        conn.rollback()
        conn.close()

    # Live round trip (only with --live and full config).
    if live:
        if not have_config():
            check("live config present", False, "WIX_API_KEY/SITE_ID missing")
        else:
            try:
                posts = list_posts()
                check("live list posts", isinstance(posts, list),
                      "%d published" % len(posts))
                d = create_draft("SBOS blog-manager selftest (auto-deleted)",
                                 md_to_ricos("Selftest draft. Safe to delete."))
                check("live create draft", bool(d.get("id")), d.get("id", ""))
                if d.get("id"):
                    delete_draft(d["id"])
                    check("live delete test draft", True)
            except WixError as e:
                check("live api round trip", False, str(e)[:200])

    passed = sum(1 for _, ok, _ in results if ok)
    lines = ["%s %s%s" % ("PASS" if ok else "FAIL", name,
                          (" — " + note) if note else "")
             for name, ok, note in results]
    lines.append("selftest: %d/%d PASS" % (passed, len(results)))
    if passed != len(results):
        raise SystemExit("\n".join(lines))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="blog_manager")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    lp = sub.add_parser("list")
    lp.add_argument("--drafts", action="store_true")
    dp = sub.add_parser("draft")
    dp.add_argument("--title", required=True)
    dp.add_argument("--file", required=True)
    dp.add_argument("--source")
    dp.add_argument("--publish", action="store_true")
    pp = sub.add_parser("publish")
    pp.add_argument("--draft-id", required=True)
    xp = sub.add_parser("delete-draft")
    xp.add_argument("--draft-id", required=True)
    sub.add_parser("sync")
    sp = sub.add_parser("selftest")
    sp.add_argument("--live", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        print(selftest(live=args.live))
        return 0

    conn = pm_core.conn()
    try:
        if args.cmd == "init":
            out = cmd_init(conn)
        elif args.cmd == "status":
            out = cmd_status(conn)
        elif args.cmd == "list":
            out = cmd_list(conn, drafts=args.drafts)
        elif args.cmd == "draft":
            out = cmd_draft(conn, args.title, args.file,
                            source=args.source, publish=args.publish)
        elif args.cmd == "publish":
            out = cmd_publish(conn, args.draft_id)
        elif args.cmd == "delete-draft":
            out = cmd_delete_draft(conn, args.draft_id)
        elif args.cmd == "sync":
            out = cmd_sync(conn)
        else:  # pragma: no cover
            ap.error("unknown command")
    finally:
        conn.close()
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
