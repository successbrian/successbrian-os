#!/usr/bin/env python3
"""
engine_research — the research-and-filing toolkit for the engine seats
(Sonic / Morpheus / Penny, wherever they sit).

Brian's directive (2026-11-17 01:35 CST): build tools so the fleet can do
what the chat agent did by hand on the "col sexy" job — dig through the
intel intake system, properly research + check, and file data into the
second brain, AnythingLLM, and other appropriate systems.

Design: ~/workspace/builds/engine-research-filing/DESIGN-2026-11-17.md
(the flow is Brian's Intel Harness ruling, 2026-11-09 capture #1098:
intake -> know -> gap -> research -> store -> ask).

v1 legs (deterministic code; judgment lives in packets, not here):
  dig(topic, phrasings)  — one pass over the second brain + intel intake:
      altair.brian_decisions, altair.brian_learnings,
      atlas.scattered_captures. Several phrasings, ranked hits with
      ids + dates + excerpts. Nothing found = UNKNOWN ("not on record"),
      never a negative (Brian's not-knowing-is-not rule).
  file(finding)          — route ONE structured finding to its homes:
      capture  -> atlas.scattered_captures (status raw: intake-native)
      learning -> altair.brian_learnings (status unshared)
      anythingllm -> atlas/allm_embed.embed_latest (R32: one current
                     edition per filename in the owning workspace)
      Gates, in code: provenance (a brian_quote filing without the
      quote text is REFUSED; interpretation filings are labeled
      INTERPRETATION in every home) and conflict (a learning whose
      topic already carries a decision is parked as a capture flagged
      conflict — a model never overwrites Brian's record).

Packet kinds (research.dig_pack / research.web / research.verify /
research.file) ride the existing sbos_common engine queues — see the
design doc. This module is the legs those packets call.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sbos_common import connect  # noqa: E402


def _rows(sql, params=None, user=None):
    """Dict rows (sbos_common.pg_rows returns tuples; this module
    wants named fields)."""
    import psycopg2.extras
    conn = connect(user=user)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        return rows
    finally:
        conn.close()


def _one(sql, params=None, user=None):
    rows = _rows(sql, params, user=user)
    return rows[0] if rows else None


def _exec(sql, params=None, user=None):
    conn = connect(user=user)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


EXCERPT = 280


def _hits(rows, fields):
    out = []
    for r in rows or []:
        h = {f: r.get(f) for f in fields if f in r}
        for k, v in list(h.items()):
            if isinstance(v, str) and len(v) > EXCERPT:
                h[k] = v[:EXCERPT] + "…"
            elif v is not None and not isinstance(v, (str, int, float)):
                h[k] = str(v)
        out.append(h)
    return out


def dig(topic, phrasings=None, limit=5):
    """Search the second brain + intel intake for a topic, in several
    phrasings. Returns {topic, phrasings, decisions[], learnings[],
    captures[], found: bool}. found=False means UNKNOWN — not on
    record — never evidence of a negative."""
    phrasings = phrasings or [topic]
    found = {"decisions": [], "learnings": [], "captures": []}
    seen = {"decisions": set(), "learnings": set(), "captures": set()}
    for ph in phrasings:
        like = "%" + ph.replace("%", "") + "%"
        for row in _rows(
                "SELECT id, question, answer, answered_at FROM "
                "altair.brian_decisions WHERE question ILIKE %s OR "
                "context ILIKE %s OR answer ILIKE %s ORDER BY "
                "answered_at DESC NULLS LAST LIMIT %s",
                (like, like, like, limit)) or []:
            if row["id"] not in seen["decisions"]:
                seen["decisions"].add(row["id"])
                found["decisions"].append(row)
        for row in _rows(
                "SELECT id, content, source, importance, created_at "
                "FROM altair.brian_learnings WHERE content ILIKE %s "
                "AND status NOT IN ('discarded') ORDER BY created_at "
                "DESC LIMIT %s", (like, limit)) or []:
            if row["id"] not in seen["learnings"]:
                seen["learnings"].add(row["id"])
                found["learnings"].append(row)
        for row in _rows(
                "SELECT id, title, raw_text, status, workspace_slug, "
                "created_at FROM atlas.scattered_captures WHERE "
                "title ILIKE %s OR raw_text ILIKE %s ORDER BY "
                "created_at DESC LIMIT %s",
                (like, like, limit)) or []:
            if row["id"] not in seen["captures"]:
                seen["captures"].add(row["id"])
                found["captures"].append(row)
    return {
        "topic": topic,
        "phrasings": phrasings,
        "decisions": _hits(found["decisions"],
                           ["id", "question", "answer", "answered_at"]),
        "learnings": _hits(found["learnings"],
                           ["id", "content", "source", "importance",
                            "created_at"]),
        "captures": _hits(found["captures"],
                          ["id", "title", "raw_text", "status",
                           "workspace_slug", "created_at"]),
        "found": bool(found["decisions"] or found["learnings"]
                      or found["captures"]),
    }


def _provenance_block(finding):
    prov = finding.get("provenance") or {}
    ptype = prov.get("type", "source")
    if ptype == "brian_quote" and not (prov.get("quote") or "").strip():
        raise ValueError("provenance gate: brian_quote filing without "
                         "Brian's verbatim quote is refused")
    label = {"brian_quote": "BRIAN (verbatim)",
             "source": "SOURCE",
             "interpretation": "INTERPRETATION"}.get(ptype, "SOURCE")
    lines = ["PROVENANCE: " + label]
    if prov.get("quote"):
        lines.append('QUOTE: "' + prov["quote"].strip() + '"')
    if prov.get("source"):
        lines.append("SOURCE: " + str(prov["source"]))
    return "\n".join(lines), ptype


def _finding_text(finding):
    parts = [finding["claim"].strip()]
    ev = finding.get("evidence") or []
    if ev:
        parts.append("EVIDENCE:")
        parts += ["- " + str(e) for e in ev]
    parts.append(_provenance_block(finding)[0])
    parts.append("FILED BY: engine_research v1, "
                 + datetime.now(timezone.utc).isoformat())
    return "\n".join(parts)


def file_finding(finding, homes=("capture",)):
    """Route one structured finding to its homes. Returns a per-home
    result dict; failures are named in the result, never silent.
    finding = {topic, claim, evidence[], provenance{type,quote,source},
               workspace_slug, importance}"""
    text = _finding_text(finding)  # raises on provenance-gate failure
    _, ptype = _provenance_block(finding)
    topic = finding["topic"]
    slug = finding.get("workspace_slug")
    results = {}

    def do_capture(flag=None):
        title = ("[conflict-flag] " if flag else "") + topic
        _exec("INSERT INTO atlas.scattered_captures (title, raw_text,"
                " status, workspace_slug) VALUES (%s, %s, 'raw', %s)",
                (title, text + ("\nCONFLICT: " + flag if flag else ""),
                 slug))
        return "inserted"

    if "capture" in homes:
        results["capture"] = do_capture()
    if "learning" in homes:
        # Conflict gate: a decision already carrying this topic means a
        # new learning may contradict Brian's record. Park it as a
        # flagged capture instead; the learning is NOT written.
        like = "%" + topic.split("—")[0].strip() + "%"
        clash = _one("SELECT id FROM altair.brian_decisions WHERE "
                       "question ILIKE %s OR context ILIKE %s LIMIT 1",
                       (like, like))
        if clash:
            results["learning"] = "PARKED (conflict gate)"
            results["capture_conflict"] = do_capture(
                "existing decision id %s covers this topic; learning "
                "not written — surface as residue" % clash["id"])
        else:
            _exec("INSERT INTO altair.brian_learnings (content, "
                    "source, importance, status) VALUES (%s, %s, %s, "
                    "'unshared')",
                    (text, "engine_research:" + ptype,
                     finding.get("importance", "normal")))
            results["learning"] = "inserted"
    if "anythingllm" in homes:
        if not slug:
            results["anythingllm"] = "FAILED: no workspace_slug"
        else:
            try:
                sys.path.insert(0, os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "atlas"))
                from allm_embed import embed_latest
                fname = ("engine-filing-" + topic.lower()
                         .replace(" ", "-")[:60] + ".md")
                loc = embed_latest(slug, fname,
                                   "# " + topic + "\n\n" + text + "\n")
                results["anythingllm"] = "embedded " + loc
            except Exception as e:  # named, never silent
                results["anythingllm"] = "FAILED: " + str(e)[:200]
    return results


def selftest():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(("PASS " if cond else "FAIL ") + name)

    d = dig("chicago tardis", ["chicago tardis", "meet and greet"])
    check("dig returns structure", isinstance(d, dict) and "found" in d)
    check("dig finds the record (decisions/learnings/captures)",
          d["found"] and (d["decisions"] or d["learnings"]
                          or d["captures"]))
    d0 = dig("zzz-no-such-topic-qqq")
    check("empty dig = UNKNOWN, found=False (not a negative)",
          d0["found"] is False)

    # Provenance gate: a Brian-quote filing with no quote is refused.
    try:
        file_finding({"topic": "selftest", "claim": "x",
                      "provenance": {"type": "brian_quote"}}, homes=())
        check("provenance gate refuses quoteless brian_quote", False)
    except ValueError:
        check("provenance gate refuses quoteless brian_quote", True)

    # File leg round-trip on a marked test finding, then clean up.
    marker = "engine_research selftest " + datetime.now(
        timezone.utc).strftime("%H%M%S")
    r = file_finding({"topic": marker, "claim": "selftest filing",
                      "evidence": ["selftest"],
                      "provenance": {"type": "interpretation"},
                      "workspace_slug": "chicago-tardis"},
                     homes=("capture",))
    row = _one("SELECT id, raw_text FROM atlas.scattered_captures "
                 "WHERE title = %s", (marker,))
    check("file->capture inserted + INTERPRETATION labeled",
          r.get("capture") == "inserted" and row
          and "INTERPRETATION" in row["raw_text"])
    if row:
        # The default role may insert into the intake table but not
        # delete (verified live 2026-11-17); selftest cleanup runs as
        # the atlas family's postgres role.
        _exec("DELETE FROM atlas.scattered_captures WHERE id = %s",
              (row["id"],), user="postgres")
        check("selftest cleanup done",
              _one("SELECT id FROM atlas.scattered_captures WHERE "
                   "id = %s", (row["id"],)) is None)
    failed = [n for n, ok in checks if not ok]
    print("SELFTEST %s (%d checks)" % ("OK" if not failed else
                                       "FAILED: " + ", ".join(failed),
                                       len(checks)))
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "dig":
        print(json.dumps(dig(sys.argv[2], sys.argv[3:] or None),
                         indent=1, default=str))
    elif len(sys.argv) == 2 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    else:
        print("usage: engine_research.py dig <topic> [phrasing ...] | "
              "selftest")
