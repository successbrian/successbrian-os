#!/usr/bin/env python3
"""Ingest worker — the synthesis leg of the Intel Bridge pipeline.

# @docmap successbrian_os.ingest_leg

DOCTRINE (Brian, 2026-11-14, verbatim): "chat agents should dump
dump dump. intel workers dump. everything dumps. the ecosystem
manages the rest from there." Producers dump dumb and cheap; ALL
intelligence is downstream. This worker assumes abundant, messy,
duplicate-prone input and owns: dedupe / near-duplicate collapse,
the extraction sweep, flagging, the gamma deep pass, and DRAFT
filings. It never writes a live store: filings land only when
verified, per Brian's approval discipline — this worker prepares,
it does not apply. Workers flag; they do not silently rewrite.

Shape (Brian's ruled deliberation flow, second customer):
  claim 'ingest' jobs (enqueued by ingest_producer) from an
  engine queue -> SWEEP with a worker-class seat (extract facts,
  decisions, people, dates, open items, flags; structured
  sections) -> deterministic near-duplicate collapse inside the
  batch -> if the batch carries FLAGS or DECISIONS (rulings are
  load-bearing by definition), ONE small deep pass goes to REAP
  on gamma through its real contract (bus.events reap_infer,
  result returns in successbrian_os.outbox) -> DRAFT filings
  written to the review location board/ingest_drafts/ ->
  captures marked processed in successbrian_os.capture_ingest
  with full provenance {engine, host, endpoint, gamma event}.

Seat-agnostic by construction: the queue is configuration
(INGEST_QUEUE, default penny); the sweep calls the seat that
queue names through sbos_common.llm_chat with that engine's
env-overridable URL. Gamma note (measured 2026-11-14): gamma
claims NO engine queue — its contract is the bus (28 jobs sat
unclaimed in reap_queue while bus reap_infer events completed
the same afternoon), so gamma works this leg through the deep
pass, which is the deliberation flow's own shape anyway.

Usage:
  ingest_worker.py [--once] [--max N] [--selftest]
Cron: every 15 min, flock /tmp/ingest-worker.lock, --once --max 2.
"""
import argparse
import json
import os
import re
import socket
import sys
import time
from datetime import datetime

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
import sbos_common  # noqa: E402

QUEUE = os.environ.get("INGEST_QUEUE", "penny")
DRAFT_DIR = os.path.expanduser(
    "~/successbrian-os/board/ingest_drafts")
GAMMA_WAIT_S = int(os.environ.get("INGEST_GAMMA_WAIT_S", "600"))
ENGINE_URLS = {
    "morpheus": sbos_common.MORPHEUS_URL,
    "penny": sbos_common.PENNY_URL,
    "sonic": sbos_common.SONIC_URL,
}
HOST = socket.gethostname()

SWEEP_SYSTEM = (
    "You are the ingestion sweep for Brian Lathe's SuccessBrian "
    "OS. You read raw Intel Bridge captures dumped from chats "
    "and extract what is durable. Be exact: copy names, dates, "
    "and numbers verbatim; never invent; if a section has "
    "nothing, write NONE. Flag anything contradictory, "
    "duplicated, or needing a deeper look — a flag costs a "
    "look, a miss costs correctness.")


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def collapse_duplicates(caps):
    """Deterministic near-duplicate collapse inside one batch:
    same cluster_key or same normalized title -> later captures
    collapse onto the first. Returns (kept, dup_map)."""
    seen = {}
    kept, dup_map = [], {}
    for cap in caps:
        keys = [("t", norm_title(cap["title"]))]
        if cap.get("cluster_key"):
            keys.append(("c", cap["cluster_key"]))
        hit = None
        for k in keys:
            if k in seen:
                hit = seen[k]
                break
        if hit is not None:
            dup_map[cap["id"]] = hit
        else:
            for k in keys:
                seen[k] = cap["id"]
            kept.append(cap)
    return kept, dup_map


def build_prompt(cap):
    """ONE capture per sweep call — the never-oversize law at
    the sender. Proof-run evidence (2026-11-14): whole-batch
    prompts (3 captures, ~10k chars in / 1000+ tokens out)
    timed out at 240s on Morpheus AND at 300s on Penny on the
    loaded alpha seats; the fleet's proven shape is small
    chained calls (500-token REAP passes completed 16/16 while
    1600-token passes completed 0/10)."""
    return (
        "Extract the durable content of the capture below. "
        "Reply in EXACTLY this shape:\n\n"
        f"## CAPTURE {cap['id']}\n"
        "FACTS:\n- <fact> (NONE if none)\n"
        "DECISIONS:\n- <ruling/decision> (NONE if none)\n"
        "PEOPLE:\n- <Name — what is now known> (NONE if none)\n"
        "DATES:\n- <date — what> (NONE if none)\n"
        "OPEN_ITEMS:\n- <unresolved thing> (NONE if none)\n"
        "FLAGS:\n- <contradiction / near-duplicate / needs a "
        "deeper look> (NONE if none)\n\n"
        f"=== CAPTURE #{cap['id']}: {cap['title']} ===\n"
        f"CONTEXT: {(cap['context'] or '')[:600]}\n"
        f"RAW: {(cap['raw'] or '')[:1400]}")


SECTION_NAMES = ("FACTS", "DECISIONS", "PEOPLE", "DATES",
                 "OPEN_ITEMS", "FLAGS")


def parse_sweep(text):
    """Parse the sweep's structured reply. Tolerant: returns
    {capture_id: {SECTION: [lines]}}, batch_flags, raw text is
    kept by the caller regardless — a parse miss never loses
    the model's output."""
    per_cap = {}
    batch_flags = []
    cur_id, cur_sec, sink = None, None, None
    for line in (text or "").splitlines():
        m = re.match(r"##\s+CAPTURE\s+(\d+)", line)
        if m:
            cur_id = int(m.group(1))
            per_cap.setdefault(cur_id, {s: [] for s in
                                        SECTION_NAMES})
            cur_sec, sink = None, None
            continue
        if re.match(r"##\s+BATCH_FLAGS", line):
            cur_id, cur_sec = None, None
            sink = batch_flags
            continue
        m = re.match(r"(FACTS|DECISIONS|PEOPLE|DATES|"
                     r"OPEN_ITEMS|FLAGS):\s*$", line.strip())
        if m and cur_id is not None:
            cur_sec = m.group(1)
            sink = per_cap[cur_id][cur_sec]
            continue
        s = line.strip()
        if sink is not None and s.startswith("-"):
            item = s.lstrip("- ").strip()
            if item and item.upper() != "NONE":
                sink.append(item)
    return per_cap, batch_flags


def all_flags(per_cap, batch_flags):
    out = list(batch_flags)
    for cid, secs in per_cap.items():
        for f in secs.get("FLAGS", []):
            out.append(f"#{cid}: {f}")
    return out


def has_decisions(per_cap):
    return any(secs.get("DECISIONS")
               for secs in per_cap.values())


def parse_reap_body(body):
    """Gamma returns the inference in the outbox body: JSON with
    result.text (the overdue_relevance shape). Tolerate plain
    text bodies."""
    try:
        data = json.loads(body)
        text = (data.get("result") or {}).get("text")
        if text:
            return text
    except Exception:
        pass
    return (body or "")[:4000]


def gamma_deep_pass(job_id, flags, per_cap):
    """One small REAP packet to gamma via the bus — the only
    contract gamma claims (measured 2026-11-14). Returns
    (status_line, verdict_text_or_None)."""
    lines = ["A batch of Intel Bridge captures was swept by the "
             "ingestion leg. Below are the sweep's flags and "
             "decisions. Give a short verdict: (1) which store "
             "each flagged item most likely belongs in (people "
             "record / goal file / calendar / AnythingLLM "
             "workspace / discard as noise), (2) any outright "
             "contradiction you can settle from the text, "
             "(3) anything Brian himself must decide. Be brief "
             "and concrete."]
    if flags:
        lines.append("\nFLAGS:")
        lines += [f"- {f}" for f in flags[:12]]
    for cid, secs in per_cap.items():
        for d in secs.get("DECISIONS", [])[:6]:
            lines.append(f"DECISION (capture #{cid}): {d}")
    packet = sbos_common.build_reap_packet(
        "\n".join(lines)[:6000], source="ingest-worker",
        probe_id=f"ingest-job-{job_id}", max_tokens=500)
    eid = sbos_common.dispatch_reap_packet(
        packet, source="ingest-worker", priority=5)  # intake lane
    deadline = time.time() + GAMMA_WAIT_S
    while time.time() < deadline:
        row = sbos_common.pg_one(
            "SELECT body FROM successbrian_os.outbox "
            "WHERE message_type = 'inference_result' "
            "AND subject = %s ORDER BY id DESC LIMIT 1",
            (f"gamma: event {eid} done (reap_infer)",))
        if row:
            return (f"gamma verdict landed (bus event {eid})",
                    parse_reap_body(row))
        st = sbos_common.pg_one(
            "SELECT status FROM bus.events WHERE id = %s",
            (eid,))
        if st in ("dead_letter", "failed"):
            return (f"gamma pass failed on gamma "
                    f"(bus event {eid}: {st})", None)
        time.sleep(20)
    return (f"gamma verdict not landed within {GAMMA_WAIT_S}s "
            f"(bus event {eid} dispatched; draft proceeds "
            f"without it)", None)


def load_captures(ids):
    rows = sbos_common.pg_rows(
        "SELECT id, title, COALESCE(context,''), "
        "COALESCE(raw_text,''), cluster_key "
        "FROM atlas.scattered_captures WHERE id = ANY(%s) "
        "ORDER BY id", (list(ids),)) or []
    return [{"id": int(r[0]), "title": r[1], "context": r[2],
             "raw": r[3], "cluster_key": r[4]} for r in rows]


def assemble_draft(job, caps, kept, dup_map, sweep_text,
                   per_cap, batch_flags, gamma_status,
                   gamma_text, engine, url, usage):
    now = datetime.now().isoformat(timespec="seconds")
    ids = [c["id"] for c in caps]
    out = []
    out.append(f"# Ingest draft — job {job['id']} "
               f"({now})")
    out.append("")
    out.append("PROVENANCE: "
               f"engine={engine} host={HOST} endpoint={url} "
               f"queue={QUEUE} job={job['id']} "
               f"captures={ids} usage={usage}")
    out.append(f"GAMMA: {gamma_status}")
    out.append("")
    out.append("STATUS: DRAFT for verification. Nothing in this "
               "file has been applied to any live store. Filings "
               "land only when verified (Brian's approval "
               "discipline).")
    if dup_map:
        out.append("")
        out.append("## Duplicates collapsed (deterministic)")
        for dup, canon in sorted(dup_map.items()):
            out.append(f"- capture #{dup} collapsed onto "
                       f"#{canon} (same cluster/title)")
    out.append("")
    out.append("## Sweep extraction (model output, verbatim)")
    out.append("")
    out.append(sweep_text.strip() or "(empty sweep output)")
    if gamma_text:
        out.append("")
        out.append("## Gamma deep pass (REAP verdict, verbatim)")
        out.append("")
        out.append(gamma_text.strip())
    out.append("")
    out.append("## Draft AnythingLLM addendum (ready to embed "
               "after verification)")
    out.append("")
    out.append(f"### Ingested captures "
               f"{', '.join('#%d' % i for i in ids)} — {now}")
    for cap in kept:
        secs = per_cap.get(cap["id"], {})
        out.append(f"\n**{cap['title']}** (capture #{cap['id']})")
        for name in ("FACTS", "DECISIONS"):
            for item in secs.get(name, []):
                out.append(f"- {item}")
    out.append("")
    out.append("## Proposed record updates (apply only after "
               "verification)")
    any_prop = False
    for cap in kept:
        secs = per_cap.get(cap["id"], {})
        for p in secs.get("PEOPLE", []):
            any_prop = True
            out.append(f"- [ ] PEOPLE (from #{cap['id']}): {p} "
                       f"-> people record")
        for d in secs.get("DATES", []):
            any_prop = True
            out.append(f"- [ ] DATE (from #{cap['id']}): {d} "
                       f"-> calendar / record")
        for o in secs.get("OPEN_ITEMS", []):
            any_prop = True
            out.append(f"- [ ] OPEN (from #{cap['id']}): {o} "
                       f"-> follow-up")
    if not any_prop:
        out.append("- none proposed by this sweep")
    out.append("")
    return "\n".join(out)


def serve_job(job, engine, url):
    ids = (job.get("payload") or {}).get("capture_ids") or []
    caps = load_captures(ids)
    if not caps:
        sbos_common.engine_job_finish(
            QUEUE, job["id"],
            "ingest: no captures found for payload ids "
            f"{ids}; nothing to sweep")
        return "empty"
    kept, dup_map = collapse_duplicates(caps)
    # Chained small calls, one per capture (see build_prompt).
    texts, per_cap, usage = [], {}, {}
    for cap in kept:
        t, usage = sbos_common.llm_chat(
            messages=[{"role": "system",
                       "content": SWEEP_SYSTEM},
                      {"role": "user",
                       "content": build_prompt(cap)}],
            url=url, model=None, max_tokens=450,
            temperature=0.2, timeout=300)
        texts.append(t)
        pc, _bf = parse_sweep(t)
        per_cap.update(pc)
    text = "\n\n".join(texts)
    batch_flags = []
    if dup_map:
        batch_flags.append(
            f"{len(dup_map)} duplicate(s) collapsed "
            f"deterministically in this batch: "
            f"{sorted(dup_map)}")
    flags = all_flags(per_cap, batch_flags)
    gamma_status, gamma_text = "not fired (no flags, no " \
        "decisions — sweep stands alone)", None
    if flags or has_decisions(per_cap):
        gamma_status, gamma_text = gamma_deep_pass(
            job["id"], flags, per_cap)
    os.makedirs(DRAFT_DIR, exist_ok=True)
    draft_path = os.path.join(
        DRAFT_DIR, f"ingest-job-{job['id']}.md")
    draft = assemble_draft(job, caps, kept, dup_map, text,
                           per_cap, batch_flags, gamma_status,
                           gamma_text, engine, url, usage)
    with open(draft_path, "w") as f:
        f.write(draft)
    sbos_common.pg_exec(
        "UPDATE successbrian_os.capture_ingest "
        "SET processed_at = now(), draft_path = %s, "
        "sweep_engine = %s, sweep_host = %s "
        "WHERE capture_id = ANY(%s)",
        (draft_path, engine, HOST, [c["id"] for c in caps]))
    result = (f"ingest sweep: {len(caps)} capture(s), "
              f"{len(dup_map)} duplicate(s) collapsed, "
              f"{len(flags)} flag(s); gamma: {gamma_status}; "
              f"draft: {draft_path}")
    sbos_common.engine_job_finish(QUEUE, job["id"], result)
    print(f"ingest-worker: job {job['id']} done — {result}")
    return "done"


def run(max_jobs=1):
    engine = QUEUE
    url = ENGINE_URLS.get(QUEUE, sbos_common.MORPHEUS_URL)
    worker = f"ingest-worker@{HOST}"
    jobs = sbos_common.engine_job_claim(
        QUEUE, worker, kinds=[KIND], limit=max_jobs)
    if not jobs:
        print(f"ingest-worker: no ingest jobs in {QUEUE}")
        return 0
    for job in jobs:
        try:
            serve_job(job, engine, url)
        except Exception as e:  # seat failure etc: requeue
            print(f"ingest-worker: job {job['id']} failed "
                  f"({e}); released back to queue")
            sbos_common.engine_job_release(QUEUE, job["id"])
    return 0


KIND = "ingest"


def selftest():
    caps = [
        {"id": 1, "title": "Lease confirmed for HQ",
         "context": "ctx", "raw": "raw",
         "cluster_key": "lease"},
        {"id": 2, "title": "Lease confirmed for HQ",
         "context": "ctx2", "raw": "raw2",
         "cluster_key": "lease"},
        {"id": 3, "title": "A ruling about dashboards",
         "context": "", "raw": "", "cluster_key": None},
    ]
    kept, dup_map = collapse_duplicates(caps)
    assert len(kept) == 2 and dup_map == {2: 1}, (kept, dup_map)
    sample = (
        "## CAPTURE 1\nFACTS:\n- Lease runs through Feb 2028\n"
        "DECISIONS:\n- NONE\nPEOPLE:\n- NONE\nDATES:\n"
        "- 2028-02-29 — lease end\nOPEN_ITEMS:\n- NONE\n"
        "FLAGS:\n- NONE\n\n## CAPTURE 3\nFACTS:\n- NONE\n"
        "DECISIONS:\n- Dashboards are a lead idea\nPEOPLE:\n"
        "- Ben Firkus — President\nDATES:\n- NONE\n"
        "OPEN_ITEMS:\n- Ask about renewal\nFLAGS:\n"
        "- Contradicts capture #1 on scope\n\n## BATCH_FLAGS\n"
        "- One cross-batch note\n")
    per_cap, batch_flags = parse_sweep(sample)
    assert per_cap[1]["FACTS"] == ["Lease runs through "
                                   "Feb 2028"]
    assert per_cap[1]["DECISIONS"] == []
    assert per_cap[3]["DECISIONS"] == ["Dashboards are a "
                                       "lead idea"]
    assert per_cap[3]["PEOPLE"] == ["Ben Firkus — President"]
    assert all_flags(per_cap, batch_flags) == [
        "One cross-batch note",
        "#3: Contradicts capture #1 on scope"]
    assert has_decisions(per_cap)
    p = build_prompt(kept[0])
    assert "CAPTURE #1" in p and "CAPTURE #3" not in p
    print("INGEST_WORKER_OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="claim up to --max jobs, then exit")
    ap.add_argument("--max", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    return run(max_jobs=a.max)


if __name__ == "__main__":
    sys.exit(main())
