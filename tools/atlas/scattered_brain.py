#!/usr/bin/env python3
"""The Scattered Second Brain (R31) — Brian's idea-refinery.

Brian (2026-10-23): "I'm kind of a 'scattered' person so as
I'm talking and planning one idea out, I might offshoot into
14 or more other things... successbrian-os needs to figure
out during my sleep and game time do I need to hang on to
those newly created workspaces? do I need to further finish
out the planning on really good ideas... it needs to help
me sort the chaos... this is the 'scattered second brain' —
that takes the really raw stuff and refines it into
something more workable."

The loop:
  capture  — a stray idea is dumped raw in ONE call, with
             the context of what Brian was planning when it
             offshot. No friction, no judging at capture.
  triage   — the downtime pass (cron, ~04:30): clusters
             repeats, scores each capture against Brian's
             business goals and the workspace map
             (determine()), and writes a recommendation.
             Triage NEVER promotes, deletes, or rules — it
             sorts and recommends.
  rule     — Brian's ruling: promote (a planning body
             starts via R30), park (held, alive), discard
             (with why — recorded, never deleted).
  digest   — the standing report: what came in, what is
             awaiting a ruling, what was promoted.

Scoring is deterministic and explained per capture
(score_reasons) so Brian can see — and correct — the
refinery's judgment. His rulings are the training signal.
"""

import os
import subprocess
import sys

import psycopg2

# SBOS common routines — Batch B migration (2026-10-27): the DB
# helpers below delegate to sbos_common (tools/), the one shared
# module. sys.path gets the tools/ dir (this file lives in tools/atlas/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sbos_common  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import allm_workspaces as allm  # noqa: E402

DBNAME = "ecosystem_central"
DIGEST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ssb-digest-latest.md")

DDL = """
CREATE TABLE IF NOT EXISTS atlas.scattered_captures (
    id             serial PRIMARY KEY,
    title          text NOT NULL,
    raw_text       text NOT NULL DEFAULT '',
    context        text NOT NULL DEFAULT '',
    status         text NOT NULL DEFAULT 'raw'
                   CHECK (status IN ('raw','triaged','promoted',
                                     'parked','discarded')),
    cluster_key    text,
    score          integer,
    score_reasons  text,
    recommendation text,
    workspace_slug text,
    ruling_why     text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    triaged_at     timestamptz,
    ruled_at       timestamptz,
    depth          text NOT NULL DEFAULT 'unclassified'
);
"""

# Signals from the business-goals charter (R29): an idea
# that serves a standing goal scores. Keys are goal names;
# values are keyword fragments matched against the capture.
GOAL_SIGNALS = {
    "gotbackup-40-month": ["gotbackup", "got backup",
                           "sponsor", "backup"],
    "contactflowcrm": ["contactflowcrm", "crm", "contacts",
                       "rolodex", "who knows who"],
    "trafficstreemz": ["trafficstreemz", "traffic"],
    "erp-and-desks": ["erp", "dealsdesk", "campaignsdesk",
                      "tradesdesk", "hosting", "calendar",
                      "budget"],
    "inference-fleet": ["deepseek", "epyc", "inference",
                        "ddr4", "fleet", "sonic", "colibri",
                        "strata", "gpu", "server"],
    "audience-content": ["blog", "podcast", "medium",
                         "audience", "youtube", "content",
                         "subscribers"],
    "systeme-business": ["systeme", "email", "funnel"],
    "mlm-network": ["mlm", "zilara", "vate", "oliabo",
                    "downline", "recruiting",
                    "network marketing"],
}

STOPWORDS = {
    "idea", "ideas", "plan", "planning", "thing", "things",
    "stuff", "make", "build", "with", "that", "this",
    "from", "about", "into", "really", "just", "like",
    "want", "need", "brian", "should", "could", "would",
    "some", "more", "very", "what", "when", "then",
}


def pg():
    # Batch B migration (2026-10-27): the connection comes from the one
    # shared factory — same database, host, and 'postgres' role as before.
    return sbos_common.connect(user="postgres")


def ensure(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            "ALTER TABLE atlas.scattered_captures "
            "ADD COLUMN IF NOT EXISTS depth text "
            "NOT NULL DEFAULT 'unclassified'")
    conn.commit()


def _tokens(text):
    raw = "".join(c if c.isalnum() else " "
                  for c in text.lower()).split()
    return [t for t in raw if len(t) >= 3 and t not in STOPWORDS]


def cluster_key(title):
    toks = sorted({t for t in _tokens(title) if len(t) >= 4})
    return "-".join(toks[:4]) if toks else "misc"


def capture(conn, title, context="", raw=""):
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO atlas.scattered_captures "
            "(title, raw_text, context, cluster_key) VALUES "
            "(%s, %s, %s, %s) RETURNING id",
            (title, raw, context, cluster_key(title)))
        cid = cur.fetchone()[0]
    conn.commit()
    return cid


def score_capture(conn, row, cluster_sizes):
    """Deterministic, explained scoring. Returns
    (score, reasons, forced_recommendation_or_None)."""
    cid, title, raw, context = row[0], row[1], row[2], row[3]
    text = (title + " " + raw + " " + context).lower()
    score = 0
    reasons = []
    goals_hit = []
    for goal, kws in GOAL_SIGNALS.items():
        if any(k in text for k in kws):
            goals_hit.append(goal)
    if goals_hit:
        pts = min(6, 2 * len(goals_hit))
        score += pts
        reasons.append("serves goal(s): %s (+%d)"
                       % (", ".join(goals_hit), pts))
    forced = None
    d = allm.determine(conn, title)
    if d["verdict"] in ("not_building", "dead_business",
                        "disliked"):
        forced = "discard-candidate"
        reasons.append(
            "subject is ruled out by Brian's own registries "
            "-> %s (%s)" % (d["workspace"], d.get("tag", "")))
    else:
        # Connectivity: a capture is a sentence, not a
        # subject — scan its text for the bodies it names.
        text_norm = allm._norm(title + " " + context)
        hits = [r[0] for r in allm.registry_rows(conn)
                if len(allm._norm(r[0])) >= 4
                and allm._norm(r[0]) in text_norm]
        if hits:
            best = max(hits, key=len)
            score += 3
            reasons.append("connects to body: %s (+3)" % best)
        else:
            for pslug, psubj, _st in allm.planning_rows(conn):
                if allm._norm(psubj) in text_norm:
                    score += 3
                    reasons.append(
                        "a plan is already active: %s (+3)"
                        % pslug)
                    break
    mates = max(0, cluster_sizes.get(cluster_key(title), 1) - 1)
    if mates:
        pts = min(2, mates)
        score += pts
        reasons.append("came up %d time(s) before (+%d)"
                       % (mates, pts))
    if len(raw) >= 1200:
        score += 2
        reasons.append("already fleshed out (+2)")
    elif len(raw) >= 400:
        score += 1
        reasons.append("some flesh on it (+1)")
    return score, reasons, forced


def recommend(score, forced):
    if forced:
        return forced
    if score >= 7:
        return "promote-candidate"
    if score >= 4:
        return "refine"
    if score >= 1:
        return "park"
    return "discard-candidate"


# Intel depths (Brian 2026-11-13 06:45; INTEL_DEPTHS.md) — the clerk
# stamps a depth on every capture AT TRIAGE. Deterministic phrase
# rules, checked in priority order: an explicit Brian-action marker
# wins, then system-self markers, then review markers, then
# planning markers. Anything else triaged is internal working intel
# (team_working). Raw captures stay 'unclassified' until triage
# stamps them — unclassified is a real state, never assumed.
# Depth markers — PRECISION RULE (fixed after the first backfill
# showed the inversion): the Brian-facing depths are TITLE-ONLY.
# A capture's title is its label ("BRIAN TO DO: ..."); a body that
# merely mentions "ask Brian" or "heartbeat" in prose is discussion,
# not the item's purpose, and must never escalate the item onto
# Brian's surface. system_self additionally accepts machine-shaped
# body keys (the cycle tool's finding keys), which never occur in
# prose. A false brian_decision is worse than a missed one: it
# would push a non-decision at Brian, the exact harm depths exist
# to prevent.
DEPTH_BRIAN_DECISION = (
    "brian to do", "brian to rule", "ask brian", "needs brian",
    "brian decision", "brian to decide", "for brian to decide",
    "decision needed", "brian must decide",
)
DEPTH_SYSTEM_SELF_TITLE = (
    "spencer cycle", "qa failing", "qa checks failing",
    "price_intel", "backlog growing", "improvement_log",
    "verification due", "verification check", "queue health",
    "sizing watch", "agent cycle", "cycle #",
)
DEPTH_SYSTEM_SELF_BODY = (
    "qa_failing:", "price_expired:", "backlog_growing",
)
DEPTH_BRIAN_REVIEW = (
    "scoreboard", "ecosystem review", "verification verdict",
    "improvement verdict",
)
DEPTH_AGENT_PLANNING_PREFIXES = ("design", "spec:", "architecture")
DEPTH_AGENT_PLANNING = ("design doc", "build plan", "architecture doc")


def depth_for(title, raw="", context=""):
    """Deterministic depth for a capture at triage. Returns one of
    the six registry depths; never raises on odd input."""
    text = ((title or "") + " " + (raw or "") + " "
            + (context or "")).lower()
    title_l = (title or "").lower().strip()
    if any(m in title_l for m in DEPTH_BRIAN_DECISION):
        return "brian_decision"
    if (any(m in title_l for m in DEPTH_SYSTEM_SELF_TITLE)
            or any(m in text for m in DEPTH_SYSTEM_SELF_BODY)):
        return "system_self"
    if any(m in title_l for m in DEPTH_BRIAN_REVIEW):
        return "brian_review"
    if (title_l.startswith(DEPTH_AGENT_PLANNING_PREFIXES)
            or title_l.startswith("plan:")
            or any(m in title_l for m in DEPTH_AGENT_PLANNING)):
        return "agent_planning"
    return "team_working"


def backfill_depths(conn, dry_run=False):
    """Stamp depths on already-triaged captures still sitting at
    'unclassified', using the same rule triage() applies. Raw
    captures are left alone — their depth is stamped at triage.
    Returns (rows_considered, rows_stamped)."""
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, raw_text, context FROM "
            "atlas.scattered_captures WHERE status <> 'raw' "
            "AND depth = 'unclassified' ORDER BY id")
        rows = cur.fetchall()
    changed = 0
    for cid, title, raw, context in rows:
        depth = depth_for(title, raw, context)
        changed += 1
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE atlas.scattered_captures SET depth = %s "
                    "WHERE id = %s AND depth = 'unclassified'",
                    (depth, cid))
    if not dry_run:
        conn.commit()
    return len(rows), changed


def sweep_depths(conn, dry_run=False):
    """Stamp depths on EVERY unclassified capture, any status —
    raw rows waiting on the next triage run and discarded rows
    triage never touches included (B25: the unclassified backlog
    refills between triage runs, and a discarded row never gets
    triaged at all, so it would sit unclassified forever).
    Uses the same depth_for() rule triage() applies, so a later
    triage re-stamps the identical value; idempotent.
    Returns (rows_considered, rows_stamped)."""
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, raw_text, context FROM "
            "atlas.scattered_captures WHERE depth = 'unclassified' "
            "ORDER BY id")
        rows = cur.fetchall()
    stamped = 0
    for cid, title, raw, context in rows:
        depth = depth_for(title, raw, context)
        stamped += 1
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE atlas.scattered_captures SET depth = %s "
                    "WHERE id = %s AND depth = 'unclassified'",
                    (depth, cid))
    if not dry_run:
        conn.commit()
    return len(rows), stamped


def triage(conn):
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cluster_key, count(*) FROM "
            "atlas.scattered_captures WHERE status <> "
            "'discarded' GROUP BY cluster_key")
        sizes = dict(cur.fetchall())
        cur.execute(
            "SELECT id, title, raw_text, context FROM "
            "atlas.scattered_captures WHERE status = 'raw' "
            "ORDER BY id")
        rows = cur.fetchall()
    done = 0
    for row in rows:
        score, reasons, forced = score_capture(conn, row, sizes)
        rec = recommend(score, forced)
        depth = depth_for(row[1], row[2], row[3])
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'triaged', score = %s, "
                "score_reasons = %s, recommendation = %s, "
                "depth = %s, "
                "triaged_at = now() WHERE id = %s",
                (score, "; ".join(reasons), rec, depth, row[0]))
        conn.commit()
        done += 1
    text = digest(conn)
    with open(DIGEST_PATH, "w") as f:
        f.write(text)
    try:
        import allm_embed
        allm_embed.embed_latest("scattered-second-brain",
                                "ssb-digest-latest.md", text)
    except Exception as e:
        print("warning: digest embed failed (R32): %s" % e)
    return done, text


def digest(conn):
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, count(*) FROM "
            "atlas.scattered_captures GROUP BY status")
        counts = dict(cur.fetchall())
        cur.execute(
            "SELECT id, title, score, recommendation FROM "
            "atlas.scattered_captures WHERE status = "
            "'triaged' ORDER BY score DESC NULLS LAST, id "
            "LIMIT 8")
        awaiting = cur.fetchall()
        cur.execute(
            "SELECT title, workspace_slug FROM "
            "atlas.scattered_captures WHERE status = "
            "'promoted' ORDER BY ruled_at DESC LIMIT 5")
        promoted = cur.fetchall()
    lines = ["# Scattered Second Brain — digest", ""]
    lines.append("Captures by status: %s"
                 % (", ".join("%s %d" % kv
                              for kv in sorted(counts.items()))
                    or "none yet"))
    lines.append("")
    lines.append("## Awaiting Brian's ruling (top scored)")
    if awaiting:
        for cid, title, score, rec in awaiting:
            lines.append("- #%d [%s, score %s] %s"
                         % (cid, rec, score, title))
    else:
        lines.append("(nothing awaiting)")
    lines.append("")
    lines.append("## Recently promoted to planning bodies")
    if promoted:
        for title, slug in promoted:
            lines.append("- %s -> %s" % (title, slug))
    else:
        lines.append("(none yet)")
    lines.append("")
    return "\n".join(lines)


def rule(conn, cid, ruling, why=""):
    ensure(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, status FROM "
            "atlas.scattered_captures WHERE id = %s", (cid,))
        row = cur.fetchone()
    if not row:
        print("no capture #%d" % cid)
        return 1
    title = row[0]
    if ruling in ("park", "keep"):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'parked', ruling_why = %s, "
                "ruled_at = now() WHERE id = %s", (why, cid))
        conn.commit()
        print("#%d parked — held, alive" % cid)
        return 0
    if ruling == "discard":
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'discarded', ruling_why = %s, "
                "ruled_at = now() WHERE id = %s", (why, cid))
        conn.commit()
        print("#%d discarded (recorded, not deleted)" % cid)
        return 0
    if ruling == "promote":
        slug = allm.plan_slug(title)
        here = os.path.dirname(os.path.abspath(__file__))
        proc = subprocess.run(
            [sys.executable,
             os.path.join(here, "allm_workspaces.py"),
             "plan", "start", title],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            print("promotion FAILED — plan start did not "
                  "complete:\n%s%s" % (proc.stdout, proc.stderr))
            return 1
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'promoted', workspace_slug = %s, "
                "ruling_why = %s, ruled_at = now() WHERE "
                "id = %s", (slug, why, cid))
        conn.commit()
        print("#%d promoted -> planning body %s" % (cid, slug))
        return 0
    print("unknown ruling: %s (use promote|park|discard)"
          % ruling)
    return 2


def selftest(conn):
    failures = []

    def check(cond, label):
        print(("PASS  " if cond else "FAIL  ") + label)
        if not cond:
            failures.append(label)

    ensure(conn)
    raw_rich = ("SSBTEST follow-up system for sponsors: "
                "every GotBackup sponsor gets a contacts "
                "pipeline entry, reminders, and a who-knows-"
                "who view so the monthly 40 actually "
                "happens. " * 3)
    ids = [
        capture(conn,
                "SSBTEST gotbackup sponsor crm contacts "
                "pipeline push",
                context="planning ContactFlowCRM",
                raw=raw_rich),
        capture(conn, "SSBTEST sipology revival party"),
        capture(conn, "SSBTEST zebra umbrella moonlight"),
        capture(conn, "SSBTEST BRIAN TO DO - look up the order"),
        capture(conn, "SSBTEST qa_failing:1,2,3"),
        capture(conn, "SSBTEST design doc for the new queue"),
    ]
    done, _ = triage(conn)
    check(done >= 3, "triage processed the test captures")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, score, recommendation FROM "
            "atlas.scattered_captures WHERE id = ANY(%s) "
            "ORDER BY id", (ids,))
        got = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    check(got[ids[0]][0] >= 6
          and got[ids[0]][1] in ("promote-candidate", "refine"),
          "goal-rich capture scores high (%s, %s)"
          % got[ids[0]])
    check(got[ids[1]][1] == "discard-candidate",
          "a ruled-out subject (sipology) is forced to "
          "discard-candidate")
    check(got[ids[2]][0] <= 1
          and got[ids[2]][1] in ("park", "discard-candidate"),
          "an unconnected stray scores low (%s, %s)"
          % got[ids[2]])
    # Depth probes (B8b-1): triage stamps a depth per capture.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, depth FROM atlas.scattered_captures "
            "WHERE id = ANY(%s) ORDER BY id", (ids,))
        depths = {r[0]: r[1] for r in cur.fetchall()}
    check(depths[ids[0]] == "team_working",
          "goal-rich capture defaults to team_working (%s)"
          % depths[ids[0]])
    check(depths[ids[3]] == "brian_decision",
          "BRIAN TO DO capture is brian_decision (%s)"
          % depths[ids[3]])
    check(depths[ids[4]] == "system_self",
          "qa_failing capture is system_self (%s)"
          % depths[ids[4]])
    check(depths[ids[5]] == "agent_planning",
          "design-doc capture is agent_planning (%s)"
          % depths[ids[5]])
    check(depth_for("BRIAN TO DO - x") == "brian_decision",
          "depth_for: brian_decision marker")
    check(depth_for("qa_failing:1,2") == "system_self",
          "depth_for: system_self marker")
    check(depth_for("Design doc: the new queue") == "agent_planning",
          "depth_for: agent_planning prefix")
    check(depth_for("plan: migrate the fleet") == "agent_planning",
          "depth_for: plan: prefix")
    check(depth_for("Weekly scoreboard") == "brian_review",
          "depth_for: brian_review marker")
    check(depth_for("a stray idea about dogs") == "team_working",
          "depth_for: default team_working")
    check(depth_for("Spencer cycle: 131 QA checks failing")
          == "system_self",
          "depth_for: cycle-finding title is system_self")
    check(depth_for("Spencer cycle: 32 price_intel rows past shelf "
                    "life") == "system_self",
          "depth_for: price-intel cycle title is system_self")
    check(depth_for("DealsDesk code audit",
                    raw="three-copy drift; ask Brian which copy is "
                    "canonical") == "team_working",
          "depth_for: body-only 'ask Brian' does NOT escalate")
    check(depth_for("INTEL - Paperclip: heartbeat model",
                    raw="their heartbeat model runs the agent")
          == "team_working",
          "depth_for: body/title 'heartbeat' prose does NOT "
          "escalate")
    # Backfill probe: reset one stamped row to unclassified and
    # confirm backfill_depths() re-stamps it with the same rule.
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE atlas.scattered_captures SET depth = "
            "'unclassified' WHERE id = %s", (ids[0],))
    conn.commit()
    total, changed = backfill_depths(conn)
    check(changed >= 1,
          "backfill_depths stamps at least the reset row "
          "(%d/%d)" % (changed, total))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT depth FROM atlas.scattered_captures "
            "WHERE id = %s", (ids[0],))
        check(cur.fetchone()[0] == "team_working",
              "backfilled row re-stamped team_working")
    # Sweep probe (B25): a raw row AND a discarded row, both
    # unclassified, get stamped by sweep_depths() — the two legs
    # backfill-depths never reaches (raw is excluded there;
    # discarded is never triaged). Both rows are SSBTEST-titled,
    # so the cleanup below removes them.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO atlas.scattered_captures "
            "(title, raw_text, context, cluster_key, status, depth) "
            "VALUES (%s, %s, %s, %s, 'raw', 'unclassified') "
            "RETURNING id",
            ("SSBTEST sweep raw brian to do",
             "", "", cluster_key("SSBTEST sweep raw brian to do")))
        sweep_raw = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO atlas.scattered_captures "
            "(title, raw_text, context, cluster_key, status, depth) "
            "VALUES (%s, %s, %s, %s, 'discarded', 'unclassified') "
            "RETURNING id",
            ("SSBTEST sweep discarded qa_failing:9,9",
             "", "",
             cluster_key("SSBTEST sweep discarded qa_failing")))
        sweep_disc = cur.fetchone()[0]
    conn.commit()
    total, stamped = sweep_depths(conn)
    check(stamped >= 2,
          "sweep_depths stamps the raw + discarded rows "
          "(%d/%d)" % (stamped, total))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, depth FROM atlas.scattered_captures "
            "WHERE id = ANY(%s) ORDER BY id",
            ([sweep_raw, sweep_disc],))
        swept = {r[0]: r[1] for r in cur.fetchall()}
    check(swept.get(sweep_raw) == "brian_decision",
          "swept raw row is brian_decision (%s)"
          % swept.get(sweep_raw))
    check(swept.get(sweep_disc) == "system_self",
          "swept discarded row is system_self (%s)"
          % swept.get(sweep_disc))
    print("SWEEP_OK")
    print("DEPTH_OK")
    rc = rule(conn, ids[2], "park", "selftest hold")
    check(rc == 0, "ruling 'park' applies")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM atlas.scattered_captures "
            "WHERE id = %s", (ids[2],))
        check(cur.fetchone()[0] == "parked",
              "parked status persisted")
        cur.execute(
            "DELETE FROM atlas.scattered_captures WHERE "
            "title LIKE 'SSBTEST%'")
    conn.commit()
    if failures:
        print("SELFTEST FAILED: %d check(s)" % len(failures))
        return 1
    print("SELFTEST OK")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "digest"
    conn = pg()
    try:
        if cmd == "capture":
            if len(argv) < 3:
                print('usage: capture "<title>" '
                      '[--context X] [--raw Y]')
                return 2
            title = argv[2]
            if title.startswith("--"):
                print("refusing flag-like title %r — pass a real title"
                      % title)
                return 2
            context = raw = ""
            if "--context" in argv:
                context = argv[argv.index("--context") + 1]
            if "--raw" in argv:
                raw = argv[argv.index("--raw") + 1]
            cid = capture(conn, title, context, raw)
            print("captured #%d: %s" % (cid, title))
            return 0
        if cmd == "list":
            ensure(conn)
            status = None
            if "--status" in argv:
                status = argv[argv.index("--status") + 1]
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT id, title, status, score, "
                        "recommendation FROM "
                        "atlas.scattered_captures WHERE "
                        "status = %s ORDER BY id", (status,))
                else:
                    cur.execute(
                        "SELECT id, title, status, score, "
                        "recommendation FROM "
                        "atlas.scattered_captures ORDER BY id "
                        "DESC LIMIT 30")
                for r in cur.fetchall():
                    print("#%-4d %-9s %-4s %-16s %s"
                          % (r[0], r[2], r[3] or "-", r[4] or "-",
                             r[1]))
            return 0
        if cmd == "triage":
            done, text = triage(conn)
            print("triaged %d capture(s)" % done)
            print(text)
            return 0
        if cmd == "digest":
            print(digest(conn))
            return 0
        if cmd == "rule":
            if len(argv) < 4:
                print("usage: rule <id> promote|park|discard "
                      "[--why ...]")
                return 2
            why = ""
            if "--why" in argv:
                why = " ".join(argv[argv.index("--why") + 1:])
            return rule(conn, int(argv[2]), argv[3], why)
        if cmd == "backfill-depths":
            dry = "--dry-run" in argv
            total, changed = backfill_depths(conn, dry_run=dry)
            print("backfill-depths%s: %d unclassified triaged "
                  "capture(s), %d stamped"
                  % (" (dry run)" if dry else "", total, changed))
            return 0
        if cmd == "sweep-depths":
            dry = "--dry-run" in argv
            total, stamped = sweep_depths(conn, dry_run=dry)
            print("sweep-depths%s: %d unclassified capture(s), "
                  "%d stamped"
                  % (" (dry run)" if dry else "", total, stamped))
            return 0
        if cmd == "selftest":
            return selftest(conn)
        print("usage: scattered_brain.py "
              "[capture|list|triage|digest|rule|backfill-depths|"
              "sweep-depths|selftest]")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
