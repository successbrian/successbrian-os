#!/usr/bin/env python3
"""Insert empty-paragraph spacers between body paragraphs (and above
headings/quotes) in EXISTING Wix posts, via blog_manager's API layer.

Why: Wix blog post text styles expose no paragraph-spacing control
(found 2026-10-30). The empty-paragraph spacer is the mechanism already
proven on this blog for media (blog_manager converter, Brian 2026-10-29:
"An empty paragraph on each side renders as vertical space in the Wix
theme"). Words are never touched: the transform only inserts spacer
nodes; verification asserts the concatenated text is byte-identical
before/after and the cover media is unchanged.

Usage: add_paragraph_spacing.py <post_id|--all> [--dry-run]
Backups: ~/backups/spacing-20261030/<post_id>-before.json
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blog_manager as bm

BACKUP_DIR = os.path.expanduser("~/backups/spacing-20261030")
TEXT_TYPES = ("PARAGRAPH", "BLOCKQUOTE", "BULLETED_LIST", "ORDERED_LIST")

def node_text(n):
    out = []
    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "TEXT":
                out.append((x.get("textData") or {}).get("text") or "")
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(n)
    return "".join(out)

def is_empty_para(n):
    if n.get("type") != "PARAGRAPH":
        return False
    if node_text(n).strip():
        return False
    return all(c.get("type") == "TEXT" for c in (n.get("nodes") or []))

def is_text_block(n):
    return n.get("type") in TEXT_TYPES and bool(node_text(n).strip())

def transform(nodes, id_prefix):
    existing = {n.get("id") for n in nodes}
    counter = [0]
    def spacer():
        while True:
            counter[0] += 1
            nid = "%ssp%03d" % (id_prefix, counter[0])
            if nid not in existing:
                existing.add(nid)
                return {"type": "PARAGRAPH", "id": nid, "nodes": [], "paragraphData": {}}
    out = []
    added = 0
    for n in nodes:
        t = n.get("type")
        prev = out[-1] if out else None
        need = False
        if prev is not None and not is_empty_para(prev) and prev.get("type") != "DIVIDER" and t != "DIVIDER":
            if is_text_block(n) and is_text_block(prev) and t == "PARAGRAPH" and prev.get("type") == "PARAGRAPH":
                need = True
            elif t in ("HEADING", "BLOCKQUOTE") and is_text_block(prev):
                need = True
            elif t == "PARAGRAPH" and prev.get("type") == "BLOCKQUOTE" and is_text_block(prev):
                need = True
        if need:
            out.append(spacer()); added += 1
        out.append(n)
    return out, added

def fetch_post(cfg, post_id):
    res = bm.api("POST", "/posts/query",
                 body={"query": {"paging": {"limit": 50}}, "fieldsets": ["RICH_CONTENT"]}, cfg=cfg)
    for p in res.get("posts") or []:
        if p.get("id") == post_id:
            return p
    raise SystemExit("post not found: %s" % post_id)

def all_text(nodes):
    # Word-sequence comparison: spacer nodes contribute no words, so a
    # spacing-only change must leave this string byte-identical.
    return " ".join(" ".join(node_text(n) for n in nodes).split())

def cover_of(post):
    m = post.get("media") or {}
    return json.dumps(m, sort_keys=True)

def fetch_media(cfg, post_id):
    p = bm.api("GET", "/posts/%s" % post_id, cfg=cfg).get("post", {})
    return p.get("media") or {}

def process(cfg, post_id, dry):
    post = fetch_post(cfg, post_id)
    title = post.get("title")
    rc = post.get("richContent") or {}
    nodes = rc.get("nodes") or []
    before_text = all_text(nodes)
    before_cover = json.dumps(fetch_media(cfg, post_id), sort_keys=True)
    new_nodes, added = transform(nodes, post_id[:4])
    print("%s: nodes %d -> %d (+%d spacers) dry=%s" % (title, len(nodes), len(new_nodes), added, dry))
    if dry or added == 0:
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(os.path.join(BACKUP_DIR, post_id + "-before.json"), "w") as f:
        json.dump({"richContent": rc, "media": fetch_media(cfg, post_id)}, f)
    new_rc = dict(rc); new_rc["nodes"] = new_nodes
    # Wix draft PATCH resets media unless media is re-sent (the capture
    # #548 defect, hit live 2026-10-30 on Office Manager: cover stripped
    # by a richContent-only patch, restored same pass). Re-send the
    # existing cover in the same update whenever the post has one.
    cur_media = fetch_media(cfg, post_id)
    cur_img = ((cur_media.get("wixMedia") or {}).get("image") or {}).get("id")
    cover = bm.cover_media({"id": cur_img}) if cur_img else None
    bm.update_draft(post_id, cfg=cfg, ricos=new_rc, cover=cover)
    bm.publish_draft(post_id, cfg=cfg)
    time.sleep(2)
    after = fetch_post(cfg, post_id)
    after_nodes = (after.get("richContent") or {}).get("nodes") or []
    assert all_text(after_nodes) == before_text, "TEXT CHANGED for %s" % title
    after_cover = json.dumps(fetch_media(cfg, post_id), sort_keys=True)
    assert after_cover == before_cover, "COVER CHANGED for %s" % title
    print("  verified: text identical, cover unchanged, nodes now %d" % len(after_nodes))

def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    cfg = bm.config()
    if args and args[0] == "--all":
        res = bm.api("POST", "/posts/query",
                     body={"query": {"paging": {"limit": 50}}}, cfg=cfg)
        ids = [p["id"] for p in res.get("posts") or []]
    else:
        ids = args
    for pid in ids:
        process(cfg, pid, dry)

if __name__ == "__main__":
    main()
