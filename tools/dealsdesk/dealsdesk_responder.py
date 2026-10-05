#!/usr/bin/env python3
"""dealsdesk_responder.py — DealsDesk answers the ecosystem's questions autonomously.

PURPOSE: Before any question reaches Brian, DealsDesk tries to answer it
         itself with deterministic routines (solver, market, budget, timing).
         Only questions it cannot answer with fresh data and high confidence
         stay open for the human-facing sweeper.
WHY:     Brian 2026-10-01: DealsDesk should be fully autonomous in answering,
         not just flagging him. Purchases and priority calls still need Brian;
         answers never do.
CALLED BY: question-sweeper.service (runs first, then question_sweeper.py).
NOTES:   Confidence gate is the integrity core: stale data or inconclusive
         rules => no answer, question stays open. Every answer is logged with
         its basis so it can be audited later.
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/dealsdesk_responder.py
    - DEPLOYED COPY: /home/dealsdesk/scripts/dealsdesk_responder.py (k11-alpha; systemd timers).

"""

import logging
import re
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [responder] %(message)s")
LOG = logging.getLogger("responder")

DB_NAME = "ecosystem_central"
DB_USER = "successbrian"


def psql(sql, write=False):
    flag = "-c" if write else "-c"
    cmd = ["psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F\x1f", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        LOG.error("psql failed: %s", r.stderr.strip()[:200])
        return [] if not write else False
    if write:
        return True
    return [l.split("\x1f") for l in r.stdout.strip().split("\n") if l.strip()]


def esc(s):
    return (s or "").replace("'", "''")


def fresh_market():
    """True if market price history is fresh enough to answer pricing questions."""
    rows = psql("""SELECT EXTRACT(EPOCH FROM (NOW() - MAX(observed_at)))/3600
                   FROM dealsdesk.market_price_history""")
    try:
        return float(rows[0][0]) < 36
    except Exception:
        return False


def fresh_feed():
    rows = psql("""SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts)))/3600
                   FROM public.price_history""")
    try:
        return float(rows[0][0]) < 36
    except Exception:
        return False


def answer_deal_check(question):
    """'Is X a deal?' — needs fresh market data and a matching key."""
    if not fresh_market():
        return None  # cannot prove it; stay silent
    m = re.search(r"\$?\d[\d,]*", question)
    keys = psql("""SELECT key, price, source FROM dealsdesk.market_prices
                   ORDER BY updated_at DESC LIMIT 50""")
    ql = question.lower()
    for row in keys:
        key, price, source = (row + ["", "", ""])[:3]
        token = key.replace("_", " ")
        if token and token.split()[0] in ql:
            return (f"Market reference for {key}: ${price} via {source}. "
                    f"Compare the listing against that; 10%+ below the 30-day trend is a deal signal.",
                    "high", f"market_prices.{key}")
    return None


def answer_budget(question):
    """'Can we afford X?' — budget guard projection, always answerable."""
    rows = psql("""SELECT build_id, projected, budget, over_by, checked_at
                   FROM dealsdesk.budget_checks ORDER BY checked_at DESC LIMIT 10""")
    if not rows:
        return None
    def over_by(r):
        try:
            return float(r[3] or 0)
        except (TypeError, ValueError):
            return 0.0
    over = [r for r in rows if over_by(r) > 0]
    if over:
        r = over[0]
        return (f"No — build {r[0]} is projected at ${r[1]} against a ${r[2]} budget, over by ${over_by(r):.2f} (checked {r[4]}).",
                "high", "dealsdesk.budget_checks")
    r = rows[0]
    return (f"Yes — latest check has build {r[0]} projected at ${r[1]} against a ${r[2]} budget, within budget.",
            "high", "dealsdesk.budget_checks")


def answer_timing(question):
    """'Wait or buy?' — triggers and trend signals, needs fresh data."""
    if not (fresh_market() or fresh_feed()):
        return None
    rows = psql("""SELECT key, signal_type, created_at FROM dealsdesk.deal_signals
                   WHERE consumed = FALSE ORDER BY created_at DESC LIMIT 5""")
    if rows:
        s = "; ".join(f"{r[0]}:{r[1]}" for r in rows)
        return (f"Active deal signals: {s}. If your item matches a drop signal, buy; otherwise hold.",
                "high", "dealsdesk.deal_signals")
    return ("No active drop signals; no trigger prices hit. Default: wait.", "medium",
            "dealsdesk.deal_signals empty")


STRATEGIES = [
    (re.compile(r"\bdeal\b|\bworth it\b|\bsteal\b|\bfair price\b", re.I), answer_deal_check),
    (re.compile(r"\bafford\b|\bbudget\b|\bover budget\b", re.I), answer_budget),
    (re.compile(r"\bwait\b|\bbuy now\b|\bwhen.*buy\b|\btiming\b", re.I), answer_timing),
]


def main():
    dry = "--dry-run" in sys.argv
    rows = psql("""SELECT id, asked_by, question FROM successbrian_os.pending_questions
                   WHERE status = 'open' ORDER BY priority ASC, created_at ASC""")
    answered = 0
    for row in rows:
        qid, asked_by, question = (row + ["", "", ""])[:3]
        result = None
        for pattern, fn in STRATEGIES:
            if not pattern.search(question or ""):
                continue
            try:
                result = fn(question)
            except Exception as e:
                LOG.error("strategy failed on q%s: %s", qid, e)
                result = None
            if result:
                text, conf, basis = result
                if dry:
                    LOG.info("dry-run would answer q%s (%s): %s", qid, conf, text[:120])
                else:
                    psql(f"""UPDATE successbrian_os.pending_questions
                             SET status='answered', answer='{esc(text)}',
                                 research_notes=COALESCE(research_notes,'') || '{esc(chr(10)+"[dealsdesk_responder " + conf + " via " + basis + "]")}',
                                 updated_at=NOW() WHERE id={qid}""", write=True)
                    LOG.info("answered q%s with %s confidence (%s)", qid, conf, basis)
                answered += 1
            break  # one strategy per question per run
        if not result and not dry:
            psql(f"""UPDATE successbrian_os.pending_questions
                     SET research_notes=COALESCE(research_notes,'') || '{esc(chr(10)+"[dealsdesk: no confident answer -- needs triage by altair/spencer/meghan]")}',
                         updated_at=NOW() WHERE id={qid}""", write=True)
    LOG.info("responder done: %d answered, %d left open", answered, len(rows) - answered)


if __name__ == "__main__":
    main()
