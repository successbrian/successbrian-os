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
        # Evidence gate (Distillation System design, 2026-11-17):
        # a learning may not exist without evidence. Decisions have
        # the Brian-quote gate; learnings have this one. No evidence
        # entries -> refused, loudly.
        ev = finding.get("evidence") or []
        if not ev:
            raise ValueError("evidence gate: learning filing without "
                             "evidence entries — refused")
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
                    "source, importance, status, evidence, "
                    "valid_from) VALUES (%s, %s, %s, 'unshared', %s, "
                    "now())",
                    (text, "engine_research:" + ptype,
                     finding.get("importance", "normal"),
                     "\n".join(str(e) for e in ev)))
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


OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"


def embed_texts(texts):
    """Embed a list of texts with the local Ollama embedder.
    Returns a list of 768-dim vectors (lists of floats)."""
    import urllib.request as _u
    payload = json.dumps({"model": EMBED_MODEL,
                          "input": texts}).encode()
    req = _u.Request(OLLAMA + "/api/embed", data=payload,
                     headers={"Content-Type": "application/json"})
    with _u.urlopen(req, timeout=120) as r:
        body = json.loads(r.read().decode())
    return body["embeddings"]


def _vec_literal(vec):
    return "[" + ",".join("%.6f" % x for x in vec) + "]"


def embed_backfill(batch=32):
    """Fill NULL embeddings on decisions + learnings. Idempotent —
    safe to run on the bridge cycle. Returns counts filled."""
    filled = {}
    jobs = [
        ("decisions", "altair.brian_decisions",
         "coalesce(question,'') || ' ' || coalesce(answer,'')"),
        ("learnings", "altair.brian_learnings", "content"),
    ]
    for name, table, textexpr in jobs:
        rows = _rows("SELECT id, left(%s, 2000) AS txt FROM %s "
                     "WHERE embedding IS NULL" % (textexpr, table))
        n = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            vecs = embed_texts([r["txt"] or "" for r in chunk])
            for r, v in zip(chunk, vecs):
                _exec("UPDATE %s SET embedding = %s::vector "
                      "WHERE id = %s" % (table, "%s", "%s"),
                      (_vec_literal(v), r["id"]))
                n += 1
        filled[name] = n
    return filled


def dig2(topic, limit=5):
    """Hybrid dig over decisions + learnings: meaning (pgvector
    cosine) + full-text rank + trigram fuzz, fused with reciprocal
    rank fusion. This replaces dig()'s ILIKE-only matching on the
    two curated stores — a ruling filed under different words than
    the question is still findable. Captures still ride keyword
    search (the clerk's own indexes cover them). found=False still
    means UNKNOWN, never a negative."""
    qvec = _vec_literal(embed_texts([topic])[0])
    # Full-text leg needs OR semantics: websearch_to_tsquery ANDs
    # every word, so a natural-language question matches almost
    # nothing (measured 2026-11-17: FTS leg empty on every golden
    # question). Build an OR tsquery from the topic's real words.
    import re as _re
    # Postgres's english tsvector config drops stopwords entirely,
    # so a stopword's document frequency is always 0 — it would
    # look maximally "distinctive" and poison the carrier logic
    # (measured 2026-11-17: "who" became a strong carrier and
    # vetoed the audience ruling). Exclude the full stopword set.
    _stop = {"what", "did", "does", "is", "the", "a", "an", "of",
             "on", "to", "brian", "brians", "about", "should",
             "can", "how", "when", "was", "were", "are", "who",
             "whom", "which", "why", "where", "do", "could",
             "would", "has", "have", "had", "been", "being",
             "this", "that", "it", "its", "as", "at", "by",
             "from", "his", "her", "their", "our", "your", "my",
             "he", "she", "they", "we", "you", "i", "me", "him",
             "them", "us", "am", "be", "not", "no", "if", "then",
             "than", "so", "such", "into", "over", "under",
             "again", "once", "here", "there", "all", "any",
             "both", "each", "few", "more", "most", "other",
             "some", "only", "own", "same", "too", "very",
             "just", "because", "but", "until", "while",
             "during", "before", "after", "above", "below",
             "between", "through", "against", "off", "out",
             "up", "down", "in", "for", "with", "and", "or"}
    _words = [w for w in _re.findall(r"[a-z0-9]+", topic.lower())
              if len(w) >= 3 and w not in _stop]
    or_query = " | ".join(_words) if _words else topic
    fused = {}
    legs = {}

    def add(store, row_id, rank, leg="vec"):
        key = (store, row_id)
        fused[key] = fused.get(key, 0.0) + 1.0 / (60 + rank)
        legs.setdefault(key, set()).add(leg)

    stores = [
        ("decisions", "altair.brian_decisions",
         "id, question, answer, answered_at",
         "coalesce(question,'') || ' ' || coalesce(answer,'')"),
        ("learnings", "altair.brian_learnings",
         "id, content, source, importance, created_at",
         "content"),
    ]
    picked = {"decisions": {}, "learnings": {}}
    for name, table, cols, textexpr in stores:
        extra = (" AND status NOT IN ('discarded')"
                 if name == "learnings" else "")
        for rank, row in enumerate(_rows(
                "SELECT %s FROM %s WHERE embedding IS NOT NULL%s "
                "ORDER BY embedding <=> %%s::vector LIMIT 20"
                % (cols, table, extra), (qvec,)) or []):
            add(name, row["id"], rank, "vec")
            picked[name][row["id"]] = row
        for rank, row in enumerate(_rows(
                "SELECT %s FROM %s WHERE tsv @@ "
                "to_tsquery('english', %%s)%s ORDER BY "
                "ts_rank(tsv, to_tsquery('english', %%s)) "
                "DESC LIMIT 20" % (cols, table, extra),
                (or_query, or_query)) or []):
            add(name, row["id"], rank, "fts")
            picked[name][row["id"]] = row
        # Trigram leg: similarity ranking only, against the row's
        # first 120 chars (its title line). The original design
        # gated on the full topic appearing verbatim (ILIKE) — a
        # natural question never does — and full-text similarity
        # dilutes the title's signal in hundreds of body words.
        for rank, row in enumerate(_rows(
                "SELECT %s FROM %s WHERE similarity(left(%s, 120), "
                "%%s) > 0.05%s ORDER BY similarity(left(%s, 120), "
                "%%s) DESC LIMIT 20"
                % (cols, table, textexpr, extra, textexpr),
                (topic, topic)) or []):
            add(name, row["id"], rank, "tri")
            picked[name][row["id"]] = row
    out = {"topic": topic, "decisions": [], "learnings": []}
    for name in ("decisions", "learnings"):
        ranked = sorted(
            ((score, rid) for (s, rid), score in fused.items()
             if s == name), reverse=True)[:limit]
        fields = (["id", "question", "answer", "answered_at"]
                  if name == "decisions" else
                  ["id", "content", "source", "importance",
                   "created_at"])
        rows = []
        for score, rid in ranked:
            row = dict(picked[name][rid])
            row["score"] = round(score, 4)
            rows.append(row)
        out[name] = _hits(rows, fields + ["score"])
    # Relevance gate (measured on the golden probe set,
    # 2026-11-17): raw vector distance cannot separate known from
    # unknown (good 0.13–0.39, unknown 0.35–0.37 — overlapping),
    # and any single leg corroborates junk. What separated them:
    # a genuinely-matching row is found by the vector leg AND the
    # full-text leg AND the trigram leg; junk nearest-neighbours
    # are vector-only (at most one extra leg). FOUND therefore
    # requires a top row carrying all three legs, or a very strong
    # vector distance (<= 0.25). Otherwise found=False = UNKNOWN,
    # and the returned rows are unvetted neighbours, not evidence.
    # Distinctive-word requirement (second measurement round,
    # 2026-11-17): triple-leg alone still false-positives, because
    # frame words (decide / ruling / gate) appear in hundreds of
    # Brian's rows and corroborate junk. The words that carry a
    # question are its RARE words (in <15% of rows). If the topic
    # has rare words, a top row must actually contain one of them;
    # quantum/bakery/duluth appear in NO row, so those questions
    # are UNKNOWN no matter what the vectors say.
    total_rows = {}
    for name, table, _c, _t in stores:
        total_rows[name] = (_one("SELECT count(*) AS n FROM %s"
                                 % table) or {}).get("n", 0)
    # Carrier words: document frequency < 10% in BOTH stores.
    # (Measured rounds, 2026-11-17: at a 2% threshold the gate
    # misfired — "content" at 1.5% hijacked a question whose real
    # carrier was "audience" at 3%. At 10%: suggestions 0.2%,
    # audience 3%, muse 3%, strata 1% are carriers; ruling 67%,
    # opening 17%, decide 12% are not. Absent words (df 0:
    # quantum, bakery, submarine) are carriers that can never be
    # found in a top row, so those questions stay UNKNOWN.)
    # Two carrier tiers. STRONG (<2% in both stores): the words a
    # question is really about (suggestions 0.2%, xrp, quantum 0%).
    # MID (2–10%): supporting words (audience 3%, buying 5.6%).
    # An absent-word veto was tried and rejected the same night:
    # natural questions carry incidental absent words ("treat",
    # "recommendation") that vetoed true rulings. Instead: when
    # strong words exist, the rare-word match must be a STRONG
    # word — "buying" alone can no longer carry the boat question.
    distinctive = []
    strong = []
    for w in _words:
        worst = 0.0
        for name, table, _c, _t in stores:
            if not total_rows[name]:
                continue
            hit = _one("SELECT count(*) AS n FROM %s WHERE tsv @@ "
                       "to_tsquery('english', %%s)" % table, (w,))
            frac = (hit["n"] / total_rows[name]) if hit else 0.0
            worst = max(worst, frac)
        if worst < 0.10:
            distinctive.append(w)
            if worst < 0.02:
                strong.append(w)
    if strong:
        distinctive = strong
    found_any = False
    for name, table, _cols, _texpr in stores:
        d = _one("SELECT min(embedding <=> %s::vector) AS d FROM "
                 "%s WHERE embedding IS NOT NULL" % ("%s", table),
                 (qvec,))
        best = float(d["d"]) if d and d["d"] is not None else 9.9
        top_ids = [rid for (s, rid), _sc in sorted(
            ((k, v) for k, v in fused.items() if k[0] == name),
            key=lambda kv: -kv[1])[:limit]]
        triple = any({"vec", "fts", "tri"} <= legs.get((name, rid),
                                                       set())
                     for rid in top_ids)
        if distinctive:
            has_rare = False
            for rid in top_ids:
                for w in distinctive:
                    hit = _one("SELECT 1 AS x FROM %s WHERE id = %%s "
                               "AND tsv @@ to_tsquery('english', "
                               "%%s)" % table, (rid, w))
                    if hit:
                        has_rare = True
                        break
                if has_rare:
                    break
            if has_rare and (triple or best <= 0.35):
                found_any = found_any or bool(top_ids)
        elif triple or best <= 0.25:
            found_any = found_any or bool(top_ids)
    out["found"] = found_any
    return out


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
    elif len(sys.argv) >= 3 and sys.argv[1] == "dig2":
        print(json.dumps(dig2(sys.argv[2]), indent=1, default=str))
    elif len(sys.argv) == 2 and sys.argv[1] == "embed-backfill":
        print(embed_backfill())
    elif len(sys.argv) == 2 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    else:
        print("usage: engine_research.py dig <topic> [phrasing ...] | "
              "dig2 <topic> | embed-backfill | selftest")
