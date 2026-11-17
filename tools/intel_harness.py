#!/usr/bin/env python3
"""
Intel Harness — SuccessBrian OS core helpers for the one flow.

Brian's order (2026-11-09 22:30-22:33 CST, Intel Bridge capture #1098):
the system looks at things, finds what it needs to know, FIRST digs into
its existing knowledge to know what it knows, then figures out what it
still needs to know, creates the research, stores the research, and only
then — for questions it cannot resolve — asks Brian simple questions,
one by one.

Placement ruling (Brian, 2026-11-09 22:44-22:45 CST, capture #1105 +
steering): the clerk is part of SuccessBrian OS; the harness is the name
for the FLOW of the whole system — intake -> know -> gap -> research ->
store -> ask — one solid flow. The clerk is the system's
knowledge-tending role inside the flow; the desks are stops in it. This
module is shared code in SBOS core because there is one system, not
because components share a library (shared-functions-once law).

Full spec: ~/successbrian-os/docs/intel-harness-spec.md

This module holds the flow's pure/shared mechanics:
  KNOW      what_do_we_know()      — dig the existing stores first
  RULINGS   find_blocking_ruling() — Brian's rulings as DATA (Q4)
  RESEARCH  time_to_clear()        — the missing computation (DealsDesk
                                     proof instance, capture #1098)
  STORE     signal hits + shelf life (Q3: first source stored at once,
            more agreeing sources = higher signal)
  ASK       ask_gate()             — Brian's standing 5-tries rule
            (2026-10-29): asking is earned after 5 logged attempts and
            the system's own idea outreaches drying up.
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sbos_common import pg_rows
except Exception:  # pragma: no cover - import context only
    pg_rows = None

# ---------------------------------------------------------------------------
# STORE — shelf life. Values mirror board/scatter_clerk.py SHELF_LIFE_DAYS
# (the clerk's own table is the source of truth; the principle is Brian's —
# assess only how long the info is valuable — the numbers are operating
# defaults, not Brian-ruled figures).
# ---------------------------------------------------------------------------
SHELF_LIFE_DAYS = {
    "price": 7,
    "page": 90,
    "video": 180,
    "reference": 90,
}


def valid_until(kind, base=None):
    """Shelf-life expiry for a stored research item of the given kind."""
    base = base or datetime.now(timezone.utc)
    return base + timedelta(days=SHELF_LIFE_DAYS.get(kind, 90))


def agreement_hits(this_median, peer_medians, tol=0.10):
    """Q3 signal strength: 1 + number of independent sources whose median
    agrees with this one within tol (default ±10%). Multiple hits are a
    higher signal of intel (Brian, 2026-11-09 22:37 CST, capture #1101).
    """
    if not this_median:
        return 1
    hits = 1
    for m in peer_medians:
        if m and abs(m - this_median) / this_median <= tol:
            hits += 1
    return hits


# ---------------------------------------------------------------------------
# RESEARCH — time to clear. The computation tonight's P40 verdict needed
# and the ecosystem did not have (capture #1098 capability map).
# ---------------------------------------------------------------------------
def time_to_clear(quantity, sold_count_30d, market_share=1.0):
    """How long a pile of `quantity` units takes to sell.

    market_days assumes the seller captures the ENTIRE market flow at the
    observed rate — the fastest possible clear. effective_days divides by
    market_share (a single seller's plausible share of national flow);
    callers pass their assumption explicitly and label it. Returns a dict;
    days is None when there is no measurable sales velocity.
    """
    if not sold_count_30d or sold_count_30d <= 0:
        return {"per_day": 0.0, "market_days": None, "effective_days": None,
                "basis": "no measurable sales velocity"}
    per_day = sold_count_30d / 30.0
    market_days = quantity / per_day
    share = market_share if market_share and market_share > 0 else 1.0
    return {"per_day": round(per_day, 3),
            "market_days": round(market_days, 1),
            "effective_days": round(market_days / share, 1),
            "basis": f"{sold_count_30d} sold / 30d observed"}


# ---------------------------------------------------------------------------
# RULINGS AS DATA (Q4, capture #1102): one rulings list everything reads.
# The list is altair.brian_decisions. An evaluator must be able to learn
# "Brian ruled this out" from the DATA, not from a hardcoded list.
# ---------------------------------------------------------------------------
_BLOCK_RX = re.compile(
    r"\b(block|blocked|banned|ban|ruled (it )?out|rule out|reject|rejected|"
    r"do not buy|don't buy|never buy|not a buy|no longer|kill|killed|"
    r"off the table|not going there|is out|ruled out)\b", re.I)
_CODE_TOKEN_RX = re.compile(r"^[a-z]{1,3}\d{2,4}$|^\d+(gb|tb)$", re.I)


def _item_tokens(item_text):
    toks = re.findall(r"[a-z0-9]+", (item_text or "").lower())
    return [t for t in toks if len(t) >= 2]


def _about_item(decision_text, tokens):
    """A decision is about the item if a code-like token (p40, v100,
    24gb) hits, or at least two ordinary tokens hit."""
    text = " " + (decision_text or "").lower() + " "
    code_hits = [t for t in tokens
                 if _CODE_TOKEN_RX.match(t) and re.search(r"\b%s\b" % re.escape(t), text)]
    if code_hits:
        return True
    plain_hits = [t for t in tokens if re.search(r"\b%s\b" % re.escape(t), text)]
    return len(plain_hits) >= 2


def decisions_for(item_text, limit=10):
    """All of Brian's decisions whose text is about this item (data read)."""
    if pg_rows is None:
        return []
    tokens = _item_tokens(item_text)
    if not tokens:
        return []
    rows = pg_rows(
        "SELECT decision_id, question, context, answer, answered_at "
        "FROM altair.brian_decisions ORDER BY answered_at DESC NULLS LAST")
    out = []
    for r in rows:
        blob = " ".join(str(x or "") for x in (r[1], r[2], r[3]))
        if _about_item(blob, tokens):
            out.append({"decision_id": r[0], "question": r[1],
                        "context": r[2], "answer": r[3], "answered_at": r[4]})
            if len(out) >= limit:
                break
    return out


def find_blocking_ruling(item_text):
    """Return Brian's blocking decision for this item, read from
    altair.brian_decisions, or None. Blocking = the decision's answer
    carries block language about the item. This is the Q4 citizen: the
    ruling lives in data; code only reads it."""
    for d in decisions_for(item_text):
        if _BLOCK_RX.search(d.get("answer") or ""):
            return d
    return None


# ---------------------------------------------------------------------------
# KNOW — dig existing knowledge before researching anything (the loop's
# first step, Brian's order). Minimal real version: decisions, captures,
# price intel. Phase 2 widens this to the full gateway stores.
# ---------------------------------------------------------------------------
def what_do_we_know(topic, limit=5):
    if pg_rows is None:
        return {"error": "no db access"}
    # RETRIEVE routing (Distillation System design, 2026-11-17):
    # the curated stores are searched through engine_research.dig2
    # (hybrid meaning + full-text + fuzzy, with its measured
    # relevance gate) instead of token matching. found=False from
    # dig2 means UNKNOWN. Falls back to decisions_for if the
    # hybrid path errors — a degraded answer beats no answer, and
    # the fallback is labeled in the result.
    know = {"topic": topic}
    try:
        import engine_research as _er
        d2 = _er.dig2(topic, limit=limit)
        know["decisions"] = d2["decisions"]
        know["learnings"] = d2["learnings"]
        know["found"] = d2["found"]
        know["retrieve"] = "dig2-hybrid"
    except Exception as e:
        know["decisions"] = decisions_for(topic, limit=limit)
        know["learnings"] = []
        know["found"] = bool(know["decisions"])
        know["retrieve"] = "fallback-token (%s)" % str(e)[:80]
    like = "%" + (topic or "") + "%"
    try:
        caps = pg_rows(
            "SELECT id, title FROM atlas.scattered_captures "
            "WHERE title ILIKE %s ORDER BY id DESC LIMIT %s", (like, limit))
        know["captures"] = [{"id": c[0], "title": c[1]} for c in caps]
    except Exception as e:
        know["captures"] = [{"error": str(e)}]
    try:
        pi = pg_rows(
            "SELECT item, amount, checked_on FROM successbrian_os.price_intel "
            "WHERE item ILIKE %s ORDER BY checked_on DESC NULLS LAST LIMIT %s",
            (like, limit))
        know["price_intel"] = [
            {"item": p[0], "amount": float(p[1]) if p[1] is not None else None,
             "checked_on": str(p[2])} for p in pi]
    except Exception as e:
        know["price_intel"] = [{"error": str(e)}]
    know["gap"] = ("nothing on record" if not know["decisions"]
                   and not know.get("captures") else "see stores above")
    return know


# ---------------------------------------------------------------------------
# ASK — Brian's standing gate (2026-10-29): the ecosystem may ask Brian
# only when BOTH hold: (1) it has tried 5 times (five logged attempts /
# dead ways) without success, AND (2) its own outreaches for new ideas
# are starting to dry up. Questions then arrive simple, one by one.
# ---------------------------------------------------------------------------
ASK_GATE_TRIES = 5


def ask_gate(attempts_logged, ideas_drying_up):
    return attempts_logged >= ASK_GATE_TRIES and bool(ideas_drying_up)


# ---------------------------------------------------------------------------
def selftest():
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    ttc = time_to_clear(10, 41)
    check("time_to_clear math (10 units @41/30d = 7.3 market days)",
          ttc["market_days"] == 7.3 and ttc["per_day"] == 1.367)
    ttc2 = time_to_clear(10, 41, market_share=0.25)
    check("time_to_clear share adjustment (29.3 effective days)",
          ttc2["effective_days"] == 29.3)
    check("time_to_clear no velocity", time_to_clear(5, 0)["market_days"] is None)
    check("agreement_hits (303 vs [293, 500] -> 2)",
          agreement_hits(303, [293, 500]) == 2)
    check("ask_gate closed at 4 tries", ask_gate(4, True) is False)
    check("ask_gate closed when ideas still flowing", ask_gate(7, False) is False)
    check("ask_gate opens at 5 tries + dry", ask_gate(5, True) is True)
    check("block language classifier",
          bool(_BLOCK_RX.search("Block the P40. We ruled it out."))
          and not _BLOCK_RX.search("M40 stays. Buy 7 more."))

    if pg_rows is not None:
        try:
            d = find_blocking_ruling("Tesla P40 24GB")
            check("rulings reader: P40 blocked FROM DATA (altair.brian_decisions)",
                  d is not None and "p40" in (d["decision_id"] or "").lower())
            know = what_do_we_know("P40")
            check("know step returns stores", "decisions" in know and "captures" in know)
        except Exception as e:
            check("db-backed selftest (%s)" % e, False)
    else:
        print("SKIP db-backed checks (sbos_common unavailable)")

    print("INTEL-HARNESS SELFTEST " + ("FAIL: " + ", ".join(fails) if fails else "PASS"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest())
