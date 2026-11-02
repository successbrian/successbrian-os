#!/usr/bin/env python3
"""article_match.py — the clerk's article job (Brian, 2026-11-01 20:12 CST).

Brian's specification, in his order of operations: when new intel arrives,
ask "is this possibly related to an article we need on a blog?" — and look
FIRST to see if there is an EXISTING article.

  1. EXISTING CHECK FIRST: search published article titles (public.blog_posts
     + successbrian_os.marketing_blog_posts) for topic overlap with the
     capture. A real overlap -> verdict EXISTING_ARTICLE: the intel is an
     update/refresh candidate for that article, on that article's blog.
  2. NEW-ARTICLE CHECK: if no existing article covers it, route the topic
     through campaignsdesk.blog_boundaries (article_router's table). A blog
     whose boundary covers it -> verdict NEW_ARTICLE with that blog.
  3. NO_FIT: neither — recorded as such, never forced.

Matching is a word rule with reasons in words (shared significant words are
listed), per Brian's clerk philosophy — no opaque scores. Verdicts are
recorded in successbrian_os.clerk_article_matches, one row per capture,
idempotent. The scatter clerk calls assess() for wf3-kept intel and attaches
the one-line verdict to the filing.

CLI:  article_match.py match --capture-id N | scan | check
"""
import re
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_rows, pg_exec, pg_one  # noqa: E402

STOP = set("the a an and or of to in for on with is are was were be been it its "
           "this that from as at by new how why what when who will can could should "
           "into about over under more most other than then them they their our your "
           "his her not no yes do does did have has had".split())
# Generic words that appear in article titles constantly and prove nothing
# on their own (learned live 2026-11-01: 'build' + 'exact' falsely matched
# a Goal Driver capture to an agent-OS article).
GENERIC = set("build built using used use guide best free exact professional "
              "system systems work works working need needs make makes making "
              "way ways thing things".split())

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.clerk_article_matches (
  capture_id bigint PRIMARY KEY,
  verdict    text NOT NULL CHECK (verdict IN ('EXISTING_ARTICLE','NEW_ARTICLE','NO_FIT')),
  blog_slug  text,
  article    text,
  reason     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
)"""


def _sig_words(text):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", (text or "").lower())
            if w not in STOP}


def _corpus():
    rows = pg_rows(
        "SELECT title FROM public.blog_posts WHERE status='published' "
        "UNION ALL SELECT title FROM successbrian_os.marketing_blog_posts "
        "WHERE title IS NOT NULL")
    return [r[0] for r in rows if r[0]]


def _boundary_route(text):
    low = " " + (text or "").lower() + " "
    best = None
    for slug, in_scope, out_scope in pg_rows(
            "SELECT blog_slug, in_scope, out_scope FROM campaignsdesk.blog_boundaries"):
        ins = [p.strip() for p in in_scope.split(";")
               if p.strip() and p.strip().lower() in low]
        outs = [p.strip() for p in out_scope.split(";")
                if p.strip() and p.strip().lower() in low]
        if ins and not outs and (best is None or len(ins) > len(best[1])):
            best = (slug, ins)
    return best


def assess(cap, record=True):
    """One-line verdict for a capture dict {id,title,context,raw}.
    Returns the line (also recorded when record=True and id present)."""
    text = " ".join([cap.get("title") or "", cap.get("context") or "",
                     (cap.get("raw") or "")[:1500]])
    title_words = _sig_words(cap.get("title") or "")
    all_words = title_words | _sig_words(text)
    # 1) EXISTING ARTICLE FIRST (Brian's order). A match must be TOPICAL:
    # the capture TITLE shares >=2 words with the article title including at
    # least one distinctive (non-generic) word — or the full text shares >=4
    # distinctive words with the title. Generic overlap alone is no match.
    best_title, best_shared = None, set()
    for title in _corpus():
        t_words = _sig_words(title)
        t_shared = title_words & t_words
        distinctive = (t_shared | (all_words & t_words)) - GENERIC
        strong = (len(t_shared) >= 2 and len(t_shared - GENERIC) >= 1) or \
                 len((all_words & t_words) - GENERIC) >= 4
        shared = (t_shared | (all_words & t_words))
        if strong and len(distinctive) > len(best_shared - GENERIC):
            best_title, best_shared = title, shared
    if best_title:
        verdict, blog, article = "EXISTING_ARTICLE", None, best_title
        reason = (f"shares topic words ({', '.join(sorted(best_shared))}) "
                  f"with existing article '{best_title}'")
        line = f"article job: EXISTING article may need this intel — {reason}"
    else:
        # 2) NEW ARTICLE via boundaries
        routed = _boundary_route(text)
        if routed:
            verdict, blog, article = "NEW_ARTICLE", routed[0], None
            reason = (f"no existing article covers it; boundary of {blog} "
                      f"matches on: {', '.join(routed[1])}")
            line = f"article job: NEW article needed on {blog} — {reason}"
        else:
            verdict, blog, article = "NO_FIT", None, None
            reason = ("no existing article covers it and no blog boundary "
                      "claims the topic")
            line = f"article job: no article fit — {reason}"
    if record and cap.get("id"):
        pg_exec(DDL)
        pg_exec(
            "INSERT INTO successbrian_os.clerk_article_matches "
            "(capture_id, verdict, blog_slug, article, reason) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (capture_id) DO NOTHING",
            (cap["id"], verdict, blog, article, reason))
    return line


PROPOSALS_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.clerk_article_proposals (
  id          bigserial PRIMARY KEY,
  blog_slug   text NOT NULL,
  title       text NOT NULL,
  outline     text NOT NULL,
  capture_ids bigint[] NOT NULL,
  status      text NOT NULL DEFAULT 'proposed',
  created_at  timestamptz NOT NULL DEFAULT now()
)"""


def _sentences(text, topic_words, limit=2):
    out = []
    for s in re.split(r"(?<=[.!?])\s+", (text or "").replace("\n", " ")):
        s = s.strip()
        if 40 <= len(s) <= 220 and (_sig_words(s) & topic_words):
            out.append(s)
        if len(out) >= limit:
            break
    return out


def propose():
    """One proposal per SOURCE (Brian, 2026-11-01 20:19 CST): an article is
    never built from intel of two different sources — each source carries
    its own verification state and shelf life. Related captures (same blog,
    shared topic) are LINKED to the proposal as relatives: they sequence
    and cross-link as a series, they do not merge into the article."""
    pg_exec(PROPOSALS_DDL)
    pg_exec(DDL)
    done = set()
    for (ids,) in pg_rows("SELECT capture_ids FROM successbrian_os.clerk_article_proposals "
                          "WHERE status = 'proposed'"):
        done.update(ids or [])
    rows = pg_rows(
        "SELECT m.capture_id, m.blog_slug, sc.title, sc.context, sc.raw_text "
        "FROM successbrian_os.clerk_article_matches m "
        "JOIN atlas.scattered_captures sc ON sc.id = m.capture_id "
        "WHERE m.verdict = 'NEW_ARTICLE' ORDER BY m.capture_id")
    caps = [{"id": i, "blog": b, "title": t, "context": c, "raw": r}
            for i, b, t, c, r in rows]
    words_of = {c["id"]: (_sig_words(c["title"]) | _sig_words(c["context"])) - GENERIC
                for c in caps}
    made = 0
    for cap in caps:
        if cap["id"] in done:
            continue
        relatives = [o for o in caps
                     if o["id"] != cap["id"] and o["blog"] == cap["blog"]
                     and len(words_of[cap["id"]] & words_of[o["id"]]) >= 2]
        topic = words_of[cap["id"]]
        title = re.sub(r"^(BUILT|RULING|Intel|INTEL)[:\s—-]+", "",
                       cap["title"] or "Untitled").strip()
        lines = [f"PROPOSED ARTICLE for {cap['blog']}: {title}", "",
                 f"Single source: capture {cap['id']} (an article is built on ONE "
                 "source — its verification state and shelf life are its own)."]
        if relatives:
            lines.append("Related intel (NOT merged — publish as a linked series, "
                         "in order, each from its own source):")
            for o in relatives:
                lines.append(f"   - capture {o['id']}: {o['title']}")
        lines += ["", "ROUGH OUTLINE",
                  "1. Opening — the newest development, in plain words, dated.",
                  f"2. {title}"]
        for s in _sentences(cap["raw"], topic):
            lines.append(f"   - {s}")
        lines.append(f"3. What this means for readers of {cap['blog']} — the so-what, in their terms.")
        if relatives:
            lines.append("4. Link onward to the related piece(s) in this series.")
            lines.append("5. Sources & checked-date line (every claim dated, per blog standard).")
        else:
            lines.append("4. Sources & checked-date line (every claim dated, per blog standard).")
        outline = "\n".join(lines)
        pg_exec(
            "INSERT INTO successbrian_os.clerk_article_proposals (blog_slug, title, outline, capture_ids) "
            "VALUES (%s,%s,%s,%s)",
            (cap["blog"], title, outline, [cap["id"]]))
        print(outline)
        print("=" * 60)
        made += 1
    print(f"proposals created: {made}")
    return 0


def _load_capture(cid):
    rows = pg_rows("SELECT id, title, context, raw_text FROM atlas.scattered_captures WHERE id=%s", (cid,))
    if not rows:
        return None
    i, t, c, r = rows[0]
    return {"id": i, "title": t, "context": c, "raw": r}


def scan(limit=50):
    pg_exec(DDL)
    rows = pg_rows(
        "SELECT sc.id, sc.title, sc.context, sc.raw FROM atlas.scattered_captures sc "
        "LEFT JOIN successbrian_os.clerk_article_matches m ON m.capture_id = sc.id "
        "WHERE m.capture_id IS NULL AND sc.kind = 'intel' "
        "ORDER BY sc.id DESC LIMIT %s", (limit,))
    n = 0
    for i, t, c, r in rows:
        line = assess({"id": i, "title": t, "context": c, "raw": r})
        print(f"capture {i}: {line}")
        n += 1
    print(f"assessed {n} intel capture(s)")
    return 0


def check():
    try:
        pg_exec(DDL)
        _corpus()
        print("ARTICLE_MATCH_OK")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"DEFECT: {e}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "match" and sys.argv[2] == "--capture-id":
        cap = _load_capture(int(sys.argv[3]))
        if cap is None:
            print("capture not found")
            raise SystemExit(1)
        print(assess(cap))
        raise SystemExit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "scan":
        raise SystemExit(scan())
    if len(sys.argv) >= 2 and sys.argv[1] == "propose":
        raise SystemExit(propose())
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        raise SystemExit(check())
    print(__doc__)
    raise SystemExit(2)
