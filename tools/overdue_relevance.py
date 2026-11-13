#!/usr/bin/env python3
"""overdue_relevance.py — overdue items get re-researched,
not just re-ranked.

Brian's ruling (2026-11-12 19:41 CST): "as things get overdue
we need to research and find out the current relevance — and
build more data on what others wrote about them (if blogs)...
and find ways to build our audience and sell more of what we
sell."

Why this exists: the hourly resort + the first_next judgement
rank by recorded fields, so a stale item can sit at the top
forever on age alone (first live judgement, 2026-11-12: a
Sep 26 Crew2 event task ranked FIRST at 47 days overdue).
Age is not relevance. An overdue item owes the system a fresh
answer to: is this still a live thing, what changed, and —
for blog/article items — what have others written since,
which audience does it build, and what do we sell that fits
(the article's job: SELL or DRAW, Brian 2026-10-29; judged
down visits -> contacts -> revenue, 2026-10-27).

What this module does (deterministic spine, one bounded
model step, following the clerk/priority_pass pattern):
  1. Reads the latest first_next judgement's work items and
     joins the real age: tasks by target_date, pm_steps and
     captures by created_at. Overdue = target/creation age
     past its due point (tasks) or > 7 days old in the order
     (other sources, labeled as age not due-date).
  2. For each overdue item (cap per run, judgement order):
     records a row in successbrian_os.overdue_relevance
     (deduped per item within 7 days) and builds the research
     packet: the item, its age, what the ecosystem already
     holds on the topic (capture titles matched by topic
     words — real internal data on what we/others have
     already filed), and the standing research questions.
  3. One bounded Sonic read per item gives an immediate,
     LABELED relevance signal (still-live / likely-stale /
     needs-brian + one-line reason). It is a model read of
     the packet, NOT web verification — the packet says so.
  4. Files the packet as an Intel Bridge capture (RESEARCH
     framing) — the path that demonstrably gets researched:
     clerk triage -> board packet / passup -> decider
     packages -> the heartbeat's judgement lane. (Checked
     2026-11-12: engine-queue kinds without a registered
     handler are released unworked, and reap_queue
     priority-arbitration jobs sat queued — so this module
     does NOT enqueue-and-pray; it files where research
     actually happens and keeps its own table as the ledger.)

For blog/article items the packet additionally asks:
what others have written (angles taken, gaps left), which
core audience it builds, its capture offer, and what we
sell — with the SELL/DRAW job named.

CLI:
  overdue_relevance.py run [--no-file]   research the latest
                                         judgement's overdue
  overdue_relevance.py show              latest research rows
  overdue_relevance.py selftest
"""

import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

RELEVANCE_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.overdue_relevance (
    id serial PRIMARY KEY,
    source_type text NOT NULL,
    source_id integer NOT NULL,
    title text,
    days_overdue integer,
    judgement_rank integer,
    is_blog boolean NOT NULL DEFAULT false,
    sonic_read text,
    sonic_reason text,
    internal_hits integer DEFAULT 0,
    capture_id integer,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS overdue_relevance_item_idx
    ON successbrian_os.overdue_relevance
    (source_type, source_id, created_at);
"""

BLOG_WORDS = ["article", "blog", "substack", "post", "draft",
              "approve", "publish", "seo", "episode"]
MAX_PER_RUN = 5
RESEARCH_QUESTIONS = [
    "Is this still relevant as of today — what changed since "
    "it was filed?",
    "If it is a past-dated event or a finished thing, say so: "
    "it should be closed, not carried.",
    "What is the smallest next step if it is still live?",
]
BLOG_QUESTIONS = [
    "What have others written on this topic — angles taken, "
    "what is already covered, what gap is left for us?",
    "Which core audience does this build, and what is its "
    "capture offer (the door a reader walks through)?",
    "What do we sell that fits this topic? Name the article's "
    "job: SELL (convert, judged at contacts -> revenue) or "
    "DRAW (rank/attract, feeds the sellers).",
]

STOP = set("the a an and or of to for in on x vs with about "
           "check intel draft".split())


def is_blog(source, title):
    if source == "blog_run":
        return True
    low = " " + (title or "").lower() + " "
    return any(w in low for w in BLOG_WORDS)


def topic_words(title):
    words = re.findall(r"[a-z]{4,}", (title or "").lower())
    return [w for w in words if w not in STOP][:5]


def overdue_items(today):
    """Latest judgement's work items with real ages joined."""
    hour = sbos_common.pg_one(
        "SELECT max(order_hour) FROM "
        "successbrian_os.first_next_judgement")
    if not hour:
        return None, []
    rows = sbos_common.pg_rows(
        "SELECT rank, source_type, source_id, title, "
        "stack_tier FROM successbrian_os.first_next_judgement "
        "WHERE order_hour = %s AND block = 'work' "
        "ORDER BY rank", (hour,))
    out = []
    for rank, source, sid, title, tier in rows:
        days = None
        basis = None
        if source == "task":
            td = sbos_common.pg_one(
                "SELECT target_date FROM successbrian_os.tasks "
                "WHERE id = %s", (sid,))
            if td:
                days = (today - td).days
                basis = "target_date"
        elif source == "pm_step":
            ca = sbos_common.pg_one(
                "SELECT created_at::date FROM "
                "successbrian_os.pm_steps WHERE id = %s", (sid,))
            if ca:
                days = (today - ca).days - 7
                basis = "age past 7d (no due date on record)"
        elif source == "capture":
            ca = sbos_common.pg_one(
                "SELECT created_at::date FROM "
                "atlas.scattered_captures WHERE id = %s", (sid,))
            if ca:
                days = (today - ca).days - 7
                basis = "age past 7d (no due date on record)"
        if days is not None and days > 0:
            out.append({"rank": rank, "source": source,
                        "id": sid, "title": title, "tier": tier,
                        "days": days, "basis": basis,
                        "blog": is_blog(source, title)})
    return hour, out


def internal_data(title):
    """What the ecosystem already holds on this topic: capture
    titles matching the topic words (real internal data)."""
    words = topic_words(title)
    hits = []
    for w in words:
        rows = sbos_common.pg_rows(
            "SELECT id, title FROM atlas.scattered_captures "
            "WHERE title ILIKE %s ORDER BY id DESC LIMIT 4",
            ("%" + w + "%",))
        for cid, t in rows:
            if (cid, t) not in hits:
                hits.append((cid, t))
    return hits[:6]


def sonic_read(item, hits):
    """One bounded Sonic relevance read of the packet. Labeled
    for what it is: a model read, not web verification."""
    lines = [
        f"Item: [{item['source']}#{item['id']}] {item['title']}",
        f"Overdue: {item['days']} days ({item['basis']}).",
        "Ecosystem already holds on this topic: "
        + ("; ".join(f"#{c} {t}" for c, t in hits)
           if hits else "nothing matched"),
        "",
        "Answer with exactly one first line:",
        "READ: still-live | likely-stale | needs-brian",
        "Then one line: REASON: <one line, only from the "
        "packet — do not invent facts>.",
        "Judge: a past-dated one-time event is likely-stale; "
        "work serving a live goal or a publishing pipeline is "
        "still-live; a ruling only Brian can make is "
        "needs-brian."]
    try:
        text, _u = sbos_common.llm_chat(
            prompt=sbos_common.budget_prompt(
                "\n".join(lines), sbos_common.SONIC_KV_AUTO),
            url=sbos_common.SONIC_URL,
            model=sbos_common.SONIC_MODEL, max_tokens=300,
            temperature=0.2, timeout=600)
        read, reason = None, None
        for ln in (text or "").splitlines():
            if ln.upper().startswith("READ:"):
                read = ln.split(":", 1)[1].strip().lower()
            if ln.upper().startswith("REASON:"):
                reason = ln.split(":", 1)[1].strip()
        if read in ("still-live", "likely-stale", "needs-brian"):
            return read, reason or ""
    except Exception as e:
        return "unavailable", f"Sonic read failed: {e}"
    return "unavailable", "Sonic returned no parseable read"


def file_packet(item, hits, read, reason):
    import base64 as b64
    import subprocess

    def b64sql(s):
        return ("convert_from(decode('%s','base64'),'UTF8')"
                % b64.b64encode(s.encode()).decode())

    title = (f"RESEARCH (overdue {item['days']}d): "
             + (item["title"] or "")[:90])
    exists = sbos_common.pg_one(
        "SELECT count(*) FROM atlas.scattered_captures "
        "WHERE title = %s AND created_at > now() - interval "
        "'7 days'", (title,))
    if exists:
        return None
    parts = [
        f"OVERDUE RELEVANCE RESEARCH — {item['days']} days "
        f"overdue ({item['basis']}), judgement rank "
        f"{item['rank']}, stack tier {item['tier']}.",
        f"Item: [{item['source']}#{item['id']}] {item['title']}",
        f"Immediate Sonic read (model read of this packet, "
        f"NOT web-verified): {read}"
        + (f" — {reason}" if reason else ""),
        "",
        "RESEARCH QUESTIONS:",
    ]
    parts += [f"- {q}" for q in RESEARCH_QUESTIONS]
    if item["blog"]:
        parts.append("BLOG/ARTICLE — additionally:")
        parts += [f"- {q}" for q in BLOG_QUESTIONS]
    parts.append("")
    parts.append("WHAT THE ECOSYSTEM ALREADY HOLDS ON THIS "
                 "TOPIC (capture titles matched by topic words):")
    if hits:
        parts += [f"- #{c} {t}" for c, t in hits]
    else:
        parts.append("- nothing matched — building this data "
                     "is part of the research.")
    raw = "\n".join(parts)
    context = ("Filed by overdue_relevance (Brian's ruling "
               "2026-11-12: overdue items get re-researched "
               "for current relevance; blog items additionally "
               "build data on what others wrote, the audience "
               "built, and what we sell).")
    sql = ("insert into atlas.scattered_captures "
           "(title, raw_text, context, status) values "
           f"({b64sql(title)}, {b64sql(raw)}, "
           f"{b64sql(context)}, 'raw') returning id")
    p = subprocess.run(["psql", "-d", "ecosystem_central",
                        "-t", "-A", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    out = (p.stdout or "").strip().splitlines()
    return out[0] if out else ""


def run(do_file=True):
    sbos_common.pg_exec(RELEVANCE_DDL)
    today = dt.date.today()
    hour, items = overdue_items(today)
    if hour is None:
        print("no judgement yet — run first_next.py first")
        return 1
    print(f"overdue items in the latest judgement: {len(items)}")
    made = 0
    for item in items:
        if made >= MAX_PER_RUN:
            print(f"cap reached ({MAX_PER_RUN}/run) — the rest "
                  "re-enter next run")
            break
        recent = sbos_common.pg_one(
            "SELECT count(*) FROM "
            "successbrian_os.overdue_relevance WHERE "
            "source_type = %s AND source_id = %s AND "
            "created_at > now() - interval '7 days'",
            (item["source"], item["id"]))
        if recent:
            continue
        hits = internal_data(item["title"])
        read, reason = sonic_read(item, hits)
        cid = file_packet(item, hits, read, reason) \
            if do_file else None
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.overdue_relevance "
            "(source_type, source_id, title, days_overdue, "
            "judgement_rank, is_blog, sonic_read, "
            "sonic_reason, internal_hits, capture_id) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (item["source"], item["id"], item["title"],
             item["days"], item["rank"], item["blog"], read,
             reason, len(hits),
             int(cid) if cid and str(cid).isdigit() else None))
        made += 1
        print(f"researched [{item['source']}#{item['id']}] "
              f"{item['days']}d overdue"
              f"{' (blog)' if item['blog'] else ''} — "
              f"sonic: {read}"
              + (f" — capture #{cid}" if cid else ""))
    if not made:
        print("nothing new to research (all overdue items "
              "researched within 7 days)")
    return 0


def show():
    rows = sbos_common.pg_rows(
        "SELECT created_at, source_type, source_id, title, "
        "days_overdue, is_blog, sonic_read, sonic_reason, "
        "capture_id FROM successbrian_os.overdue_relevance "
        "ORDER BY id DESC LIMIT 15")
    if not rows:
        print("no relevance research yet — run: "
              "overdue_relevance.py run")
        return
    for r in rows:
        print(f"{r[0]:%Y-%m-%d %H:%M} [{r[1]}#{r[2]}] {r[3]}")
        print(f"   {r[4]}d overdue"
              f"{' blog' if r[5] else ''} — sonic read: {r[6]}"
              f" — {r[7] or ''}"
              f" (research capture #{r[8]})")


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    check("substack draft is a blog item",
          is_blog("task", "Substack: DRAFT the crossover "
                          "article"))
    check("blog_run source is a blog item",
          is_blog("blog_run", "anything at all"))
    check("crew blast task is not a blog item",
          not is_blog("task", "Drive Sat Sep 26 Crew2 12hr "
                              "blast"))
    check("topic words drop stop words",
          "crossover" in topic_words("Substack: DRAFT Fire "
                                     "Country crossover "
                                     "article")
          and "the" not in topic_words("the crossover"))
    check("blog packets carry the others-wrote question",
          any("others written" in q for q in BLOG_QUESTIONS))
    check("blog packets carry the sell question",
          any("SELL" in q and "DRAW" in q
              for q in BLOG_QUESTIONS))
    check("research questions ask if it should be closed",
          any("closed" in q for q in RESEARCH_QUESTIONS))
    check("relevance ddl names the table",
          "overdue_relevance" in RELEVANCE_DDL)
    check("per-run cap is bounded", 0 < MAX_PER_RUN <= 10)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if argv and argv[0] == "selftest":
        return selftest()
    if argv and argv[0] == "show":
        show()
        return 0
    if argv and argv[0] == "run":
        return run(do_file="--no-file" not in argv)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
