#!/usr/bin/env python3
"""The Mull — the ecosystem keeps improving the Fragment Pipeline design.

Brian (2026-10-24): the whole chain — scraping -> intel discovery ->
finding pain points -> finding ALL the intel in a scrape, including
potential 'hidden' intel -> identifying what goes into the database ->
identifying whether enrichment or additional research is needed —
"i need the ecosystem to keep mulling this over and helping me make
it better."

How it works, on machinery that already exists:

  WEEKLY (cron, Fridays 06:10): this script files ONE Morpheus
  judgment step carrying a compact summary of the design and ONE
  rotating standing question. Morpheus answers in the open (a JSON
  contract: improvement / why / cost_or_risk / confidence) whenever
  the judgment worker reaches it.

  PROMOTION: on each run, the script first looks for the previous
  mull step's finished answer and promotes it into a 'review' PM
  step. Altair's heartbeat pitch-in claims review steps: at >=90%
  certainty he adopts or files the follow-up himself; below that it
  parks in held_brian with his assessment — so proposals reach Brian
  only when they deserve to, and every one is decided in the stream.

  Nothing about the design changes silently: a proposal is a PM
  step with a decision trail, and the canonical document changes
  only when a ruling says so (then it is re-embedded, one copy).
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

DESIGN_SUMMARY = (
    "THE FRAGMENT PIPELINE (design, 2026-10-24). Chain: scraping -> "
    "intel discovery -> finding pain points -> finding ALL the intel "
    "in a scrape, including potential 'hidden' intel -> identifying "
    "what goes into the database -> identifying whether enrichment "
    "or additional research is needed. Layers: SCAN (scrapers/"
    "SearXNG) -> EXTRACT (Penny, Qwen2.5-7B, at the edge on DDR4 "
    "nodes; fragments ship home, raw pages don't) -> DECIDE (per-"
    "fragment: keep / investigate-more / discard). Extraction of an "
    "unknown source = a nine-lens battery (people, organizations, "
    "products, relationships, places, dates & events, money & "
    "offers, claims, questions & pain) + a sweep pass; contacts and "
    "links are pulled by code. Fragments carry source provenance "
    "and a fingerprint (unique is computed, not assumed). Known "
    "sources graduate to per-family SCHEMAS + deterministic scripts "
    "(fast path; Penny reads only the prose residue); a drift guard "
    "watches field yields. A THREAD WALKER treats multipage forum "
    "threads as one unit, walking to the resolution and harvesting "
    "community confirmations. Fragments are tagged NEED (pains) or "
    "OFFER (answers). A MATCHER on the record side joins needs to "
    "offers across the whole store (scored: product fit, place fit, "
    "freshness, graph proximity); pairs become PM steps. An "
    "unmatched recent relevant loud pain files its own RESEARCH "
    "request (known intel first — fragment store, second brain, "
    "scatter brain, Atlas, AnythingLLM — then outside). Penny "
    "extracts, she does not discover: discovery is the source map, "
    "fetch capacity, and the newness check. Intel hides in three "
    "places: in unfetched pages, inside fetched pages (the battery's "
    "war), and between pages (the join layer's war). False joins "
    "are the cardinal sin: evidence-scored merges only, never on a "
    "name alone.")

QUESTIONS = [
    "Which fragment class is the current taxonomy most likely "
    "MISSING — what kind of intel would fall through all nine "
    "lenses and the sweep today?",
    "Where would 'hidden' intel hide that this design still does "
    "not reach — a page structure, a source type, or a hiding "
    "place between pages we have not named?",
    "The step 'identifying what needs to be put into the database': "
    "what is the sharpest rule for what earns a database row versus "
    "what stays a fingerprint-only discard?",
    "When should a fragment trigger ENRICHMENT versus ADDITIONAL "
    "RESEARCH? Propose the deciding rule and its threshold.",
    "Which source family should graduate to a schema FIRST, and "
    "what evidence would prove the schema is worth building?",
    "The matcher scores pairs on product fit, place fit, freshness, "
    "and graph proximity. What fifth signal would most improve "
    "pair quality?",
    "Pain escalation fires research for recent, relevant, loud "
    "pains. What pain is QUIET but valuable — and how would the "
    "system ever notice it?",
    "The thread walker harvests community-confirmed answers. What "
    "other source type carries its own built-in validation we "
    "could harvest the same way?",
    "What is the cheapest experiment that would TEST this design "
    "end-to-end on one source family, and what result would prove "
    "or kill it?",
    "Where does this design waste model calls that code should "
    "make instead — or the reverse, where is code pretending to "
    "judge?",
]


def week_key(d=None):
    iso = (d or date.today()).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def last_mull(cur):
    cur.execute(
        "SELECT step_key, status, result FROM successbrian_os.pm_steps "
        "WHERE step_key LIKE 'mull-fragment-pipeline-%' "
        "ORDER BY created_at DESC LIMIT 1")
    return cur.fetchone()


def run():
    c = pm_core.conn()
    cur = c.cursor()
    lines = []
    prev = last_mull(cur)
    # 1. promote a finished previous proposal into Altair's review queue
    if prev and prev[1] == "done" and prev[2]:
        parsed = (prev[2] or {}).get("parsed") or {}
        improvement = (parsed.get("improvement") or "").strip()
        prop_key = f"mull-proposal-{prev[0].split('mull-fragment-pipeline-')[1]}"
        cur.execute("SELECT 1 FROM successbrian_os.pm_steps "
                    "WHERE step_key=%s", (prop_key,))
        if improvement and not cur.fetchone():
            pm_core.add_step(
                cur, prop_key,
                f"Mull proposal for the Fragment Pipeline: "
                f"{improvement}"[:300],
                kind="review", origin="system", priority=40,
                payload={"proposal": parsed, "source_step": prev[0]})
            pm_core.decide(
                cur, "design-mull",
                f"Mull proposal promoted for Altair review: "
                f"{improvement[:160]}",
                step_key=prop_key, origin="system")
            lines.append(f"promoted proposal from {prev[0]} -> {prop_key}")
    # 2. file this week's mull step (idempotent per ISO week)
    wk = week_key()
    key = f"mull-fragment-pipeline-{wk}"
    cur.execute("SELECT 1 FROM successbrian_os.pm_steps WHERE step_key=%s",
                (key,))
    if cur.fetchone():
        lines.append(f"{key} already filed")
    else:
        q = QUESTIONS[date.today().isocalendar()[1] % len(QUESTIONS)]
        context = DESIGN_SUMMARY
        if prev and prev[2]:
            p = (prev[2] or {}).get("parsed") or {}
            if p.get("improvement"):
                context += ("\n\nLAST MULL PROPOSAL (build on it or "
                            "beat it, do not repeat it): "
                            + json.dumps(p)[:600])
        pm_core.add_step(
            cur, key,
            f"Weekly mull: improve the Fragment Pipeline design ({wk})",
            kind="judgment", origin="system", priority=45,
            payload={
                "instruction": (
                    "You are mulling over the Fragment Pipeline design "
                    "to make it better. Answer this week's question "
                    "with ONE concrete improvement. Standing question: "
                    + q),
                "context": context,
                "output_keys": ["improvement", "why", "cost_or_risk",
                                "confidence"],
                "max_tokens": 700})
        lines.append(f"filed {key}: {q[:80]}...")
    c.commit()
    c.close()
    for line in lines:
        print(line)
    return lines


def main():
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
