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
  * Uploads images to the Wix Media Manager (site-media v1) and
    embeds them: a standalone markdown line ![alt](media:KEY) becomes
    a Ricos IMAGE node (KEY resolves through a media map of uploaded
    files), and ![video](youtube-url) becomes a Ricos VIDEO node.
    A draft can also carry a cover image (the draft's `media`).
  * Creates DRAFT posts, publishes drafts, REVISES published posts
    (PATCH the post's draft, then republish — the post id and URL
    survive), lists posts/drafts, deletes test drafts, and keeps the
    registry table successbrian_os.marketing_blog_posts in step
    (PostgreSQL is the state home, per R32).

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
        [--media media.json] [--cover-media media.json]
  upload --file F.png [--name N]     upload to Media Manager (JSON out)
  revise --draft-id ID --file F.md [--media media.json]
        [--cover-media media.json] [--excerpt E] [--publish]
  publish --draft-id ID
  delete-draft --draft-id ID
  sync                        reconcile registry with remote state
  selftest [--live]           offline checks; --live adds a real
                              list + create/delete test-draft round trip
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "pm"))
import pm_core  # noqa: E402

API_BASE = "https://www.wixapis.com/blog/v3"
MEDIA_BASE = "https://www.wixapis.com/site-media/v1"
ENV_PATH = os.path.expanduser("~/successbrian-os/.env")

# Brian's ruling (2026-10-26): every page of ALL of our blogs points to
# his Substack, professionally, at the bottom. One Substack for the whole
# fleet. Drafts created through this engine get the standard closing
# block appended (idempotent: skipped when the link is already present),
# so no post can ship without it and no post ever carries it twice.
SUBSTACK_URL = "https://successbrianhub.substack.com"
POST_FOOTER_MD = (
    "\n\n**Read more from Brian Lathe on Substack**\n\n"
    "This blog is one room in a bigger house. My main writing lives on "
    "Substack - longer pieces, new posts first, always free to read: "
    "[Brian Lathe on Substack](https://successbrianhub.substack.com).\n"
)


def with_post_footer(md):
    if SUBSTACK_URL in md:
        return md
    return md.rstrip() + "\n" + POST_FOOTER_MD


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


def api(method, path, body=None, cfg=None, base=API_BASE):
    cfg = cfg or config()
    if not cfg["api_key"] or not cfg["site_id"]:
        raise WixError("Wix config missing (WIX_API_KEY / WIX_SITE_ID)")
    url = base + path
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


def create_draft(title, ricos, cfg=None, excerpt=None, publish=False,
                 cover=None):
    cfg = cfg or config()
    draft = {"title": title, "richContent": ricos}
    if excerpt:
        draft["excerpt"] = excerpt
    if cover:
        draft["media"] = cover
    if cfg["member_id"]:
        draft["memberId"] = cfg["member_id"]
    out = api("POST", "/draft-posts",
              {"draftPost": draft, "publish": bool(publish)}, cfg)
    return out.get("draftPost", out)


def update_draft(draft_id, cfg=None, ricos=None, cover=None, excerpt=None,
                 title=None):
    """Revise a draft post in place (PATCH /draft-posts/{id}).

    For a PUBLISHED post this edits its draft half; call publish_draft
    afterwards to push the revision live. The post id and URL survive.
    The fieldMask format ({"paths": [...]}) was verified live against
    the API on 2026-10-28 (throwaway-draft round trip).
    """
    cfg = cfg or config()
    draft = {"id": draft_id}
    if cfg["member_id"]:
        # The API rejects updates without post owner information.
        draft["memberId"] = cfg["member_id"]
    paths = []
    if ricos is not None:
        draft["richContent"] = ricos
        paths.append("richContent")
    if cover is not None:
        draft["media"] = cover
        paths.append("media")
    if excerpt is not None:
        draft["excerpt"] = excerpt
        paths.append("excerpt")
    if title is not None:
        draft["title"] = title
        paths.append("title")
    if not paths:
        raise WixError("update_draft: nothing to update")
    out = api("PATCH", "/draft-posts/%s" % draft_id,
              {"draftPost": draft, "fieldMask": {"paths": paths}}, cfg)
    return out.get("draftPost", out)


# ------------------------------------------------------------- media

def upload_media(local_path, cfg=None, file_name=None):
    """Upload one local file to the Wix Media Manager.

    Flow (Wix site-media v1): POST /files/generate-upload-url ->
    PUT the bytes to the signed uploadUrl -> the file descriptor.
    Upload processing is async, so poll GET /files/{id} until the
    descriptor carries width/height (image ready). Returns the file
    dict: {id, url (static.wixstatic.com), width, height, ...}.
    """
    cfg = cfg or config()
    name = file_name or os.path.basename(local_path)
    mime = (mimetypes.guess_type(name)[0] or "application/octet-stream")
    out = api("POST", "/files/generate-upload-url",
              {"mimeType": mime, "fileName": name}, cfg, base=MEDIA_BASE)
    upload_url = out.get("uploadUrl")
    if not upload_url:
        raise WixError("generate-upload-url returned no uploadUrl: %s"
                       % str(out)[:200])
    with open(local_path, "rb") as fh:
        data = fh.read()
    sep = "&" if "?" in upload_url else "?"
    put_url = upload_url + sep + "filename=" + urllib.parse.quote(name)
    req = urllib.request.Request(put_url, data=data, method="PUT")
    req.add_header("Content-Type", mime)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise WixError("media PUT -> HTTP %s: %s" % (e.code, detail))
    up = json.loads(raw) if raw else {}
    file_obj = _normalize_file(up.get("file", up))
    fid = file_obj.get("id")
    # Wait for processing to finish (operationStatus READY / dims set).
    for _ in range(10):
        if file_obj.get("width") and file_obj.get("height"):
            break
        if not fid:
            break
        import time
        time.sleep(2)
        got = api("GET", "/files/%s" % urllib.parse.quote(fid, safe=""),
                  None, cfg, base=MEDIA_BASE)
        file_obj = _normalize_file(got.get("file", got)) or file_obj
    return file_obj


def _normalize_file(file_obj):
    """Flatten a site-media file descriptor.

    The PUT response carries width/height at top level; the GET
    descriptor nests them at media.image.image.{width,height} and
    names the file 'filename' there / 'displayName' at top level.
    Downstream code (media map, cover) wants one flat shape.
    """
    if not isinstance(file_obj, dict):
        return file_obj
    img = ((file_obj.get("media") or {}).get("image") or {}).get("image") \
        or {}
    if not file_obj.get("width"):
        file_obj["width"] = img.get("width")
    if not file_obj.get("height"):
        file_obj["height"] = img.get("height")
    if not file_obj.get("fileName"):
        file_obj["fileName"] = (img.get("filename")
                                or file_obj.get("displayName"))
    if not file_obj.get("url"):
        file_obj["url"] = img.get("url")
    return file_obj


def cover_media(file_obj):
    """Build a draft-post `media` (cover) value from an uploaded file.

    The Draft object has no coverMedia field — the cover lives in
    `media`, and its wixMedia.image must be an OBJECT {id} on write
    (the wix:image:// URI string only appears on reads). Verified
    live 2026-10-28 on a throwaway draft: coverMedia was silently
    ignored, the URI-string form errored ("Expected an object"),
    and this shape round-trips.
    """
    return {"wixMedia": {"image": {"id": file_obj["id"]}},
            "displayed": True, "custom": True}


def media_entry(file_obj):
    """One media-map entry for md_to_ricos ![alt](media:KEY) nodes."""
    return {"id": file_obj["id"], "width": file_obj.get("width"),
            "height": file_obj.get("height")}


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
# Bold-wrapped link **[label](url)** and plain link, in one token pass.
_TOKEN_RE = re.compile(
    r"\*\*\[(?P<bl>[^\]]+)\]\((?P<bu>https?://[^)\s]+)\)\*\*"
    r"|\[(?P<l>[^\]]+)\]\((?P<u>https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
# Standalone media lines: ![alt](media:KEY) or ![video](youtube-url).
_MEDIA_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


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
    """Parse **bold**, *italic*, [label](url) into TEXT nodes.

    A bold-wrapped link **[label](url)** is a single token: the label
    gets BOLD + LINK decorations and no literal ** survives (the old
    link-first pass left the asterisks as plain text — visible on the
    live post 1 GitHub CTA until the 2026-10-28 revision).
    """
    nodes = []
    pos = 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() > pos:
            nodes.extend(_inline_plain(text[pos:m.start()]))
        if m.group("bl") is not None:
            label, url, bold = m.group("bl"), m.group("bu"), True
        else:
            label, url, bold = m.group("l"), m.group("u"), False
        deco = [{"type": "LINK",
                 "linkData": {"link": {"url": url, "target": "BLANK"}}}]
        for sn in _inline_plain(label):
            d = list(sn["textData"]["decorations"])
            if bold and not any(x["type"] == "BOLD" for x in d):
                d = [{"type": "BOLD"}] + d
            sn["textData"]["decorations"] = d + deco
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


def _media_node(stripped, media, ids):
    """IMAGE / VIDEO node for a standalone media line, else None.

    ![alt](media:KEY)  -> IMAGE node; KEY resolves through the media
        map ({KEY: {"id", "width", "height"}} from uploaded files).
    ![video](URL)      -> VIDEO node for a YouTube watch URL.
    An unresolved media:KEY is a hard error — silently dropping an
    image the author asked for is how posts ship without their art.
    """
    m = _MEDIA_LINE_RE.match(stripped)
    if not m:
        return None
    alt, target = m.group(1), m.group(2)
    if target.startswith("media:"):
        key = target[len("media:"):]
        entry = (media or {}).get(key)
        if not entry:
            raise ValueError("media line references unknown key %r "
                             "(not in the media map)" % key)
        node = {"type": "IMAGE", "id": ids.next(), "nodes": [],
                "imageData": {
                    "containerData": {"width": {"size": "CONTENT"},
                                      "alignment": "CENTER"},
                    "image": {"src": {"id": entry["id"]},
                              "width": entry.get("width"),
                              "height": entry.get("height")},
                    "altText": alt}}
        if entry.get("link"):
            # Optional click-through (media map entry "link": URL) —
            # Brian 2026-10-29: blog images click through to WhatsApp.
            node["imageData"]["link"] = {"url": entry["link"],
                                         "target": "BLANK"}
        return node
    if alt.strip().lower() == "video" and (
            "youtube.com/watch" in target or "youtu.be/" in target):
        return {"type": "VIDEO", "id": ids.next(), "nodes": [],
                "videoData": {
                    "containerData": {"width": {"size": "CONTENT"},
                                      "alignment": "CENTER",
                                      "textWrap": True},
                    "video": {"src": {"url": target}}}}
    return None


def md_to_ricos(md, media=None):
    """Convert markdown to a Wix Ricos document ({'nodes': [...]}).

    Supports #/##/### headings, paragraphs, > blockquotes, - bullets,
    1. numbered lists, --- dividers, inline bold/italic/links (including bold-wrapped
    links), and standalone media lines ![alt](media:KEY) /
    ![video](youtube-url) when a media map is supplied. Anything else
    is passed through as plain paragraph text — deterministic, no
    model.
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
        mnode = _media_node(stripped, media, ids)
        if mnode is not None:
            # Breathing room around standalone media (Brian 2026-10-29:
            # images sat jammed against the text). An empty paragraph
            # on each side renders as vertical space in the Wix theme;
            # collapse doubles so back-to-back media stay tight-ish.
            spacer = lambda: {"type": "PARAGRAPH", "id": ids.next(),
                              "nodes": [], "paragraphData": {}}
            if nodes and nodes[-1]["type"] != "PARAGRAPH":
                nodes.append(spacer())
            elif nodes and nodes[-1].get("nodes"):
                nodes.append(spacer())
            nodes.append(mnode)
            nodes.append(spacer())
            i += 1
            continue
        if stripped in ("---", "***", "___"):
            nodes.append({"type": "DIVIDER", "id": ids.next(), "nodes": [],
                          "dividerData": {"lineStyle": "SINGLE",
                                          "alignment": "CENTER",
                                          "width": "LARGE"}})
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
            if not nxt or nxt in ("---", "***", "___") \
                    or re.match(r"^(#{1,3}\s|>|[-*]\s|\d+\.\s)", nxt):
                break
            if _MEDIA_LINE_RE.match(nxt):
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


def _load_json(path):
    with open(path) as fh:
        return json.load(fh)


def cmd_draft(conn, title, path, source=None, publish=False,
              media_path=None, cover_path=None):
    with open(path) as fh:
        md = with_post_footer(fh.read())
    media = _load_json(media_path) if media_path else None
    ricos = md_to_ricos(md, media=media)
    cover = None
    if cover_path:
        cover = cover_media(_load_json(cover_path))
    cfg = config()
    draft_post = create_draft(title, ricos, cfg, cover=cover)
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


def cmd_upload(_conn, path, name=None):
    file_obj = upload_media(path, file_name=name)
    return json.dumps(file_obj, indent=1)


def cmd_revise(conn, draft_id, path, media_path=None, cover_path=None,
               excerpt=None, publish=False):
    """Revise an existing post: PATCH its draft, optionally republish.

    Content file is a full replacement article (same footer rule as
    drafts). The registry row is refreshed, keeping the same post id.
    """
    with open(path) as fh:
        md = with_post_footer(fh.read())
    media = _load_json(media_path) if media_path else None
    ricos = md_to_ricos(md, media=media)
    cover = None
    if cover_path:
        cover = cover_media(_load_json(cover_path))
    cfg = config()
    update_draft(draft_id, cfg, ricos=ricos, cover=cover, excerpt=excerpt)
    msg = "draft revised in place: %s" % draft_id
    if publish:
        post_id = publish_draft(draft_id, cfg)
        msg += "; republished as post %s" % post_id
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE successbrian_os.marketing_blog_posts
                      SET post_id = %s, status = 'published',
                          updated_at = now()
                    WHERE site_id = %s AND draft_id = %s""",
                (post_id, cfg["site_id"], draft_id))
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
    # Bold-wrapped link: **[label](url)** -> BOLD+LINK, no literal **.
    bdoc = md_to_ricos("**[Get it](https://example.com/get)** — free\n")
    bpara = bdoc["nodes"][0]
    btexts = [t["textData"]["text"] for t in bpara["nodes"]]
    bdecos = [d["type"] for t in bpara["nodes"]
              for d in t["textData"]["decorations"]]
    check("bold-link has no literal **",
          not any("**" in t for t in btexts), "".join(btexts)[:60])
    check("bold-link carries BOLD+LINK",
          "BOLD" in bdecos and "LINK" in bdecos)
    # Media lines: image via media map, video via YouTube URL.
    mmap = {"hero": {"id": "abc123_hero.png", "width": 1600,
                     "height": 900}}
    mdoc = md_to_ricos("Before.\n\n![A diagram](media:hero)\n\n"
                       "![video](https://www.youtube.com/watch?v=XYZ123)\n\n"
                       "After.\n", media=mmap)
    mtypes = [n["type"] for n in mdoc["nodes"]]
    check("image node from media line", "IMAGE" in mtypes)
    check("video node from media line", "VIDEO" in mtypes)
    img = next(n for n in mdoc["nodes"] if n["type"] == "IMAGE")
    check("image node src id + dims",
          img["imageData"]["image"]["src"]["id"] == "abc123_hero.png"
          and img["imageData"]["image"]["width"] == 1600)
    vid = next(n for n in mdoc["nodes"] if n["type"] == "VIDEO")
    check("video node src url",
          vid["videoData"]["video"]["src"]["url"]
          == "https://www.youtube.com/watch?v=XYZ123")
    try:
        md_to_ricos("![x](media:missing)\n", media=mmap)
        check("unknown media key is a hard error", False)
    except ValueError:
        check("unknown media key is a hard error", True)
    cov = cover_media({"id": "abc123_hero.png", "width": 1600,
                       "height": 900, "fileName": "hero.png"})
    check("cover media shape (media.wixMedia.image {id})",
          cov["wixMedia"]["image"]["id"] == "abc123_hero.png"
          and cov["displayed"] is True)
    footed = with_post_footer(md)
    check("substack footer appended", SUBSTACK_URL in footed)
    check("substack footer idempotent", with_post_footer(footed) == footed)

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
    dp.add_argument("--media", help="media map JSON for ![alt](media:KEY)")
    dp.add_argument("--cover-media",
                    help="uploaded-file JSON to set as cover image")
    up = sub.add_parser("upload")
    up.add_argument("--file", required=True)
    up.add_argument("--name")
    rp = sub.add_parser("revise")
    rp.add_argument("--draft-id", required=True)
    rp.add_argument("--file", required=True)
    rp.add_argument("--media", help="media map JSON for ![alt](media:KEY)")
    rp.add_argument("--cover-media",
                    help="uploaded-file JSON to set as cover image")
    rp.add_argument("--excerpt")
    rp.add_argument("--publish", action="store_true")
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
                            source=args.source, publish=args.publish,
                            media_path=args.media,
                            cover_path=args.cover_media)
        elif args.cmd == "upload":
            out = cmd_upload(conn, args.file, name=args.name)
        elif args.cmd == "revise":
            out = cmd_revise(conn, args.draft_id, args.file,
                             media_path=args.media,
                             cover_path=args.cover_media,
                             excerpt=args.excerpt, publish=args.publish)
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
