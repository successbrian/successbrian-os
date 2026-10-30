#!/usr/bin/env python3
"""
harness_worker.py — the Mantis coding harness gets its code written.

PURPOSE: Pick up queued harness jobs and do the coding, on one of two engines:
         --engine v4pro (default): DeepSeek V4 Pro, when its rental credits are
           available. Hard jobs first, then by priority. Max 3/run (spend bound).
         --engine sonic: the local Sonic model (Qwen3.6-35B-A3B, :11439), free,
           always runs when the server is up. Easy jobs only. Max 2/run (it's slow).
         Both stage returned files under mantis-coding-harness/staging/<job-id>/
         for review and record the outcome. Neither ever deploys.
WHY: Brian 2026-10-12: "deepseek v4 pro needs to run the coding harness when
     it is available" + "can we get sonic running?" The Oct 7 worker rule said
     "V4 Pro available -> burn hard jobs with cloud; down -> easy queue with
     local models", but no worker was ever built — jobs queued with no executor
     (Spencer was the fallback coder). V4 Pro is the cloud coder, Sonic the
     local coder; the box stages and validates. Neither model "runs" anything
     itself, so execution/validation stays on Brian's hardware by design.
CALLED BY: system cron — v4pro 12,42 * * * *; sonic 7,37 * * * * (successbrian).
           Staggered off the heartbeat (:05/:35) and handoff worker (:00/:15/:30/:45).
NOTES:
  - V4 Pro availability ONLY from v4pro_router.get_availability() (checker table),
    re-checked before EVERY API call. Never spends when stale or $0.
    Queued jobs wait; they are never failed for lack of credits.
  - Key: DEEPSEEK_API_KEY from /home/successbrian/.hermes/.env (the
    InstantlyClaw rental). Never printed, logged, or written.
  - Sonic availability: llama-server health on localhost:11439.
  - Staging only — the worker NEVER deploys. Staged files land under
    staging/<job-id>/ preserving repo-relative paths (sanitized: no
    absolute paths, no .. escapes). Spencer / the X79 agent reviews and
    promotes per the harness code-move policy.
  - On model error the job is marked failed with the error text (truncated);
    it can be re-queued. Nothing retries silently.
  - Profile routing: a job's profile column (NULL = legacy difficulty routing)
    names its profile; PROFILE_ROUTING maps it to an engine ('altair' -> sonic).
    Unknown profiles are claimed by neither engine.
  - Usage capture (sprint cycle 18, 2026-10-26): call_model_with_usage
    returns the server's usage field alongside the text, and run_job
    records it in the job's result_summary -- proof runs report tokens
    instead of discarding them, as the Qwen worker does since cycle 15.
  - Claiming is atomic in ONE statement (UPDATE ... WHERE status='queued'
    RETURNING id), and a job counts as claimed only when the returned id
    matches — a lost race returns only "UPDATE 0", so no two concurrent
    runs (same engine, or sonic :07/:37 vs v4pro :12/:42 on a legacy
    easy job) can double-work a job or double-stage under staging/<id>/.
    No lockfile is needed: the single-statement claim IS the lock.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability  # noqa: E402
import sbos_common  # SBOS common routines — Batch A migration (2026-10-27)

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]

ENV_FILE = Path("/home/successbrian/.hermes/.env")
V4PRO_URL = "https://api.deepseek.com/v1/chat/completions"
V4PRO_MODEL = "deepseek-v4-pro"
SONIC_URL = "http://localhost:11439/v1/chat/completions"

ENGINE_CFG = {
    "v4pro": {"max_per_run": 3, "timeout": 600, "model": V4PRO_MODEL},
    "sonic": {"max_per_run": 2, "timeout": 1500, "model": "sonic"},
}
# Profile routing (sprint cycle 16, 2026-10-26): ONE profile end to end.
# A job's profile column (NULL = legacy) names the profile it must be coded
# under. PROFILE_ROUTING maps a profile name to the engine that owns it; a
# profile with no mapping is claimed by NEITHER engine, so a typo never
# builds on the wrong engine -- it stays queued, visible.
# The first (and only) profile: 'altair' -> 'sonic'. Altair's own model
# stays Sonic (Brian 2026-10-26 09:28/11:23 rulings), so a coding job filed
# under Altair's profile is coded by Sonic whatever its difficulty --
# profile overrides difficulty, by design.
PROFILE_ROUTING = {"altair": "sonic"}
PROFILE_PROMPT = {
    "altair": ("PROFILE: altair -- code this as Altair would: Sonic engine, "
               "deterministic first, no placeholders, no TODOs."),
}


def profile_engine(profile):
    """Engine owning a profile name, or None (legacy/unknown)."""
    if not profile:
        return None
    return PROFILE_ROUTING.get(str(profile).strip().lower())


def claim_where(engine):
    """Pure WHERE clause for claim_jobs -- unit-tested offline.

    sonic: profile='altair' jobs (any difficulty) plus legacy
    (profile IS NULL) easy jobs. v4pro: legacy jobs only, so a
    profiled job can never be claimed by the wrong engine.
    """
    if engine == "sonic":
        return ("WHERE status = 'queued' AND (profile = 'altair' OR "
                "(profile IS NULL AND difficulty = 'easy')) ")
    return "WHERE status = 'queued' AND profile IS NULL "


# Queue-adaptive caps for v4pro (per Brian 2026-10-13): when the task queue is
# high AND v4pro is available, more workers assist — the per-run cap scales
# with queued hard-job depth. Availability is still re-checked per job, so a
# dead API never burns the higher cap.
V4PRO_SURGE = [(12, 9), (6, 6)]  # (queued_hard >= depth) -> cap


def adaptive_cap(engine):
    base = ENGINE_CFG[engine]["max_per_run"]
    if engine != "v4pro":
        return base
    try:
        queued = int(query(
            "SELECT count(*) FROM successbrian_os.harness_jobs "
            "WHERE status = 'queued' AND profile IS NULL AND difficulty = 'hard';").strip() or 0)
    except Exception:
        return base
    for depth, cap in V4PRO_SURGE:
        if queued >= depth:
            print("v4pro surge: queued_hard=%d -> cap %d/run" % (queued, cap))
            return cap
    return base
STAGING = Path("/home/successbrian/mantis-coding-harness/staging")

FILE_RE = re.compile(
    r"===\s*FILE:\s*(.+?)\s*===\s*\n(.*?)(?=\n===\s*FILE:|\n===\s*END\s*FILE\s*===|\Z)",
    re.DOTALL)


def pq(s):
    # Batch A migration (2026-10-27): the escaping delegates to
    # sbos_common.esc; pq keeps its quote-wrapping shape for callers.
    return "'" + sbos_common.esc(s) + "'"


def get_key():
    try:
        for line in ENV_FILE.read_text().splitlines():
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                v = s.split("=", 1)[1].strip().strip("'\"")
                if v and v != "none":
                    return v
    except Exception:
        pass
    return ""


def query(sql):
    # Batch A migration (2026-10-27): delegates to sbos_common.pg_text
    # (tab separator, psql-exact formatting, equivalence-tested against
    # the psql CLI; '' on error, as before).
    return sbos_common.pg_text(sql, sep="\t").strip()


def exec_sql(sql):
    # Batch A migration (2026-10-27): delegates to sbos_common.
    return sbos_common.pg_exec_bool(sql)


def claim_jobs(engine, limit):
    where = claim_where(engine)
    if engine == "sonic":
        # Sonic: altair-profile jobs (any difficulty) + legacy easy jobs.
        order = "ORDER BY priority ASC, id ASC"
    else:
        # V4 Pro: legacy jobs only, hard first, then priority.
        order = ("ORDER BY CASE WHEN difficulty = 'hard' THEN 0 ELSE 1 END, "
                 "priority ASC, id ASC")
    sql = ("SELECT id FROM successbrian_os.harness_jobs %s %s LIMIT %d;"
           % (where, order, limit))
    ids = [ln.strip() for ln in query(sql).split("\n") if ln.strip().isdigit()]
    claimed = []
    for jid in ids:
        # Single-statement atomic claim (sprint cycle 23, 2026-10-26):
        # the old code checked only psql's exit code, which is 0 even
        # when the UPDATE touches 0 rows — so a second concurrent run
        # (same engine on the next tick, or the other engine 5 min
        # later on a legacy easy job) would "claim" a job another run
        # already held, double-coding it and double-staging under
        # staging/<id>/. RETURNING id fixes it: query() returns
        # "<id>\nUPDATE 1" on a won race and "UPDATE 0" on a lost
        # one, so only a first line equal to the job id counts.
        u = ("UPDATE successbrian_os.harness_jobs SET status = 'working' "
             "WHERE id = %s AND status = 'queued' RETURNING id;" % jid)
        returned = query(u).splitlines()
        if returned and returned[0].strip() == str(jid):
            claimed.append(int(jid))
    return claimed


def load_job(jid):
    row = query("SELECT title, spec, difficulty, priority, coalesce(profile, '__NULL_PROFILE__') "
                "FROM successbrian_os.harness_jobs WHERE id = %d;" % jid)
    parts = row.split("\t")
    if len(parts) < 4:
        return None
    # Last fields are difficulty, priority, profile: the spec itself
    # may contain tabs, so it takes everything between title and the
    # trailing fields. The SELECT above coalesces a NULL profile to a
    # sentinel, so the last field is never empty and query()'s strip
    # cannot shift the trailing fields.
    if len(parts) == 4:
        return {"id": jid, "title": parts[0], "spec": "\t".join(parts[1:-2]),
                "difficulty": parts[-2], "priority": parts[-1],
                "profile": None}
    prof = parts[-1]
    return {"id": jid, "title": parts[0], "spec": "\t".join(parts[1:-3]),
            "difficulty": parts[-3], "priority": parts[-2],
            "profile": None if prof in ("", "__NULL_PROFILE__") else prof}


def build_prompt(job):
    prompt = (
        "You are the coding tier of Brian's agent fleet, working inside his "
        "Mantis coding harness. Write working code — no placeholders, no TODOs.\n\n"
        "JOB #%d: %s\n\nSPEC:\n%s\n\n"
        "RULES:\n"
        "- Python: every file gets a docstring with PURPOSE / WHY / CALLED BY / NOTES.\n"
        "- Deterministic first: dumb code before clever code.\n"
        "- Never hardcode runtime state (balances, availability); read it from tables at runtime.\n"
        "- Output the deliverable as file blocks, one per file:\n"
        "  === FILE: <repo-relative path> ===\n"
        "  <complete file content>\n"
        "  === END FILE ===\n"
        "- Then a VERIFY section: the exact commands that run the mechanical done-check.\n"
        "- If the spec can't be built as written, say what's wrong and build the closest working version.\n"
        % (job["id"], job["title"], job["spec"] or "(no spec — do the obvious thing well)")
    )
    if job.get("profile"):
        line = (PROFILE_PROMPT.get(str(job["profile"]).strip().lower())
                or ("PROFILE: %s" % job["profile"]))
        prompt = prompt.replace("\n\nSPEC:", "\n\n" + line + "\nSPEC:", 1)
    return prompt


def sonic_available():
    """Check the local Sonic llama-server is up and serving.
    Batch A migration (2026-10-27): the GET-200 checks delegate to
    sbos_common.http_ok; the /props fallback is preserved."""
    if sbos_common.http_ok("http://localhost:11439/health"):
        return True
    # fallback: /props exists on llama-server even without /health
    return sbos_common.http_ok("http://localhost:11439/props")


def call_model_with_usage(engine, key, prompt):
    """Model call returning (text, usage dict), like cycle 15's
    ask_qwen_with_usage. usage keys: prompt_tokens, completion_tokens,
    total_tokens, model -- ints or None when the server omits them;
    total is derived from the two parts when the server omits it.
    Opens NO database connection.
    Batch A migration (2026-10-27): delegates to sbos_common.llm_chat,
    whose usage normalization is this same logic (total derived from
    parts; model from the response or the engine cfg fallback)."""
    cfg = ENGINE_CFG[engine]
    if engine == "sonic":
        url, headers, model = SONIC_URL, None, None
    else:
        url = V4PRO_URL
        headers = {"Authorization": "Bearer " + key}
        model = cfg["model"]
    text_out, usage = sbos_common.llm_chat(
        messages=[
            {"role": "system",
             "content": "You are the coding tier. Write complete, working code. Be concrete."},
            {"role": "user", "content": prompt},
        ],
        url=url, model=model, max_tokens=None, temperature=0.3,
        timeout=cfg["timeout"], headers=headers)
    if not usage.get("model"):
        usage["model"] = cfg["model"]
    return text_out, usage


def call_model(engine, key, prompt):
    """Backward-compatible wrapper: plain text only, existing callers unbroken."""
    text_out, _usage = call_model_with_usage(engine, key, prompt)
    return text_out


def usage_line(usage, duration_s):
    """One-line usage summary for the job summary and the worker log."""
    u = usage or {}

    def tok(k):
        v = u.get(k)
        return str(v) if v is not None else "?"

    return ("Usage: %s prompt + %s completion = %s total tokens, model %s, %.1f s"
            % (tok("prompt_tokens"), tok("completion_tokens"),
               tok("total_tokens"), u.get("model") or "?", duration_s))


def safe_stage_path(base, rel):
    rel = (rel or "").strip()
    if not rel:
        return None
    p = os.path.normpath("/" + rel).lstrip("/")
    if not p or p == ".":
        return None
    return base / p


def stage_files(jid, response):
    """Write parsed file blocks under staging/<jid>/. Returns [rel paths]."""
    staged = []
    base = STAGING / str(jid)
    for m in FILE_RE.finditer(response or ""):
        dest = safe_stage_path(base, m.group(1))
        if not dest:
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(m.group(2).rstrip() + "\n")
            staged.append(str(dest.relative_to(STAGING)))
        except OSError:
            continue
    return staged


def mark(jid, status, summary="", error=""):
    if error:
        summary = "ERROR: %s\n\n%s" % (error[:1000], summary)
    if status in ("done", "failed"):
        sql = ("UPDATE successbrian_os.harness_jobs SET status = %s, "
               "result_summary = %s, completed_at = now() WHERE id = %d;"
               % (pq(status), pq(summary[:20000]), jid))
    else:
        sql = ("UPDATE successbrian_os.harness_jobs SET status = %s, "
               "result_summary = %s WHERE id = %d;"
               % (pq(status), pq(summary[:20000]), jid))
    exec_sql(sql)


def release(jid):
    exec_sql("UPDATE successbrian_os.harness_jobs SET status = 'queued' "
             "WHERE id = %d;" % jid)


def run_job(engine, key, jid, dry_run=False):
    job = load_job(jid)
    if not job:
        print("#%d: could not load — released" % jid)
        release(jid)
        return
    if dry_run:
        print("DRY-RUN would code job #%d [%s] on %s: %s"
              % (jid, job["difficulty"], engine, job["title"][:70]))
        release(jid)
        return
    print("#%d: coding on %s [%s]: %s"
          % (jid, engine, job["difficulty"], job["title"][:60]))
    try:
        started = time.monotonic()
        response, usage = call_model_with_usage(engine, key, build_prompt(job))
        duration_s = time.monotonic() - started
    except Exception as e:
        mark(jid, "failed", error=str(e)[:1000])
        print("#%d: failed: %s" % (jid, str(e)[:200]))
        return
    staged = stage_files(jid, response)
    verify = ""
    mv = re.search(r"VERIFY\s*\n(.*?)(?=\n#|\Z)", response, re.DOTALL | re.IGNORECASE)
    if mv:
        verify = mv.group(1).strip()[:1500]
    summary = ("Coded by %s.\n%s\n"
               "Staged %d file(s) under staging/%d/ for review:\n%s\n\n"
               "VERIFY (from model):\n%s\n\n"
               "Raw response head:\n%s"
               % (engine, usage_line(usage, duration_s), len(staged), jid,
                  "\n".join("- " + s for s in staged) or "(no file blocks parsed)",
                  verify or "(none given)",
                  response[:2000]))
    mark(jid, "done", summary=summary)
    print("#%d: done — staged %d file(s), %s"
          % (jid, len(staged), usage_line(usage, duration_s)))


def engine_ready(engine, key):
    """Check the engine can work right now. Returns (ready, reason)."""
    if engine == "sonic":
        if sonic_available():
            return True, "sonic up on :11439"
        return False, "sonic server not responding on :11439"
    if not key:
        return False, "no DEEPSEEK_API_KEY"
    avail = get_availability()
    if not avail.get("usable"):
        return False, "V4 Pro not usable (%s)" % avail.get("reason")
    return True, "V4 Pro usable (balance $%.2f)" % avail.get("usd", 0)


def bridge_scream(subject, body):
    """File a scream on the live bridge. Silence is never just logged."""
    b = ("STARVATION-ALARM " + body).replace("'", "''")
    s = subject.replace("'", "''")
    exec_sql(f"INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
             f"VALUES ('harness-worker','dealsdesk','{s}','{b}','important')")


def starvation_diagnostic(engine, key):
    """Queue claimed empty. Brian's law: silence is a 5-alarm until proven
    healthy. Diagnose: is the engine actually reachable, or is the worker
    blind? Scream if broken; log the verdict if genuinely idle."""
    # independent second probe of the engine endpoint
    if engine == "sonic":
        engine_up = sonic_available()
        engine_name = "sonic :11439"
    else:
        avail = get_availability()
        engine_up = bool(key) and bool(avail.get("usable"))
        engine_name = "V4 Pro API"
    # race-safe recount
    left = query("SELECT count(*) FROM successbrian_os.harness_jobs "
                 "WHERE status = 'queued';").strip()
    # feeder freshness: when was work last filed?
    last_filed = query("SELECT coalesce(max(created_at)::text,'never') "
                       "FROM successbrian_os.harness_jobs;").strip()
    if not engine_up:
        msg = ("%s unreachable at idle check — worker blind, not idle. "
               "queue=%s last_filed=%s" % (engine_name, left, last_filed))
        print("STARVED-BROKEN: " + msg)
        bridge_scream("harness worker starved: %s down" % engine, msg)
        return 1
    print("idle-healthy: queue=%s confirmed empty, %s up, last job filed %s. "
          "Feeder (heartbeat decomposition) owns backlog refill."
          % (left, engine_name, last_filed))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["v4pro", "sonic"], default="v4pro")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    engine = args.engine
    cfg = ENGINE_CFG[engine]
    dry_run = args.dry_run

    key = get_key() if engine == "v4pro" else ""
    ready, reason = engine_ready(engine, key)
    if not ready:
        print("%s not ready (%s) — jobs wait" % (engine, reason))
        return 0
    claimed = claim_jobs(engine, adaptive_cap(engine))
    if not claimed:
        # Brian's law: an empty queue is a 5-alarm until proven healthy.
        # Diagnose before declaring idle — never just log "nothing to do".
        return starvation_diagnostic(engine, key)
    print("%s — %d job(s) claimed" % (reason, len(claimed)))
    for jid in claimed:
        ok, why = engine_ready(engine, key)
        if not ok:
            print("#%d: %s went unready (%s) — released" % (jid, engine, why))
            release(jid)
            continue
        run_job(engine, key, jid, dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
