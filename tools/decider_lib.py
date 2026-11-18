#!/usr/bin/env python3
"""Decider loop — Altair + Meghan package machinery.

Brian, 2026-11-08: Altair keeps a half-hour heartbeat (:05/:35);
Meghan (the OpenClaw CEO on alpha) runs a half-hour heartbeat on
a 15-minute offset (:20/:50). The clerk passes up anything
requiring reasoning at a Sonic-or-higher level as PACKAGES.
Either seat may start a package: break it into tasks across the
engine queues (REAP / Sonic / Morpheus / Penny). The package is
kept in the record; when ALL its tasks are complete, BOTH seats
review it independently (neither sees the other's review),
each votes with a certainty, and the package is decided only
when both agree at 98% certainty or higher. Anything less sends
the package around again with the gaps named; a package that
cannot converge after 3 rounds is escalated toward Brian
through the scatter (the clerk's lane), never silently dropped.

Seats think on different engines so the two reviews are
genuinely independent: Altair via Sonic, Meghan via Morpheus.
All reasoning happens as queued 'chat' jobs (engine_runner
executes them); this library is the deterministic spine:
lifecycle, parsing, tallies. No model calls live here.

Package states: queued -> breaking_down -> in_progress ->
ready_for_review -> decided | needs_more_work (-> queued,
round+1) | escalated.
"""
import json
import re
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
import sbos_common  # noqa: E402

SEAT_ENGINE = {"altair": "sonic", "meghan": "morpheus"}
AGREE_CERTAINTY = 98
MAX_ROUNDS = 3

DDL = """
CREATE TABLE IF NOT EXISTS successbrian_os.decider_packages (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_kind TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    title TEXT NOT NULL,
    brief TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
        ('queued','breaking_down','in_progress','ready_for_review',
         'decided','needs_more_work','escalated')),
    started_by TEXT,
    round INT NOT NULL DEFAULT 1,
    decision TEXT,
    decided_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS successbrian_os.decider_reviews (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    package_id BIGINT NOT NULL,
    round INT NOT NULL,
    seat TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('agree','disagree')),
    certainty INT NOT NULL DEFAULT 0,
    review_text TEXT NOT NULL DEFAULT '',
    UNIQUE (package_id, round, seat)
);
"""

BREAKDOWN_PROMPT = """You are {seat}, one of two deciders (Altair and Meghan) in Brian's ecosystem. The clerk has passed up an issue that needs reasoning. Break it into tasks for the fleet's engines. Choose engines by the work:
- REAP: the deepest, hardest reasoning (slow, thorough)
- SONIC: fast, higher-volume reasoning and drafting
- MORPHEUS: mid-level judgment and synthesis
- PENNY: mechanical work only — extraction, counting, checking, formatting

Output EXACTLY this shape, one task per line, nothing after the block:
TASKS:
- ENGINE: <reap|sonic|morpheus|penny> | TITLE: <short title> | SPEC: <a complete, self-contained instruction for that engine — include every fact it needs; it cannot see this issue or the other tasks>

Rules: 1 to 5 tasks. Prefer the cheapest engine that can truly do the task. The task results will be reviewed to decide the issue, so specs must ask for evidence, not opinions without grounds.

ISSUE: {title}

BRIEF:
{brief}"""

REVIEW_PROMPT = """You are {seat}, one of two deciders (Altair and Meghan) in Brian's ecosystem, reviewing a finished package INDEPENDENTLY — the other decider is reviewing it separately and you must not assume their conclusion. All engine tasks for this issue are complete. Their results are below.

Decide the issue on this evidence. Answer in EXACTLY this shape:
VERDICT: <agree|disagree>
CERTAINTY: <0-100>
DECISION: <your decision / assessment in a few sentences>
MISSING: <if you disagree, or your certainty is under 98, state precisely what evidence or work is missing; otherwise 'none'>

'agree' means: the evidence supports a clear decision and you stand behind the DECISION as written. The package is only decided when both deciders agree at 98+ certainty, so hold that bar honestly.

ISSUE: {title}

BRIEF:
{brief}

TASK RESULTS:
{results}"""


def ensure_schema():
    sbos_common.pg_exec(DDL)


def create_package(source_kind, source_ref, title, brief):
    """Create a package, or return the existing open one for the
    same source (a source never spawns duplicates)."""
    ensure_schema()
    if source_ref:
        row = sbos_common.pg_one(
            "SELECT id FROM successbrian_os.decider_packages "
            "WHERE source_kind = %s AND source_ref = %s "
            "AND status NOT IN ('decided','escalated') "
            "ORDER BY id LIMIT 1", (source_kind, source_ref))
        if row:
            return int(row)
    return int(sbos_common.pg_one(
        "INSERT INTO successbrian_os.decider_packages "
        "(source_kind, source_ref, title, brief) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (source_kind, source_ref, title[:300], brief or "")))


def _set_status(pkg_id, status, **kw):
    sets = ["status = %s", "updated_at = now()"]
    params = [status]
    for k, v in kw.items():
        sets.append("%s = %%s" % k)
        params.append(v)
    params.append(pkg_id)
    sbos_common.pg_exec(
        "UPDATE successbrian_os.decider_packages SET "
        + ", ".join(sets) + " WHERE id = %s", tuple(params))


def _pkg(pkg_id):
    rows = sbos_common.pg_rows(
        "SELECT id, title, brief, status, started_by, round "
        "FROM successbrian_os.decider_packages WHERE id = %s",
        (pkg_id,))
    if not rows:
        return None
    r = rows[0]
    return {"id": int(r[0]), "title": r[1], "brief": r[2] or "",
            "status": r[3], "started_by": r[4], "round": int(r[5])}


def _queue_jobs(source_ref):
    """All engine jobs (any engine) carrying a source_ref."""
    out = []
    for engine, table in sbos_common.ENGINE_JOB_TABLES.items():
        for r in sbos_common.pg_rows(
                "SELECT id, kind, title, status, result FROM %s "
                "WHERE source_ref = %%s ORDER BY id" % table,
                (source_ref,)):
            out.append({"engine": engine, "id": int(r[0]),
                        "kind": r[1], "title": r[2], "status": r[3],
                        "result": r[4] or ""})
    return out


def _result_text(job):
    try:
        return json.loads(job["result"] or "{}").get("text", "")
    except Exception:
        return job["result"] or ""


# ------------------------------------------------------------ breakdown

def enqueue_breakdown(pkg, seat):
    prompt = BREAKDOWN_PROMPT.format(
        seat=seat, title=pkg["title"], brief=pkg["brief"][:6000])
    engine = "morpheus"  # reading room: breakdowns read there
    return sbos_common.engine_job_enqueue(
        engine, "decider-" + seat, "chat",
        "Decider breakdown: pkg #%d" % pkg["id"],
        payload={"prompt": sbos_common.budget_prompt(
                     prompt, sbos_common.SONIC_KV_AUTO_DEEP),
                 "max_tokens": 1200,
                 "temperature": 0.3},
        source_ref="pkg:%d:breakdown:%d" % (pkg["id"], pkg["round"]))


TASK_LINE = re.compile(
    r"^-\s*ENGINE:\s*(reap|sonic|morpheus|penny)\s*\|\s*TITLE:\s*"
    r"(.+?)\s*\|\s*SPEC:\s*(.+)$", re.IGNORECASE)


def _spec_with_urls(spec, brief):
    """Guarantee the engine sees the issue's source URL(s).

    The breakdown seat is told to write self-contained SPECs, but it
    repeatedly dropped the source URL (pkg #282: penny asked for the
    URL 3 rounds running while the brief held it plainly). Engines
    cannot see the brief, so append every URL found in the brief to
    the SPEC unless already present. Deterministic, not prompt luck.
    """
    raw = re.findall(r"https?://\S+", brief or "")
    urls = sorted({u.rstrip(").,;\"'") for u in raw})
    missing = [u for u in urls if u not in spec]
    if not missing:
        return spec
    return spec.rstrip() + "\n\nSource URL(s) from the issue brief: " + " ".join(missing)


def consume_breakdowns(seat):
    """Turn this seat's finished breakdown jobs into engine
    tasks. Returns tasks created."""
    made = 0
    table = sbos_common.ENGINE_JOB_TABLES["morpheus"]
    rows = sbos_common.pg_rows(
        "SELECT id, source_ref, result FROM %s WHERE kind = 'chat' "
        "AND status = 'done' AND source_ref ~ '^pkg:[0-9]+:breakdown:[0-9]+$' "
        "AND created_by = %%s ORDER BY id" % table,
        ("decider-" + seat,))
    for job_id, source_ref, _result in rows:
        pkg_id = int(source_ref.split(":")[1])
        pkg = _pkg(pkg_id)
        if not pkg or pkg["status"] != "breaking_down":
            continue
        job = {"result": _result}
        text = _result_text(job)
        tasks = []
        in_block = False
        for ln in text.split("\n"):
            if ln.strip().upper().startswith("TASKS:"):
                in_block = True
                continue
            if in_block:
                m = TASK_LINE.match(ln.strip())
                if m:
                    tasks.append((m.group(1).lower(),
                                  m.group(2).strip(),
                                  m.group(3).strip()))
        if not tasks:
            _set_status(pkg_id, "needs_more_work")
            sbos_common.pg_exec(
                "UPDATE successbrian_os.decider_packages "
                "SET brief = brief || %s, status = 'queued', "
                "round = round + 1, updated_at = now() WHERE id = %s",
                ("\n\n[round %d: breakdown produced no parseable "
                 "tasks — re-break with clearer structure]"
                 % pkg["round"], pkg_id))
            print("pkg #%d: breakdown unparseable — requeued round %d"
                  % (pkg_id, pkg["round"] + 1))
            continue
        for eng, title, spec in tasks[:5]:
            spec = _spec_with_urls(spec, pkg["brief"])
            sbos_common.engine_job_enqueue(
                eng, "decider-" + seat, "chat",
                "Pkg #%d: %s" % (pkg_id, title[:80]),
                payload={"prompt": spec, "max_tokens": 1500,
                         "temperature": 0.3},
                source_ref="pkg:%d" % pkg_id)
            made += 1
        _set_status(pkg_id, "in_progress")
        print("pkg #%d: broke into %d task(s)" % (pkg_id, len(tasks)))
    return made


# ------------------------------------------------------------ completion

def refresh_packages():
    """Move in_progress packages whose tasks are ALL terminal
    to ready_for_review. Returns how many moved."""
    moved = 0
    rows = sbos_common.pg_rows(
        "SELECT id FROM successbrian_os.decider_packages "
        "WHERE status = 'in_progress' ORDER BY id")
    for (pkg_id,) in rows:
        jobs = _queue_jobs("pkg:%d" % pkg_id)
        if jobs and all(j["status"] in ("done", "failed", "cancelled")
                        for j in jobs):
            _set_status(int(pkg_id), "ready_for_review")
            print("pkg #%d: all tasks complete — ready for review"
                  % pkg_id)
            moved += 1
    return moved


# ------------------------------------------------------------ reviews

def enqueue_review(pkg, seat):
    jobs = _queue_jobs("pkg:%d" % pkg["id"])
    parts = []
    for j in jobs:
        body = _result_text(j) if j["status"] == "done" \
            else "(task %s)" % j["status"]
        parts.append("--- task (%s): %s ---\n%s"
                     % (j["engine"], j["title"], body[:2500]))
    prompt = REVIEW_PROMPT.format(
        seat=seat, title=pkg["title"], brief=pkg["brief"][:4000],
        results="\n\n".join(parts)[:14000])
    engine = SEAT_ENGINE[seat]
    return sbos_common.engine_job_enqueue(
        engine, "decider-" + seat, "chat",
        "Decider review: pkg #%d" % pkg["id"],
        payload={"prompt": sbos_common.budget_prompt(
                     prompt, sbos_common.SONIC_KV_AUTO_DEEP),
                 "max_tokens": 900, "temperature": 0.2},
        source_ref="pkg:%d:review:%s:%d"
                   % (pkg["id"], seat, pkg["round"]))


VERDICT_RE = re.compile(r"VERDICT:\s*(agree|disagree)", re.IGNORECASE)
CERT_RE = re.compile(r"CERTAINTY:\s*(\d{1,3})", re.IGNORECASE)


def consume_reviews(seat):
    """Record this seat's finished review jobs as votes."""
    engine = SEAT_ENGINE[seat]
    table = sbos_common.ENGINE_JOB_TABLES[engine]
    rows = sbos_common.pg_rows(
        "SELECT source_ref, result FROM %s WHERE kind = 'chat' "
        "AND status = 'done' AND source_ref ~ '^pkg:[0-9]+:review:(altair|meghan):[0-9]+$' "
        "AND created_by = %%s ORDER BY id" % table,
        ("decider-" + seat,))
    n = 0
    for source_ref, result in rows:
        _p, pkg_id, _r, rseat, rnd = source_ref.split(":")
        if rseat != seat:
            continue
        text = _result_text({"result": result})
        vm = VERDICT_RE.search(text)
        cm = CERT_RE.search(text)
        if not vm:
            continue  # unparseable vote: no record, will re-review
        verdict = vm.group(1).lower()
        certainty = min(100, int(cm.group(1))) if cm else 0
        sbos_common.pg_exec(
            "INSERT INTO successbrian_os.decider_reviews "
            "(package_id, round, seat, verdict, certainty, review_text) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (package_id, round, seat) DO NOTHING",
            (int(pkg_id), int(rnd), seat, verdict, certainty,
             text[:6000]))
        n += 1
    return n


def tally():
    """Decide or recycle every ready_for_review package that has
    both seats' votes for its current round."""
    rows = sbos_common.pg_rows(
        "SELECT id, round FROM successbrian_os.decider_packages "
        "WHERE status = 'ready_for_review' ORDER BY id")
    for pkg_id, rnd in rows:
        votes = sbos_common.pg_rows(
            "SELECT seat, verdict, certainty, review_text "
            "FROM successbrian_os.decider_reviews "
            "WHERE package_id = %s AND round = %s",
            (pkg_id, rnd))
        if len(votes) < 2:
            continue
        agreed = all(v[1] == "agree" and int(v[2]) >= AGREE_CERTAINTY
                     for v in votes)
        if agreed:
            decision = "\n\n".join(
                "[%s, certainty %s] %s" % (v[0], v[2], v[3])
                for v in votes)
            sbos_common.pg_exec(
                "UPDATE successbrian_os.decider_packages "
                "SET status = 'decided', decision = %s, "
                "decided_at = now(), updated_at = now() WHERE id = %s",
                (decision, pkg_id))
            print("pkg #%d DECIDED (both agree, >=%d%%)"
                  % (pkg_id, AGREE_CERTAINTY))
            continue
        gaps = "\n\n".join(
            "[%s voted %s at %s%%] %s" % (v[0], v[1], v[2], v[3])
            for v in votes
            if v[1] != "agree" or int(v[2]) < AGREE_CERTAINTY)
        if int(rnd) >= MAX_ROUNDS:
            _set_status(int(pkg_id), "escalated")
            sbos_common.pg_exec(
                "INSERT INTO atlas.scattered_captures "
                "(title, raw_text, context, status) VALUES (%s, %s, %s, "
                "'raw')",
                ("DECIDER ESCALATION: package #%d could not reach "
                 "agreement" % pkg_id,
                 "Package #%d failed to reach dual %d%% agreement "
                 "after %d rounds.\n\n%s" % (pkg_id, AGREE_CERTAINTY,
                                             rnd, gaps),
                 "Filed by the decider loop (decider_lib) — Brian's "
                 "escalation lane via the clerk.",))
            print("pkg #%d ESCALATED after %d rounds" % (pkg_id, rnd))
        else:
            sbos_common.pg_exec(
                "UPDATE successbrian_os.decider_packages "
                "SET status = 'queued', round = round + 1, "
                "brief = brief || %s, updated_at = now() WHERE id = %s",
                ("\n\n[round %d did not reach agreement — gaps named "
                 "by the reviewers:]\n%s" % (rnd, gaps[:3000]), pkg_id))
            print("pkg #%d: no agreement — requeued for round %d"
                  % (pkg_id, int(rnd) + 1))


# ------------------------------------------------------------ the step

def decider_step(seat, dry_run=False, max_breakdowns=1, max_reviews=2):
    """One seat's heartbeat step, in order: consume this seat's
    finished reasoning jobs, refresh completions, tally votes,
    enqueue this seat's reviews for ready packages it has not
    reviewed this round, then (capacity permitting) claim the
    oldest queued package and enqueue its breakdown."""
    ensure_schema()
    log = []
    if dry_run:
        print("DRY-RUN decider step for %s (no writes)" % seat)
        return log
    consume_breakdowns(seat)
    consume_reviews(seat)
    refresh_packages()
    tally()
    # reviews owed by this seat
    owed = sbos_common.pg_rows(
        "SELECT p.id, p.title, p.brief, p.status, p.started_by, p.round "
        "FROM successbrian_os.decider_packages p "
        "WHERE p.status = 'ready_for_review' AND NOT EXISTS "
        "(SELECT 1 FROM successbrian_os.decider_reviews r "
        "WHERE r.package_id = p.id AND r.round = p.round "
        "AND r.seat = %s) ORDER BY p.id",
        (seat,))
    review_jobs = 0
    for r in owed:
        if review_jobs >= max_reviews:
            break
        pkg = {"id": int(r[0]), "title": r[1], "brief": r[2] or "",
               "status": r[3], "started_by": r[4], "round": int(r[5])}
        # skip if a review job for this round is already in flight
        ref = "pkg:%d:review:%s:%d" % (pkg["id"], seat, pkg["round"])
        inflight = _queue_jobs(ref)
        if any(j["status"] in ("queued", "claimed") for j in inflight):
            continue
        if any(j["status"] == "done" for j in inflight):
            continue  # consume_reviews will record it next step
        enqueue_review(pkg, seat)
        print("pkg #%d: %s review enqueued" % (pkg["id"], seat))
        review_jobs += 1
    # claim a package to break down
    row = sbos_common.pg_one(
        "UPDATE successbrian_os.decider_packages "
        "SET status = 'breaking_down', started_by = %s, "
        "updated_at = now() "
        "WHERE id = (SELECT id FROM successbrian_os.decider_packages "
        "WHERE status = 'queued' ORDER BY id LIMIT 1 "
        "FOR UPDATE SKIP LOCKED) RETURNING id", (seat,))
    if row and max_breakdowns > 0:
        pkg = _pkg(int(row))
        enqueue_breakdown(pkg, seat)
        print("pkg #%d: %s claimed it — breakdown enqueued"
              % (pkg["id"], seat))
    return log


def selftest():
    # _spec_with_urls: the pkg #282 regression — penny's SPEC dropped
    # the source URL 3 rounds running while the brief held it.
    brief = ("source URL: https://forums.servethehome.com/index.php?"
             "threads/fs-us-can-4x-rtx-a5000-gpus.56788/; checked 2026-10-27")
    spec = "From the provided source URL, extract the GPU count and price."
    out = _spec_with_urls(spec, brief)
    assert "threads/fs-us-can-4x-rtx-a5000-gpus.56788/" in out, out
    assert out.startswith(spec)
    spec_with_url = (spec + " URL: https://forums.servethehome.com/"
                     "index.php?threads/fs-us-can-4x-rtx-a5000-gpus.56788/")
    assert _spec_with_urls(spec_with_url, brief) == spec_with_url  # already present: unchanged
    assert _spec_with_urls(spec, "no links here") == spec
    ensure_schema()
    a = create_package("manual", "selftest:pkg", "Selftest package",
                       "A package that exists only to prove the "
                       "lifecycle tables work.")
    b = create_package("manual", "selftest:pkg", "Selftest package",
                       "duplicate attempt")
    assert a == b, (a, b)
    sbos_common.pg_exec(
        "DELETE FROM successbrian_os.decider_packages WHERE id = %s",
        (a,))
    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) > 2 and sys.argv[1] == "step":
        decider_step(sys.argv[2])
    else:
        print("usage: decider_lib.py --selftest | step <altair|meghan>")
