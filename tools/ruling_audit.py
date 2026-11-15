#!/usr/bin/env python3
"""ruling_audit — guard against ASSISTANT INTERPRETATION HARDENED INTO
BRIAN'S RECORD (failure family named 2026-11-15, specimen: the systeme.io
"platform ruling", daily log 2026-10-28, corrected by Brian 2026-11-15,
Intel Bridge capture #1814).

Pipeline (Brian's deliberation-flow shape; jobs sized small):
  extract  deterministic: ruling/decision entries from daily logs +
           ruling-asserting MEMORY.md bullets; claim headline + Brian's
           quoted spans. No-quote entries are a risk class of their own.
  sweep    Penny/Morpheus-class passes via sbos_common.llm_chat, one
           entry per call: does the claim follow, read plainly, from
           the quoted words alone? SUPPORTED / UNSUPPORTED / UNCLEAR.
  deep     Sonic-class pass over sweep UNSUPPORTED/UNCLEAR plus a 10%
           audit sample of SUPPORTED (the specimen passed a Penny sweep
           as SUPPORTED — sweep false-negatives exist, so we sample):
           SUPPORTED / INTERPRETATION-RISK / UNRESOLVED + reason.
  collect  lands bus-dispatched deep verdicts from the outbox into
           deep_results.jsonl; when the dispatched set completes
           it runs the report step once (marker file:
           collect_report_done.json).
  report   writes flags.jsonl (interpretation-risk + no-quote classes)
           and, with --file-captures, files one Intel Bridge capture per
           NEW interpretation-risk flag (idempotent via a state file).
           Flags NEVER edit the record. Corrections are Brian's.
  selftest fixture extraction + verdict parsing + plumbing; asserts the
           detector's deterministic halves. (A PASS means the tool ran
           and its deterministic checks held — not that zero flags
           exist in any record.)

Standard enforced (ruling-provenance standard, 2026-11-15): a ruling
entry carries Brian's verbatim words, or is labeled INTERPRETATION in
its headline; the claim asserts no more than the quote plainly carries;
hedges in the quote survive into the claim; consumers re-read the
verbatim words before repeating a ruling or flagging against it.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import sbos_common
except ImportError:  # running outside the repo tree (e.g. baseline host)
    sbos_common = None

TAG_RE = re.compile(r"^- \[(ruling|decision)\|([a-z]+)\]\s*(.*)$")
QUOTE_RE = re.compile(r'"([^"]{2,600})"|“([^”]{2,600})”')
RULING_KW = re.compile(
    r"Brian('s)? (ruling|ruled|correction|directive|order)|"
    r"\bRULED\b|\bruled\b|verbatim", re.I)

SWEEP_PROMPT = """You check a written record. A log entry claims that a man named Brian decided or ruled something. Brian's own quoted words are given below. Judge ONLY from the quoted words, read plainly and literally. Do not use outside knowledge.

CLAIM: {claim}

BRIAN'S QUOTED WORDS: {quotes}

Does the claim follow from the quoted words alone?
Reply with exactly one verdict word first - SUPPORTED, UNSUPPORTED, or UNCLEAR - then a reason of at most 12 words."""

DEEP_PROMPT = """You are the deep pass in a record audit. A log entry claims Brian decided or ruled something. Below: the claim with quoted spans removed, Brian's quoted words, and a fuller excerpt of the entry. Judge whether the claim, read plainly, is carried by Brian's quoted words - or whether the writer's interpretation added something the words do not say (a different kind of statement, a dropped hedge, a scope widening, a name or topic read as a decision about something else).

Watch for the known failure: a quote that NAMES or MENTIONS a thing being recorded as a DECISION about that thing's properties (platform, owner, price, scope).

CLAIM (quotes stripped): {claim}
BRIAN'S QUOTED WORDS: {quotes}
ENTRY EXCERPT: {excerpt}

Reply: first line exactly one of SUPPORTED / INTERPRETATION-RISK / UNRESOLVED; second line one sentence of reasoning."""


def quotes_of(text):
    out = []
    for m in QUOTE_RE.finditer(text):
        q = (m.group(1) or m.group(2) or "").strip()
        if q:
            out.append(q)
    return out


def headline_of(text, limit=240):
    t = text.strip()
    idx = t.find("): ")
    if 0 < idx < limit:
        return t[: idx + 1].strip()
    cut = t[:limit]
    for sep in (". ", " — ", ": "):
        i = cut.find(sep)
        if 60 < i:
            return cut[:i].strip()
    return cut.strip()


def strip_quotes(text):
    t = QUOTE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- extract
def extract(logs_dir, memory_file):
    rows = []
    logs_dir = Path(logs_dir)
    for path in sorted(logs_dir.glob("2026-*.md")):
        for ln, line in enumerate(
                path.read_text(errors="replace").splitlines(), 1):
            m = TAG_RE.match(line)
            if not m:
                continue
            body = m.group(3)
            qs = quotes_of(body)
            rows.append({
                "id": f"log-{path.stem}-{ln}",
                "source_file": f"{logs_dir.name}/{path.name}", "line": ln,
                "kind": m.group(1), "headline": headline_of(body),
                "quotes": qs, "has_quote": bool(qs),
                "excerpt": body[:1600]})
    mem_path = Path(memory_file)
    if mem_path.exists():
        section = ""
        for ln, line in enumerate(
                mem_path.read_text(errors="replace").splitlines(), 1):
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if not line.startswith("- "):
                continue
            body = line[2:]
            if not RULING_KW.search(body):
                continue
            qs = quotes_of(body)
            rows.append({
                "id": f"mem-{ln}", "source_file": mem_path.name, "line": ln,
                "kind": "memory-bullet", "section": section,
                "headline": headline_of(body), "quotes": qs,
                "has_quote": bool(qs), "excerpt": body[:1600]})
    return rows


# ------------------------------------------------------------------ sweep
def _verdict(text, words):
    t = (text or "").upper()
    for w in words:
        if w in t:
            return w
    return "PARSE_FAIL"


def _load_done(path):
    done = {}
    p = Path(path)
    if p.exists():
        for l in p.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                done[r["id"]] = r
    return done


def sweep(rows, out, tiers=("penny", "morpheus"), limit=0):
    if sbos_common is None:
        raise SystemExit("sbos_common not importable — run from the repo")
    todo = [r for r in rows if r["has_quote"]]
    done = _load_done(out)
    todo = [r for r in todo if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    urls = {"penny": (sbos_common.PENNY_URL, sbos_common.PENNY_MODEL),
            "morpheus": (sbos_common.MORPHEUS_URL, sbos_common.MORPHEUS_MODEL)}
    with Path(out).open("a") as f:
        for i, r in enumerate(todo):
            tier = tiers[i % len(tiers)]
            url, model = urls[tier]
            quotes = " | ".join(q.strip() for q in r["quotes"])[:700]
            prompt = SWEEP_PROMPT.format(claim=r["headline"][:240],
                                         quotes=quotes)
            t0 = time.time()
            try:
                text, usage = sbos_common.llm_chat(
                    prompt=prompt, url=url, model=model, max_tokens=70,
                    temperature=0.1, timeout=240)
                rec = {"id": r["id"], "tier": tier,
                       "model": usage.get("model") or model,
                       "verdict": _verdict(text, ("UNSUPPORTED", "UNCLEAR",
                                                  "SUPPORTED")),
                       "raw": (text or "").strip()[:200],
                       "secs": round(time.time() - t0, 1)}
            except Exception as e:
                rec = {"id": r["id"], "tier": tier, "model": model,
                       "verdict": "ERROR", "raw": str(e)[:160],
                       "secs": round(time.time() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    return len(todo)


def deep(rows, sweep_results, out, sample_rate=0.10, limit=0):
    if sbos_common is None:
        raise SystemExit("sbos_common not importable — run from the repo")
    by_id = {r["id"]: r for r in rows}
    targets = []
    supported = []
    for rid, res in sweep_results.items():
        if res["verdict"] in ("UNSUPPORTED", "UNCLEAR", "ERROR",
                              "PARSE_FAIL"):
            targets.append(rid)
        elif res["verdict"] == "SUPPORTED":
            supported.append(rid)
    supported.sort(key=lambda rid: hashlib.md5(rid.encode()).hexdigest())
    n_sample = int(len(supported) * sample_rate)
    sampled = supported[:n_sample]
    targets += sampled
    done = _load_done(out)
    targets = [t for t in targets if t not in done]
    if limit:
        targets = targets[:limit]
    with Path(out).open("a") as f:
        for rid in targets:
            r = by_id[rid]
            quotes = " | ".join(q.strip() for q in r["quotes"])[:800]
            prompt = DEEP_PROMPT.format(
                claim=strip_quotes(r["headline"])[:240], quotes=quotes,
                excerpt=r["excerpt"][:1400])
            t0 = time.time()
            try:
                text, usage = sbos_common.llm_chat(
                    prompt=prompt, url=sbos_common.SONIC_URL,
                    model=sbos_common.SONIC_MODEL, max_tokens=160,
                    temperature=0.1, timeout=300)
                rec = {"id": rid, "tier": "sonic",
                       "model": usage.get("model") or sbos_common.SONIC_MODEL,
                       "verdict": _verdict(text, ("INTERPRETATION-RISK",
                                                  "UNRESOLVED", "SUPPORTED")),
                       "raw": (text or "").strip()[:400],
                       "audit_sample": rid in sampled,
                       "secs": round(time.time() - t0, 1)}
            except Exception as e:
                rec = {"id": rid, "tier": "sonic", "model": "sonic",
                       "verdict": "ERROR", "raw": str(e)[:160],
                       "audit_sample": rid in sampled,
                       "secs": round(time.time() - t0, 1)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    return len(targets), len(sampled)



# ---------------------------------------------------------------- collect
def collect(wd, rows, sweep_results):
    """Land gamma-bus deep-pass verdicts into deep_results.jsonl.

    Idempotent: ids already in deep_results.jsonl are never rewritten.
    Failed or dead-lettered events land as ERROR records so the set
    completes honestly. When every dispatched event has finished, run
    the report step (flags + captures) once and drop the marker file
    collect_report_done.json.
    """
    if sbos_common is None:
        raise SystemExit("sbos_common not importable — run from the repo")
    disp_path = wd / "deep_results.jsonl.dispatched"
    dispatched = {}
    if disp_path.exists():
        for l in disp_path.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                dispatched[r["id"]] = r["bus_event"]
    if not dispatched:
        print("collect: no dispatched deep packets on record — nothing to do")
        return 0
    done = _load_done(wd / "deep_results.jsonl")
    todo = {cid: eid for cid, eid in dispatched.items() if cid not in done}
    new = 0
    running = 0
    if todo:
        eids = list(todo.values())
        ev = {r[0]: {"status": r[1], "last_error": r[2]}
              for r in sbos_common.pg_rows(
                  "SELECT id, status, last_error FROM bus.events "
                  "WHERE id = ANY(%s)", (eids,))}
        results = {}
        for r in sbos_common.pg_rows(
                "SELECT body FROM successbrian_os.outbox "
                "WHERE message_type='inference_result' "
                "AND (body::jsonb->>'event_id')::bigint = ANY(%s)",
                (eids,)):
            b = json.loads(r[0])
            results[int(b["event_id"])] = b
        with (wd / "deep_results.jsonl").open("a") as f:
            for cid, eid in todo.items():
                e = ev.get(eid)
                if e is None:
                    continue
                if e["status"] in ("pending", "processing"):
                    running += 1
                    continue
                sample = (sweep_results.get(cid, {}).get("verdict")
                          == "SUPPORTED")
                if e["status"] == "done" and eid in results:
                    res = results[eid].get("result") or {}
                    text = (res.get("text") or "").strip()
                    rec = {"id": cid, "tier": "reap",
                           "model": res.get("engine") or "reap",
                           "verdict": _verdict(
                               text, ("INTERPRETATION-RISK", "UNRESOLVED",
                                      "SUPPORTED")),
                           "raw": text[:400], "audit_sample": sample,
                           "secs": res.get("wall_s")}
                else:
                    rec = {"id": cid, "tier": "reap", "model": "reap",
                           "verdict": "ERROR",
                           "raw": (e.get("last_error") or
                                   f"event ended {e['status']} with no "
                                   "result")[:400],
                           "audit_sample": sample, "secs": None}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                done[cid] = rec
                new += 1
    landed = len(done)
    total = len(dispatched)
    try:
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.worker_heartbeats "
            "(worker_name, last_heartbeat, last_status, last_error, "
            "last_run_output) VALUES ('ruling-audit-collect', now(), "
            "'ok', NULL, %s) ON CONFLICT (worker_name) DO UPDATE SET "
            "last_heartbeat = EXCLUDED.last_heartbeat, "
            "last_status = EXCLUDED.last_status, last_error = NULL, "
            "last_run_output = EXCLUDED.last_run_output",
            (f"deep verdicts landed {landed}/{total}; {running} still "
             f"running on gamma",))
    except Exception as exc:  # the heartbeat must never kill the collect
        print(f"collect: heartbeat failed: {exc}", file=sys.stderr)
    print(f"collect: {new} new verdicts landed; {landed}/{total} in; "
          f"{running} still running")
    marker = wd / "collect_report_done.json"
    if running == 0 and landed >= total and not marker.exists():
        census_path = wd / "census_candidates.jsonl"
        if census_path.exists():
            rows = [json.loads(l) for l in
                    census_path.read_text().splitlines() if l.strip()]
        by_id = {r["id"]: r for r in rows}
        deep_results = {k: v for k, v in
                        _load_done(wd / "deep_results.jsonl").items()
                        if k in by_id}
        flags = build_flags(rows, sweep_results, deep_results)
        (wd / "flags.jsonl").write_text(
            "".join(json.dumps(fl, ensure_ascii=False) + "\n"
                    for fl in flags))
        counts = {}
        for fl in flags:
            counts[fl["class"]] = counts.get(fl["class"], 0) + 1
        filed, skipped = file_captures(flags, wd / "capture_state.json")
        marker.write_text(json.dumps(
            {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             "flags": counts, "captures_filed": filed,
             "captures_skipped": skipped}, indent=1))
        print(f"report: flags {counts} -> {wd / 'flags.jsonl'}")
        print(f"captures: filed {filed} new, skipped {skipped} "
              "already-filed")
        print("RULING_AUDIT_PIPELINE_COMPLETE")
    return 0


# ----------------------------------------------------------------- report
def build_flags(rows, sweep_results, deep_results):
    by_id = {r["id"]: r for r in rows}
    flags = []
    for r in rows:
        if not r["has_quote"]:
            flags.append({"id": r["id"], "class": "no-quote",
                          "source_file": r["source_file"], "line": r["line"],
                          "headline": r["headline"], "quotes": []})
    for rid, d in deep_results.items():
        if d["verdict"] == "INTERPRETATION-RISK":
            r = by_id[rid]
            flags.append({"id": rid, "class": "interpretation-risk",
                          "source_file": r["source_file"], "line": r["line"],
                          "headline": r["headline"], "quotes": r["quotes"],
                          "deep_reason": d["raw"],
                          "audit_sample": d.get("audit_sample", False)})
        elif d["verdict"] == "UNRESOLVED":
            r = by_id[rid]
            flags.append({"id": rid, "class": "unresolved",
                          "source_file": r["source_file"], "line": r["line"],
                          "headline": r["headline"], "quotes": r["quotes"],
                          "deep_reason": d["raw"]})
    return flags


def file_captures(flags, state_path):
    """One Intel Bridge capture per NEW interpretation-risk flag.
    Returns (filed, skipped). Uses atlas_manage's capture op."""
    import subprocess
    state = {"filed": []}
    sp = Path(state_path)
    if sp.exists():
        state = json.loads(sp.read_text())
    filed = skipped = 0
    tool = Path(__file__).resolve().parent / "atlas" / "atlas_manage.py"
    for fl in flags:
        if fl["class"] != "interpretation-risk":
            continue
        if fl["id"] in state["filed"]:
            skipped += 1
            continue
        raw = (f"RULING-AUDIT FLAG [{fl['id']}] {fl['source_file']}:"
               f"{fl['line']}\nCLAIM: {fl['headline']}\n"
               f"BRIAN'S QUOTED WORDS: {' | '.join(fl['quotes'])[:700]}\n"
               f"DEEP-PASS REASON: {fl.get('deep_reason', '')[:300]}\n"
               "Flag only — do not correct without Brian's word.")
        r = subprocess.run(
            [sys.executable, str(tool), "capture", "--actor", "ruling-audit",
             "--title", f"Ruling-audit flag: {fl['headline'][:80]}",
             "--context", "ruling_audit.py weekly/baseline run — failure "
                          "family: assistant interpretation hardened into "
                          "Brian's record",
             "--raw", raw], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            state["filed"].append(fl["id"])
            filed += 1
        else:
            print(f"capture failed for {fl['id']}: {r.stderr[:160]}",
                  file=sys.stderr)
    sp.write_text(json.dumps(state, indent=1))
    return filed, skipped


# --------------------------------------------------------------- selftest
FIXTURE_LOG = """- [decision|high] AOEM BLOG — PLATFORM DECIDED (Brian, 2026-10-28: "we need to plan an aoem blog. a systeme.io blog for sure"): the platform is SETTLED.
- [ruling|high] QUEUES BY CLASS (Brian, 2026-11-12: "jobs are assigned to the lowest model type that can do it well"): ruled.
- [ruling|high] SOMETHING WITH NO WORDS FROM BRIAN AT ALL: the assistant decided this quietly.
"""


def selftest():
    import tempfile
    ok = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "2026-10-28.md").write_text(FIXTURE_LOG)
        mem = d / "MEMORY.md"
        mem.write_text("## Facts\n- SOMETHING ELSE ENTIRELY (Brian's ruling, "
                       "2026-11-01: \"carry forward, never drop\"): noted.\n")
        rows = extract(d, mem)
        ok.append(("extract-count", len(rows) == 4))
        by = {r["id"]: r for r in rows}
        spec = [r for r in rows if "PLATFORM DECIDED" in r["headline"]]
        ok.append(("specimen-quote", bool(spec) and
                   spec[0]["quotes"] == ["we need to plan an aoem blog. "
                                         "a systeme.io blog for sure"]))
        noq = [r for r in rows if not r["has_quote"]]
        ok.append(("noquote-detected", len(noq) == 1 and
                   noq[0]["kind"] == "ruling"))
        ok.append(("verdict-parse", _verdict("UNSUPPORTED because x",
                                             ("UNSUPPORTED", "UNCLEAR",
                                              "SUPPORTED")) == "UNSUPPORTED"))
        ok.append(("strip-quotes", "systeme.io blog for sure" not in
                   strip_quotes(spec[0]["headline"])))
        flags = build_flags(rows, {}, {})
        ok.append(("flags-noquote", len(flags) == 1 and
                   flags[0]["class"] == "no-quote"))
    for name, passed in ok:
        print(f"  {'ok' if passed else 'FAIL'}  {name}")
    good = all(p for _, p in ok)
    print("RULING_AUDIT_SELFTEST", "OK" if good else "FAILED")
    return 0 if good else 1


# -------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "sweep", "deep", "report", "collect"):
        p = sub.add_parser(name)
        p.add_argument("--logs-dir", default=str(Path.home() / "memory"))
        p.add_argument("--memory-file", default=str(Path.home() / "MEMORY.md"))
        p.add_argument("--workdir", default="/tmp/ruling-audit")
        if name == "sweep":
            p.add_argument("--limit", type=int, default=0)
        if name == "deep":
            p.add_argument("--limit", type=int, default=0)
            p.add_argument("--sample-rate", type=float, default=0.10)
        if name == "report":
            p.add_argument("--file-captures", action="store_true")
    sub.add_parser("selftest")
    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    wd = Path(args.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    rows = extract(args.logs_dir, args.memory_file)
    cand = wd / "candidates.jsonl"
    cand.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows))
    quoted = sum(r["has_quote"] for r in rows)
    print(f"extract: {len(rows)} entries ({quoted} with quotes, "
          f"{len(rows) - quoted} no-quote)")
    if args.cmd == "extract":
        return 0
    if args.cmd == "sweep":
        n = sweep(rows, wd / "sweep_results.jsonl", limit=args.limit)
        print(f"sweep: judged {n} new entries")
        return 0
    sweep_results = _load_done(wd / "sweep_results.jsonl")
    if args.cmd == "deep":
        n, ns = deep(rows, sweep_results, wd / "deep_results.jsonl",
                     sample_rate=args.sample_rate, limit=args.limit)
        print(f"deep: judged {n} entries ({ns} audit-sample)")
        return 0
    if args.cmd == "collect":
        return collect(wd, rows, sweep_results)
    deep_results = _load_done(wd / "deep_results.jsonl")
    flags = build_flags(rows, sweep_results, deep_results)
    (wd / "flags.jsonl").write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in flags))
    counts = {}
    for f in flags:
        counts[f["class"]] = counts.get(f["class"], 0) + 1
    print(f"report: flags {counts} -> {wd / 'flags.jsonl'}")
    if args.file_captures:
        filed, skipped = file_captures(flags, wd / "capture_state.json")
        print(f"captures: filed {filed} new, skipped {skipped} already-filed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
