#!/usr/bin/env python3
"""Engine queue runner — claims queued engine jobs and executes
them against the local model endpoints.

Built 2026-11-08 for the heartbeat queue mode (Brian: "can the
heartbeat be sent to a queue; multiple small prompts?"), and
extended the same day for Brian's heartbeat-optimization pass:
heartbeats become multiple tasks in various queues — REAP 150B,
Sonic, Penny, Morpheus.

Kinds are registered handlers per engine; a job kind with no
handler here is left in the queue for its own claimant —
REAP's jobs are NEVER touched by this runner (REAP is its own
thing, node-agnostic, Brian 2026-11-08; this runner has no
reap engine entry at all).

Handlers:
  (sonic, heartbeat-decompose) — the heartbeat's decomposition
    prompt, executed exactly as altair_heartbeat_v4pro.call_sonic
    does (same system message, temperature, uncapped reply).
  (sonic|morpheus|penny, chat) — generic one-shot chat:
    payload {prompt, system?, max_tokens?, temperature?} ->
    {"text": ...}. Domain logic (prompt building, reply
    parsing) stays with the job's owner; the runner only runs
    the model call. Results are stored as JSON strings in the
    queue's TEXT result column.

usage: engine_runner.py [--engine sonic] [--max N]
       [--kinds a,b] [--selftest]
Cron: every 5 minutes per engine. Does nothing when the queue
holds no claimable jobs of a registered kind.

Failure reduction (Brian, 2026-11-08 — "do what is best"
after the 14:20 live check: sonic_queue 8 done / 11 failed,
morpheus 10 / 18, penny 6 / 3, EVERY failure a timeout):
  * A timed-out job is RELEASED back to queued via
    sbos_common.engine_job_timeout_retry (attempt counted,
    prompt tiered down); only the 3rd timed-out attempt fails,
    loudly, as 'timed out after 3 attempts'. Non-timeout
    errors still fail immediately.
  * SLOT-PRESSURE GATE (sonic only): before claiming new
    sonic jobs, GET /slots — if every slot is processing,
    claim nothing and exit quietly with one GATE-ENGAGED log
    line (the runner's cron log is the measurement). Chat is
    never gated: this runner only runs automated queue jobs.
    Morpheus/Penny claiming is not gated on Sonic's slots.
"""
import argparse
import json
import sys
import urllib.request

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
import sbos_common  # noqa: E402

ENGINE_URLS = {
    "sonic": sbos_common.SONIC_URL,
    "morpheus": sbos_common.MORPHEUS_URL,
    "penny": sbos_common.PENNY_URL,
}


def handle_heartbeat_decompose(payload):
    """Mirror of altair_heartbeat_v4pro.call_sonic — same system
    message, temperature and reply budget, so shadow comparisons
    are apples-to-apples."""
    prompt = (payload or {}).get("prompt", "")
    text, _usage = sbos_common.llm_chat(
        messages=[
            {"role": "system",
             "content": "You are a task decomposer for Brian's agent "
                        "fleet. Be concrete, decisive, and brief."},
            {"role": "user", "content": prompt},
        ],
        url=sbos_common.SONIC_URL, model=None, max_tokens=None,
        temperature=0.7, timeout=300)
    return {"text": text}


def make_chat_handler(engine):
    url = ENGINE_URLS[engine]

    def handle_chat(payload):
        payload = payload or {}
        messages = payload.get("messages")
        if not messages:
            messages = []
            if payload.get("system"):
                messages.append({"role": "system",
                                 "content": payload["system"]})
            messages.append({"role": "user",
                             "content": payload.get("prompt", "")})
        text, _usage = sbos_common.llm_chat(
            messages=messages, url=url, model=None,
            max_tokens=payload.get("max_tokens"),
            temperature=payload.get("temperature", 0.3),
            timeout=payload.get("timeout", 300))
        return {"text": text}

    return handle_chat


HANDLERS = {
    ("sonic", "heartbeat-decompose"): handle_heartbeat_decompose,
    ("sonic", "chat"): make_chat_handler("sonic"),
    ("morpheus", "chat"): make_chat_handler("morpheus"),
    ("penny", "chat"): make_chat_handler("penny"),
}

DEFAULT_KINDS = {
    "sonic": "heartbeat-decompose,chat",
    "morpheus": "chat",
    "penny": "chat",
}


def is_timeout_error(e):
    """True when an engine call died on time, not on substance:
    a builtin TimeoutError (urllib raises it on read timeouts,
    message 'timed out'), or any error whose text says so."""
    if isinstance(e, TimeoutError):
        return True
    s = str(e).lower()
    return "timed out" in s or "timeout" in s


SONIC_SLOTS_URL = (sbos_common.SONIC_URL.split("/v1/")[0]
                   + "/slots")


def _slots_all_busy(slots):
    """Pure gate test: a non-empty slot list where EVERY slot
    is processing. An empty/unreadable list never engages the
    gate (fail-open — a broken probe must not stop the fleet)."""
    return bool(slots) and all(
        s.get("is_processing") for s in slots
        if isinstance(s, dict))


def sonic_gate():
    """(engaged, busy, total) from Sonic's live /slots.
    Fail-open: any probe error returns (False, 0, 0)."""
    try:
        req = urllib.request.Request(SONIC_SLOTS_URL)
        with urllib.request.urlopen(req, timeout=5) as r:
            slots = json.loads(r.read().decode())
    except Exception:
        return (False, 0, 0)
    if not isinstance(slots, list):
        return (False, 0, 0)
    busy = sum(1 for s in slots
               if isinstance(s, dict) and s.get("is_processing"))
    return (_slots_all_busy(slots), busy, len(slots))


def _execute(engine, job):
    """Run one claimed job through its handler. Returns an
    outcome word: done / released / requeued / failed.
    Timeout outcomes go through the shared retry core —
    a timeout is unfinished work, not a verdict on the job."""
    handler = HANDLERS.get((engine, job["kind"]))
    if not handler:
        sbos_common.engine_job_release(engine, job["id"])
        print("job #%s kind %s has no handler — released "
              "for its own claimant" % (job["id"], job["kind"]))
        return "released"
    try:
        result = handler(job.get("payload") or {})
        sbos_common.engine_job_finish(
            engine, job["id"], json.dumps(result))
        print("job #%s (%s/%s) done"
              % (job["id"], engine, job["kind"]))
        return "done"
    except Exception as e:
        if is_timeout_error(e):
            outcome = sbos_common.engine_job_timeout_retry(
                engine, job["id"])
            if outcome == "requeued":
                print("job #%s (%s/%s) TIMED OUT — requeued "
                      "(attempt counted, prompt tiered down)"
                      % (job["id"], engine, job["kind"]))
            else:
                print("job #%s (%s/%s) FAILED: timed out after "
                      "%d attempts"
                      % (job["id"], engine, job["kind"],
                         sbos_common.TIMEOUT_MAX_ATTEMPTS))
            return outcome
        sbos_common.engine_job_finish(
            engine, job["id"], str(e)[:400], ok=False)
        print("job #%s (%s/%s) FAILED: %s"
              % (job["id"], engine, job["kind"], str(e)[:150]))
        return "failed"


def run(engine="sonic", max_jobs=3, kinds=None):
    want = None
    kinds = kinds or DEFAULT_KINDS.get(engine, "")
    if kinds:
        want = [k.strip() for k in kinds.split(",") if k.strip()]
    done = 0
    while done < max_jobs:
        if engine == "sonic":
            engaged, busy, total = sonic_gate()
            if engaged:
                print("GATE-ENGAGED: sonic slots all processing "
                      "(%d/%d) — no new sonic jobs claimed this "
                      "run" % (busy, total))
                break
        jobs = sbos_common.engine_job_claim(
            engine, "engine-runner-alpha", kinds=want,
            limit=max_jobs - done)
        if not jobs:
            break
        for job in jobs:
            _execute(engine, job)
            done += 1
    return done


SELFTEST_TAG = "engine-runner-selftest"


def _claim_own(engine, tag):
    """Claim until we hold one job created by `tag`, releasing
    anything else back untouched. Returns the job or None."""
    for _ in range(10):
        jobs = sbos_common.engine_job_claim(
            engine, SELFTEST_TAG, kinds=["chat"], limit=5)
        if not jobs:
            return None
        mine = None
        for j in jobs:
            if j["created_by"] == tag and mine is None:
                mine = j
            else:
                sbos_common.engine_job_release(engine, j["id"])
        if mine:
            return mine
    return None


def _cleanup_selftest(engine="penny"):
    sbos_common.pg_exec(
        "DELETE FROM %s WHERE created_by = %%s"
        % sbos_common.ENGINE_JOB_TABLES[engine], (SELFTEST_TAG,))


def _job_row(engine, job_id):
    rows = sbos_common.pg_rows(
        "SELECT status, attempts, result, payload FROM %s "
        "WHERE id = %%s" % sbos_common.ENGINE_JOB_TABLES[engine],
        (int(job_id),))
    return rows[0] if rows else None


def selftest():
    for key in [("sonic", "heartbeat-decompose"), ("sonic", "chat"),
                ("morpheus", "chat"), ("penny", "chat")]:
        assert key in HANDLERS, key
    assert "reap" not in ENGINE_URLS  # REAP is never ours to run
    jobs = sbos_common.engine_job_claim(
        "sonic", "engine-runner-selftest",
        kinds=["__no_such_kind__"], limit=1)
    assert jobs == [], jobs
    # --- timeout detection + gate shape (pure, no DB) ---
    assert is_timeout_error(TimeoutError("timed out"))
    assert is_timeout_error(Exception("HTTP timeout expired"))
    assert not is_timeout_error(ValueError("bad prompt"))
    assert _slots_all_busy([{"is_processing": True},
                            {"is_processing": True}])
    assert not _slots_all_busy([{"is_processing": True},
                                {"is_processing": False}])
    assert not _slots_all_busy([])
    # --- timeout -> requeue -> tier-down -> terminal failure ---
    # Live roundtrip on the penny queue (cheapest engine; the
    # retry core is shared by all four queues). Test rows are
    # tagged and deleted at the end — no residue.
    _cleanup_selftest("penny")
    big = "x" * (sbos_common.SONIC_KV_AUTO * 4 + 5000)
    try:
        jid = sbos_common.engine_job_enqueue(
            "penny", SELFTEST_TAG, "chat",
            "selftest timeout-requeue",
            payload={"prompt": big, "max_tokens": 10},
            source_ref="selftest:failred")
        job = _claim_own("penny", SELFTEST_TAG)
        assert job and job["id"] == jid, job
        out = sbos_common.engine_job_timeout_retry("penny", jid)
        assert out == "requeued", out
        st, att, res, payload = _job_row("penny", jid)
        assert st == "queued" and att == 1, (st, att)
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert len(payload["prompt"]) < len(big), \
            "retry prompt was not tiered down"
        job = _claim_own("penny", SELFTEST_TAG)
        assert job and job["id"] == jid
        out = sbos_common.engine_job_timeout_retry("penny", jid)
        assert out == "requeued", out
        job = _claim_own("penny", SELFTEST_TAG)
        assert job and job["id"] == jid
        out = sbos_common.engine_job_timeout_retry("penny", jid)
        assert out == "failed", out
        st, att, res, _p = _job_row("penny", jid)
        assert st == "failed" and att == 3, (st, att)
        assert "timed out after 3 attempts" in (res or ""), res
        # --- the runner's own branch: stub handler times out ---
        jid2 = sbos_common.engine_job_enqueue(
            "penny", SELFTEST_TAG, "chat",
            "selftest runner timeout branch",
            payload={"prompt": "small", "max_tokens": 10},
            source_ref="selftest:failred")
        job = _claim_own("penny", SELFTEST_TAG)
        assert job and job["id"] == jid2, job
        real = HANDLERS[("penny", "chat")]

        def _raiser(payload):
            raise TimeoutError("timed out")
        HANDLERS[("penny", "chat")] = _raiser
        try:
            outcome = _execute("penny", job)
        finally:
            HANDLERS[("penny", "chat")] = real
        assert outcome == "requeued", outcome
        st, att, _r, _p = _job_row("penny", jid2)
        assert st == "queued" and att == 1, (st, att)
    finally:
        _cleanup_selftest("penny")
    left = sbos_common.pg_one(
        "SELECT count(*) FROM %s WHERE created_by = %%s"
        % sbos_common.ENGINE_JOB_TABLES["penny"], (SELFTEST_TAG,))
    assert int(left) == 0, left
    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="sonic",
                    choices=["sonic", "morpheus", "penny"])
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--kinds", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    n = run(engine=a.engine, max_jobs=a.max, kinds=a.kinds)
    print("runner: %d job(s) executed" % n)
