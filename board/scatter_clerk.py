#!/usr/bin/env python3
"""The Scatter Clerk — the board looks at new scatter entries daily.

Brian (2026-10-24): "every day the board should be looking at new
entries to the scatter — our clerk should be creating packets."

The clerk is a software role (the serious flow's build order starts
with 'packet builder in software'). The clerk looks THROUGH THE DAY,
every day (Brian: the 04:50-only cadence became an hourly sweep the
same morning he ordered the clerk — a capture should never wait
overnight to become a packet). On every pass, the clerk:

  1. Reads NEW raw captures from atlas.scattered_captures (a
     watermark guarantees each capture is packeted exactly once).
  2. Groups repeats: captures whose titles strongly overlap are one
     tangent said twice, so they share a packet.
  3. Builds each packet by packet law — it states WHY IT MATTERS,
     states THE DILEMMA, and asks MANY EASY QUESTIONS (never one big
     hard question; the complexity surfaces from the answer set).
  4. Files each packet as an atlas_task node whose details carry
     the full packet text in `question` — the exact field the board
     harness reads — so the packet is in the agenda the panel, the
     wave-2 closer, and the decider heartbeats already pull.
  5. Writes one decision-stream line per run that created packets.

The clerk never judges and never rules the scatter: promote / park /
discard stays Brian's SSB ruling. The board looks; the deciders
work the packet; the recommendation comes back through the stream.

WORKFLOW #3 — THE KEEPING WORKFLOW (Brian, 2026-10-25: "create
workflow #3"): the sort is now three-way. A capture that arrives
as INTEL (a research result from a requested lookup — a video
analyzed, a page read, a price checked) does not need judging
and is not a task to do: it needs to be KEPT. The clerk
files it as a document into its determined AnythingLLM workspace
(determine() + allm_embed, the R32 sanctioned home), marks the
capture wf3-kept with its workspace_slug, and creates NO board
packet. EXCEPTION (Brian, 2026-10-25): prices are database state,
not documents — a price capture's facts are extracted into
successbrian_os.price_intel rows instead, and no AnythingLLM
document is created for them. If the filing cannot complete (workspace determined but
not yet created, embed failure), the kick-aside law applies: the
item goes to Workflow #2 as an atlas task for Altair, with the
reason — never forced, never silently dropped. Every kept filing
carries the clerk's one assessment — how long the info stays
valuable (a valid-until date in successbrian_os.wf3_filings);
each sweep, filings past their date resurface once as recheck
tasks for Altair (Brian, 2026-10-25: "a price should be
rechecked").
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))
import pm_core  # noqa: E402
import allm_embed  # noqa: E402
import allm_workspaces as allm  # noqa: E402

ATLAS_PY = os.path.expanduser("~/successbrian-os/tools/atlas/atlas.py")
STATE = os.path.expanduser("~/successbrian-os/board/state/scatter_clerk.json")

# THE CLERK SORTS (Brian, 2026-10-25: "things should be sorted by
# the clerk"). Every capture is classified BY THE CLERK — the
# role's one-sentence definition ("the clerk looks at a mess and
# puts it in one stack or another") applied to all three stacks.
# Producer stamps and title tags are EVIDENCE the clerk weighs,
# never the verdict: no producer sorts its own filing.
#
# THE ONLY ASSESSMENT IS SHELF LIFE (Brian, 2026-10-25: "the only
# thing it needs to assess is how long that info is valuable. a
# price should be rechecked"). The clerk does NOT grade intel —
# no score of worth, no tally of merit. It makes exactly one
# assessment about a kept item: HOW LONG THE INFO STAYS VALUABLE.
# That goes on the filing as a valid-until date, and when the
# date passes the item resurfaces as a recheck task for Altair
# (Workflow #2). The routing rule itself is stated in words, not
# arithmetic: an item is KEPT when it arrives as a finished
# result — it declares itself one (a filing tag or the producer's
# lookup stamp) AND it carries the work (a fleshed-out result
# body or its source). Everything else goes to the board:
# judgment is the safe default.
INTEL_MARKER = "INTEL dump"

# Shelf-life windows in days, by intel kind. The PRINCIPLE is
# Brian's (assess only how long the info is valuable; prices get
# rechecked). The NUMBERS are operating defaults, tunable in one
# place — they are not Brian-ruled figures.
SHELF_LIFE_DAYS = {
    "price": 7,
    "page": 90,
    "video": 180,
    "reference": 90,
}

FILINGS_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.wf3_filings (
    capture_id INT PRIMARY KEY,
    workspace_slug TEXT NOT NULL,
    doc_filename TEXT NOT NULL,
    kind TEXT NOT NULL,
    checked_on DATE,
    filed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ NOT NULL,
    recheck_requested_at TIMESTAMPTZ,
    superseded_by INT
)
"""


def classify(cap):
    """The clerk's sort, stated in words. Returns (route, reasons)
    where route is 'wf3' (keep: Workflow #3) or 'board' (Workflow
    #1 packet — the exit for everything the clerk doesn't keep;
    Workflow #2 receives kick-asides and WF1-check issues, as
    chartered)."""
    title = cap.get("title") or ""
    context = cap.get("context") or ""
    raw = cap.get("raw") or ""
    reasons = []
    declares = False
    if re.match(r"(?i)^INTEL\b", title) or re.match(
            r"(?i)^(VIDEO|PAGE|PRICE|WEB|RESEARCH)\s*:", title):
        declares = True
        reasons.append("arrives tagged as a filed result")
    if INTEL_MARKER in context:
        declares = True
        reasons.append("producer filed it as a lookup result")
    carries = False
    if len(raw) >= 400:
        carries = True
        reasons.append("carries a fleshed-out result body "
                       "(%d chars)" % len(raw))
    if "http://" in context or "https://" in context:
        carries = True
        reasons.append("carries its source (URL in context)")
    if declares and carries:
        return "wf3", reasons
    if not declares:
        reasons.append("does not declare itself a result — "
                       "judgment is the default")
    if not carries:
        reasons.append("carries no worked result or source — "
                       "judgment is the default")
    return "board", reasons


def _checked_on(cap):
    """The date the intel was checked, parsed from its context
    ('checked 2026-10-20'); None when the filing doesn't say."""
    m = re.search(r"checked[^0-9]{0,12}(\d{4}-\d{2}-\d{2})",
                  cap.get("context") or "", re.I)
    if m:
        try:
            from datetime import date as _date
            y, mo, d = (int(x) for x in m.group(1).split("-"))
            return _date(y, mo, d)
        except Exception:
            return None
    return None


def assess_shelf_life(cap):
    """THE clerk's one assessment: how long this intel stays
    valuable. Returns (kind, days, basis_text). Validity runs
    from the checked date when the filing states one, else from
    the filing date."""
    title = cap.get("title") or ""
    if re.match(r"(?i)^(INTEL\s*[—-]\s*)?PRICE\b", title) \
            or re.search(r"(?i)\bprice\b", title) \
            or "$" in title:
        kind = "price"
    elif re.match(r"(?i)^(INTEL\s*[—-]\s*)?VIDEO\b", title):
        kind = "video"
    elif re.match(r"(?i)^(INTEL\s*[—-]\s*)?(PAGE|WEB)\b", title):
        kind = "page"
    else:
        kind = "reference"
    days = SHELF_LIFE_DAYS[kind]
    basis = (f"{kind} intel is valuable for {days} days "
             f"(operating default)")
    return kind, days, basis

EASY_QUESTIONS = [
    "Is this connected to a standing goal or launch — which one?",
    "Is this new, or a repeat of something the ecosystem already holds?",
    "What is the smallest next step that would move it?",
    "What breaks, rots, or is lost if this waits a month?",
    "What single piece of research would settle whether it matters?",
    "Does this need Brian himself, or can the ecosystem carry it?",
    "If it works, what does it feed — a desk, a launch, the fleet, the graph?",
]

STOP = set("the a an and or of to for in on with is are it its this "
           "that from by at as be was were will would can could".split())


def words(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower())
            if w not in STOP and len(w) > 2}


def group(captures):
    """Group by the SSB's own cluster_key (set at capture time);
    title-word overlap is the fallback for unclustered captures."""
    by_cluster = {}
    loose = []
    for cap in captures:
        if cap.get("cluster"):
            by_cluster.setdefault(cap["cluster"], []).append(cap)
        else:
            loose.append(cap)
    groups = list(by_cluster.values())
    for cap in loose:
        ws = words(cap["title"])
        placed = False
        for g in groups:
            gw = words(g[0]["title"])
            union = ws | gw
            sim = len(ws & gw) / len(union) if union else 0
            if sim >= 0.45:
                g.append(cap)
                placed = True
                break
        if not placed:
            groups.append([cap])
    return groups


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"last_capture_id": 0}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=1)


def fetch_new(last_id):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT id, title, coalesce(context,''), "
        "coalesce(raw_text,''), score, coalesce(recommendation,''), "
        "cluster_key "
        "FROM atlas.scattered_captures "
        "WHERE status='raw' AND id > %s ORDER BY id", (last_id,))
    rows = cur.fetchall()
    c.close()
    return [{"id": r[0], "title": r[1], "context": r[2], "raw": r[3],
             "score": r[4], "recommendation": r[5], "cluster": r[6]}
            for r in rows]


def packet_text(members):
    lines = []
    titles = "; ".join(m["title"] for m in members)
    lines.append(f"SCATTER PACKET — {titles}")
    lines.append("")
    lines.append("WHY IT MATTERS:")
    for m in members:
        why = (m["context"] or m["raw"] or "").strip()
        if why:
            lines.append(f"- (capture #{m['id']}) {why[:600]}")
        if m["recommendation"]:
            lines.append(f"- SSB triage read: {m['recommendation']}"
                         + (f" (score {m['score']})" if m["score"]
                            is not None else ""))
    lines.append("")
    lines.append("THE DILEMMA: does this tangent deserve promotion "
                 "into planned work, parking until its moment, or "
                 "discard — and what would settle it? (The ruling "
                 "itself stays Brian's under SSB doctrine; the "
                 "board's job is to look, judge the questions, and "
                 "bring back a recommendation.)")
    lines.append("")
    lines.append("QUESTIONS FOR THE JUDGES:")
    for i, q in enumerate(EASY_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("SOURCE: atlas.scattered_captures "
                 + ", ".join(f"#{m['id']}" for m in members))
    return "\n".join(lines)


def file_packet(members, dry_run=False):
    ids = "-".join(str(m["id"]) for m in members)
    key = f"task:ssb-packet-{ids}"
    title = ("Scatter packet: " + members[0]["title"])[:180]
    details = {
        "question": packet_text(members),
        "why_it_matters": (members[0]["context"]
                           or members[0]["raw"] or "")[:600],
        "dilemma": "promote into planned work, park, or discard — "
                   "and what research settles it",
        "easy_questions": EASY_QUESTIONS,
        "source_captures": [m["id"] for m in members],
        "theme": "scatter",
        "found_by": "scatter-clerk",
        "clerk_sort": [
            {"capture": m["id"], "route": "wf1-board",
             "reasons": m["_sort"][1]}
            for m in members if "_sort" in m],
    }
    if dry_run:
        print(f"[dry-run] would file {key}: {title}")
        print(details["question"][:800])
        return key
    r = subprocess.run(
        ["python3", ATLAS_PY, "add-node", key, "atlas_task", title,
         "--status", "queued", "--details", json.dumps(details)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"add-node failed: {r.stderr[:300]}")
    return key


def is_wf3(cap):
    """Back-compat wrapper: the clerk's sort decides (classify)."""
    return classify(cap)[0] == "wf3"


def fetch_capture(cid):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT id, title, coalesce(context,''), "
        "coalesce(raw_text,''), score, coalesce(recommendation,''), "
        "cluster_key, status "
        "FROM atlas.scattered_captures WHERE id = %s", (cid,))
    r = cur.fetchone()
    c.close()
    if not r:
        return None
    return {"id": r[0], "title": r[1], "context": r[2], "raw": r[3],
            "score": r[4], "recommendation": r[5], "cluster": r[6],
            "status": r[7]}


def _wf3_subject(title):
    """The subject determine() routes on: the title minus the
    producer's filing tags (INTEL —, VIDEO:, ...)."""
    s = re.sub(r"^INTEL\s*[—-]\s*", "", title or "")
    s = re.sub(r"^(VIDEO|PAGE|PRICE|WEB|RESEARCH)\s*:\s*", "", s,
               flags=re.I)
    return s.strip() or (title or "")


def _wf3_mark(cap_id, recommendation, slug=None):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(
        "UPDATE atlas.scattered_captures SET status='triaged', "
        "triaged_at=now(), recommendation=%s, workspace_slug=%s "
        "WHERE id=%s", (recommendation, slug, cap_id))
    c.commit()
    c.close()


def _wf3_kick(cap, reason, dry_run=False):
    """Kick-aside to Workflow #2: an atlas task for Altair carrying
    the filing failure. The clerk never forces a misfit and never
    drops one silently."""
    key = f"task:wf3-kickaside-{cap['id']}"
    title = (f"WF3 filing failed for capture #{cap['id']} — "
             f"Altair to place: {cap['title']}")[:180]
    details = {
        "question": (
            f"Workflow #3 (the keeping workflow) could not file "
            f"Intel Bridge capture #{cap['id']} ('{cap['title']}')."
            f"\n\nREASON: {reason}\n\nCONTEXT: "
            f"{(cap['context'] or '')[:800]}\n\nINTEL: "
            f"{(cap['raw'] or '')[:2000]}\n\nAltair: file this intel "
            f"into its proper knowledge home (or create the "
            f"workspace it waits on), then close this task."),
        "theme": "wf3-kickaside",
        "found_by": "scatter-clerk-wf3",
        "source_captures": [cap["id"]],
    }
    if dry_run:
        print(f"[dry-run] would kick capture #{cap['id']} -> {key} "
              f"({reason})")
        return key
    r = subprocess.run(
        ["python3", ATLAS_PY, "add-node", key, "atlas_task", title,
         "--status", "queued", "--details", json.dumps(details)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kick-aside add-node failed: "
                           f"{r.stderr[:300]}")
    _wf3_mark(cap["id"], "wf3-kicked-to-wf2")
    return key


PRICE_DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.price_intel (
    id BIGSERIAL PRIMARY KEY,
    capture_id INT NOT NULL,
    item TEXT NOT NULL,
    amount NUMERIC,
    currency TEXT NOT NULL DEFAULT 'USD',
    source_label TEXT,
    source_url TEXT,
    statement TEXT,
    checked_on DATE,
    valid_until TIMESTAMPTZ NOT NULL,
    in_stock BOOLEAN,
    stock_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
PRICE_ALTERS = [
    "ALTER TABLE successbrian_os.price_intel "
    "ADD COLUMN IF NOT EXISTS in_stock BOOLEAN",
    "ALTER TABLE successbrian_os.price_intel "
    "ADD COLUMN IF NOT EXISTS stock_text TEXT",
]
# STOCK IS TRACKED TOO (Brian, 2026-10-25: "we also want to track
# inventories if known... so see if we can find out if things are
# sold out. eventually all 680M's will be sold out. then at some
# point all 780M's will be sold out"). Every price observation
# records the stock state WHEN THE FILING STATES ONE: in_stock
# true/false, with the exact phrase that carried it (stock_text)
# for audit. Unknown stays NULL — not knowing is not the same as
# sold out. A sold-out observation is still an observation (the
# price archived with its date, per Brian's market-price rule);
# it is simply never a current offer. The generational sell-out
# (a whole chip class going dark) is read from the series.
# PRICES ARE DATABASE STATE (Brian, 2026-10-25: "prices themselves
# kept in databases — not anythingllm"). A price capture's FACTS
# are extracted into successbrian_os.price_intel rows — queryable,
# comparable over time — and NO AnythingLLM document is created
# for them. (The capture's full text already lives in PostgreSQL
# in atlas.scattered_captures; the AnythingLLM copy was the
# redundant one.) The curated domain registers (dealsdesk's
# price_reference and the tracker tables) stay separate;
# price_intel is the bridge's general price shelf, every row
# linked back to its capture.


def _price_points(cap):
    """Headline price points from the capture's title:
    '$999.59 at Walmart' pairs first; bare $ amounts otherwise.
    A pairing is only recorded when the title states it — the
    clerk never invents which price belongs to which source."""
    title = cap.get("title") or ""
    points = []
    for amt, label in re.findall(
            r"\$([\d,]+(?:\.\d{1,2})?)\s*(?:at|from)\s*([^,;·—–(-]+)",
            title):
        try:
            points.append((float(amt.replace(",", "")),
                           label.strip() or None))
        except ValueError:
            pass
    if not points:
        for amt in re.findall(r"\$([\d,]+(?:\.\d{1,2})?)", title):
            try:
                points.append((float(amt.replace(",", "")), None))
            except ValueError:
                pass
    return points


def _item_name(cap):
    s = _wf3_subject(cap.get("title") or "")
    s = re.sub(r"\s*\((?:checked|retrieved)[^)]*\)\s*$", "", s)
    if "$" in s:
        # The item is named in the dash-segment that carries the
        # first price ("GMKtec K15 at $869.99 ...") — or, when
        # that segment starts with the price itself, in the
        # segment just before it ("GMKtec K11 mini PC — $999.59
        # at Walmart").
        segs = [p.strip() for p in re.split(r"\s*[—–]\s*", s)
                if p.strip()]
        for i, seg in enumerate(segs):
            if "$" in seg:
                head = re.split(r"\s+(?:at|for)\s*(?=\$)", seg)[0]
                head = head.split("$")[0].strip(" -—–(")
                if head:
                    s = head
                elif i > 0:
                    s = segs[i - 1]
                break
    return s.strip() or (cap.get("title") or "")[:120]


def _source_url(cap):
    m = re.search(r"https?://[^\s)]+", cap.get("context") or "")
    return m.group(0) if m else None


def _record_filing(cap_id, home, doc_filename, kind, checked,
                   valid_until):
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(FILINGS_DDL)
    cur.execute(
        "INSERT INTO successbrian_os.wf3_filings "
        "(capture_id, workspace_slug, doc_filename, kind, "
        "checked_on, valid_until) VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (capture_id) DO UPDATE SET "
        "workspace_slug = EXCLUDED.workspace_slug, "
        "doc_filename = EXCLUDED.doc_filename, "
        "kind = EXCLUDED.kind, checked_on = EXCLUDED.checked_on, "
        "valid_until = EXCLUDED.valid_until, "
        "recheck_requested_at = NULL",
        (cap_id, home, doc_filename, kind, checked, valid_until))
    c.commit()
    c.close()


PRICE_TREND_DDL = """
DROP VIEW IF EXISTS successbrian_os.price_trend;
CREATE VIEW successbrian_os.price_trend AS
SELECT item, observed_on, amount, source_label, in_stock,
       CASE WHEN prev_capture IS DISTINCT FROM capture_id
            THEN amount - prev_amount END AS change_from_prev,
       capture_id
FROM (
    SELECT item, checked_on AS observed_on, amount,
           source_label, in_stock, capture_id,
           lag(amount) OVER w AS prev_amount,
           lag(capture_id) OVER w AS prev_capture
    FROM successbrian_os.price_intel
    WHERE amount IS NOT NULL
    WINDOW w AS (PARTITION BY item, coalesce(source_label, '')
                 ORDER BY checked_on, capture_id)
) s
ORDER BY item, observed_on, capture_id
"""
# change_from_prev compares ACROSS observations only: two price
# points from the SAME capture (e.g. the endpoints of a range)
# are one observation, never a movement.
# TIMESTAMPS ARE THE TREND (Brian, 2026-10-25: "we keep timestamps
# on price data so we can see pricing trends over time" — the same
# rule as his 2026-10-23 market-price DB rule for DealsDesk).
# Every price row carries its OBSERVATION date (checked_on): the
# date the price was actually seen, never silently the filing
# date — when a filing doesn't state one, the effective date is
# the filing date and that is what gets recorded, so no row ever
# lacks an observation time. Rows are observations: a recheck
# files a NEW capture with NEW rows, and nothing ever rewrites an
# old observation. The only delete in this module clears a single
# capture's own rows so re-filing the SAME observation stays
# idempotent. price_trend reads the series per item + source.


_SOLD_OUT_PHRASES = ["sold out", "out of stock", "delisted",
                     "no longer available", "back-order",
                     "backorder", "discontinued"]
_IN_STOCK_PHRASES = ["verified in stock", "in stock",
                     "available now", "in-stock"]


def _stock_signal(cap):
    """The filing's stated stock state: (True|False|None, phrase).
    A sold-out phrase wins over a generic in-stock mention (the
    sold-out statement is the deliberate one; 'in stock' also
    appears inside statements of Brian's price RULE). A phrase
    immediately negated ('not sold out') doesn't count."""
    text = " ".join([cap.get("title") or "",
                     cap.get("context") or "",
                     cap.get("raw") or ""]).lower()
    def _unnegated(phrase):
        i = text.find(phrase)
        while i != -1:
            before = text[max(0, i - 14):i]
            if not re.search(r"(not|never|isn't|isnt)\s+$", before):
                return True
            i = text.find(phrase, i + 1)
        return False
    for phrase in _SOLD_OUT_PHRASES:
        if _unnegated(phrase):
            return False, phrase
    for phrase in _IN_STOCK_PHRASES:
        if _unnegated(phrase):
            return True, phrase
    return None, None


PRICE_LATEST_DDL = """
DROP VIEW IF EXISTS successbrian_os.price_latest;
CREATE VIEW successbrian_os.price_latest AS
SELECT DISTINCT ON (item, coalesce(source_label, ''))
       item, source_label, amount, checked_on AS observed_on,
       in_stock, stock_text, valid_until, capture_id
FROM successbrian_os.price_intel
ORDER BY item, coalesce(source_label, ''),
         checked_on DESC, capture_id DESC
"""
# price_latest = the shelf's current state per item + source:
# the newest observation, its price, and whether it was in stock
# when seen. A row with in_stock = false is a sold-out shelf —
# archived, dated, and never a current offer.


def _write_price_rows(cap, checked, valid_until):
    """Insert the capture's price rows; returns the row count.
    At least one row is always written (amount NULL when the
    filing states no parseable headline price) so the shelf
    holds the statement and its dates even then."""
    points = _price_points(cap) or [(None, None)]
    item = _item_name(cap)
    url = _source_url(cap)
    statement = (cap.get("title") or "")[:300]
    in_stock, stock_text = _stock_signal(cap)
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(PRICE_DDL)
    for alter in PRICE_ALTERS:
        cur.execute(alter)
    cur.execute(PRICE_TREND_DDL)
    cur.execute(PRICE_LATEST_DDL)
    cur.execute("DELETE FROM successbrian_os.price_intel "
                "WHERE capture_id = %s", (cap["id"],))
    for amount, label in points:
        cur.execute(
            "INSERT INTO successbrian_os.price_intel "
            "(capture_id, item, amount, source_label, source_url, "
            "statement, checked_on, valid_until, in_stock, "
            "stock_text) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (cap["id"], item, amount, label, url, statement,
             checked, valid_until, in_stock, stock_text))
    c.commit()
    c.close()
    return len(points)


def file_price_intel(cap, kind, checked, valid_until,
                     dry_run=False):
    """The price branch of Workflow #3: facts to the database,
    no AnythingLLM document."""
    points = _price_points(cap)
    if dry_run:
        print(f"[dry-run] would write {len(points) or 1} price "
              f"row(s) for capture #{cap['id']} -> "
              f"successbrian_os.price_intel "
              f"(valid until {valid_until.date().isoformat()})")
        return {"id": cap["id"], "outcome": "kept",
                "workspace": "db:price_intel", "detail": "dry-run",
                "kind": kind,
                "valid_until": valid_until.date().isoformat()}
    n = _write_price_rows(cap, checked, valid_until)
    _wf3_mark(cap["id"], "wf3-kept", slug="db:price_intel")
    _record_filing(cap["id"], "db:price_intel", "price_intel",
                   kind, checked, valid_until)
    return {"id": cap["id"], "outcome": "kept",
            "workspace": "db:price_intel",
            "detail": f"{n} price row(s) in "
                      f"successbrian_os.price_intel",
            "kind": kind,
            "valid_until": valid_until.date().isoformat()}


def file_wf3(cap, dry_run=False, sort_info=None):
    """File one intel capture into its knowledge home (WF3).

    Returns {"id", "outcome": kept|kicked, "workspace", "detail",
    and for kept filings "kind"/"valid_until"}. sort_info (route,
    reasons) from classify() is recorded in the filed document;
    None means a directed manual filing.

    Prices take the database branch (file_price_intel) — their
    facts are state, not a document.
    """
    kind, days, basis = assess_shelf_life(cap)
    checked = _checked_on(cap)
    from datetime import date as _date, datetime as _dt, \
        timedelta as _td
    base = checked or _date.today()
    valid_until = _dt(base.year, base.month, base.day) \
        + _td(days=days)
    if kind == "price":
        # The recorded observation date is the EFFECTIVE one
        # (stated checked date, else the filing date = base) —
        # a trend point is never left dateless.
        return file_price_intel(cap, kind, base, valid_until,
                                dry_run=dry_run)
    subject = _wf3_subject(cap["title"])
    c = pm_core.conn()
    try:
        d = allm.determine(c, subject)
    finally:
        c.close()
    slug = d.get("workspace") or d.get("proposed_slug")
    if not slug:
        reason = f"determine() returned no workspace ({d})"
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": None, "detail": reason}
    live = allm.live_workspaces()
    if slug not in live:
        reason = (f"workspace '{slug}' determined "
                  f"(verdict {d.get('verdict')}) but not created in "
                  f"AnythingLLM yet — filing waits on its creation")
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": slug, "detail": reason}
    if sort_info:
        sort_line = ("Clerk sort: Workflow #3 — "
                     + "; ".join(sort_info[1]))
    else:
        sort_line = "Clerk sort: manual filing (clerk file job)"
    assess_line = (
        f"Clerk assessment (the only one it makes): {basis}. "
        f"Checked {checked.isoformat() if checked else 'date not stated'}; "
        f"valuable until {valid_until.date().isoformat()} — "
        f"recheck after that date.")
    text = (f"# {cap['title']}\n\n"
            f"Intel Bridge capture #{cap['id']}, filed by Workflow "
            f"#3 (the keeping workflow).\n{sort_line}\n{assess_line}\n\n"
            f"## Context\n{cap['context'] or ''}\n\n"
            f"## Intel\n{cap['raw'] or ''}\n")
    filename = f"intel-capture-{cap['id']}.md"
    if dry_run:
        print(f"[dry-run] would file capture #{cap['id']} -> "
              f"{slug}/{filename} ({assess_line})")
        return {"id": cap["id"], "outcome": "kept",
                "workspace": slug, "detail": "dry-run",
                "kind": kind,
                "valid_until": valid_until.date().isoformat()}
    try:
        loc = allm_embed.embed_latest(slug, filename, text)
    except Exception as e:
        reason = f"embed into '{slug}' failed: {type(e).__name__}: {e}"
        _wf3_kick(cap, reason, dry_run=dry_run)
        return {"id": cap["id"], "outcome": "kicked",
                "workspace": slug, "detail": reason}
    _wf3_mark(cap["id"], "wf3-kept", slug=slug)
    _record_filing(cap["id"], slug, filename, kind, checked,
                   valid_until)
    return {"id": cap["id"], "outcome": "kept",
            "workspace": slug, "detail": loc,
            "kind": kind,
            "valid_until": valid_until.date().isoformat()}


def send_due_rechecks(dry_run=False):
    """The shelf-life loop: kept intel whose valid-until has
    passed resurfaces ONCE as a recheck task for Altair
    (Workflow #2). Returns the list of task keys created."""
    c = pm_core.conn()
    cur = c.cursor()
    cur.execute(FILINGS_DDL)
    c.commit()
    cur.execute(
        "SELECT f.capture_id, f.workspace_slug, f.kind, "
        "f.valid_until, sc.title FROM successbrian_os.wf3_filings f "
        "JOIN atlas.scattered_captures sc ON sc.id = f.capture_id "
        "WHERE f.valid_until < now() "
        "AND f.recheck_requested_at IS NULL "
        "AND f.superseded_by IS NULL ORDER BY f.valid_until")
    rows = cur.fetchall()
    c.close()
    keys = []
    for cid, slug, kind, valid_until, title in rows:
        key = f"task:wf3-recheck-{cid}"
        details = {
            "question": (
                f"RECHECK EXPIRED INTEL — capture #{cid} "
                f"('{title}'), kept by Workflow #3 in workspace "
                f"'{slug}'. Its {kind} intel passed its "
                f"valid-until date ({valid_until:%Y-%m-%d}); per "
                f"Brian's shelf-life rule it must be rechecked at "
                f"its source, not trusted. Altair: re-verify the "
                f"facts — INCLUDING whether the item is still in "
                f"stock or has sold out (state it in the filing; "
                f"stock is tracked alongside price) — file the "
                f"fresh result as a NEW capture noting 'recheck "
                f"of capture #{cid}', and close this task."),
            "theme": "wf3-recheck",
            "found_by": "scatter-clerk-wf3",
            "source_captures": [cid],
        }
        if dry_run:
            print(f"[dry-run] would send recheck for capture "
                  f"#{cid} -> {key}")
            keys.append(key)
            continue
        r = subprocess.run(
            ["python3", ATLAS_PY, "add-node", key, "atlas_task",
             (f"Recheck expired {kind} intel: capture #{cid} — "
              f"{title}")[:180],
             "--status", "queued", "--details", json.dumps(details)],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"recheck add-node failed: "
                               f"{r.stderr[:300]}")
        c = pm_core.conn()
        cur = c.cursor()
        cur.execute(
            "UPDATE successbrian_os.wf3_filings SET "
            "recheck_requested_at = now() WHERE capture_id = %s",
            (cid,))
        c.commit()
        c.close()
        keys.append(key)
        print(f"recheck sent for capture #{cid} "
              f"(expired {valid_until:%Y-%m-%d}) -> {key}")
    return keys


def run(dry_run=False):
    rechecks = send_due_rechecks(dry_run=dry_run)
    state = load_state()
    caps = fetch_new(state["last_capture_id"])
    if not caps:
        print("scatter clerk: no new raw captures")
        return [], [], rechecks
    for cap in caps:
        cap["_sort"] = classify(cap)
    wf3_caps = [c for c in caps if c["_sort"][0] == "wf3"]
    board_caps = [c for c in caps if c["_sort"][0] != "wf3"]
    wf3_results = []
    for cap in wf3_caps:
        res = file_wf3(cap, dry_run=dry_run, sort_info=cap["_sort"])
        wf3_results.append(res)
        print(f"wf3 {res['outcome']} capture #{res['id']} -> "
              f"{res['workspace'] or 'wf2'} ({res['detail']}) "
              f"[clerk sort: {'; '.join(cap['_sort'][1])}]")
    groups = group(board_caps)
    keys = []
    for g in groups:
        keys.append(file_packet(g, dry_run=dry_run))
        print(f"packet for captures {[m['id'] for m in g]} -> {keys[-1]}")
    if not dry_run:
        state["last_capture_id"] = max(m["id"] for m in caps)
        save_state(state)
        c = pm_core.conn()
        cur = c.cursor()
        if rechecks:
            pm_core.decide(
                cur, "scatter-clerk",
                f"Workflow #3 shelf-life: {len(rechecks)} expired "
                f"intel filing(s) sent to Altair for recheck: "
                f"{', '.join(rechecks)}",
                origin="system")
        if keys:
            pm_core.decide(
                cur, "scatter-clerk",
                f"Scatter clerk packeted {len(board_caps)} new "
                f"capture(s) into {len(keys)} board packet(s): "
                f"{', '.join(keys)}",
                origin="system")
        if wf3_results:
            kept = [r for r in wf3_results if r["outcome"] == "kept"]
            kicked = [r for r in wf3_results
                      if r["outcome"] == "kicked"]
            pm_core.decide(
                cur, "scatter-clerk",
                f"Workflow #3 filed {len(kept)} intel capture(s) to "
                f"their knowledge homes "
                f"({', '.join('#%d->%s (%s, valid until %s)' % (r['id'], r['workspace'], r.get('kind', '?'), r.get('valid_until', '?')) for r in kept) or 'none'}); "
                f"{len(kicked)} kicked to Workflow #2 "
                f"({', '.join('#%d' % r['id'] for r in kicked) or 'none'})",
                origin="system")
        c.commit()
        c.close()
    return keys, wf3_results, rechecks


def main(argv=None):
    dry = "--dry-run" in (argv or sys.argv)
    run(dry_run=dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
