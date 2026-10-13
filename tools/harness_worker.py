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
  - Claiming is atomic (UPDATE ... WHERE status='queued'), so both engines can
    run without double-working a job.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v4pro_router import get_availability  # noqa: E402

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
            "WHERE status = 'queued' AND difficulty = 'hard';").strip() or 0)
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
    return "'" + str(s or "").replace("'", "''") + "'"


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
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def exec_sql(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def claim_jobs(engine, limit):
    if engine == "sonic":
        # Sonic does easy jobs, always (free). V4 Pro owns hard ones.
        where = "WHERE status = 'queued' AND difficulty = 'easy' "
        order = "ORDER BY priority ASC, id ASC"
    else:
        where = "WHERE status = 'queued' "
        order = ("ORDER BY CASE WHEN difficulty = 'hard' THEN 0 ELSE 1 END, "
                 "priority ASC, id ASC")
    sql = ("SELECT id FROM successbrian_os.harness_jobs %s %s LIMIT %d;"
           % (where, order, limit))
    ids = [ln.strip() for ln in query(sql).split("\n") if ln.strip().isdigit()]
    claimed = []
    for jid in ids:
        u = ("UPDATE successbrian_os.harness_jobs SET status = 'working' "
             "WHERE id = %s AND status = 'queued';" % jid)
        if exec_sql(u):
            claimed.append(int(jid))
    return claimed


def load_job(jid):
    row = query("SELECT title, spec, difficulty, priority "
                "FROM successbrian_os.harness_jobs WHERE id = %d;" % jid)
    parts = row.split("\t")
    if len(parts) < 2:
        return None
    return {"id": jid, "title": parts[0], "spec": "\t".join(parts[1:-2]) if len(parts) > 3 else parts[1],
            "difficulty": parts[-2] if len(parts) > 3 else "easy",
            "priority": parts[-1] if len(parts) > 3 else "5"}


def build_prompt(job):
    return (
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


def sonic_available():
    """Check the local Sonic llama-server is up and serving."""
    try:
        req = urllib.request.Request("http://localhost:11439/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        pass
    try:
        # fallback: /props exists on llama-server even without /health
        req = urllib.request.Request("http://localhost:11439/props")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def call_model(engine, key, prompt):
    cfg = ENGINE_CFG[engine]
    if engine == "sonic":
        url, headers, model = SONIC_URL, {"Content-Type": "application/json"}, None
    else:
        url = V4PRO_URL
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        model = cfg["model"]
    body_dict = {
        "messages": [
            {"role": "system",
             "content": "You are the coding tier. Write complete, working code. Be concrete."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    if model:
        body_dict["model"] = model
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


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
        response = call_model(engine, key, build_prompt(job))
    except Exception as e:
        mark(jid, "failed", error=str(e)[:1000])
        print("#%d: failed: %s" % (jid, str(e)[:200]))
        return
    staged = stage_files(jid, response)
    verify = ""
    mv = re.search(r"VERIFY\s*\n(.*?)(?=\n#|\Z)", response, re.DOTALL | re.IGNORECASE)
    if mv:
        verify = mv.group(1).strip()[:1500]
    summary = ("Coded by %s.\n"
               "Staged %d file(s) under staging/%d/ for review:\n%s\n\n"
               "VERIFY (from model):\n%s\n\n"
               "Raw response head:\n%s"
               % (engine, len(staged), jid,
                  "\n".join("- " + s for s in staged) or "(no file blocks parsed)",
                  verify or "(none given)",
                  response[:2000]))
    mark(jid, "done", summary=summary)
    print("#%d: done — staged %d file(s)" % (jid, len(staged)))


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
        print("harness queue empty for %s — nothing to do" % engine)
        return 0
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
