#!/usr/bin/env python3
"""overdue_relevance.py — overdue items get re-researched,
not just re-ranked.

Brian's rulings:
  2026-11-12 19:41 CST — "as things get overdue we need to
  research and find out the current relevance — and build
  more data on what others wrote about them (if blogs)...
  and find ways to build our audience and sell more of what
  we sell."
  2026-11-12 19:56 CST — "'likely stale'... is NOT the
  quality of result I'm expecting. I think a 7B model could
  have told me it's stale. I want a 150B to figure out how
  to make money and plan the future."

So the Sonic one-line read built in v1 is DEMOTED: it is a
triage note, never the result. The result is a DeepSeek
REAP 150B deep pass per overdue item, dispatched over the
node bus to gamma (bus.events reap_infer — verified live
2026-11-12: gamma claims, runs, and returns the result in
successbrian_os.outbox as an inference_result naming the
event id). REAP gets the full packet — the item, its age,
its stack tier, and what the ecosystem already holds on the
topic (matched captures WITH text) — plus Brian's money
context, and must return a plan, in sections:

  VERDICT — still-live / changed / dead-close-it, with the
    evidence from the packet (never a bare label);
  MONEY — how this makes money, or an honest "no money
    path": what to sell, to whom, through which door;
  AUDIENCE — for blogs/articles: which core audience it
    builds, the capture offer, what others have written
    (from the packet's data; angles taken, gaps left) and
    the article's job: SELL or DRAW (Brian 2026-10-29);
  PLAN — first / second / third concrete steps, each with
    an owner (the system, or Brian);
  FUTURE — where this leads in 30-90 days if worked.

REAP has no web access; its job is deep reasoning and
planning over the packet + ecosystem data, and it must say
what outside research is still needed rather than invent
it. Web checking remains the filed packet's path (clerk
triage -> board/passup -> decider lane).

Flow per hourly run:
  1. COLLECT: for every row with a pending REAP event, look
     for gamma's outbox result; when it lands, store the
     full text on the row and file it as a REAP DEEP
     capture in the Intel Bridge.
  2. DISPATCH: for new overdue items from the latest
     first_next judgement (cap per run, 7-day dedupe),
     record the row, build the packet, dispatch the REAP
     event, and file the research packet capture (the
     standing questions ride along for the board path).

Ages are real: tasks by target_date; pm_steps / captures
as age past 7 days, labeled as age (no invented due dates).

CLI:
  overdue_relevance.py run [--no-file]
  overdue_relevance.py show
  overdue_relevance.py selftest
"""

import datetime as dt
import json
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
    reap_event_id bigint,
    reap_status text,
    reap_text text,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE successbrian_os.overdue_relevance
    ADD COLUMN IF NOT EXISTS reap_event_id bigint;
ALTER TABLE successbrian_os.overdue_relevance
    ADD COLUMN IF NOT EXISTS reap_status text;
ALTER TABLE successbrian_os.overdue_relevance
    ADD COLUMN IF NOT EXISTS reap_text text;
ALTER TABLE successbrian_os.overdue_relevance
    ADD COLUMN IF NOT EXISTS reap_event_id2 bigint;
ALTER TABLE successbrian_os.overdue_relevance
    ADD COLUMN IF NOT EXISTS reap_passes int DEFAULT 0;
CREATE INDEX IF NOT EXISTS overdue_relevance_item_idx
    ON successbrian_os.overdue_relevance
    (source_type, source_id, created_at);
"""

BLOG_WORDS = ["article", "blog", "substack", "post", "draft",
              "approve", "publish", "seo", "episode"]
MAX_PER_RUN = 5
# The feeder packet ceiling lives in sbos_common (B2, the shared
# packet standard) — one source of truth, enforced by
# build_reap_packet. Gamma's REAP handler kills any job past 900s.
# 1600-token passes completed 0 of 10 (events 217-220 timed out
# 2026-11-12); 500 is the PROVEN ceiling. Do not raise without
# re-measuring against the 900s runway.
REAP_MAX_TOKENS = sbos_common.REAP_MAX_TOKENS
# Deep passes are bottom-rung filler in the never-idle ladder: they ride
# BELOW the clerk lane (5) and the chat lanes (10/20/30), so an hourly batch
# can never clog the road or starve live work. (Was hardcoded 40 — above
# Brian's own ASAP ASAP tier — until 2026-11-13.)
REAP_PRIORITY = 3  # priority map: recurring upkeep waits a cycle
# (below project work at 4, below the intake pipeline at 5)
MONEY_CONTEXT = (
    "Brian's money context (his record): the big goal is "
    "sponsoring 40 people a month into GotBackup on a fixed "
    "income ladder; TrafficStreemz launches at $30/mo and "
    "ContactFlowCRM at $20/mo (hosting + finished code are "
    "the launch gates); he also needs roughly $1,000 in the "
    "next 30 days from strangers via real vendor products at "
    "about $300 per sale. His blogs exist to build owned, "
    "captured audiences — judged down one chain: visits -> "
    "contacts -> revenue. Every article has one job: SELL "
    "(convert) or DRAW (attract traffic, feed the sellers). "
    "He works a day job (Crew 2, top closer) and builds this "
    "system so it works while he is away; his own hours are "
    "the scarcest resource in every plan.")
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


def internal_data(title, with_text=False):
    """What the ecosystem already holds on this topic:
    captures matched by topic words. Captures matching at
    least two topic words are preferred — one-word matches
    proved too loose (a 'fire' match pulled an unrelated
    capture into a Fire Country packet, 2026-11-12).
    with_text adds a text excerpt — the substance REAP
    reasons over."""
    words = topic_words(title)
    scored = {}
    for w in words:
        if with_text:
            rows = sbos_common.pg_rows(
                "SELECT id, title, left(raw_text, 600) FROM "
                "atlas.scattered_captures WHERE title ILIKE %s "
                "ORDER BY id DESC LIMIT 4", ("%" + w + "%",))
            for cid, t, raw in rows:
                if cid in scored:
                    scored[cid][2] += 1
                else:
                    scored[cid] = [t, raw, 1]
        else:
            rows = sbos_common.pg_rows(
                "SELECT id, title FROM "
                "atlas.scattered_captures WHERE title ILIKE %s "
                "ORDER BY id DESC LIMIT 4", ("%" + w + "%",))
            for cid, t in rows:
                if cid in scored:
                    scored[cid][1] += 1
                else:
                    scored[cid] = [t, 1]
    if with_text:
        hits = [(cid, v[0], v[1]) for cid, v in
                sorted(scored.items(),
                       key=lambda kv: -kv[1][2])]
        strong = [h for h in hits
                  if scored[h[0]][2] >= 2]
        return (strong or hits)[:6]
    hits = [(cid, v[0]) for cid, v in
            sorted(scored.items(), key=lambda kv: -kv[1][1])]
    strong = [h for h in hits if scored[h[0]][1] >= 2]
    return (strong or hits)[:6]


def deep_prompt(item, hits):
    """The REAP 150B deep-pass prompt: plan the money and
    the future, in sections, from the packet's evidence."""
    parts = [
        "You are the DeepSeek REAP 150B deep-planning seat "
        "for Brian Lathe's SuccessBrian OS ecosystem. A small "
        "model already glanced at this overdue item and "
        "produced a one-word label; that is NOT the quality "
        "wanted. Your job is the deep work: figure out how "
        "this item makes money and plan its future.",
        "",
        MONEY_CONTEXT,
        "",
        f"THE ITEM: [{item['source']}#{item['id']}] "
        f"{item['title']}",
        f"OVERDUE: {item['days']} days ({item['basis']}). "
        f"Judgement rank {item['rank']}, priority-stack tier "
        f"{item['tier']}.",
        "",
        "WHAT THE ECOSYSTEM ALREADY HOLDS ON THIS TOPIC "
        "(capture excerpts — your evidence; work only from "
        "this and the item, and name what outside research "
        "is still needed instead of inventing facts):",
    ]
    if hits:
        for cid, t, raw in hits[:4]:
            parts.append(f"- capture #{cid}: {t}")
            fact = sbos_common.trim_fact_whole(raw, 350)
            if fact:
                parts.append("  " + fact)
    else:
        parts.append("- nothing matched — say what data "
                     "should be built first.")
    parts += [
        "",
        "Reply in exactly these sections. Be dense: 2-4 "
        "sentences per section, concrete, no filler. Your "
        "run is time-boxed — a complete short plan beats "
        "an unfinished long one:",
        "VERDICT: still-live, changed, or dead-close-it — "
        "and the evidence from the packet for that call.",
        "MONEY: how this item makes money — what is sold, "
        "to whom, through which capture door, at what kind "
        "of price — or an honest 'no money path here' with "
        "the reason.",
    ]
    if item["blog"]:
        parts.append(
            "AUDIENCE: which core audience this builds, the "
            "capture offer, what others have already written "
            "(angles taken, gaps left — from the packet data; "
            "flag what needs a live web check), and the "
            "article's job: SELL or DRAW.")
    parts += [
        "PLAN: FIRST / SECOND / THIRD — concrete steps, "
        "each with its owner (the system, or Brian).",
        "FUTURE: where this leads in 30-90 days if the plan "
        "is worked — and what it unlocks next.",
    ]
    return "\n".join(parts)


def dispatch_reap(item, hits):
    """Insert the deep-pass job on the node bus for gamma's
    REAP 150B, built through the shared feeder packet standard
    (sbos_common.build_reap_packet). Returns the bus event id."""
    packet = sbos_common.build_reap_packet(
        deep_prompt(item, hits),
        source="overdue-relevance",
        probe_id=f"overdue-relevance-{item['source']}-{item['id']}",
        item_ref=f"{item['source']}#{item['id']}",
        max_tokens=REAP_MAX_TOKENS,
        thinking=False)
    return sbos_common.dispatch_reap_packet(
        packet, source="overdue-relevance", priority=REAP_PRIORITY)


SECTION_ORDER = ["MONEY", "AUDIENCE", "PLAN", "FUTURE"]
MAX_CHAIN = 5


def missing_sections(text, blog):
    """Sections the deep pass still owes. Empirically the
    gamma REAP seat returns ONE section per run (its
    500-token runs end after the first section), so the
    full document is assembled as a chain of
    single-section passes."""
    want = ["MONEY"] + (["AUDIENCE"] if blog else []) + \
        ["PLAN", "FUTURE"]
    have = (text or "").upper()
    return [x for x in want if (x + ":") not in have]


def section_prompt(row, section):
    rid, source, sid, title, days, blog, prior = row
    parts = [
        "You are the DeepSeek REAP 150B deep-planning "
        "seat for Brian Lathe's SuccessBrian OS "
        "ecosystem. A deep pass on this overdue item "
        "produced the text below. Write ONLY the one "
        "section named - nothing else, no preamble. 3-5 "
        "dense sentences, concrete, no filler. Your run "
        "is time-boxed.",
        "",
        MONEY_CONTEXT,
        "",
        f"THE ITEM: [{source}#{sid}] {title} "
        f"({days} days overdue).",
        "TEXT SO FAR:",
        prior or "",
        "",
    ]
    if section == "MONEY":
        parts.append(
            "Write the MONEY section (start with "
            "'MONEY:'): how this item makes money - what "
            "is sold, to whom, through which capture "
            "door, at what kind of price - or an honest "
            "'no money path here' with the reason.")
    elif section == "AUDIENCE":
        parts.append(
            "Write the AUDIENCE section (start with "
            "'AUDIENCE:'): which core audience this "
            "builds, the capture offer, and the "
            "article's job: SELL or DRAW. What others "
            "have written needs a live web check - name "
            "the searches to run rather than inventing "
            "coverage.")
    elif section == "PLAN":
        parts.append(
            "Write the PLAN section (start with "
            "'PLAN:'): FIRST / SECOND / THIRD - concrete "
            "steps, each with its owner (the system, or "
            "Brian).")
    else:
        parts.append(
            "Write the FUTURE section (start with "
            "'FUTURE:'): where this leads in 30-90 days "
            "if the plan is worked - and what it unlocks "
            "next.")
    return "\n".join(parts)


def dispatch_section(row, section, hits, chain_index=1):
    packet = sbos_common.build_reap_packet(
        section_prompt(row, section),
        source="overdue-relevance",
        probe_id=f"overdue-sec-{section.lower()}-"
                 f"{row[1]}-{row[2]}",
        section=section,
        chain_index=chain_index,
        item_ref=f"{row[1]}#{row[2]}",
        max_tokens=REAP_MAX_TOKENS,
        thinking=False)
    return sbos_common.dispatch_reap_packet(
        packet, source="overdue-relevance", priority=REAP_PRIORITY)


def file_capture(title, raw, context):
    """One Intel Bridge capture, deduped by exact title
    within 7 days. Returns the capture id or None."""
    import base64 as b64
    import subprocess

    def b64sql(s):
        return ("convert_from(decode('%s','base64'),'UTF8')"
                % b64.b64encode(s.encode()).decode())

    exists = sbos_common.pg_one(
        "SELECT count(*) FROM atlas.scattered_captures "
        "WHERE title = %s AND created_at > now() - interval "
        "'7 days'", (title,))
    if exists:
        return None
    sql = ("insert into atlas.scattered_captures "
           "(title, raw_text, context, status) values "
           f"({b64sql(title)}, {b64sql(raw)}, "
           f"{b64sql(context)}, 'raw') returning id")
    p = subprocess.run(["psql", "-d", "ecosystem_central",
                        "-t", "-A", "-c", sql],
                       capture_output=True, text=True, timeout=60)
    out = (p.stdout or "").strip().splitlines()
    return out[0] if out else ""


def parse_reap_body(body):
    """Gamma's outbox body is a JSON envelope; the REAP
    text lives at result.text. Tolerates a pre-parsed
    dict. Returns None on anything unparseable."""
    if not body:
        return None
    try:
        data = body if isinstance(body, dict) else \
            json.loads(body)
        text = (data.get("result") or {}).get("text")
        return text.strip() if text else None
    except Exception:
        return None


def collect_sections():
    """Land a finished section pass: append it; the row
    re-opens for its next missing section until the
    document is complete ('done-full')."""
    rows = sbos_common.pg_rows(
        "SELECT id, reap_event_id2, title, reap_text, "
        "is_blog FROM successbrian_os.overdue_relevance "
        "WHERE reap_status = 'chaining' AND "
        "reap_event_id2 IS NOT NULL")
    landed = 0
    for rid, eid, title, text, blog in rows:
        estatus = sbos_common.pg_one(
            "SELECT status FROM bus.events WHERE id = %s",
            (eid,))
        if estatus in ("failed", "dead_letter"):
            sbos_common.pg_exec(
                "UPDATE successbrian_os.overdue_relevance "
                "SET reap_status = 'chain-open', "
                "reap_event_id2 = NULL WHERE id = %s",
                (rid,))
            continue
        body = sbos_common.pg_one(
            "SELECT body FROM successbrian_os.outbox "
            "WHERE source_agent = 'gamma' AND "
            "message_type = 'inference_result' AND "
            "subject = %s",
            (f"gamma: event {eid} done (reap_infer)",))
        if not body:
            continue
        sec = parse_reap_body(body)
        if not sec:
            continue
        full = (text or "") + "\n\n" + sec
        done = not missing_sections(full, blog)
        sbos_common.pg_exec(
            "UPDATE successbrian_os.overdue_relevance "
            "SET reap_status = %s, reap_text = %s, "
            "reap_event_id2 = NULL WHERE id = %s",
            ("done-full" if done else "chain-open",
             full, rid))
        landed += 1
        print(f"REAP section landed for event #{eid} "
              f"({title})"
              + (" - document complete" if done else
                 " - chain continues"))
        if done:
            file_capture(
                "REAP DEEP (overdue, full): "
                + (title or "")[:84], full,
                "Complete REAP 150B deep pass on an "
                "overdue item: verdict + money + plan + "
                "future (Brian's ruling 2026-11-12 "
                "19:56 CST).")
    return landed


def dispatch_sections(limit=MAX_PER_RUN):
    """Rows with an incomplete document and chain budget
    left get their next single-section pass."""
    rows = sbos_common.pg_rows(
        "SELECT id, source_type, source_id, title, "
        "days_overdue, is_blog, reap_text, reap_passes "
        "FROM successbrian_os.overdue_relevance WHERE "
        "reap_status IN ('done', 'chain-open', "
        "'done-full') AND "
        "reap_event_id2 IS NULL AND reap_passes < %s "
        "ORDER BY id LIMIT %s", (MAX_CHAIN, limit))
    n = 0
    for row in rows:
        rid, source, sid, title, days, blog, text, \
            passes = row
        miss = missing_sections(text, blog)
        if not miss:
            sbos_common.pg_exec(
                "UPDATE successbrian_os.overdue_relevance "
                "SET reap_status = 'done-full' WHERE "
                "id = %s", (rid,))
            continue
        hits = internal_data(title, with_text=True)
        eid = dispatch_section(row[:7], miss[0], hits,
                               chain_index=(passes or 0) + 1)
        sbos_common.pg_exec(
            "UPDATE successbrian_os.overdue_relevance "
            "SET reap_event_id2 = %s, reap_status = "
            "'chaining', reap_passes = %s WHERE id = %s",
            (eid, (passes or 0) + 1, rid))
        n += 1
        print(f"dispatched REAP {miss[0]} section "
              f"[{source}#{sid}] - bus event #{eid}")
    return n


def collect_reap():
    """Land any finished REAP deep passes: store the text,
    file it as a REAP DEEP capture. Returns count landed."""
    rows = sbos_common.pg_rows(
        "SELECT id, reap_event_id, title FROM "
        "successbrian_os.overdue_relevance WHERE "
        "reap_status = 'pending' AND reap_event_id IS NOT "
        "NULL")
    landed = 0
    for rid, eid, title in rows:
        estatus = sbos_common.pg_one(
            "SELECT status FROM bus.events WHERE id = %s",
            (eid,))
        if estatus in ("failed", "dead_letter"):
            sbos_common.pg_exec(
                "UPDATE successbrian_os.overdue_relevance "
                "SET reap_status = 'failed' WHERE id = %s",
                (rid,))
            print(f"REAP event #{eid} failed on gamma "
                  f"({title}) — item will re-dispatch in "
                  f"the smaller format next run")
            continue
        body = sbos_common.pg_one(
            "SELECT body FROM successbrian_os.outbox WHERE "
            "source_agent = 'gamma' AND message_type = "
            "'inference_result' AND subject = %s",
            (f"gamma: event {eid} done (reap_infer)",))
        if not body:
            continue
        text = parse_reap_body(body)
        if not text:
            sbos_common.pg_exec(
                "UPDATE successbrian_os.overdue_relevance "
                "SET reap_status = 'unparseable' WHERE id = %s",
                (rid,))
            continue
        sbos_common.pg_exec(
            "UPDATE successbrian_os.overdue_relevance SET "
            "reap_status = 'done', reap_text = %s WHERE "
            "id = %s", (text, rid))
        cid = file_capture(
            "REAP DEEP (overdue): " + (title or "")[:90],
            text,
            "DeepSeek REAP 150B deep pass on an overdue "
            "item (Brian's ruling 2026-11-12 19:56 CST: the "
            "150B figures out how to make money and plan "
            "the future — a one-word stale label is not the "
            "quality wanted). Full text also on "
            "successbrian_os.overdue_relevance.")
        landed += 1
        print(f"REAP result landed for event #{eid} "
              f"({title})"
              + (f" — filed as capture #{cid}" if cid else ""))
    return landed


def run(do_file=True):
    sbos_common.pg_exec(RELEVANCE_DDL)
    landed = collect_reap()
    if landed:
        print(f"collected {landed} REAP deep pass(es)")
    pl = collect_sections()
    if pl:
        print(f"collected {pl} REAP section pass(es)")
    dispatch_sections()
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
            "created_at > now() - interval '7 days' AND "
            "reap_event_id IS NOT NULL AND reap_status IN "
            "('pending', 'done', 'plan-pending', "
            "'done-full', 'chaining', 'chain-open')",
            (item["source"], item["id"]))
        if recent:
            continue
        hits = internal_data(item["title"], with_text=True)
        eid = dispatch_reap(item, hits)
        cid = None
        if do_file:
            parts = [
                f"OVERDUE RELEVANCE RESEARCH — {item['days']} "
                f"days overdue ({item['basis']}), judgement "
                f"rank {item['rank']}, stack tier "
                f"{item['tier']}.",
                f"Item: [{item['source']}#{item['id']}] "
                f"{item['title']}",
                f"REAP 150B deep pass dispatched as bus "
                f"event #{eid} (money + future planning, "
                f"Brian's ruling 2026-11-12 19:56 CST). Its "
                f"result is collected by this module into "
                f"successbrian_os.overdue_relevance and "
                f"filed as a REAP DEEP capture when gamma "
                f"returns it.",
                "",
                "RESEARCH QUESTIONS (the board path):",
            ]
            parts += [f"- {q}" for q in RESEARCH_QUESTIONS]
            if item["blog"]:
                parts.append("BLOG/ARTICLE — additionally:")
                parts += [f"- {q}" for q in BLOG_QUESTIONS]
            parts.append("")
            parts.append("WHAT THE ECOSYSTEM ALREADY HOLDS:")
            if hits:
                parts += [f"- #{c} {t}" for c, t, _r in hits]
            else:
                parts.append("- nothing matched — building "
                             "this data is part of the "
                             "research.")
            cid = file_capture(
                f"RESEARCH (overdue {item['days']}d): "
                + (item["title"] or "")[:90],
                "\n".join(parts),
                "Filed by overdue_relevance (Brian's "
                "rulings 2026-11-12: overdue items get "
                "re-researched for current relevance; the "
                "deep quality bar is the REAP 150B money/"
                "future pass, not a one-word label).")
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.overdue_relevance "
            "(source_type, source_id, title, days_overdue, "
            "judgement_rank, is_blog, sonic_read, "
            "internal_hits, capture_id, reap_event_id, "
            "reap_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,"
            "%s,%s,'pending')",
            (item["source"], item["id"], item["title"],
             item["days"], item["rank"], item["blog"],
             "superseded — REAP deep pass is the result "
             "(Brian 2026-11-12)", len(hits),
             int(cid) if cid and str(cid).isdigit() else None,
             eid))
        made += 1
        print(f"dispatched REAP deep pass [{item['source']}"
              f"#{item['id']}] {item['days']}d overdue"
              f"{' (blog)' if item['blog'] else ''} — "
              f"bus event #{eid}"
              + (f", packet capture #{cid}" if cid else ""))
    if not made:
        print("nothing new to dispatch (all overdue items "
              "researched within 7 days)")
    return 0


def show():
    rows = sbos_common.pg_rows(
        "SELECT created_at, source_type, source_id, title, "
        "days_overdue, is_blog, reap_status, reap_event_id, "
        "left(reap_text, 400) FROM "
        "successbrian_os.overdue_relevance ORDER BY id "
        "DESC LIMIT 10")
    if not rows:
        print("no relevance research yet — run: "
              "overdue_relevance.py run")
        return
    for r in rows:
        print(f"{r[0]:%Y-%m-%d %H:%M} [{r[1]}#{r[2]}] {r[3]}")
        print(f"   {r[4]}d overdue{' blog' if r[5] else ''} "
              f"— REAP: {r[6] or 'none'} (event #{r[7]})")
        if r[8]:
            print("   " + " ".join(r[8].split())[:380])


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    check("substack draft is a blog item",
          is_blog("task", "Substack: DRAFT the crossover "
                          "article"))
    check("crew blast task is not a blog item",
          not is_blog("task", "Drive Sat Sep 26 Crew2 12hr "
                              "blast"))
    fake = {"source": "task", "id": 1, "title": "Substack: "
            "DRAFT the crossover article", "days": 4,
            "basis": "target_date", "rank": 3, "tier": 1,
            "blog": True}
    prompt = deep_prompt(fake, [(9, "held capture",
                                 "some held text")])
    check("deep prompt demands a MONEY section",
          "MONEY:" in prompt)
    check("deep prompt demands a PLAN with FIRST/SECOND/"
          "THIRD", "FIRST / SECOND / THIRD" in prompt)
    check("deep prompt demands a FUTURE section",
          "FUTURE:" in prompt)
    check("blog deep prompt demands an AUDIENCE section",
          "AUDIENCE:" in prompt)
    check("deep prompt carries the money context",
          "GotBackup" in prompt and "visits -> contacts "
          "-> revenue" in prompt)
    check("deep prompt forbids inventing facts",
          "instead of inventing" in prompt)
    check("reap token budget is the shared packet standard",
          REAP_MAX_TOKENS == sbos_common.REAP_MAX_TOKENS)
    long_fact = deep_prompt(
        fake, [(9, "held capture",
                "Short fact here. " + "word " * 100)])
    check("deep prompt trims facts whole, never mid-sentence",
          "Short fact here." in long_fact
          and "word word word" not in long_fact)
    body = json.dumps({"result": {"text": "VERDICT: "
                                            "still-live"}})
    check("outbox body parses to result text",
          parse_reap_body(body) == "VERDICT: still-live")
    check("bad outbox body parses to None",
          parse_reap_body("not json") is None)
    check("relevance ddl carries the reap columns",
          "reap_event_id" in RELEVANCE_DDL
          and "reap_text" in RELEVANCE_DDL)
    check("per-run cap is bounded", 0 < MAX_PER_RUN <= 10)
    check("reap token budget fits the 900s runway",
          REAP_MAX_TOKENS <= 500)
    check("reap jobs ride below the clerk lane",
          REAP_PRIORITY < 5)
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
