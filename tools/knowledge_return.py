#!/usr/bin/env python3
"""knowledge_return.py - Knowledge-return collector v1 (BUILD_QUEUE B3).

Brian directive 2026-11-13: feed DeepSeek REAP 150B (gamma) the right
intel in runway-sized packets and RETURN its knowledge to the ecosystem.
The road out is bus.events reap_infer -> gamma; the road back is
successbrian_os.outbox inference_result rows. This tool lands the
return leg: every gamma verdict of ROUTING: intel becomes one
provenance-stamped row in successbrian_os.knowledge_index, so the
second brain holds what REAP judged worth keeping.

What lands (v1):
  - canonical_id  ki:reap-infer-<event_id>  (PK; re-runs land nothing new)
  - subject/title the "Item title:" from the reap event's prompt
  - kind          reap-inference, status current, version 1
  - distilled     the REAP verdict line itself (ROUTING: intel - reason)
  - doc_text      the "Item text:" from the prompt, HTML-stripped
  - pointer_note  provenance: gamma outbox id, reap event id, probe_id,
                  engine, wall time, tokens, verdict timestamp
  - source_capture_id is NULL in v1: reap payloads carry no capture id;
    the probe_id in pointer_note names the feeder that sent the item.

DELIVERY STAMP (2026-11-19, friction #54): every row this collector
scans gets a terminal disposition here — landed, already-landed, or
a counted skip — so a non-dry collect stamps delivered_at on every
scanned row still unstamped. Until this fix the two consumers of
inference_result rows (this collector and verdict_applier) read
them but never marked them, so all 1,144 rows sat 'undelivered'
forever and the bus read as write-only. verdict_applier selects
its rows independently of the stamp (30-day window, by event), so
stamping never starves it.

What does NOT land: ROUTING: discard / kick-aside (counted, skipped),
ROUTING: board (counted, skipped — a board verdict needs a person; a
later item routes board verdicts to the decision queue), failed events
(ok != true), and results with no ROUTING line (investigation sections
and deep-prompt returns use other collectors). Skips are counted, never
silent.

Usage:
  python3 knowledge_return.py collect [--dry] [--limit N] [--json]
  python3 knowledge_return.py status [--json]
  python3 knowledge_return.py selftest

Exit codes: 0 ok; 1 refused / not found; 2 usage or store errors.
Nothing in this module sends, buys, publishes, or contacts anyone — it
only reads the operator's own outbox/bus and writes knowledge_index.
"""
import argparse
import html
import json
import re
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

SCHEMA = "successbrian_os"
KIND = "reap-inference"
MAX_TITLE = 200
MAX_DOC = 4000
SELFTEST_PROBE = "knowledge-return-selftest"

ROUTING_RE = re.compile(
    r"^ROUTING:\s*([A-Za-z-]+)\s*(?:-\s*(.+))?$", re.IGNORECASE)
ITEM_RE = re.compile(
    r"Item title:\s*(.*?)\s*Item text:\s*(.*)$", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _parse_routing(text: str):
    """'ROUTING: intel - reason' -> ('intel', 'reason'); the reason is
    optional — early verdicts were a bare 'ROUTING: intel'. Else None."""
    if not text:
        return None
    m = ROUTING_RE.match(text.strip().splitlines()[0])
    if not m:
        return None
    return (m.group(1).lower(), (m.group(2) or "").strip())


def _strip_html(text: str) -> str:
    """Drop tags, unescape entities, collapse whitespace."""
    if not text:
        return ""
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", text))).strip()


def _extract_item(prompt: str):
    """(title, item_text) from a reap classify prompt; ('', '') if absent."""
    if not prompt:
        return ("", "")
    m = ITEM_RE.search(prompt)
    if not m:
        return ("", "")
    return (m.group(1).strip(), _strip_html(m.group(2)))


def _parse_reap_body(body: str):
    """Outbox envelope -> (event_id, ok, result_text, result_dict) or None."""
    try:
        env = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(env, dict):
        return None
    try:
        eid = int(env.get("event_id"))
    except (TypeError, ValueError):
        return None
    result = env.get("result") or {}
    text = result.get("text") if isinstance(result, dict) else None
    return (eid, bool(env.get("ok")), text, result
            if isinstance(result, dict) else {}, env.get("at"))


def collect_knowledge_returns(dry: bool = False, limit: int | None = None,
                              verbose: bool = True) -> dict:
    """Land gamma ROUTING: intel verdicts into knowledge_index.

    Idempotent on canonical_id ki:reap-infer-<event_id>. dry=True
    rehearses only: it reports what would land and writes nothing."""
    rows = pg_rows(
        f"""select id, body from {SCHEMA}.outbox
             where source_agent = 'gamma'
               and message_type = 'inference_result'
             order by id""")
    if limit is not None:
        rows = rows[:limit]
    out = {"scanned": 0, "landed": 0, "already_landed": 0,
           "would_land": 0, "skipped_discard": 0, "skipped_kick_aside": 0,
           "skipped_board": 0, "skipped_failed": 0,
           "skipped_unparseable": 0, "skipped_no_routing": 0,
           "delivered_stamped": 0}
    # Event prompts in one query: the item title/text live there.
    eids = []
    parsed = []
    for (oid, body) in rows:
        p = _parse_reap_body(body)
        if p is None:
            out["scanned"] += 1
            out["skipped_unparseable"] += 1
            continue
        parsed.append((oid, p))
        eids.append(p[0])
    prompts = {}
    if eids:
        for (eid, prompt, probe) in pg_rows(
                "select id, payload->>'prompt', payload->>'probe_id' "
                "from bus.events where id = any(%s)", (eids,)):
            prompts[eid] = (prompt or "", probe or "")
    for (oid, (eid, ok, text, result, at)) in parsed:
        out["scanned"] += 1
        if not ok:
            out["skipped_failed"] += 1
            continue
        routing = _parse_routing(text or "")
        if routing is None:
            out["skipped_no_routing"] += 1
            continue
        word, reason = routing
        if word == "discard":
            out["skipped_discard"] += 1
            continue
        if word == "kick-aside":
            out["skipped_kick_aside"] += 1
            continue
        if word == "board":
            out["skipped_board"] += 1
            continue
        if word != "intel":
            out["skipped_no_routing"] += 1
            continue
        canonical = f"ki:reap-infer-{eid}"
        prompt, probe = prompts.get(eid, ("", ""))
        title, item_text = _extract_item(prompt)
        verdict = (text or "").strip().splitlines()[0]
        subject = title or reason or f"reap-infer event {eid}"
        subject = subject[:MAX_TITLE]
        doc = item_text or verdict
        doc = doc[:MAX_DOC]
        note = (f"gamma outbox id {oid} | reap event {eid} "
                f"| probe {probe or 'unknown'} | engine "
                f"{result.get('engine', 'reap')} | "
                f"wall {result.get('wall_s', '?')}s, "
                f"{result.get('tokens', '?')} tok"
                + (f" | {at}" if at else "")
                + (" | bus event row missing; title/text unavailable"
                   if eid not in prompts else ""))
        if dry:
            already = pg_one(
                f"""select count(*) from {SCHEMA}.knowledge_index
                     where canonical_id = %s""", (canonical,))
            if int(already or 0):
                out["already_landed"] += 1
            else:
                out["would_land"] += 1
                if verbose:
                    print(f"event {eid}: would land {canonical} "
                          f"({subject[:80]})")
            continue
        n = pg_exec(
            f"""insert into {SCHEMA}.knowledge_index
                   (canonical_id, subject, title, kind, status, version,
                    distilled, doc_text, pointer_note)
                 values (%s, %s, %s, %s, 'current', 1, %s, %s, %s)
                 on conflict (canonical_id) do nothing""",
            (canonical, subject, subject, KIND, verdict, doc, note))
        if n == 1:
            out["landed"] += 1
            if verbose:
                print(f"event {eid}: landed {canonical}")
        else:
            out["already_landed"] += 1
    if not dry and rows:
        oids = [oid for (oid, _body) in rows]
        n = pg_exec(
            f"update {SCHEMA}.outbox set delivered_at = now() "
            f"where id = any(%s) and delivered_at is null", (oids,))
        out["delivered_stamped"] = int(n or 0)
    return out


def status(verbose: bool = True) -> dict:
    """One-screen state of the return leg."""
    total = pg_one(
        f"""select count(*) from {SCHEMA}.outbox
             where source_agent = 'gamma'
               and message_type = 'inference_result'""")
    intel = pg_one(
        f"""select count(*) from {SCHEMA}.outbox
             where source_agent = 'gamma'
               and message_type = 'inference_result'
               and body like '%ROUTING: intel%'""")
    landed = pg_one(
        f"""select count(*) from {SCHEMA}.knowledge_index
             where kind = %s""", (KIND,))
    latest = pg_one(
        f"""select coalesce(max(created_at)::text, 'none')
             from {SCHEMA}.outbox
             where source_agent = 'gamma'
               and message_type = 'inference_result'""")
    out = {"outbox_results": int(total or 0),
           "intel_verdicts": int(intel or 0),
           "landed": int(landed or 0),
           "unlanded_intel": int(intel or 0) - int(landed or 0),
           "latest_result": latest}
    if verbose:
        print("KNOWLEDGE RETURN STATUS")
        for k, v in out.items():
            print(f"  {k}: {v}")
    return out


def selftest() -> None:
    """Pure-function checks + live landing proof on disposable rows
    (fabricated bus events + outbox rows; gamma never runs)."""
    steps = []
    assert _parse_routing("ROUTING: intel - worth filing.") == (
        "intel", "worth filing."), "intel verdict parses"
    assert _parse_routing("ROUTING: discard - internal noise.") == (
        "discard", "internal noise."), "discard verdict parses"
    assert _parse_routing("ROUTING: board - needs a person.") == (
        "board", "needs a person."), "board verdict parses"
    assert _parse_routing("ROUTING: intel") == ("intel", ""), \
        "bare early-format verdict parses (no reason)"
    assert _parse_routing("WHAT: not a routing") is None, \
        "section text is not a routing"
    assert _parse_routing("") is None, "empty text is not a routing"
    assert _parse_routing('{"result": {}}') is None, \
        "non-routing line is not a routing"
    steps.append("routing parser (intel/discard/board/non-routing)")
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world", \
        "tags strip, text kept"
    assert _strip_html("a &amp; b") == "a & b", "entities unescape"
    title, text = _extract_item(
        "preamble Item title: My Title Here. Item text: <p>Body text</p>")
    assert title == "My Title Here.", "item title extracts"
    assert text == "Body text", "item text extracts + strips"
    assert _extract_item("no item markers here") == ("", ""), \
        "prompt without item markers extracts empty"
    steps.append("item extraction (title/text, html strip, absent markers)")
    assert _parse_reap_body("not json") is None, "bad body parses to None"
    assert _parse_reap_body('{"event_id": "x"}') is None, \
        "body without numeric event_id parses to None"
    steps.append("outbox envelope parsing (bad json, bad event id)")

    # Live landing, end-to-end on disposable rows.
    fake_ev = fake_ev2 = None
    try:
        fake_ev = pg_one(
            "insert into bus.events (event_type, source, target, "
            "priority, payload, status) values ('reap_infer', %s, "
            "'gamma', %s, %s, 'done') returning id",
            ("spencer-selftest", 5,
             Json({"probe_id": SELFTEST_PROBE,
                   "prompt": "classify Item title: SELFTEST title here. "
                             "Item text: <p>SELFTEST body text</p>",
                   "thinking": False, "max_tokens": 100})))
        pg_exec(
            "insert into successbrian_os.outbox (source_agent, "
            "message_type, subject, body) values ('gamma', "
            "'inference_result', %s, %s)",
            (f"gamma: event {fake_ev} done (reap_infer)",
             json.dumps({"event_id": fake_ev, "event_type": "reap_infer",
                         "ok": True,
                         "result": {"text": "ROUTING: intel - SELFTEST "
                                            "verdict reason.",
                                    "tokens": 9, "wall_s": 1.5,
                                    "engine": "reap"},
                         "node": "gamma",
                         "at": "2026-11-13T13:45:00Z"})))
        dry = collect_knowledge_returns(dry=True, verbose=False)
        assert dry["would_land"] >= 1, \
            "dry rehearsal reports the landable intel verdict"
        gone = pg_one(
            "select count(*) from successbrian_os.knowledge_index "
            "where canonical_id = %s", (f"ki:reap-infer-{fake_ev}",))
        assert int(gone or 0) == 0, "dry collector writes nothing"
        steps.append("collector dry rehearsal (would land, writes nothing)")

        live = collect_knowledge_returns(verbose=False)
        assert live["landed"] >= 1, "live collector lands the verdict"
        row = pg_rows(
            "select subject, title, kind, status, distilled, doc_text, "
            "pointer_note from successbrian_os.knowledge_index "
            "where canonical_id = %s", (f"ki:reap-infer-{fake_ev}",))
        assert len(row) == 1, "exactly one knowledge row lands"
        subject, title, kind, status, distilled, doc, note = row[0]
        assert subject == "SELFTEST title here.", \
            f"subject is the item title (got {subject!r})"
        assert kind == KIND and status == "current", \
            "kind/status stamped"
        assert distilled.startswith("ROUTING: intel - SELFTEST"), \
            "distilled is the verdict line"
        assert "SELFTEST body text" in (doc or ""), \
            "doc_text is the stripped item text"
        assert f"reap event {fake_ev}" in (note or "") \
            and SELFTEST_PROBE in (note or ""), \
            "pointer_note carries provenance"
        steps.append("collector live landing (row + provenance verified)")

        again = collect_knowledge_returns(verbose=False)
        assert again["landed"] == 0, \
            "second run lands nothing new (idempotent)"
        assert again["already_landed"] >= 1, \
            "second run counts the row as already landed"
        steps.append("collector idempotency (re-run lands 0)")

        # A discard verdict on a second fake event must NOT land.
        fake_ev2 = pg_one(
            "insert into bus.events (event_type, source, target, "
            "priority, payload, status) values ('reap_infer', %s, "
            "'gamma', %s, %s, 'done') returning id",
            ("spencer-selftest", 5,
             Json({"probe_id": SELFTEST_PROBE,
                   "prompt": "classify Item title: SELFTEST discard. "
                             "Item text: <p>noise</p>",
                   "thinking": False, "max_tokens": 100})))
        pg_exec(
            "insert into successbrian_os.outbox (source_agent, "
            "message_type, subject, body) values ('gamma', "
            "'inference_result', %s, %s)",
            (f"gamma: event {fake_ev2} done (reap_infer)",
             json.dumps({"event_id": fake_ev2, "event_type": "reap_infer",
                         "ok": True,
                         "result": {"text": "ROUTING: discard - SELFTEST "
                                            "internal noise.",
                                    "tokens": 9, "wall_s": 1.5,
                                    "engine": "reap"},
                         "node": "gamma",
                         "at": "2026-11-13T13:45:00Z"})))
        after = collect_knowledge_returns(verbose=False)
        assert after["landed"] == 0, "discard verdict lands nothing"
        assert after["skipped_discard"] >= 1, "discard is counted"
        gone2 = pg_one(
            "select count(*) from successbrian_os.knowledge_index "
            "where canonical_id = %s", (f"ki:reap-infer-{fake_ev2}",))
        assert int(gone2 or 0) == 0, "no knowledge row for a discard"
        steps.append("discard verdict skipped + counted (no row)")
    finally:
        for ev in (fake_ev, fake_ev2):
            if ev:
                pg_exec(
                    "delete from successbrian_os.knowledge_index "
                    "where canonical_id = %s", (f"ki:reap-infer-{ev}",))
                pg_exec("delete from bus.events where id = %s", (ev,))
                pg_exec(
                    "delete from successbrian_os.outbox where subject = %s",
                    (f"gamma: event {ev} done (reap_infer)",))
    print(f"SELFTEST PASS ({len(steps)} steps)")
    for s in steps:
        print(f"  - {s}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="land intel verdicts")
    c.add_argument("--dry", action="store_true")
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("status", help="return-leg state")
    s.add_argument("--json", action="store_true")
    sub.add_parser("selftest", help="run the selftest")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "collect":
            out = collect_knowledge_returns(dry=a.dry, limit=a.limit)
            if a.json:
                print(json.dumps(out, indent=2))
            else:
                print("COLLECT " + ("DRY " if a.dry else "")
                      + json.dumps(out))
            return 0
        if a.cmd == "status":
            out = status()
            if a.json:
                print(json.dumps(out, indent=2))
            return 0
        if a.cmd == "selftest":
            selftest()
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
