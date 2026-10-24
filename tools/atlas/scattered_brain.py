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
    ruled_at       timestamptz
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
    return psycopg2.connect(dbname=DBNAME, host="localhost",
                            user="postgres", password="postgres")


def ensure(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
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
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.scattered_captures SET "
                "status = 'triaged', score = %s, "
                "score_reasons = %s, recommendation = %s, "
                "triaged_at = now() WHERE id = %s",
                (score, "; ".join(reasons), rec, row[0]))
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
        if cmd == "selftest":
            return selftest(conn)
        print("usage: scattered_brain.py "
              "[capture|list|triage|digest|rule|selftest]")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
