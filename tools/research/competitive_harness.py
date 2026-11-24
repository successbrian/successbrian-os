#!/usr/bin/env python3
"""competitive_harness.py - the COMPETITIVE RESEARCH HARNESS
(Brian's order, 2026-11-23 18:51 CST: "we need a 'competitive
research' harness -- and the things we learned today need to be
part of that research -- which can lead to tasks, blog articles
and anything relevant").

PURPOSE: a standing loop that turns competitive questions into
evidence and routes the findings into work:

  QUESTION (registered with its origin and what it feeds)
    -> EVIDENCE DIG: a deterministic fetch leg pulls primary
       sources (the rival's own pages, measured data - never
       landing-page claims taken on faith), then ONE Einstein
       (DeepSeek V4 Flash REAP 150B) deep pass over the evidence
       on the gamma bus synthesizes findings. Fleet inference
       does the thinking per Brian's cost rule - mechanical
       fetching and watching are fleet work, never chat credits.
    -> STUDY FILED in the ecosystem's sanctioned homes:
       AnythingLLM successbrian-os workspace doc +
       altair.second_brain entry + Intel Bridge capture
       (Brian's rule: research writes to the second brain and
       AnythingLLM, not chat dumps).
    -> FINDINGS ROUTED to outputs, each linked back to its
       study: proposed TASKS (pm_steps), proposed BLOG ARTICLES
       (campaignsdesk.article_ideas at the planning stage -
       proposals only; CampaignsDesk planning gates still apply
       and nothing publishes from here), DECISIONS for Brian
       (review_decisions - residue only), DESIGN INPUTS to an
       active build (Intel Bridge captures addressed to it).

WHY: on 2026-11-23 this pattern ran three times by hand and paid
every time - the goal-tests study (Brian's four tests vs the
strategy literature), the Paperclip decomposition study (its
steal list went straight into the goal-harness build), and the
Paperclip field scan. Done by hand, the pattern dies with the
chat. As a machine it compounds: every blog's planning already
owes a competitor scan + readership analysis (Brian, 2026-11-13;
blog_fleet standard items) - this harness is the engine those
scans can call, not a replacement for the blog planning package.

BUS DISCIPLINE: digs dispatch through sbos_common's REAP lane at
priority 4 - the bus map's project-work tier (chat 30/20/10 and
the intake pipeline at 5 are never starved by research). One dig
per cycle. The REAP return leg keeps only the first text block,
so the prompt demands ONE unbroken block with inline section
headers and the parser splits on the headers wherever they land
(the einstein_planner lesson, events 1722/1728).

CALLED BY: user crontab every 2h at :20 (flock) - collect landed
digs, route their outputs, dispatch the next queued question.
Registry: program_registry competitive-research-harness-py;
QA sbos-program-registry/competitive-research-proof-fresh +
competitive-research-outcomes-moving (outcomes, not activity -
the distiller lesson).

AUTHORITY: research outputs are PROPOSALS until they pass their
own gates. This module never publishes, sends, buys, or rules;
decisions it surfaces wait for Brian like all decisions.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "pm"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "atlas"))

import sbos_common  # noqa: E402
import pm_core      # noqa: E402
import allm_embed   # noqa: E402

SOURCE = "competitive-research-harness"
REAP_PRIORITY = 4            # bus map: project work tier
MAX_TOKENS = 500             # sbos_common.REAP_MAX_TOKENS ceiling
PAGE_TEXT_CAP = 9000         # chars of extracted text per page
EVIDENCE_CAP = 30000         # total evidence chars in the packet
ALLM_WORKSPACE = "successbrian-os"
CAPTURE_CLI = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "atlas", "scattered_brain.py")

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.research_questions (
    id            serial PRIMARY KEY,
    question      text NOT NULL,
    subject       text NOT NULL UNIQUE,
    origin        text,
    feeds         text,
    article_ref   text,
    fetch_urls    jsonb NOT NULL DEFAULT '[]'::jsonb,
    status        text NOT NULL DEFAULT 'queued',
    priority      int  NOT NULL DEFAULT 50,
    bus_event_id  bigint,
    probe_id      text,
    evidence      jsonb,
    study_text    text,
    allm_pointer  text,
    second_brain_id bigint,
    capture_id    bigint,
    created_at    timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,
    collected_at  timestamptz,
    routed_at     timestamptz
);
CREATE TABLE IF NOT EXISTS successbrian_os.research_routes (
    id          serial PRIMARY KEY,
    question_id int NOT NULL
        REFERENCES successbrian_os.research_questions(id),
    route_kind  text NOT NULL,
    ref         text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (question_id, route_kind, ref)
);
CREATE INDEX IF NOT EXISTS research_questions_status_idx
    ON successbrian_os.research_questions (status, priority DESC, id);
"""


def init_db():
    sbos_common.pg_exec(DDL)
    print("competitive harness tables ready")


def register(question, subject, origin, feeds, article_ref=None,
             fetch_urls=(), priority=50, status="queued"):
    row = sbos_common.pg_one(
        "INSERT INTO successbrian_os.research_questions "
        "(question, subject, origin, feeds, article_ref, fetch_urls, "
        "priority, status) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s) "
        "ON CONFLICT (subject) DO NOTHING RETURNING id",
        (question, subject, origin, feeds, article_ref,
         json.dumps(list(fetch_urls)), priority, status))
    if row is None:
        row = sbos_common.pg_one(
            "SELECT id FROM successbrian_os.research_questions "
            "WHERE subject=%s", (subject,))
        print(f"question already registered: #{row} ({subject})")
        return row, False
    print(f"question #{row} registered ({subject})")
    return row, True


# ------------------------------------------------------------ seeds
# Today's three hand-run studies become the harness's first
# registered questions - LINKED, not copied (Brian: document in
# the right places, not a dump). Their routed outputs are recorded
# as routes so the pattern's track record is part of the machine.

SEEDS = [
    dict(
        subject="goal-tests-2026-11-23",
        question="Are Brian's four goal tests (ecosystem fit; "
                 "better than current; easy/hard to add; more "
                 "lucrative - under his bandwidth constraint) the "
                 "best available tests for judging a goal?",
        origin="brian-chat 2026-11-23 (Brian: 'are these the very "
               "best tests? maybe someone already laid out better "
               "goal strategies than this')",
        feeds="goal harness WORTH grading in Einstein's plan "
              "contract",
        status="routed",
        allm_pointer="successbrian-os/goal-tests-study-2026-11-23.md "
                     "(AnythingLLM doc 88955)",
        second_brain_id=103682, capture_id=3115,
        routes=[("design_input",
                 "goal-harness WORTH section (commit bea827e)",
                 {"note": "Brian's four tests adopted into the "
                          "Einstein plan contract the same day; "
                          "the study's refined 7-test set + form "
                          "gate filed as PROPOSAL, awaiting Brian"})],
    ),
    dict(
        subject="paperclip-decomposition-2026-11-23",
        question="How effectively does Paperclip break goals down "
                 "into tasks?",
        origin="brian-chat 2026-11-23 (Brian: 'how effectively "
               "does paperclip break goals down into tasks...')",
        feeds="goal harness build - prior-art for the aiming "
              "layer",
        status="routed",
        allm_pointer="successbrian-os/"
                     "paperclip-decomposition-study-2026-11-23.md",
        second_brain_id=103683, capture_id=3121,
        routes=[("design_input",
                 "goal-harness steal list (commit a7b0096)",
                 {"note": "accepted-plan decomposition bookkeeping, "
                          "blocker edges with wakes, disposition "
                          "guard, heartbeat-context packet, "
                          "restraint doctrine, exact-title dedup "
                          "floor - folded into the goal harness"})],
    ),
    dict(
        subject="paperclip-field-scan-2026-11-23",
        question="Is anyone doing goal-to-task breakdown better "
                 "than Paperclip? Are people complaining about it, "
                 "quitting it, or is it still gaining popularity?",
        origin="brian-chat 2026-11-23 (Brian: 'is anyone out "
               "there doing a better job at this? ... are they "
               "quitting it? or is it still gaining popularity?')",
        feeds="goal harness prior-art; adopt/avoid judgment on "
              "Paperclip patterns",
        status="external_in_flight",
        allm_pointer=None, second_brain_id=None, capture_id=None,
        routes=[],
    ),
]


def seed():
    init_db()
    for s in SEEDS:
        qid, created = register(
            s["question"], s["subject"], s["origin"], s["feeds"],
            status=s["status"])
        sbos_common.pg_exec(
            "UPDATE successbrian_os.research_questions SET "
            "allm_pointer=%s, second_brain_id=%s, capture_id=%s, "
            "collected_at=COALESCE(collected_at, now()), "
            "routed_at=CASE WHEN status='routed' THEN "
            "COALESCE(routed_at, now()) ELSE routed_at END "
            "WHERE id=%s",
            (s["allm_pointer"], s["second_brain_id"],
             s["capture_id"], qid))
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            for kind, ref, detail in s["routes"]:
                cur.execute(
                    "INSERT INTO successbrian_os.research_routes "
                    "(question_id, route_kind, ref, detail) "
                    "VALUES (%s,%s,%s,%s::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    (qid, kind, ref, json.dumps(detail)))
            conn.commit()
        finally:
            conn.close()
        print(f"seeded {s['subject']}: status={s['status']}, "
              f"{len(s['routes'])} route(s)")


# ------------------------------------------------------------ fetch leg
# Deterministic evidence: the rival's own pages and measured data.
# A failed fetch is recorded as failed - never smoothed over.

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def _html_to_text(html):
    html = _TAG_RE.sub(" ", html)
    html = _ANY_TAG_RE.sub(" ", html)
    html = (html.replace("&amp;", "&").replace("&nbsp;", " ")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", html).strip()


def _fetch_one(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux "
                      "x86_64) SuccessBrianOSResearch/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read(600_000)
        final = resp.geturl()
        status = resp.status
    return status, final, _html_to_text(raw.decode("utf-8", "ignore"))


def fetch_evidence_rich(urls):
    """Fetch each URL; from the first page, also follow up to 2
    same-domain links whose href names pricing/services (bounded
    crawl). Returns (evidence_text, evidence_meta). A dead source
    degrades the dig, never kills it."""
    meta, chunks, total = [], [], 0
    extra = []
    for i, url in enumerate(urls):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (X11; "
                              "Linux x86_64) SuccessBrianOSResearch/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read(600_000).decode("utf-8", "ignore")
                final, status = resp.geturl(), resp.status
            text = _html_to_text(raw)
            meta.append({"url": url, "final_url": final,
                         "status": status, "chars": len(text)})
            take = text[:PAGE_TEXT_CAP]
            chunks.append(f"[SOURCE {final} fetched "
                          f"{datetime.now(timezone.utc):%Y-%m-%d} "
                          f"status {status}]\n{take}")
            total += len(take)
            if i == 0:
                base = re.match(r"(https?://[^/]+)", final)
                for href in _HREF_RE.findall(raw):
                    low = href.lower()
                    if ("pricing" in low or "services" in low) \
                            and len(extra) < 2:
                        if href.startswith("/") and base:
                            href = base.group(1) + href
                        if href.startswith("http") and href != final:
                            extra.append(href)
        except Exception as exc:
            meta.append({"url": url, "error":
                         f"{type(exc).__name__}: {exc}"[:200]})
    for url in extra:
        if total >= EVIDENCE_CAP:
            break
        try:
            status, final, text = _fetch_one(url)
            meta.append({"url": url, "final_url": final,
                         "status": status, "chars": len(text),
                         "via": "crawl"})
            take = text[:PAGE_TEXT_CAP]
            chunks.append(f"[SOURCE {final} fetched "
                          f"{datetime.now(timezone.utc):%Y-%m-%d} "
                          f"status {status}]\n{take}")
            total += len(take)
        except Exception as exc:
            meta.append({"url": url, "error":
                         f"{type(exc).__name__}: {exc}"[:200],
                         "via": "crawl"})
    return "\n\n".join(chunks), meta


# ------------------------------------------------------------ dig

PROMPT_TEMPLATE = """You are Einstein, the deep-research engine in a solo operator's competitive research system. Below this contract you will find one competitive QUESTION, what it feeds, and the EVIDENCE - primary sources fetched today from the subject's own pages and measured data. Judge ONLY from this evidence. A source that failed to load could not be read - report it as unread, never guess about it. Where the evidence is silent, say UNKNOWN - never invent a price, a feature, or a fact.

Write a competitive assessment with EXACTLY these three sections, in this order, plain text, no preamble, no closing remarks. CRITICAL FORMAT RULE: write the ENTIRE assessment as one single unbroken block of text - NO blank lines anywhere, NO paragraph breaks, NO markdown, NO title. The channel that carries your answer back keeps only the first block, so a blank line ends your answer and the rest is lost. Start immediately with "FINDINGS:" and run each section's header inline, like this: FINDINGS: <text> CANNOT VERIFY: <text> OUTPUTS: <lines>

FINDINGS: What the evidence proves, in plain words, every number tied to its source. At most 130 words.
CANNOT VERIFY: What the evidence could not settle. At most 40 words.
OUTPUTS: The work this study should create, at most 5 outputs, one per line, each in the form KIND| short title | why it matters - KIND is one of TASK (a doable work step), RESEARCH (a follow-up question worth a dig), ARTICLE (a blog article proposal), DECISION (a choice only Brian can make), DESIGN (an input for an active build - name the build in the title). Propose only outputs the findings actually support; omit a kind entirely rather than inventing one. If the evidence is thin, say so in FINDINGS and propose a RESEARCH output to thicken it.

QUESTION: {question}
THIS QUESTION FEEDS: {feeds}
EVIDENCE (fetched {today}):
{evidence}"""


def build_prompt(qrow, evidence_text):
    return PROMPT_TEMPLATE.format(
        question=qrow[1], feeds=qrow[4] or "ecosystem work",
        today=f"{datetime.now(timezone.utc):%Y-%m-%d}",
        evidence=evidence_text or "(no source could be fetched)")


def dispatch(qid=None):
    if qid:
        row = sbos_common.pg_one(
            "SELECT id, question, subject, origin, feeds, "
            "fetch_urls, priority FROM successbrian_os."
            "research_questions WHERE id=%s AND status='queued'",
            (qid,))
    else:
        row = sbos_common.pg_one(
            "SELECT id, question, subject, origin, feeds, "
            "fetch_urls, priority FROM successbrian_os."
            "research_questions WHERE status='queued' "
            "ORDER BY priority DESC, id LIMIT 1")
    if not row:
        print("dispatch: no queued question")
        return None
    qid = row[0]
    urls = row[5] or []
    evidence_text, meta = fetch_evidence_rich(urls) if urls else ("", [])
    fetched_ok = [m for m in meta if "status" in m]
    if urls and not fetched_ok:
        sbos_common.pg_exec(
            "UPDATE successbrian_os.research_questions SET "
            "evidence=%s::jsonb WHERE id=%s",
            (json.dumps({"fetches": meta, "failed_attempts": 0}),
             qid))
        print(f"dispatch: question #{qid} - every source failed; "
              f"left queued for a later cycle")
        return None
    probe_id = f"crh-q{qid}"
    packet = sbos_common.build_reap_packet(
        build_prompt(row, evidence_text), source=SOURCE,
        probe_id=probe_id, max_tokens=MAX_TOKENS, thinking=False)
    event_id = sbos_common.dispatch_reap_packet(
        packet, source=SOURCE, priority=REAP_PRIORITY)
    prior = sbos_common.pg_one(
        "SELECT evidence FROM successbrian_os.research_questions "
        "WHERE id=%s", (qid,))
    attempts = 0
    if isinstance(prior, dict):
        attempts = int(prior.get("failed_attempts") or 0)
    elif isinstance(prior, list):
        attempts = 0
    sbos_common.pg_exec(
        "UPDATE successbrian_os.research_questions SET "
        "status='dispatched', bus_event_id=%s, probe_id=%s, "
        "evidence=%s::jsonb, dispatched_at=now() WHERE id=%s",
        (event_id, probe_id,
         json.dumps({"fetches": meta, "failed_attempts": attempts}),
         qid))
    print(f"dispatch: question #{qid} ({row[2]}) -> bus event "
          f"{event_id} at priority {REAP_PRIORITY}; "
          f"{len(fetched_ok)}/{len(urls)} sources fetched")
    return event_id


# ------------------------------------------------------------ collect

_HEADERS = ("FINDINGS:", "CANNOT VERIFY:", "OUTPUTS:")
_KIND_RE = re.compile(
    r"(TASK|RESEARCH|ARTICLE|DECISION|DESIGN)\s*\|")


def _result_for_event(event_id):
    row = sbos_common.pg_one(
        "SELECT body FROM successbrian_os.outbox "
        "WHERE message_type = 'inference_result' AND subject = %s "
        "ORDER BY id DESC LIMIT 1",
        (f"gamma: event {event_id} done (reap_infer)",))
    if not row:
        return None
    try:
        env = json.loads(row)
    except (ValueError, TypeError):
        return {"ok": False, "result": {"text": str(row)}}
    return env


def parse_study(text):
    """Split the one-block REAP reply on its inline headers."""
    idx = {}
    for h in _HEADERS:
        i = text.find(h)
        if i >= 0:
            idx[h] = i
    def section(name, nxt):
        if name not in idx:
            return ""
        end = idx[nxt] if nxt in idx else len(text)
        return text[idx[name] + len(name):end].strip()
    outputs = []
    raw = section("OUTPUTS:", "\x00")
    matches = list(_KIND_RE.finditer(raw))
    for i, m in enumerate(matches):
        seg_end = matches[i + 1].start() if i + 1 < len(matches) \
            else len(raw)
        seg = raw[m.start():seg_end].strip().strip("|").strip()
        parts = [p.strip() for p in seg.split("|")]
        if len(parts) >= 3 and parts[1]:
            outputs.append({"kind": parts[0],
                            "title": parts[1],
                            "why": "|".join(parts[2:]).strip()})
    return {"findings": section("FINDINGS:", "CANNOT VERIFY:"),
            "cannot_verify": section("CANNOT VERIFY:", "OUTPUTS:"),
            "outputs": outputs}


def _file_capture(title, context, raw=None):
    parts = ["python3", CAPTURE_CLI, "capture", title,
             "--context", context]
    if raw:
        parts += ["--raw", raw]
    out = subprocess.run(parts, capture_output=True, text=True,
                         timeout=120)
    m = re.search(r"captured #(\d+)", out.stdout or "")
    if not m:
        raise RuntimeError(f"capture failed: {out.stdout} "
                           f"{out.stderr}")
    return int(m.group(1))


def _route_outputs(cur, qrow, parsed, capture_id):
    qid, subject = qrow[0], qrow[2]
    filed = []
    for n, o in enumerate(parsed["outputs"], 1):
        kind, title, why = o["kind"], o["title"][:300], o["why"]
        payload = {"question_id": qid, "subject": subject,
                   "study_capture_id": capture_id, "why": why}
        if kind in ("TASK", "RESEARCH"):
            step_kind = "research" if kind == "RESEARCH" else "task"
            key = f"crh-q{qid}-{step_kind}-{n}"
            step_id, created = pm_core.add_step(
                cur, key, title, kind=step_kind,
                source=f"competitive-research:q{qid}",
                origin="ecosystem", priority=qrow[6] or 50,
                payload=payload)
            ref = key
            detail = {"step_id": step_id, "created": created,
                      "title": title}
            rkind = "task" if kind == "TASK" else "research_task"
        elif kind == "ARTICLE":
            row = cur.execute(
                "INSERT INTO campaignsdesk.article_ideas "
                "(raw_idea, serves_kind, serves_ref, stage, origin, "
                "angle, evidence, reasoning) VALUES "
                "(%s,'blog',%s,'idea',%s,%s,%s,%s) RETURNING id",
                (title, qrow[5] or "ai-services", SOURCE, why,
                 json.dumps({"study": f"question #{qid} "
                             f"({subject})",
                             "capture_id": capture_id,
                             "source": SOURCE}), why))
            ref = str(cur.fetchone()[0])
            detail = {"title": title, "serves_ref": qrow[5]}
            rkind = "article"
        elif kind == "DECISION":
            row = cur.execute(
                "INSERT INTO successbrian_os.review_decisions "
                "(item, context, numbers, source_capture_id) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (title, f"{why} (competitive study: question "
                 f"#{qid} {subject}, capture #{capture_id})",
                 None, capture_id))
            ref = str(cur.fetchone()[0])
            detail = {"title": title}
            rkind = "decision"
        elif kind == "DESIGN":
            cid = _file_capture(
                f"DESIGN INPUT from competitive study q{qid}: "
                f"{title}",
                f"{why} Source study: question #{qid} "
                f"({subject}), Intel Bridge capture "
                f"#{capture_id}. Proposal from the competitive "
                f"research harness - the owning build judges it.")
            ref = str(cid)
            detail = {"title": title}
            rkind = "design_input"
        else:
            continue
        cur.execute(
            "INSERT INTO successbrian_os.research_routes "
            "(question_id, route_kind, ref, detail) VALUES "
            "(%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING",
            (qid, rkind, ref, json.dumps(detail)))
        filed.append((rkind, ref))
    return filed


def collect():
    rows = sbos_common.pg_rows(
        "SELECT id, question, subject, origin, feeds, "
        "article_ref, priority, bus_event_id, evidence FROM "
        "successbrian_os.research_questions "
        "WHERE status='dispatched' ORDER BY id") or []
    done = 0
    for qrow in rows:
        env = _result_for_event(qrow[7])
        if not env:
            continue
        text = ((env.get("result") or {}).get("text") or "").strip()
        if not text:
            print(f"collect: question #{qrow[0]} result empty; "
                  f"left dispatched")
            continue
        parsed = parse_study(text)
        date = f"{datetime.now(timezone.utc):%Y-%m-%d}"
        filename = f"competitive-study-{qrow[2]}.md"
        ev_raw = qrow[8] or []
        if isinstance(ev_raw, dict):
            ev_meta = ev_raw.get("fetches") or []
            ev_attempts = int(ev_raw.get("failed_attempts") or 0)
        else:
            ev_meta, ev_attempts = ev_raw, 0
        if not parsed["findings"]:
            # The return leg delivered an unparseable first block
            # (a title/preamble block eats the whole study). One
            # automatic retry under the strict contract; a second
            # failure files as an honestly-marked FAILED DIG with
            # a repair task - never a hollow study.
            attempts = ev_attempts + 1
            if attempts < 2:
                sbos_common.pg_exec(
                    "UPDATE successbrian_os.research_questions "
                    "SET status='queued', bus_event_id=NULL, "
                    "evidence=%s::jsonb WHERE id=%s",
                    (json.dumps({"fetches": ev_meta,
                                 "failed_attempts": attempts}),
                     qrow[0]))
                print(f"collect: question #{qrow[0]} dig came "
                      f"back unparseable (attempt {attempts}); "
                      f"re-queued for one strict-contract retry")
                continue
            parsed = {
                "findings": "FAILED DIG (2 attempts): the REAP "
                    "return leg delivered an unparseable first "
                    "block both times, so no usable synthesis "
                    "landed. Raw returned text: " + text[:300],
                "cannot_verify": "everything - no synthesis "
                    "landed",
                "outputs": [{
                    "kind": "RESEARCH",
                    "title": "Repair the competitive dig output "
                             "contract",
                    "why": "Two consecutive digs returned "
                           "unparseable first blocks; the harness "
                           "cannot route findings it cannot "
                           "parse."}]}
        ev_lines = "\n".join(
            f"- {m.get('url')} -> {m.get('final_url', 'FAILED')} "
            f"({m.get('status', m.get('error', '?'))})"
            for m in ev_meta)
        study_doc = (
            f"# Competitive study: {qrow[2]}\n\n"
            f"Question: {qrow[1]}\n\nFeeds: {qrow[4]}\n\n"
            f"Origin: {qrow[3]}\n\nDig: competitive research "
            f"harness, Einstein REAP pass over primary-source "
            f"fetches, {date}. Bus event {qrow[7]}.\n\n"
            f"## Findings\n\n{parsed['findings']}\n\n"
            f"## Cannot verify\n\n{parsed['cannot_verify']}\n\n"
            f"## Evidence sources\n\n{ev_lines}\n")
        allm_pointer = allm_embed.embed_latest(
            ALLM_WORKSPACE, filename, study_doc)
        capture_id = _file_capture(
            f"Competitive study filed: {qrow[2]} (harness)",
            f"Question #{qrow[0]}: {qrow[1]} Findings: "
            f"{parsed['findings'][:1200]} Cannot verify: "
            f"{parsed['cannot_verify'][:400]} Study: "
            f"{allm_pointer}.",
            raw=text[:6000])
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO altair.second_brain (topic, category, "
                "content, confidence, source, verification, tags, "
                "expires_at, allm_pointer) VALUES (%s,"
                "'general_knowledge',%s,'medium',%s,"
                "'fleet_dig_primary_fetch',%s,"
                "now() + interval '6 months',%s) RETURNING id",
                (f"{qrow[2]} - competitive study ({date})",
                 (parsed["findings"] + " CANNOT VERIFY: " +
                  parsed["cannot_verify"])[:1800], SOURCE,
                 "{competitive-research," +
                 qrow[2].split("-")[0] + "}", allm_pointer))
            sb_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE successbrian_os.research_questions SET "
                "status='studied', study_text=%s, allm_pointer=%s, "
                "second_brain_id=%s, capture_id=%s, "
                "collected_at=now() WHERE id=%s",
                (text, allm_pointer, sb_id, capture_id, qrow[0]))
            conn.commit()
        finally:
            conn.close()
        conn = sbos_common.connect()
        try:
            cur = conn.cursor()
            filed = _route_outputs(cur, qrow, parsed, capture_id)
            cur.execute(
                "UPDATE successbrian_os.research_questions SET "
                "status='routed', routed_at=now() WHERE id=%s",
                (qrow[0],))
            conn.commit()
        finally:
            conn.close()
        print(f"collect: question #{qrow[0]} ({qrow[2]}) studied "
              f"+ routed: study {allm_pointer}, second_brain "
              f"#{sb_id}, capture #{capture_id}, outputs "
              f"{filed}")
        done += 1
    if not done:
        print("collect: nothing landed yet")
    return done


# ------------------------------------------------------------ cycle / status

def cycle():
    collect()
    dispatch()


def status():
    rows = sbos_common.pg_rows(
        "SELECT q.id, q.subject, q.status, q.capture_id, "
        "count(r.id) FROM successbrian_os.research_questions q "
        "LEFT JOIN successbrian_os.research_routes r "
        "ON r.question_id = q.id GROUP BY q.id ORDER BY q.id") or []
    for r in rows:
        print(f"#{r[0]} {r[1]} [{r[2]}] capture={r[3]} "
              f"routes={r[4]}")
    print(f"{len(rows)} question(s)")


# ------------------------------------------------------------ selftest

_SAMPLE = (
    "FINDINGS: Rival A publishes a $7,500 setup on its own "
    "pricing page (fetched today); Rival B's domain now redirects "
    "to an unrelated site. CANNOT VERIFY: Rival A's monthly "
    "retainer - not on the fetched pages. OUTPUTS: TASK| Verify "
    "remaining named rivals' domains | Two of five named rivals "
    "are gone; the funnel's SEO plan cites them. RESEARCH| What "
    "do surviving rivals charge monthly? | Retainer is the "
    "recurring-revenue benchmark. ARTICLE| What a $7,500 AI "
    "setup actually buys a small office | Rival A's published "
    "price is the searcher's anchor. DECISION| Publish a "
    "starting price or stay negotiable? | The study puts the "
    "credibility pattern in front of Brian. DESIGN| goal "
    "harness: add a domain-liveness check to briefs | Dead "
    "rivals in briefs waste Einstein's looks.")


def selftest():
    checks = []
    # 1. tables exist
    n = sbos_common.pg_one(
        "SELECT count(*) FROM information_schema.tables WHERE "
        "table_schema='successbrian_os' AND table_name IN "
        "('research_questions','research_routes')")
    checks.append(("tables present", n == 2))
    # 2. parser: sections + all five output kinds
    p = parse_study(_SAMPLE)
    kinds = sorted(o["kind"] for o in p["outputs"])
    checks.append(("parser sections", bool(p["findings"]) and
                   bool(p["cannot_verify"])))
    checks.append(("parser outputs x5", kinds == [
        "ARTICLE", "DECISION", "DESIGN", "RESEARCH", "TASK"]))
    # 3. packet shape under the REAP invariants
    pkt = sbos_common.build_reap_packet(
        "probe", source=SOURCE, probe_id="crh-selftest",
        max_tokens=MAX_TOKENS, thinking=False)
    checks.append(("packet invariants", pkt["max_tokens"] <=
                   sbos_common.REAP_MAX_TOKENS and
                   pkt["thinking"] is False))
    # 4. transactional register + route, rolled back
    conn = sbos_common.connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO successbrian_os.research_questions "
            "(question, subject, origin, feeds, article_ref, "
            "priority) VALUES ('selftest?','crh-selftest',"
            "'selftest','selftest','ai-services',50) RETURNING id")
        qid = cur.fetchone()[0]
        qrow = (qid, "selftest?", "crh-selftest", "selftest",
                "selftest", "ai-services", 50)
        # DESIGN routes shell out to the capture CLI (a real side
        # effect, not transactional) - excluded from the probe.
        probe = dict(p, outputs=[o for o in p["outputs"]
                                 if o["kind"] != "DESIGN"])
        filed = _route_outputs(cur, qrow, probe, 0)
        checks.append(("route files 4 store outputs",
                       len([f for f in filed if f[0] !=
                            "design_input"]) == 4))
        conn.rollback()
    finally:
        conn.close()
    # 5. seeds registered
    n = sbos_common.pg_one(
        "SELECT count(*) FROM successbrian_os.research_questions "
        "WHERE subject IN ('goal-tests-2026-11-23',"
        "'paperclip-decomposition-2026-11-23',"
        "'paperclip-field-scan-2026-11-23')")
    checks.append(("seeds registered", n == 3))
    ok = all(v for _, v in checks)
    for name, v in checks:
        print(f"  {'PASS' if v else 'FAIL'} {name}")
    print(f"COMPETITIVE-HARNESS-SELFTEST-"
          f"{'OK' if ok else 'FAILED'} "
          f"{sum(v for _, v in checks)}/{len(checks)}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="verb")
    sub.add_parser("init")
    sub.add_parser("seed")
    sub.add_parser("collect")
    sub.add_parser("cycle")
    sub.add_parser("status")
    sub.add_parser("selftest")
    p = sub.add_parser("register")
    p.add_argument("--question", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--origin", default="")
    p.add_argument("--feeds", default="")
    p.add_argument("--article-ref", default=None)
    p.add_argument("--fetch", action="append", default=[])
    p.add_argument("--priority", type=int, default=50)
    p = sub.add_parser("dispatch")
    p.add_argument("--id", type=int, default=None)
    args = ap.parse_args()
    if args.verb == "init":
        init_db()
    elif args.verb == "seed":
        seed()
    elif args.verb == "register":
        register(args.question, args.subject, args.origin,
                 args.feeds, args.article_ref, args.fetch,
                 args.priority)
    elif args.verb == "dispatch":
        dispatch(args.id)
    elif args.verb == "collect":
        collect()
    elif args.verb == "cycle":
        cycle()
    elif args.verb == "status":
        status()
    elif args.verb == "selftest":
        return selftest()
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
