#!/usr/bin/env python3
"""DeepSeek 150B job splitter — the downward flow, built.

Brian (2026-10-28 08:00 CDT): the DeepSeek 150B splits big jobs into
SONIC JOBS and MORPHEUS JOBS. Brian (08:03): "build this and track it
so we know how efficient it is."

Design, per the record:
  * The deep tier (150B on Colibri; bravo first) decomposes, keeps the
    unsplittable pieces and the synthesis, and hands sized pieces DOWN:
    volume/routine -> Sonic (qwen_task_queue), bounded judgment with
    named outputs -> Morpheus (pm_steps kind=judgment). Judgment code
    can settle never becomes a model job (it stays out of the split).
  * Every piece arrives SET UP TO WIN (Brian, 2026-10-28 07:45): one
    narrow job, its content attached, a fixed answer shape.
  * Rule 25: every job carries a named cap (max pieces) and its
    done-check at creation. Hitting the cap stops the split.
  * The split is CODE-CHECKED, never trusted: strict JSON, tier set,
    per-tier size limits (Morpheus packet rule 24,000 chars), piece
    count vs the cap, and a coverage ratio (piece content vs job body)
    recorded on the job. A decomposition is a proposal until it passes.
  * EFFICIENCY LEDGER: deep_jobs / deep_pieces record every piece's
    tier, lane reference, status, tokens and duration, so the report
    can state the OFFLOAD RATIO (how much of each job the cheap tiers
    carried) against the whole-job deep-tier estimate (0.66 tok/s,
    Brian's measured REAP rate on alpha-class hardware, 2026-10-24).

The decomposer is a pluggable engine slot. "deep" is the real tier and
is NOT LIVE until bravo runs the 150B on Colibri (step zero: bravo
tailnet enrollment). Until then, mechanics are proven with a labeled
stand-in (decomposer field says so on every record it touches).
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pm"))
import sbos_common as S  # noqa: E402

MORPHEUS_URL = "http://127.0.0.1:11437/v1/chat/completions"
DEEP_URL = None  # bravo Colibri endpoint — set when the tier goes live
DEEP_TOK_S = 0.66  # Brian's measured REAP rate, alpha-class hardware
MORPHEUS_MAX_CHARS = 24000
SONIC_MAX_CHARS = 4000
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "state", "deep-split-report.md")
TIERS = ("sonic", "morpheus", "deep")
TERMINAL = ("done", "failed", "escalated", "held-deep")

SPLIT_PROMPT = """You are the decomposition step of a job splitter. Break the JOB below into pieces for cheaper worker tiers.

TIERS:
- "sonic": fast routine volume work - sorting, listing, extracting, drafting, counting. Fixed simple answer shape.
- "morpheus": ONE bounded judgment call with named outputs (a verdict, a choice, a match). Packet must stay small.
- "deep": only the parts that truly cannot be split and the final synthesis. Use sparingly.

RULES:
- At most {cap} pieces.
- Each piece is self-contained: include the content it needs inside its "content".
- If a part can be settled by a simple rule or count, fold it into another piece - it is not a piece of its own.
- "output_keys" is required for morpheus pieces (the named outputs), optional elsewhere.
- End with one "deep" piece titled "Synthesis" ONLY if the job needs its pieces joined into one answer.

Reply with a single JSON object only:
{{"pieces": [{{"tier": "sonic|morpheus|deep", "title": "...", "content": "...", "output_keys": ["..."]}}], "coverage_note": "how the pieces together cover the whole job"}}

JOB TITLE: {title}
DONE-CHECK (what finished looks like): {done_check}
JOB:
{body}"""


def ensure_schema():
    S.pg_exec("""CREATE TABLE IF NOT EXISTS successbrian_os.deep_jobs (
        id serial PRIMARY KEY, title text NOT NULL, body text NOT NULL,
        status text NOT NULL DEFAULT 'new', decomposer text,
        cap_pieces int NOT NULL, done_check text NOT NULL,
        coverage_ratio numeric, split_json jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz)""")
    S.pg_exec("""CREATE TABLE IF NOT EXISTS successbrian_os.deep_pieces (
        id serial PRIMARY KEY, job_id int NOT NULL, seq int NOT NULL,
        tier text NOT NULL, title text NOT NULL, content text NOT NULL,
        output_keys jsonb, status text NOT NULL DEFAULT 'split',
        lane_ref text, result text,
        prompt_tokens int, completion_tokens int, duration_s numeric,
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz)""")


def submit(title, body, cap, done_check):
    return S.pg_one("""INSERT INTO successbrian_os.deep_jobs
        (title, body, cap_pieces, done_check) VALUES (%s,%s,%s,%s)
        RETURNING id""", (title, body, cap, done_check))


def _extract_json(text):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def validate_split(data, cap, body_len):
    """Code-check a proposed decomposition. Returns (pieces, problems)."""
    problems = []
    if not isinstance(data, dict) or not isinstance(data.get("pieces"), list):
        return [], ["split is not an object with a pieces list"]
    pieces = data["pieces"]
    if not pieces:
        problems.append("split has zero pieces")
    if len(pieces) > cap:
        problems.append(f"split has {len(pieces)} pieces, cap is {cap}")
    for i, p in enumerate(pieces):
        t = p.get("tier")
        if t not in TIERS:
            problems.append(f"piece {i}: tier {t!r} not in {TIERS}")
        if not (p.get("title") or "").strip():
            problems.append(f"piece {i}: empty title")
        c = p.get("content") or ""
        if not c.strip():
            problems.append(f"piece {i}: empty content")
        if t == "morpheus" and len(c) > MORPHEUS_MAX_CHARS:
            problems.append(f"piece {i}: morpheus packet {len(c)} chars "
                            f"> {MORPHEUS_MAX_CHARS} (needs breakdown)")
        if t == "sonic" and len(c) > SONIC_MAX_CHARS:
            problems.append(f"piece {i}: sonic content {len(c)} chars "
                            f"> {SONIC_MAX_CHARS} (too big for one Sonic job)")
        if t == "morpheus" and not p.get("output_keys"):
            problems.append(f"piece {i}: morpheus piece without output_keys")
    return pieces, problems


def store_split(job_id, data, decomposer_label):
    job = S.pg_one("SELECT cap_pieces, body FROM successbrian_os.deep_jobs "
                   "WHERE id=%s", (job_id,))
    cap, body = job[0], job[1]
    pieces, problems = validate_split(data, cap, len(body))
    if problems:
        S.pg_exec("UPDATE successbrian_os.deep_jobs SET status='split-rejected', "
                  "decomposer=%s, split_json=%s, updated_at=now() WHERE id=%s",
                  (decomposer_label, json.dumps({"problems": problems,
                                                 "raw": data}), job_id))
        return None, problems
    total_chars = sum(len(p.get("content") or "") for p in pieces)
    coverage = round(min(1.0, total_chars / max(1, len(body))), 3)
    for i, p in enumerate(pieces):
        S.pg_exec("""INSERT INTO successbrian_os.deep_pieces
            (job_id, seq, tier, title, content, output_keys)
            VALUES (%s,%s,%s,%s,%s,%s)""",
                  (job_id, i + 1, p["tier"], p["title"].strip(),
                   p["content"], json.dumps(p.get("output_keys") or [])))
    S.pg_exec("""UPDATE successbrian_os.deep_jobs SET status='split',
        decomposer=%s, coverage_ratio=%s, split_json=%s, updated_at=now()
        WHERE id=%s""",
              (decomposer_label, coverage, json.dumps(data), job_id))
    S.pulse("deep-split", f"job {job_id} split into {len(pieces)} pieces",
            {"job_id": job_id, "pieces": len(pieces),
             "coverage_ratio": float(coverage), "decomposer": decomposer_label})
    return pieces, []


def decompose(job_id, engine):
    job = S.pg_one("SELECT title, body, cap_pieces, done_check FROM "
                   "successbrian_os.deep_jobs WHERE id=%s", (job_id,))
    title, body, cap, done_check = job
    prompt = SPLIT_PROMPT.format(cap=cap, title=title,
                                 done_check=done_check, body=body)
    if engine == "deep":
        if not DEEP_URL:
            raise SystemExit("deep engine is not live yet — bravo's 150B "
                             "(Colibri) is step zero. Use a labeled stand-in.")
        text, usage = S.llm_chat(prompt, url=DEEP_URL, model=None,
                                 max_tokens=4000, timeout=1800)
        label = "deepseek-150b (colibri)"
    elif engine == "morpheus":
        text, usage = S.llm_chat(prompt, url=MORPHEUS_URL, model="morpheus",
                                 max_tokens=3000, timeout=900)
        label = "morpheus-standin"
    else:
        text, usage = S.llm_chat(prompt, max_tokens=3000, timeout=600)
        label = "sonic-standin"
    data = _extract_json(text)
    if data is None:
        raise SystemExit("decomposer returned no parseable JSON — split "
                         "refused, nothing stored as pieces")
    pieces, problems = store_split(job_id, data, label)
    return pieces, problems, usage


def dispatch(job_id):
    import pm_core
    pieces = S.pg_rows("""SELECT id, seq, tier, title, content, output_keys
        FROM successbrian_os.deep_pieces WHERE job_id=%s AND status='split'
        ORDER BY seq""", (job_id,))
    sent = {"sonic": 0, "morpheus": 0, "deep": 0}
    for pid, seq, tier, title, content, keys in pieces:
        if tier == "sonic":
            desc = (f"Deep job {job_id} piece {seq} — split work from the "
                    f"deep tier. Do this one piece and report its result.\n\n"
                    f"PIECE: {title}\n\n{content}")
            lane = S.add_queue_task(f"[deep {job_id}.{seq}] {title}", desc,
                                    source="deep_split", priority=2)
            S.pg_exec("UPDATE successbrian_os.deep_pieces SET status='queued', "
                      "lane_ref=%s WHERE id=%s", (lane, pid))
            sent["sonic"] += 1
        elif tier == "morpheus":
            key = f"deep-{job_id}-{seq}"
            c = pm_core.conn()
            cur = c.cursor()
            okeys = keys or ["result"]
            # Key pinning (measured 2026-10-28): both proof-job Morpheus
            # pieces failed the worker's output contract because the model
            # returned good content NOT wrapped under the decomposer's key
            # names. Pinning the exact keys in the instruction fixed it
            # (retry passed first try). So the instruction always names
            # the keys explicitly — the split sets the piece up to win.
            instr = (f"{title}\n\nReply with a single JSON object containing "
                     f"exactly these output keys: {', '.join(okeys)}.")
            pm_core.add_step(
                cur, key, f"[deep {job_id}.{seq}] {title}", kind="judgment",
                source="deep_split", priority=90,
                payload={"instruction": instr, "context": content,
                         "output_keys": okeys,
                         "max_tokens": 800})
            c.commit()
            c.close()
            S.pg_exec("UPDATE successbrian_os.deep_pieces SET status='queued', "
                      "lane_ref=%s WHERE id=%s", (key, pid))
            sent["morpheus"] += 1
        else:
            S.pg_exec("UPDATE successbrian_os.deep_pieces SET "
                      "status='held-deep' WHERE id=%s", (pid,))
            sent["deep"] += 1
    S.pg_exec("UPDATE successbrian_os.deep_jobs SET status='dispatched', "
              "updated_at=now() WHERE id=%s", (job_id,))
    S.pulse("deep-split", f"job {job_id} dispatched", {"job_id": job_id, **sent})
    return sent


def _as_text(v, limit):
    """Lane results are not always text: pm_steps.result is jsonb and
    arrives as a dict. Coerce before slicing (a dict slice crashed
    collect on 2026-10-28)."""
    if v is None:
        return ""
    if not isinstance(v, str):
        v = json.dumps(v)
    return v[:limit]


def _sonic_tokens(task_id):
    rows = S.pg_rows("""SELECT metrics FROM successbrian_os.clerk_checkins
        WHERE source='qwen-task-worker'
          AND metrics->>'task_id' = %s""", (task_id,))
    pt = ct = 0
    for (m,) in rows:
        m = m or {}
        pt += int(m.get("prompt_tokens") or 0)
        ct += int(m.get("completion_tokens") or 0)
    return (pt or None), (ct or None)


def collect(job_id=None):
    q = ("SELECT id, job_id, tier, lane_ref FROM successbrian_os.deep_pieces "
         "WHERE status='queued'")
    args = ()
    if job_id:
        q += " AND job_id=%s"
        args = (job_id,)
    changed = 0
    for pid, jid, tier, lane in S.pg_rows(q, args):
        if tier == "sonic":
            r = S.pg_one("SELECT status, result, finished_at FROM "
                         "successbrian_os.qwen_task_queue WHERE id=%s", (lane,))
            if not r:
                continue
            st, result, fin = r
            if st in ("done", "completed"):
                pt, ct = _sonic_tokens(lane)
                S.pg_exec("""UPDATE successbrian_os.deep_pieces SET status='done',
                    result=%s, prompt_tokens=%s, completion_tokens=%s,
                    finished_at=now() WHERE id=%s""",
                          (_as_text(result, 4000), pt, ct, pid))
                changed += 1
            elif st in ("needs_brian", "escalated"):
                S.pg_exec("UPDATE successbrian_os.deep_pieces SET "
                          "status='escalated', finished_at=now() WHERE id=%s",
                          (pid,))
                changed += 1
        elif tier == "morpheus":
            r = S.pg_one("""SELECT status, result, EXTRACT(EPOCH FROM
                (finished_at - created_at)) FROM successbrian_os.pm_steps
                WHERE step_key=%s""", (lane,))
            if not r:
                continue
            st, result, dur = r
            if st == "done":
                S.pg_exec("""UPDATE successbrian_os.deep_pieces SET status='done',
                    result=%s, duration_s=%s, finished_at=now() WHERE id=%s""",
                          (_as_text(result, 4000),
                           float(dur) if dur else None, pid))
                changed += 1
            elif st in ("failed", "blocked"):
                S.pg_exec("""UPDATE successbrian_os.deep_pieces SET status='failed',
                    result=%s, finished_at=now() WHERE id=%s""",
                          (_as_text(result, 2000), pid))
                changed += 1
    jobs = S.pg_rows("SELECT DISTINCT job_id FROM successbrian_os.deep_pieces "
                     "WHERE status IN ('done','failed','escalated','held-deep')")
    for (jid,) in jobs:
        if job_id and jid != job_id:
            continue
        open_n = S.pg_one("SELECT count(*) FROM successbrian_os.deep_pieces "
                          "WHERE job_id=%s AND status NOT IN "
                          "('done','failed','escalated','held-deep')",
                          (jid,))
        if open_n == 0:
            held = S.pg_one("SELECT count(*) FROM successbrian_os.deep_pieces "
                            "WHERE job_id=%s AND status='held-deep'", (jid,))
            new = "awaiting-deep" if held else "pieces-done"
            S.pg_exec("""UPDATE successbrian_os.deep_jobs SET status=%s,
                finished_at=COALESCE(finished_at, now()), updated_at=now()
                WHERE id=%s AND status NOT IN ('pieces-done','awaiting-deep')""",
                      (new, jid))
    return changed


def report(check=False):
    ensure_schema()
    jobs = S.pg_rows("""SELECT id, title, status, decomposer, coverage_ratio,
        cap_pieces, created_at, finished_at FROM successbrian_os.deep_jobs
        ORDER BY id DESC LIMIT 25""")
    lines = ["# Deep split — efficiency ledger", "",
             f"Rendered {time.strftime('%Y-%m-%d %H:%M %Z')}. Whole-job "
             f"baseline: the deep tier alone at {DEEP_TOK_S} tok/s "
             "(Brian's measured REAP rate).", ""]
    tot_pieces = tot_off = 0
    for jid, title, status, dec, cov, cap, created, fin in jobs:
        pcs = S.pg_rows("""SELECT tier, status, prompt_tokens, completion_tokens,
            duration_s FROM successbrian_os.deep_pieces WHERE job_id=%s""",
                        (jid,))
        by_tier = {}
        for t, st, pt, ct, dur in pcs:
            d = by_tier.setdefault(t, {"n": 0, "done": 0, "pt": 0, "ct": 0,
                                       "dur": 0.0})
            d["n"] += 1
            if st == "done":
                d["done"] += 1
            d["pt"] += pt or 0
            d["ct"] += ct or 0
            d["dur"] += float(dur or 0)
        n = len(pcs)
        off = sum(1 for t, *_ in pcs if t in ("sonic", "morpheus"))
        tot_pieces += n
        tot_off += off
        cheap_tokens = sum(by_tier.get(t, {}).get("pt", 0) +
                           by_tier.get(t, {}).get("ct", 0)
                           for t in ("sonic", "morpheus"))
        all_tokens = sum(d["pt"] + d["ct"] for d in by_tier.values())
        lines.append(f"## Job {jid} — {title}")
        lines.append(f"- status {status} | decomposer {dec or '-'} | "
                     f"coverage {cov if cov is not None else '-'} | "
                     f"pieces {n} (cap {cap})")
        for t in TIERS:
            if t in by_tier:
                d = by_tier[t]
                lines.append(f"- {t}: {d['done']}/{d['n']} done, "
                             f"{d['pt'] + d['ct']} tokens measured, "
                             f"{d['dur']:.0f}s lane time")
        if n:
            lines.append(f"- **offload: {off}/{n} pieces "
                         f"({100.0 * off / n:.0f}%) ran on Sonic/Morpheus**"
                         + (f"; {cheap_tokens} of {all_tokens} measured "
                            f"tokens at the cheap tiers" if all_tokens else
                            "; tokens still accumulating"))
        lines.append("")
    if tot_pieces:
        lines.append(f"**All jobs: offload {tot_off}/{tot_pieces} pieces "
                     f"({100.0 * tot_off / tot_pieces:.0f}%).**")
    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        f.write(text)
    if check:
        print("OK deep-split report renders;", len(jobs), "jobs")
        return 0
    print(text)
    return 0


def selftest():
    ensure_schema()
    jid = submit("selftest split", "Sort these 9 notes into piles and judge "
                 "the odd one. " + "note body. " * 20, 4,
                 "pieces terminal in the ledger")
    good = {"pieces": [
        {"tier": "sonic", "title": "Sort the notes",
         "content": "Sort the 9 notes into piles by topic."},
        {"tier": "morpheus", "title": "Judge the odd one",
         "content": "Which note does not belong, and why?",
         "output_keys": ["odd_one", "why"]},
        {"tier": "deep", "title": "Synthesis",
         "content": "Join the sort and the judgment into one answer."}],
        "coverage_note": "sort + judgment + synthesis cover the job"}
    pieces, problems = store_split(jid, good, "selftest")
    assert pieces and not problems, problems
    bad = {"pieces": [{"tier": "morpheus", "title": "Too big",
                       "content": "x" * (MORPHEUS_MAX_CHARS + 1),
                       "output_keys": ["a"]}]}
    jid2 = submit("selftest reject", "body", 4, "rejected")
    pieces2, problems2 = store_split(jid2, bad, "selftest")
    assert pieces2 is None and problems2, "oversize morpheus packet accepted!"
    S.pg_exec("DELETE FROM successbrian_os.deep_pieces WHERE job_id IN (%s,%s)",
              (jid, jid2))
    S.pg_exec("DELETE FROM successbrian_os.deep_jobs WHERE id IN (%s,%s)",
              (jid, jid2))
    print("PASS split stored with coverage; oversize morpheus packet rejected")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("selftest")
    p = sub.add_parser("submit")
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--cap", type=int, default=10)
    p.add_argument("--done-check", required=True)
    p = sub.add_parser("decompose")
    p.add_argument("--job", type=int, required=True)
    p.add_argument("--engine", default="sonic",
                   choices=["sonic", "morpheus", "deep"])
    p = sub.add_parser("dispatch")
    p.add_argument("--job", type=int, required=True)
    p = sub.add_parser("collect")
    p.add_argument("--job", type=int)
    p = sub.add_parser("report")
    p.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    ensure_schema()
    if a.cmd == "init":
        print("schema ready")
    elif a.cmd == "selftest":
        return selftest()
    elif a.cmd == "submit":
        print("job", submit(a.title, a.body, a.cap, a.done_check))
    elif a.cmd == "decompose":
        pieces, problems, usage = decompose(a.job, a.engine)
        if problems:
            print("SPLIT REJECTED:", problems)
            return 1
        print(f"job {a.job}: {len(pieces)} pieces stored; decomposer usage "
              f"{usage.get('total_tokens')} tokens")
    elif a.cmd == "dispatch":
        print("dispatched:", dispatch(a.job))
    elif a.cmd == "collect":
        print("pieces updated:", collect(a.job))
    elif a.cmd == "report":
        return report(check=a.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
