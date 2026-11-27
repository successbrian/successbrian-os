#!/usr/bin/env python3
"""clerk_tray — the clerk's held-tray self-examination loop.

Brian (2026-11-27): "I was hoping the clerk could look around and
figure this out itself." The unsorted tray (AnythingLLM `unsorted`
workspace) is where filing waits when no owner is determined (R5).
Until now it drained only when a human ran board/resort_unsorted.py
by hand (last: the 2026-11-09 repair) — and even then the router
placed none of it, because its rules had no destinations for the
tray's subjects (frictions #42/#47).

This loop is the clerk examining its own held tray, on a schedule:

  1. INVENTORY  every tray document past the age threshold
     (younger documents are still in the normal filing pipeline
     and are left alone);
  2. ROUTE      re-run the base router (resort_unsorted.route_for)
     — anything it places now is filed (the registry heals routes
     over time and the tray should benefit automatically);
  3. CLUSTER    group what is still held: captures by their
     router's best candidate, other documents by filename family;
  4. MINE       precedent in the filed corpus — where documents
     of the same family / the exact same name were successfully
     filed before. A destination counts as precedent-backed only
     on a dominant home (>=60% of >=5 filed exemplars) or a
     single exact-name home, and only when the tray copy's
     content is not already there word-for-word (a word-identical
     copy is a true duplicate and stays held, accounted);
  5. LEARN      persist the mined rules to
     atlas.clerk_learned_routes — filename-family rules for this
     loop, subject-regex rules that allm_workspaces.route_subject
     also consults, so the standing filing path learns too;
  6. FILE       move what the mined/learned rules cover (moves,
     never deletes; add to the new home first, then remove from
     unsorted, verified — the resort machinery);
  7. ESCALATE   only the no-precedent residue, as questions into
     Brian's inbox (successbrian_os.pending_questions,
     asked_by='clerk-tray'), one per cluster, each carrying the
     cluster's size, age range, examples, and a recommended
     destination. Questions go into the system; only the residue
     surfaces (Brian, 2026-11-15). Re-runs never re-ask a cluster
     that already has an open question (marker in the context).

Nothing is force-fit and nothing is deleted: a document the loop
cannot place on precedent stays held and accounted on the held
list (~/backups/clerk-filing-repair-20261109/held-list.json,
which QA check 532 reads as the tray's accounting).

Usage:
    python3 clerk_tray.py [--dry-run] [--age-days N]
Cron (weekly, flock): see crontab — Mondays 06:41, log
~/logs/clerk-tray.log. Registered in program_registry as
clerk-tray-loop; drainage is measured by QA check
'unsorted-drainage' (filing_flow_qa.py drainage).
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/atlas"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools/pm"))
sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))

import allm_workspaces as allm          # noqa: E402
import allm_embed                       # noqa: E402
import pm_core                          # noqa: E402
import resort_unsorted as resort        # noqa: E402

ALLM_DB = os.path.expanduser("~/anything-llm/server/storage/anythingllm.db")
HELD_PATH = os.path.expanduser(
    "~/backups/clerk-filing-repair-20261109/held-list.json")
RUN_LOG = os.path.expanduser("~/logs/clerk-tray-runs.jsonl")
AGE_DAYS_DEFAULT = 7
MIN_EXEMPLARS = 5
DOMINANT_SHARE = 0.60

# Subject shapes whose series home the filed corpus establishes.
# (subject -> the same series name the document carries as its
# heading; mined evidence is attached when the rule is learned.)
SUBJECT_SERIES = [
    (r"^Daily Log:", "daily-log headings"),
    (r"^Learning Entry:", "learning-entry headings"),
    (r"^Duplicate Report", "duplicate-report headings"),
    (r"^TTL Expiry Report", "ttl-expiry headings"),
    (r"^Knowledge Sync", "knowledge-sync headings"),
    (r"^Analysis:", "analysis-fragment headings"),
    (r"^\[RPT-\d+\].*[Dd]igest", "RPT digest headings"),
    (r"^\d{4}-\d{2}-\d{2}$", "bare-date daily-log subjects"),
]

# The clerk's own recommendation where precedent runs out, for
# families it knows well. Everything else is recommended by
# plurality (the filed corpus's most common home, share stated).
RECOMMEND = {
    "sb-batch-unsorted-N.md": (
        "scattered-second-brain",
        "R31: the Scattered Second Brain body holds the method, "
        "criteria and digest material of the capture system; these "
        "batches are that system's working digests of unsorted "
        "intel. The batches that filed went by topic one by one; "
        "the mixed ones have no topic home."),
}

# Per-document recommendations for one-off held documents
# (family-normalized base filename -> (destination, why)).
SINGLES_REC = {
    "ai-advantage-intel-DATE.md": (
        "ai-strategies-competitive-research",
        "consolidated intel on Mastermind.com's AI Advantage "
        "offer — competitive research on a rival's product"),
    "raw-email-agentmail-fwd-nodeameghan-see-what-fgfarmgirl-"
    "and-N-others-shared": (
        "gamma-intake",
        "an AgentMail forward from Meghan (node-gamma) — gamma "
        "intake material by origin"),
    "transcript-DATE.md": (
        "quarantine",
        "a SELFTEST transcript (LibriVox sample audio) — a test "
        "artifact, not knowledge; quarantine holds test material"),
    "DATE-til-the-billing-is.md": (
        "saturday-podcast",
        "a learning-entry variant; its sibling edition was "
        "routed to saturday-podcast, and the rest of the series "
        "sits in home-lab — either home is defensible, the "
        "sibling's is named first"),
}

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DIGITS_RE = re.compile(r"\d+")


def family_of(base):
    fam = DATE_RE.sub("DATE", base)
    fam = DIGITS_RE.sub("N", fam)
    return fam


def content_hash(docpath):
    title, content = resort.doc_text(docpath)
    if not content and not title:
        return None
    return hashlib.sha256((content or "").encode()).hexdigest()


def tray_docs():
    """All unsorted docs with age, from AnythingLLM's own DB."""
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        rows = db.execute(
            "SELECT wd.id, wd.filename, wd.docpath, wd.createdAt "
            "FROM workspace_documents wd JOIN workspaces w "
            "ON w.id = wd.workspaceId WHERE w.slug = 'unsorted' "
            "ORDER BY wd.id").fetchall()
    finally:
        db.close()
    out = []
    now = datetime.now(timezone.utc)
    for _id, fn, dp, created in rows:
        ts = created
        if isinstance(ts, (int, float)):
            ts = ts / 1000.0 if ts > 1e11 else ts
            dt = datetime.fromtimestamp(ts, timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        out.append({"id": _id, "filename": fn, "docpath": dp,
                    "created": dt, "age_days": (now - dt).days,
                    "base": resort.base_filename(fn)})
    return out


def filed_corpus():
    """base filename -> {workspace: [docpath]}; family -> Counter;
    filename token -> Counter (genre evidence)."""
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        rows = db.execute(
            "SELECT w.slug, wd.filename, wd.docpath FROM "
            "workspace_documents wd JOIN workspaces w "
            "ON w.id = wd.workspaceId WHERE w.slug <> 'unsorted'"
        ).fetchall()
    finally:
        db.close()
    by_base = defaultdict(dict)
    by_family = defaultdict(Counter)
    by_token = defaultdict(Counter)
    for slug, fn, dp in rows:
        b = resort.base_filename(fn)
        by_base[b].setdefault(slug, []).append(dp)
        by_family[family_of(b)][slug] += 1
        for t in set(re.findall(r"[a-z]{4,}", b.lower())):
            by_token[t][slug] += 1
    return by_base, by_family, by_token


TOKEN_STOP = {"unsorted", "report", "daily", "intel", "capture",
              "batch", "file", "data"}


def mine_token_rules(by_token):
    """filename token -> (workspace, n, share) where one home
    holds >=97% of >=100 filed documents carrying the token —
    genre-level precedent (e.g. 'digest' -> home-lab, 290/297)."""
    rules = {}
    for tok, counter in by_token.items():
        if tok in TOKEN_STOP:
            continue
        total = sum(counter.values())
        if total < 100:
            continue
        slug, n = counter.most_common(1)[0]
        if n / total >= 0.97:
            rules[tok] = (slug, n, round(n / total, 2))
    return rules


def ensure_learned_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS atlas.clerk_learned_routes (
                id serial PRIMARY KEY,
                match_kind text NOT NULL,
                pattern text NOT NULL,
                workspace_slug text NOT NULL,
                evidence_n int NOT NULL DEFAULT 0,
                evidence_share numeric,
                rationale text,
                learned_by text NOT NULL DEFAULT 'clerk-tray',
                active boolean NOT NULL DEFAULT true,
                created_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (match_kind, pattern)
            )
            """)
    conn.commit()


def learn_rule(conn, kind, pattern, slug, n, share, rationale):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO atlas.clerk_learned_routes
                (match_kind, pattern, workspace_slug, evidence_n,
                 evidence_share, rationale)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_kind, pattern) DO UPDATE SET
                workspace_slug = EXCLUDED.workspace_slug,
                evidence_n = EXCLUDED.evidence_n,
                evidence_share = EXCLUDED.evidence_share,
                rationale = EXCLUDED.rationale, active = true
            """, (kind, pattern, slug, n, share, rationale))
    conn.commit()


def learned_rules(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT match_kind, pattern, workspace_slug FROM "
            "atlas.clerk_learned_routes WHERE active")
        rows = cur.fetchall()
    fam, subj = {}, []
    for kind, pattern, slug in rows:
        if kind == "filename_family":
            fam[pattern] = slug
        elif kind == "subject_regex":
            subj.append((pattern, slug))
    return fam, subj


def mine_series_rules(by_family):
    """filename family -> (workspace, n, share) on dominant home."""
    rules = {}
    for fam, counter in by_family.items():
        total = sum(counter.values())
        if total < MIN_EXEMPLARS:
            continue
        slug, n = counter.most_common(1)[0]
        if n / total >= DOMINANT_SHARE:
            rules[fam] = (slug, n, round(n / total, 2))
    return rules


def _cap_id(filename):
    m = resort.CAP_RE.match(filename or "")
    return int(m.group(1)) if m else None


def pg_conn():
    return allm.pg()


def escalate(conn, cluster_key, question, context, options):
    """One open question per cluster, ever (marker in context)."""
    marker = "[clerk-tray cluster: %s]" % cluster_key
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM successbrian_os.pending_questions "
            "WHERE status = 'open' AND context LIKE %s",
            ("%" + marker + "%",))
        if cur.fetchone():
            return None
        cur.execute(
            "INSERT INTO successbrian_os.pending_questions "
            "(asked_by, question, context, options, priority) "
            "VALUES ('clerk-tray', %s, %s, %s, 3) RETURNING id",
            (question, context + "\n" + marker,
             json.dumps(options)))
        qid = cur.fetchone()[0]
    conn.commit()
    return qid


def main():
    dry = "--dry-run" in sys.argv
    age_days = AGE_DAYS_DEFAULT
    if "--age-days" in sys.argv:
        age_days = int(sys.argv[sys.argv.index("--age-days") + 1])
    conn = pg_conn()
    ensure_learned_table(conn)
    live = allm.live_workspaces()
    docs = tray_docs()
    examined = [d for d in docs if d["age_days"] >= age_days]
    young = [d for d in docs if d["age_days"] < age_days]
    print("tray: %d docs; examined (age >= %dd): %d; deferred "
          "young: %d" % (len(docs), age_days, len(examined),
                         len(young)))
    by_base, by_family, by_token = filed_corpus()
    series = mine_series_rules(by_family)
    token_rules = mine_token_rules(by_token)
    fam_rules, _subj_rules = learned_rules(conn)
    for fam, (slug, n, share) in series.items():
        if fam_rules.get(fam) != slug:
            fam_rules[fam] = slug
            if not dry:
                learn_rule(conn, "filename_family", fam, slug, n,
                           share,
                           "Precedent mine: %d of the filed corpus's "
                           "%s documents sit in %s (share %.2f)."
                           % (n, fam, slug, share))
    if not dry:
        for tok, (slug, n, share) in token_rules.items():
            learn_rule(conn, "filename_token", tok, slug, n, share,
                       "Genre precedent mine: %d filed documents "
                       "carry the filename token '%s'; %.2f of "
                       "them sit in %s." % (n, tok, share, slug))
    key = None if dry else allm_embed._key()
    moves, held = [], []
    held_by_cluster = defaultdict(list)
    for d in examined:
        verdict, subject, cid = resort.route_for(conn, d["filename"],
                                                 d["docpath"])
        target = verdict.get("workspace")
        why = verdict.get("why", "")
        base = d["base"]
        fam = family_of(base)
        route_how = None
        if verdict.get("verdict") != "intake" and target \
                and target != "unsorted" and target in live:
            route_how = "base router"
        if not route_how:
            homes = by_base.get(base, {})
            # sibling rendering: a capture whose document also
            # lives elsewhere under the same name — the capture
            # already has a filed rendering; whether the second
            # rendering files alongside is a doctrine decision,
            # escalated, never auto-filed.
            if cid and homes:
                d["cluster"] = "double-rendered-captures"
                d["subject"] = subject
                d["candidates"] = verdict.get("candidates", [])
                d["sibling_homes"] = sorted(homes)
                held.append(d)
                held_by_cluster["double-rendered-captures"].append(d)
                continue
            # exact-name precedent: the name lives in exactly
            # one other workspace
            if len(homes) == 1:
                slug = next(iter(homes))
                if slug in live:
                    target, route_how = slug, "exact-name precedent"
        if not route_how and fam in fam_rules:
            slug = fam_rules[fam]
            if slug in live:
                target, route_how = slug, "series precedent (%s)" % fam
        if not route_how:
            for tok in set(re.findall(r"[a-z]{4,}",
                                      base.lower())):
                if tok in token_rules:
                    slug = token_rules[tok][0]
                    if slug in live:
                        target = slug
                        route_how = "genre precedent (token '%s')" \
                            % tok
                        break
        if not route_how:
            d["subject"] = subject
            d["candidates"] = verdict.get("candidates", [])
            if cid:
                top = (verdict.get("candidates") or [[None]])[0][0]
                d["cluster"] = "capture:%s" % (top or "none")
            else:
                d["cluster"] = "family:%s" % fam
            held.append(d)
            held_by_cluster[d["cluster"]].append(d)
            continue
        # content guard: a word-identical copy already in the
        # target is a true duplicate — held, accounted.
        h = content_hash(d["docpath"])
        dup = False
        if h:
            for dp2 in by_base.get(base, {}).get(target, []):
                if content_hash(dp2) == h:
                    dup = True
                    break
        if dup:
            d["cluster"] = "true-duplicate"
            d["subject"] = subject
            held.append(d)
            held_by_cluster["true-duplicate"].append(d)
            continue
        rec = {"filename": d["filename"], "from": "unsorted",
               "to": target, "subject": (subject or "")[:160],
               "capture_id": cid, "how": route_how}
        if dry:
            moves.append(rec)
            print("WOULD FILE: %s -> %s (%s)"
                  % (d["filename"][:56], target, route_how))
        else:
            try:
                resort.move(key, d["docpath"], target)
                ok = resort.verify_moved(d["docpath"], target)
                if not ok:
                    # AnythingLLM's document table can lag the
                    # embeddings call by a beat; one delayed
                    # re-check before declaring failure (the
                    # 2026-11-27 first run 'failed' 3 moves
                    # that had in fact landed).
                    import time as _time
                    _time.sleep(3)
                    ok = resort.verify_moved(d["docpath"],
                                             target)
                if not ok:
                    rec["error"] = "post-move verification failed"
                    d["cluster"] = "move-failed"
                    d["subject"] = subject
                    held.append(d)
                    held_by_cluster["move-failed"].append(d)
                    continue
                if cid:
                    resort.bookkeep_capture(cid, target,
                                            d["filename"])
                by_base.setdefault(base, {}).setdefault(
                    target, []).append(d["docpath"])
                moves.append(rec)
                print("FILED: %s -> %s (%s)"
                      % (d["filename"][:56], target, route_how))
            except Exception as e:
                rec["error"] = "%s: %s" % (type(e).__name__, e)
                d["cluster"] = "move-failed"
                d["subject"] = subject
                held.append(d)
                held_by_cluster["move-failed"].append(d)
    # Learn subject-series routes from what this run filed under
    # each series heading (evidence = filed tray documents whose
    # headings carry the series name, all to the one home).
    if not dry:
        for pattern, label in SUBJECT_SERIES:
            homes = Counter()
            for m in moves:
                if re.search(pattern, m.get("subject") or ""):
                    homes[m["to"]] += 1
            if len(homes) == 1:
                slug, n = homes.most_common(1)[0]
                learn_rule(
                    conn, "subject_regex", pattern, slug, n, 1.0,
                    "Tray-loop filing evidence: %d held documents "
                    "with %s were precedent-filed to %s in the "
                    "clerk-tray run of %s."
                    % (n, label, slug,
                       datetime.now().date().isoformat()))
    # ---- escalate the residue ----------------------------------
    # Group for Brian's inbox: big clusters get their own
    # question; the RPT report families merge into one; capture
    # clusters under 4 merge into two long-tail questions (blog
    # bodies / everything else) with each sub-cluster's candidate
    # named; one-document families merge into a singles question
    # with a per-document recommendation.
    escalated = {}
    if not dry:
        esc = {}

        def put(key, kind, members, meta=None):
            e = esc.setdefault(key, {"kind": kind, "members": [],
                                     "meta": meta or {}})
            e["members"].extend(members)

        for cluster, members in sorted(held_by_cluster.items()):
            if cluster in ("true-duplicate", "move-failed"):
                continue
            if cluster == "double-rendered-captures":
                put(cluster, "double", members)
            elif cluster.startswith("capture:"):
                cand = cluster.split(":", 1)[1]
                if len(members) >= 4:
                    put(cluster, "capture", members, {"cand": cand})
                else:
                    grp = "capture-longtail-blogs" if (
                        cand.endswith("-blog") or cand in
                        ("blog-network", "saturday-podcast",
                         "console-room")) else \
                        "capture-longtail-rest"
                    e = esc.setdefault(
                        grp, {"kind": "longtail", "members": [],
                              "meta": {"subs": {}}})
                    e["members"].extend(members)
                    e["meta"]["subs"].setdefault(cand, []).extend(
                        members)
            elif cluster.startswith("family:rpt-"):
                e = esc.setdefault(
                    "rpt-reports", {"kind": "rpt", "members": [],
                                    "meta": {"subs": {}}})
                e["members"].extend(members)
                e["meta"]["subs"].setdefault(
                    cluster.split(":", 1)[1], []).extend(members)
            elif cluster.startswith("family:") \
                    and len(members) == 1:
                put("singles", "singles", members)
            else:
                put(cluster, "family", members,
                    {"fam": cluster.split(":", 1)[1]})
        for key2, e2 in esc.items():
            for m in e2["members"]:
                m["esc_cluster"] = key2
        for m in held_by_cluster.get("true-duplicate", []):
            m["esc_cluster"] = "true-duplicate"
        for m in held_by_cluster.get("move-failed", []):
            m["esc_cluster"] = "move-failed"
        for cluster, e in sorted(esc.items()):
            members = e["members"]
            n = len(members)
            ages = sorted(m["age_days"] for m in members)
            examples = [((m.get("subject") or m["base"])[:90])
                        for m in members[:3]]
            kind = e["kind"]
            if kind == "capture":
                cand = e["meta"]["cand"]
                rec_slug = None if cand == "none" else cand
                rationale = ("The router's best candidate for "
                             "these captures is %s, but no "
                             "precedent in the filed corpus backs "
                             "filing them there on the clerk's "
                             "own authority." % rec_slug) \
                    if rec_slug else (
                    "The router found no candidate home at all "
                    "for these captures.")
                q = ("Where should %d held intel captures about "
                     "'%s' be filed?" % (n, cand))
                ctx = ("The clerk's held-tray self-examination "
                       "could not place %d intel captures (ages "
                       "%d-%d days). Examples: %s. %s"
                       % (n, ages[0], ages[-1],
                          "; ".join(examples), rationale))
                opts = ([{"label": "File to %s" % rec_slug,
                          "value": rec_slug}] if rec_slug else []) \
                    + [{"label": "Keep held in unsorted",
                        "value": "unsorted"},
                       {"label": "Name another home",
                        "value": "other"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            elif kind == "longtail":
                subs = e["meta"]["subs"]
                lines_ = ["- candidate '%s': %d captures (e.g. %s)"
                          % (c, len(ms),
                             (ms[0].get("subject")
                              or ms[0]["base"])[:80])
                          for c, ms in sorted(
                              subs.items(),
                              key=lambda kv: -len(kv[1]))]
                q = ("Where should %d held intel captures in "
                     "%d small topic clusters be filed?"
                     % (n, len(subs)))
                ctx = ("The clerk's held-tray self-examination "
                       "could not place these small capture "
                       "clusters on precedent (ages %d-%d days). "
                       "Each cluster's recommended destination "
                       "is the router's best candidate:\n%s"
                       % (ages[0], ages[-1], "\n".join(lines_)))
                opts = [{"label": "File each cluster to its "
                                   "named candidate",
                         "value": "file-to-candidates"},
                        {"label": "Keep held in unsorted",
                         "value": "unsorted"},
                        {"label": "Name other homes",
                         "value": "other"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            elif kind == "double":
                homes = Counter()
                for m in members:
                    for s in m.get("sibling_homes", []):
                        homes[s] += 1
                q = ("What should happen to %d captures that "
                     "already have a filed rendering in another "
                     "workspace, while a second rendering sits "
                     "in the unsorted tray?" % n)
                ctx = ("These captures were filed once "
                       "(Workflow #3 rendering; homes: %s) and "
                       "a second, different rendering (the "
                       "clerk-sort rendering, with unique clerk "
                       "assessment content) sits held in "
                       "unsorted (ages %d-%d days). Examples: "
                       "%s. Standing resort doctrine holds "
                       "duplicate editions; whether the second "
                       "rendering should be filed alongside its "
                       "sibling (and the capture bookkeeping "
                       "corrected to match) is a doctrine call."
                       % (", ".join("%s x%d" % kv for kv in
                                    homes.most_common(4)),
                          ages[0], ages[-1],
                          "; ".join(examples)))
                opts = [{"label": "File alongside the sibling "
                                   "rendering and fix bookkeeping",
                         "value": "file-alongside"},
                        {"label": "Keep the tray rendering held "
                                  "as a duplicate edition",
                         "value": "keep-held"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            elif kind == "rpt":
                subs = e["meta"]["subs"]
                lines_ = ["- %s: %d" % (f, len(ms))
                          for f, ms in sorted(
                              subs.items(),
                              key=lambda kv: -len(kv[1]))]
                counter = Counter()
                for f in subs:
                    counter.update(by_family.get(f, {}))
                total = sum(counter.values())
                rec_slug, cnt = (counter.most_common(1)[0]
                                 if total else (None, 0))
                q = ("Where should %d held RPT reports "
                     "(research, surveys, plans, alerts — not "
                     "the digests) be filed?" % n)
                ctx = ("The clerk's held-tray self-examination "
                       "found no dominant home for the October "
                       "2026 RPT report families (ages %d-%d "
                       "days):\n%s\nThe RPT digests were filed "
                       "to home-lab on genre precedent (290 of "
                       "297 filed digest documents sit there). "
                       "For the other reports the filed corpus "
                       "is split by topic; the plurality home "
                       "is %s (%d of %d filed RPT documents). "
                       "Recommendation: file them to %s with "
                       "the digests, unless the reports should "
                       "keep routing per-topic."
                       % (ages[0], ages[-1], "\n".join(lines_),
                          rec_slug, cnt, total, rec_slug))
                opts = ([{"label": "File to %s" % rec_slug,
                          "value": rec_slug}] if rec_slug else []) \
                    + [{"label": "Keep held; route per-topic "
                                  "by hand",
                        "value": "per-topic"},
                       {"label": "Name another home",
                        "value": "other"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            elif kind == "singles":
                lines_ = []
                for m in members:
                    rec, why = SINGLES_REC.get(
                        family_of(m["base"]),
                        (None, "No recommendation on record."))
                    lines_.append("- %s -> recommend %s (%s)"
                                  % (m["base"][:60],
                                     rec or "?", why))
                q = ("Where should %d one-off held documents "
                     "be filed?" % n)
                ctx = ("The clerk's held-tray self-examination "
                       "found no precedent-backed home for "
                       "these one-off documents (ages %d-%d "
                       "days), each with its recommendation:\n%s"
                       % (ages[0], ages[-1], "\n".join(lines_)))
                opts = [{"label": "File each as recommended",
                         "value": "file-as-recommended"},
                        {"label": "Keep held in unsorted",
                         "value": "unsorted"},
                        {"label": "Name other homes",
                         "value": "other"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            else:  # family
                fam = e["meta"]["fam"]
                rec = RECOMMEND.get(fam)
                counter = by_family.get(fam, Counter())
                total = sum(counter.values())
                if rec:
                    rec_slug, rationale = rec
                elif total:
                    rec_slug, cnt = counter.most_common(1)[0]
                    rationale = ("Plurality home in the filed "
                                 "corpus: %s holds %d of %d "
                                 "filed documents of this "
                                 "family — below the dominance "
                                 "bar for the clerk to file on "
                                 "its own."
                                 % (rec_slug, cnt, total))
                else:
                    rec_slug, rationale = None, (
                        "No document of this family has ever "
                        "been filed anywhere.")
                q = ("Where should %d held documents of the "
                     "'%s' family be filed?" % (n, fam))
                ctx = ("The clerk's held-tray self-examination "
                       "found no precedent-backed home for %d "
                       "documents of family %s (ages %d-%d "
                       "days). Examples: %s. %s"
                       % (n, fam, ages[0], ages[-1],
                          "; ".join(examples), rationale))
                opts = ([{"label": "File to %s" % rec_slug,
                          "value": rec_slug}] if rec_slug else []) \
                    + [{"label": "Keep held in unsorted",
                        "value": "unsorted"},
                       {"label": "Name another home",
                        "value": "other"}]
                qid = escalate(conn, cluster, q, ctx, opts)
            if qid:
                escalated[cluster] = qid

    # ---- held list (the tray's accounting) ----------------------
    # Rebuilt from the tray's ACTUAL post-run state: a document
    # that left the tray (including one whose move verified late)
    # never appears on the list, and every document still in the
    # tray carries its cluster tag.
    remaining = held + young
    if not dry:
        tag = {}
        for d in held + young:
            tag[d["filename"]] = (
                (d.get("subject") or d["base"])[:160],
                _cap_id(d["filename"]), d.get("candidates", []),
                "clerk-tray: %s" % d.get(
                    "esc_cluster",
                    d.get("cluster", "deferred-young")))
        actual = tray_docs()
        with open(HELD_PATH, "w") as f:
            json.dump(
                [{"filename": d["filename"],
                  "subject": tag.get(
                      d["filename"],
                      (d["base"], None, [],
                       "clerk-tray: unexamined"))[0],
                  "capture_id": tag.get(
                      d["filename"], (None, None, [], ""))[1],
                  "candidates": tag.get(
                      d["filename"], (None, None, [], ""))[2],
                  "why": tag.get(
                      d["filename"],
                      (None, None, [],
                       "clerk-tray: unexamined"))[3]}
                 for d in actual], f, indent=1)
        remaining = actual
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry, "tray_before": len(docs),
        "examined": len(examined), "deferred_young": len(young),
        "filed": len(moves), "held_after": len(remaining),
        "clusters": {k: len(v) for k, v in
                     sorted(held_by_cluster.items())},
        "escalated": escalated,
        "moves": moves,
    }
    if not dry:
        with open(RUN_LOG, "a") as f:
            f.write(json.dumps(summary) + "\n")
    print("TRAY_LOOP_%s examined=%d filed=%d held=%d escalated=%d "
          "young=%d" % ("DRYRUN" if dry else "OK", len(examined),
                        len(moves), len(remaining),
                        len(escalated), len(young)))
    for k, v in sorted(summary["clusters"].items()):
        print("  cluster %-44s %d" % (k, v))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
