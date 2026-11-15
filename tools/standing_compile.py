#!/usr/bin/env python3
"""standing_compile.py - Standing compile v1 (BUILD_QUEUE B15).

Per money line (GotBackup 40/mo, TrafficStreemz $30, ContactFlowCRM $20,
the ~$1k/30-day stranger track) compile visits -> contacts -> revenue
from the live record into one REAP packet per line (the B2 feeder-packet
standard: <=500 max_tokens, facts whole, provenance fields), and file
each compile to successbrian_os.knowledge_index with kind='compile'
(the B6 residue contract - residue_inventory.py reads that kind, so a
filed compile lights up the decision stream automatically).

Piece 2 (B15-2): dispatch. --dispatch sends each line's packet to
gamma's REAP seat via sbos_common.dispatch_reap_packet, rebuilding the
packet from the FILED compile row (doc_text is the brief), so the
dispatched prompt wraps exactly what B15-1 filed. Dispatch is
idempotent per line per day: a probe_id already on the bus is never
re-sent. --roundtrip dispatches one line if needed, waits for gamma's
verdict in the outbox, runs the knowledge_return collector, and
verifies the return leg: ROUTING: intel lands as
ki:reap-infer-<event>; any other routing verifies as a counted skip
(the collector counts discards/boards/kick-asides, never silently).

Packet shape (learned live 2026-11-13, cycle 180): the REAP loop's
only verdict shape is the classify template - a bare brief with no
instruction gets a degenerate echo, not a verdict. v1 packets
(events 362-365, unwrapped briefs) proved it: event 362 burned all
500 max_tokens and returned 42 chars ("Here's the STANDING COMPILE
for GotBackup:") - ok=True but no ROUTING line, so the round trip
could NOT verify. v2 (PACKET_FORMAT 2) wraps the brief in the exact
classify template the queue-keeper's packets carry (copied verbatim
from bus event 361's stored prompt): the compile is the Item, REAP
answers one ROUTING line, the knowledge_return leg processes it.
The filed doc_text stays the bare brief (the compile record); the
dispatched prompt is the wrapped form. Probe ids carry the format
(-f2) so a corrected packet is never blocked by a superseded send.

Honesty rules, enforced in code, not prose:
  - A leg with no live source is UNKNOWN / OWED, never zero and never
    invented. blog_scorecards rows with NULL metrics are UNMEASURED,
    not zero; money_flow sums of $0.00 are recorded $0, a different
    fact from unmeasured.
  - Contacts per line are a tag/name MATCH count against the dealsdesk
    pool, labelled as such - there is no per-line attribution column,
    so no per-line contact count is claimed.
  - Targets are STATED targets (Brian's rulings as recorded in the
    queue item), cited as stated, never as measured goal rows.
  - One row per line per Chicago date: canonical_id
    ki:compile-<line>-<YYYY-MM-DD>; re-runs the same day land nothing
    new (ON CONFLICT DO NOTHING).

Usage: standing_compile.py [--compile [--dry-run] [--line KEY]]
         [--dispatch [--dry-run] [--line KEY]]
         [--roundtrip [--line KEY] [--timeout SEC]]
         [--status] [--selftest]
Plan: builds/sbos-assembly/PLAN.md Phase 5.
"""
import argparse
import importlib.util
import json
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sbos_common import (  # noqa: E402
    build_reap_packet,
    dispatch_reap_packet,
    estimate_tokens,
    pg_exec,
    pg_one,
    pg_rows,
)

SCHEMA = "successbrian_os"
KI = f"{SCHEMA}.knowledge_index"
KIND = "compile"
CHICAGO = ZoneInfo("America/Chicago")
PROMPT_TOKEN_BUDGET = 2000  # B12b: reap prompt budget; over it is a blocker

# Money lines. target: Brian's STATED target (queue B15 / alignment
# record), cited as stated. revenue_categories: public.money_flow
# categories that belong to the line (verified live 2026-11-13).
# scorecard_blog: campaignsdesk.blog_scorecards blog_slug serving the
# line, or None when no scorecard blog is mapped to it.
LINES = {
    "gotbackup": {
        "name": "GotBackup",
        "target": "40 sponsorships/month (stated target)",
        "revenue_categories": [
            "gotbackup_personal_sales",
            "gotbackup_team_override",
            "gotbackup_lead_system",
            "affiliate_gotbackup",
            "gotbackup_training_products",
        ],
        "scorecard_blog": None,
        "contact_match": "gotbackup",
    },
    "trafficstreemz": {
        "name": "TrafficStreemz",
        "target": "$30/month, first (stated target)",
        "revenue_categories": [
            "saas_trafficstreemz",
            "trafficstreemz_affiliate",
            "incubator_trafficstreemz",
        ],
        "scorecard_blog": "trafficstreemz-blog",
        "contact_match": "trafficstreemz",
    },
    "contactflowcrm": {
        "name": "ContactFlowCRM",
        "target": "$20/month, second (stated target)",
        "revenue_categories": [
            "saas_contactflowcrm",
            "incubator_contactflowcrm",
        ],
        "scorecard_blog": None,
        "contact_match": "contactflowcrm",
    },
    "stranger-1k": {
        "name": "Stranger $1k track",
        "target": "~$1,000 in 30 days from strangers, ~$300/sale "
                  "(stated target)",
        "revenue_categories": [],
        "scorecard_blog": None,
        "contact_match": None,
    },
}


def today_chicago() -> str:
    return datetime.now(CHICAGO).strftime("%Y-%m-%d")


PACKET_FORMAT = 2

# The REAP loop's only verdict shape: the classify template, copied
# verbatim from bus event 361's stored prompt (the queue-keeper's
# packet shape). {title} / {text} are the only substitutions.
CLASSIFY_TEMPLATE = """Classify this one item into exactly one routing. Reply with exactly one single line, nothing else, in this shape: ROUTING: <one word: board, kick-aside, intel, or discard> - <one short sentence saying why, tied to a specific fact in the item>. Do not add a second line.

What the words mean:
- board: the item needs a decision or action by a person — something to buy, sell, join, approve, or reply to. A marketplace want-to-buy or for-sale post for hardware we track counts as board.
- intel: the item is outside-world knowledge worth keeping — news, market or price data, company or crypto developments, security warnings about outside products. File it.
- kick-aside: the item might matter but does not fit board or intel and should not be thrown away — park it for a second look. Use only when you cannot place it in board or intel.
- discard: the item has no lasting value — internal system messages, status or error notices about our own internal processes, routine internal scheduling snapshots that repeat and are replaced by the next one, duplicates.

Rules:
1. News about the outside world is intel, even when it mixes topics. Never call a news item fake or discard it just because it covers two topics.
2. Internal notices that one of our own packages or processes failed or could not reach agreement are discard — always, every time.
3. Routine daily statistics or price reports about a real company or asset are intel — always, every time, for every company.
4. Security warnings and emergency patches for outside crypto or software products are intel.
5. Internal hourly scheduling lists (priority resort / hourly order) are discard: they repeat every hour and the next one replaces them.
6. If torn between intel and kick-aside, choose intel. If torn between discard and kick-aside for an internal system notice, choose discard.

Examples:
- Title: 'Miniflux: BitGo Q3 profit nearly doubles' (news about a company's results) -> ROUTING: intel - Outside company financial news worth filing.
- Title: 'DECIDER ESCALATION: package #52 could not reach agreement' -> ROUTING: discard - Internal notice about our own process failing, no lasting value.
- Title: '[WTB] DDR4 ECC memory, 2 GPUs' -> ROUTING: board - A buy post for tracked hardware needs a person to decide and act.
- Title: 'HOURLY ORDER — priority resort' (our hourly task list) -> ROUTING: discard - Internal schedule snapshot that repeats hourly and is replaced by the next.

Item title: {title}
Item text: {text}"""


def gather(key: str) -> dict:
    """Read-only gather for one line. Numbers are live; gaps are None."""
    line = LINES[key]
    cats = line["revenue_categories"]
    if cats:
        rev30 = pg_one(
            "select coalesce(sum(amount), 0) from public.money_flow "
            "where category = any(%s) and date >= current_date - 30",
            (cats,))
        rev_all = pg_one(
            "select coalesce(sum(amount), 0) from public.money_flow "
            "where category = any(%s)", (cats,))
        rev_rows = pg_one(
            "select count(*) from public.money_flow "
            "where category = any(%s)", (cats,))
    else:
        rev30 = rev_all = None
        rev_rows = 0
    scorecard = None
    if line["scorecard_blog"]:
        rows = pg_rows(
            "select period_start, period_end, unique_visits, "
            "contacts_captured, revenue_cents from "
            "campaignsdesk.blog_scorecards where blog_slug = %s "
            "order by period_end desc limit 1", (line["scorecard_blog"],))
        if rows:
            ps, pe, uv, cc, rc = rows[0]
            scorecard = {
                "period_start": str(ps), "period_end": str(pe),
                "unique_visits": uv, "contacts_captured": cc,
                "revenue_cents": rc,
            }
    contacts = None
    if line["contact_match"]:
        m = line["contact_match"]
        contacts = pg_one(
            "select count(*) from dealsdesk.contacts where "
            "tags::text ilike %s or company_name ilike %s "
            "or notes ilike %s or source ilike %s",
            (f"%{m}%", f"%{m}%", f"%{m}%", f"%{m}%"))
    pool = pg_one("select count(*) from dealsdesk.contacts")
    goals = pg_rows(
        "select count(*), count(*) filter (where status = 'active') "
        "from public.goals where title ilike %s", (f"%{line['name']}%",))
    g_total, g_active = goals[0] if goals else (0, 0)
    return {
        "key": key, "name": line["name"], "target": line["target"],
        "revenue_30d": (float(rev30) if rev30 is not None else None),
        "revenue_all": (float(rev_all) if rev_all is not None else None),
        "revenue_rows": int(rev_rows or 0),
        "revenue_categories": cats,
        "scorecard": scorecard,
        "scorecard_blog": line["scorecard_blog"],
        "contacts_matched": (int(contacts) if contacts is not None
                             else None),
        "contacts_pool": int(pool or 0),
        "goals_total": int(g_total or 0),
        "goals_active": int(g_active or 0),
    }


def _money(v):
    return f"${v:,.2f}" if v is not None else "UNKNOWN"


def build_brief(g: dict, day: str) -> tuple[str, str, list[str]]:
    """Compile one line into (brief, one-line verdict, owed legs).

    Pure function of the gather dict - the selftest exercises it with
    an all-UNKNOWN gather to prove nothing is invented.
    """
    owed = []
    parts = [f"STANDING COMPILE - {g['name']} - {day}",
             f"Target (stated): {g['target']}."]
    if g["revenue_30d"] is None:
        parts.append("Revenue: UNKNOWN - no money_flow category mapped "
                     "to this line.")
        owed.append("revenue (no money_flow category)")
    else:
        parts.append(
            f"Revenue: {_money(g['revenue_30d'])} last 30d / "
            f"{_money(g['revenue_all'])} all-time across "
            f"{g['revenue_rows']} money_flow rows "
            f"(categories: {', '.join(g['revenue_categories'])}).")
    sc = g["scorecard"]
    if g["scorecard_blog"] is None:
        parts.append("Visits: UNKNOWN - no scorecard blog mapped to "
                     "this line.")
        owed.append("visits (no scorecard blog)")
        parts.append("Contacts: UNKNOWN - no scorecard blog; see "
                     "tag-match below.")
        owed.append("contacts (no scorecard blog)")
    elif sc is None:
        parts.append(f"Visits: UNKNOWN - scorecard blog "
                     f"{g['scorecard_blog']} has no scorecard row.")
        owed.append(f"visits (no {g['scorecard_blog']} row)")
        parts.append("Contacts: UNKNOWN - no scorecard row.")
        owed.append("contacts (no scorecard row)")
    else:
        if sc["unique_visits"] is None:
            parts.append(
                f"Visits: UNKNOWN - {g['scorecard_blog']} scorecard "
                f"{sc['period_start']}..{sc['period_end']} has NULL "
                f"unique_visits (UNMEASURED, not zero).")
            owed.append("visits (scorecard NULL)")
        else:
            parts.append(
                f"Visits: {sc['unique_visits']} uniques "
                f"({sc['period_start']}..{sc['period_end']}, "
                f"{g['scorecard_blog']}).")
        if sc["contacts_captured"] is None:
            parts.append(
                f"Contacts: UNKNOWN - {g['scorecard_blog']} scorecard "
                f"has NULL contacts_captured (UNMEASURED, not zero).")
            owed.append("contacts (scorecard NULL)")
        else:
            parts.append(f"Contacts: {sc['contacts_captured']} captured "
                         f"({sc['period_start']}..{sc['period_end']}).")
        if sc["revenue_cents"] is None:
            parts.append("Blog revenue: UNKNOWN - scorecard "
                         "revenue_cents NULL (UNMEASURED).")
            owed.append("blog revenue (scorecard NULL)")
        else:
            parts.append(f"Blog revenue: "
                         f"${sc['revenue_cents'] / 100:,.2f}.")
    if g["contacts_matched"] is None:
        parts.append("Tag-match contacts: n/a for this line.")
    else:
        parts.append(
            f"Tag-match contacts: {g['contacts_matched']} of "
            f"{g['contacts_pool']} dealsdesk contacts match "
            f"'{LINES[g['key']]['contact_match']}' in tags/company/notes/"
            f"source (MATCH, not attribution - no per-line column "
            f"exists).")
    parts.append(f"Goals: {g['goals_total']} matching goal rows "
                 f"({g['goals_active']} active).")
    if owed:
        parts.append("OWED: " + "; ".join(owed) + ".")
    else:
        parts.append("OWED: none - every leg measured.")
    brief = "\n".join(parts)
    verdict = (f"{g['name']}: revenue "
               f"{_money(g['revenue_30d'])} 30d / "
               f"{_money(g['revenue_all'])} all-time vs target "
               f"{g['target']}; visits "
               f"{'UNKNOWN' if (sc is None or sc['unique_visits'] is None) else str(sc['unique_visits'])}; "
               f"contacts "
               f"{'UNKNOWN' if (sc is None or sc['contacts_captured'] is None) else str(sc['contacts_captured'])}"
               + (f"; OWED: {', '.join(owed)}" if owed else "; fully measured"))
    return brief, verdict, owed


def probe_id_for(key: str, day: str) -> str:
    return f"standing-compile-{key}-{day}-f{PACKET_FORMAT}"


def build_packet_for(g: dict, day: str, brief: str) -> dict:
    """One B2-standard REAP packet for the line's compile.

    The prompt is the classify template with the compile as the Item
    (v2): a bare brief gets a degenerate echo, not a verdict.
    """
    canonical = f"ki:compile-{g['key']}-{day}"
    title = f"Standing compile: {LINES[g['key']]['name']} - {day}"
    prompt = CLASSIFY_TEMPLATE.format(title=title, text=brief)
    return build_reap_packet(
        prompt, source="standing-compile",
        probe_id=probe_id_for(g["key"], day),
        section="compile", item_ref=canonical)


def file_compile(g: dict, day: str, brief: str, verdict: str,
                 owed: list[str], packet: dict) -> int:
    """File one compile row. Returns 1 landed, 0 already present."""
    canonical = f"ki:compile-{g['key']}-{day}"
    title = f"Standing compile: {g['name']} - {day}"
    note = (f"standing_compile.py B15-1 | probe "
            f"{packet['probe_id']} | prompt ~"
            f"{estimate_tokens(brief)} tok (budget {PROMPT_TOKEN_BUDGET}) "
            f"| max_tokens {packet['max_tokens']} | sources: "
            f"public.money_flow, campaignsdesk.blog_scorecards, "
            f"dealsdesk.contacts, public.goals"
            + (f" | OWED: {', '.join(owed)}" if owed else
               " | OWED: none"))
    return pg_exec(
        f"""insert into {KI} (canonical_id, subject, title, kind,
               status, version, distilled, doc_text, pointer_note)
             values (%s, %s, %s, %s, 'current', 1, %s, %s, %s)
             on conflict (canonical_id) do nothing""",
        (canonical, title, title, KIND, verdict, brief, note))


def compile_lines(keys, dry: bool = False) -> dict:
    day = today_chicago()
    out = {"day": day, "landed": 0, "already": 0, "would_land": 0,
           "lines": {}}
    for key in keys:
        g = gather(key)
        brief, verdict, owed = build_brief(g, day)
        packet = build_packet_for(g, day, brief)
        est = estimate_tokens(brief)
        if est > PROMPT_TOKEN_BUDGET:
            raise ValueError(
                f"{key}: compile prompt ~{est} tok exceeds the "
                f"{PROMPT_TOKEN_BUDGET} prompt budget - split the line")
        if dry:
            already = pg_one(
                f"select count(*) from {KI} where canonical_id = %s",
                (f"ki:compile-{key}-{day}",))
            out["would_land" if not int(already or 0) else "already"] += 1
            out["lines"][key] = {"verdict": verdict, "owed": owed,
                                 "prompt_tokens": est,
                                 "already": bool(int(already or 0))}
            print(f"{key}: would land "
                  f"ki:compile-{key}-{day} (~{est} tok)"
                  + (" (already filed)" if int(already or 0) else ""))
            continue
        n = file_compile(g, day, brief, verdict, owed, packet)
        out["landed" if n == 1 else "already"] += 1
        out["lines"][key] = {"verdict": verdict, "owed": owed,
                             "prompt_tokens": est,
                             "landed": n == 1}
        print(f"{key}: {'landed' if n == 1 else 'already present'} "
              f"ki:compile-{key}-{day} (~{est} tok)")
    return out


def _check_budget(brief: str, key: str) -> int:
    """Prompt budget (B12b, 2000 tok): over it is a blocker, never a send."""
    est = estimate_tokens(brief)
    if est > PROMPT_TOKEN_BUDGET:
        raise ValueError(
            f"{key}: compile prompt ~{est} tok exceeds the "
            f"{PROMPT_TOKEN_BUDGET} prompt budget - split the line")
    return est


def find_dispatch(probe_id: str):
    """Existing bus reap_infer event for a probe_id, or None.

    The idempotency key: one dispatch per line per day, ever.
    """
    rows = pg_rows(
        "select id, status, created_at from bus.events "
        "where event_type = 'reap_infer' and payload->>'probe_id' = %s "
        "order by id desc limit 1", (probe_id,))
    return rows[0] if rows else None


def rebuild_packet(key: str, day: str) -> dict:
    """Rebuild the identical packet from the filed compile row.

    Dispatch never re-gathers: the filed doc_text is the brief, and
    the packet wraps that exact brief in the classify template. A
    line with no filed compile for the day refuses - run --compile
    first.
    """
    canonical = f"ki:compile-{key}-{day}"
    rows = pg_rows(
        f"select doc_text from {KI} where canonical_id = %s",
        (canonical,))
    if not rows or not rows[0][0]:
        raise ValueError(
            f"{key}: no filed compile {canonical} - run --compile first")
    return build_packet_for({"key": key}, day, rows[0][0])


def dispatch_lines(keys, dry: bool = False, day: str | None = None) -> dict:
    """Dispatch each line's packet to gamma REAP. Idempotent per day."""
    day = day or today_chicago()
    out = {"day": day, "dispatched": 0, "already": 0, "would_dispatch": 0,
           "lines": {}}
    for key in keys:
        packet = rebuild_packet(key, day)
        est = _check_budget(packet["prompt"], key)
        existing = find_dispatch(packet["probe_id"])
        if existing:
            eid, st, at = existing
            out["already"] += 1
            out["lines"][key] = {"event_id": int(eid), "status": st,
                                 "already": True, "prompt_tokens": est}
            print(f"{key}: already dispatched (bus event {eid}, "
                  f"status {st}, {at})")
            continue
        if dry:
            out["would_dispatch"] += 1
            out["lines"][key] = {"would_dispatch": True,
                                 "prompt_tokens": est}
            print(f"{key}: would dispatch {packet['probe_id']} "
                  f"(~{est} tok, max_tokens {packet['max_tokens']})")
            continue
        eid = dispatch_reap_packet(packet, source="standing-compile",
                                   priority=3)  # upkeep tier
        out["dispatched"] += 1
        out["lines"][key] = {"event_id": int(eid), "status": "pending",
                             "prompt_tokens": est}
        print(f"{key}: dispatched bus event {eid} "
              f"({packet['probe_id']}, ~{est} tok)")
    return out


def _parse_routing_word(text: str):
    """First-line ROUTING word from a gamma result, or None."""
    if not text:
        return None
    first = text.strip().splitlines()[0]
    m = re.match(r"^ROUTING:\s*([A-Za-z-]+)", first, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _load_knowledge_return():
    """knowledge_return.py as a module (its collector, not its CLI)."""
    here = __file__.rsplit("/", 1)[0]
    spec = importlib.util.spec_from_file_location(
        "knowledge_return", f"{here}/knowledge_return.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_roundtrip(key: str, timeout_s: int = 600,
                    poll_s: int = 15, day: str | None = None) -> dict:
    """Dispatch one line if needed, wait for gamma's verdict, verify
    the return leg.

    The verdict's road back is the outbox inference_result row for
    our bus event; the knowledge_return collector then lands
    ROUTING: intel verdicts as ki:reap-infer-<event> rows and counts
    the rest as skips. Verified means: the outbox result exists, the
    result parsed (ok, one ROUTING line), and the collector processed
    it - landed row present, or a non-intel routing (counted skip).
    An intel verdict with no landed row is NOT verified.
    """
    day = day or today_chicago()
    probe = probe_id_for(key, day)
    existing = find_dispatch(probe)
    if existing:
        event_id = int(existing[0])
        print(f"{key}: using existing dispatch bus event {event_id}")
    else:
        res = dispatch_lines([key], day=day)
        event_id = int(res["lines"][key]["event_id"])
    deadline = time.time() + timeout_s
    result = None
    while time.time() < deadline:
        for (oid, body) in pg_rows(
                "select id, body from successbrian_os.outbox "
                "where source_agent = 'gamma' "
                "and message_type = 'inference_result' "
                "order by id desc limit 200"):
            try:
                env = json.loads(body)
            except (ValueError, TypeError):
                continue
            if isinstance(env, dict) and env.get("event_id") == event_id:
                result = env
                break
        if result is not None:
            break
        time.sleep(poll_s)
    if result is None:
        print(f"{key}: ROUNDTRIP NOT VERIFIED - no outbox result for "
              f"bus event {event_id} within {timeout_s}s")
        return {"verified": False, "event_id": event_id,
                "reason": "no outbox result within timeout"}
    res_dict = result.get("result") or {}
    text = res_dict.get("text") if isinstance(res_dict, dict) else None
    routing = _parse_routing_word(text or "")
    counts = _load_knowledge_return().collect_knowledge_returns(
        verbose=False)
    landed = pg_one(
        f"select count(*) from {KI} where canonical_id = %s",
        (f"ki:reap-infer-{event_id}",))
    landed = int(landed or 0)
    verified = bool(result.get("ok")) and routing is not None and (
        landed >= 1 or routing != "intel")
    print(f"{key}: bus event {event_id} -> outbox ok={result.get('ok')} "
          f"ROUTING: {routing or '(unparsed)'}; collector landed={landed} "
          f"(scanned {counts.get('scanned')}); "
          f"{'ROUNDTRIP VERIFIED' if verified else 'ROUNDTRIP NOT VERIFIED'}")
    return {"verified": verified, "event_id": event_id,
            "routing": routing, "landed": landed,
            "ok": bool(result.get("ok")), "collector": counts}


def status() -> dict:
    total = pg_one(f"select count(*) from {KI} where kind = %s", (KIND,))
    rows = pg_rows(
        f"""select canonical_id, distilled, created_at from {KI}
             where kind = %s order by created_at desc limit 8""",
        (KIND,))
    oldest = pg_one(
        f"""select coalesce(min(created_at)::text, 'none') from {KI}
             where kind = %s""", (KIND,))
    print(f"compile rows: {total} (oldest {oldest})")
    for cid, verdict, at in rows:
        probe = ("standing-compile-" + cid[len("ki:compile-"):]
                 + f"-f{PACKET_FORMAT}")
        disp = find_dispatch(probe)
        d = (f" dispatched event {disp[0]} [{disp[1]}]" if disp
             else " not dispatched")
        print(f"  {cid} [{at}] {verdict[:120]}{d}")
    return {"total": int(total or 0), "rows": rows}


def selftest() -> None:
    steps = []

    # 1. Four lines, each with a stated target and honest categories.
    assert len(LINES) == 4, "four money lines"
    for k, v in LINES.items():
        assert v["target"].startswith(("40 ", "$30", "$20", "~$1")), \
            f"{k}: stated target present"
        assert isinstance(v["revenue_categories"], list), \
            f"{k}: revenue categories are a list"
    steps.append("four money lines with stated targets")

    # 2. Packet ceiling enforced by the shared standard (B2).
    try:
        build_reap_packet("x", source="selftest", probe_id="t",
                          max_tokens=501)
        raise AssertionError("over-ceiling packet must raise")
    except ValueError:
        pass
    steps.append("packet ceiling enforced (501 raises)")

    # 3. All-UNKNOWN gather formats with OWED, invents nothing.
    fake = {"key": "stranger-1k", "name": "Stranger $1k track",
            "target": "~$1,000 in 30 days (stated target)",
            "revenue_30d": None, "revenue_all": None, "revenue_rows": 0,
            "revenue_categories": [], "scorecard": None,
            "scorecard_blog": None, "contacts_matched": None,
            "contacts_pool": 6854, "goals_total": 0, "goals_active": 0}
    brief, verdict, owed = build_brief(fake, "2026-11-13")
    assert "UNKNOWN" in brief and "OWED:" in brief, \
        "unknown legs named OWED"
    assert "$0" not in brief and " 0 " not in verdict, \
        "nothing invented as zero"
    assert len(owed) == 3, f"three owed legs (got {owed})"
    pkt = build_packet_for(fake, "2026-11-13", brief)
    assert pkt["max_tokens"] == 500 and \
        pkt["probe_id"] == "standing-compile-stranger-1k-2026-11-13-f2", \
        "packet shape + probe_id"
    assert pkt["prompt"].startswith("Classify this one item"), \
        "packet is the classify template, not a bare brief"
    assert brief in pkt["prompt"] and \
        "Item title: Standing compile: Stranger $1k track - 2026-11-13" \
        in pkt["prompt"], "template carries the compile as the Item"
    assert estimate_tokens(pkt["prompt"]) <= PROMPT_TOKEN_BUDGET, \
        "wrapped brief inside prompt budget"
    steps.append("all-UNKNOWN brief names OWED, invents nothing")

    # 4. Live landing probe on a disposable row, then idempotency,
    #    then cleanup (knowledge_return selftest pattern).
    probe_day = "selftest-" + datetime.now(CHICAGO).strftime(
        "%Y%m%d%H%M%S")
    g = dict(fake, key="stranger-1k")
    brief2, verdict2, owed2 = build_brief(g, probe_day)
    pkt2 = build_packet_for(g, probe_day, brief2)
    canonical = f"ki:compile-stranger-1k-{probe_day}"
    try:
        n1 = file_compile(g, probe_day, brief2, verdict2, owed2, pkt2)
        assert n1 == 1, "probe row lands"
        row = pg_rows(
            f"select kind, status, distilled, doc_text from {KI} "
            "where canonical_id = %s", (canonical,))
        assert len(row) == 1, "exactly one probe row"
        assert row[0][0] == KIND and row[0][1] == "current", \
            "kind/status stamped"
        assert verdict2[:40] in (row[0][2] or ""), "distilled is verdict"
        assert "STANDING COMPILE" in (row[0][3] or ""), \
            "doc_text is the brief"
        steps.append("live landing probe (row + provenance verified)")
        n2 = file_compile(g, probe_day, brief2, verdict2, owed2, pkt2)
        assert n2 == 0, "second file lands nothing (idempotent)"
        steps.append("idempotency (re-file lands 0)")
        # Residue contract: the B6 leg reads kind='compile'.
        c = pg_one(f"select count(*) from {KI} where kind = %s",
                   (KIND,))
        assert int(c or 0) >= 1, "compile kind visible to residue leg"
        steps.append("residue contract (kind='compile' readable)")
    finally:
        pg_exec(f"delete from {KI} where canonical_id = %s",
                (canonical,))
        gone = pg_one(f"select count(*) from {KI} where canonical_id "
                      "= %s", (canonical,))
        assert int(gone or 0) == 0, "probe row cleaned up"
    steps.append("zero residue (probe row deleted)")

    # 5. Live gather runs read-only and returns all four lines.
    for key in LINES:
        gg = gather(key)
        assert gg["key"] == key and gg["contacts_pool"] > 0, \
            f"{key}: live gather returns a pool"
    steps.append("live gather runs on all four lines")

    # 6. Dispatch rebuilds from the filed row, dry-run inserts
    #    nothing, and the budget refuses an oversized prompt.
    #    (No real bus insert in selftest: the live --roundtrip run
    #    is what proves a packet reaches gamma.)
    probe_day2 = "selftest-" + datetime.now(CHICAGO).strftime(
        "%Y%m%d%H%M%S") + "-d"
    g2 = dict(fake, key="gotbackup")
    brief3, verdict3, owed3 = build_brief(g2, probe_day2)
    pkt3 = build_packet_for(g2, probe_day2, brief3)
    canonical3 = f"ki:compile-gotbackup-{probe_day2}"
    probe3 = probe_id_for("gotbackup", probe_day2)
    try:
        assert find_dispatch(probe3) is None, \
            "probe never dispatched before"
        n3 = file_compile(g2, probe_day2, brief3, verdict3, owed3, pkt3)
        assert n3 == 1, "probe row lands"
        rebuilt = rebuild_packet("gotbackup", probe_day2)
        assert brief3 in rebuilt["prompt"], \
            "rebuilt prompt wraps the filed brief"
        assert rebuilt["prompt"].startswith("Classify this one item"), \
            "rebuilt prompt is the classify template"
        assert rebuilt["probe_id"] == probe3 and \
            rebuilt["max_tokens"] == 500, "rebuilt packet shape"
        assert rebuilt["item_ref"] == canonical3, "rebuilt item_ref"
        dry = dispatch_lines(["gotbackup"], dry=True, day=probe_day2)
        assert dry["would_dispatch"] == 1, "dry-run would dispatch"
        assert find_dispatch(probe3) is None, \
            "dry-run inserts no bus event"
        steps.append("dispatch rebuilds from filed row; dry-run "
                     "inserts nothing")
        try:
            _check_budget("x " * 5000, "gotbackup")
            raise AssertionError("over-budget prompt must raise")
        except ValueError:
            pass
        steps.append("prompt budget refuses oversized dispatch")
        try:
            rebuild_packet("trafficstreemz", probe_day2)
            raise AssertionError("unfiled line must refuse dispatch")
        except ValueError:
            pass
        steps.append("unfiled line refuses dispatch (compile first)")
    finally:
        pg_exec(f"delete from {KI} where canonical_id = %s",
                (canonical3,))
        gone = pg_one(f"select count(*) from {KI} where canonical_id "
                      "= %s", (canonical3,))
        assert int(gone or 0) == 0, "probe row cleaned up"
        assert find_dispatch(probe3) is None, "no bus residue"
    steps.append("zero residue (probe row deleted, bus untouched)")

    print(f"SELFTEST PASS ({len(steps)} steps)")
    for s in steps:
        print(f"  - {s}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--dispatch", action="store_true")
    ap.add_argument("--roundtrip", action="store_true")
    ap.add_argument("--timeout", type=int, default=600,
                    help="roundtrip wait for gamma's verdict (seconds)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--line", choices=list(LINES))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if a.status:
        status()
        return 0
    if a.compile:
        keys = [a.line] if a.line else list(LINES)
        compile_lines(keys, dry=a.dry_run)
        return 0
    if a.dispatch:
        keys = [a.line] if a.line else list(LINES)
        dispatch_lines(keys, dry=a.dry_run)
        return 0
    if a.roundtrip:
        key = a.line or "gotbackup"
        res = check_roundtrip(key, timeout_s=a.timeout)
        return 0 if res["verified"] else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
