#!/usr/bin/env python3
"""
agent_knowledge — the Agent Knowledge Gateway for SuccessBrian OS.

Brian's ruling (2026-10-31): "I want my agents to know or be able
to learn everything."

Meaning, encoded: every agent in this ecosystem can reach ALL of
the ecosystem's knowledge — the second brain, Brian's decisions and
learnings, the intel collection, the Atlas graph, the Intel Bridge
intake, the AnythingLLM knowledge homes, the companies table, and
the project/QA record — through ONE door, instead of needing to
know which of a dozen stores a fact happens to live in.

Two modes:
  KNOW  — ask(): one search across every store, grouped, with the
          store named on every hit so the agent can go deeper.
  LEARN — briefing(): everything the ecosystem holds on one topic,
          assembled into a single context an agent can load before
          working (the rehydration path).

Write-back follows the standing gates, it does not bypass them:
  - unverified findings  -> Intel Bridge capture (intake)
  - verified working knowledge -> ecosystem_intel (teach())
  - durable verified knowledge -> altair.second_brain, only via
    the owning system's writer, with provenance and expiry
Secrets are not knowledge: passwords, API keys, and credential
values stay in the Secure Vault / .env and are never served here.
Agents use them through their secure flows without seeing them.

Stores (all read live; nothing is copied into this module):
  second_brain   altair.second_brain (active, unexpired entries)
  decisions      altair.brian_decisions
  learnings      altair.brian_learnings
  intel          ecosystem_intel facts/howtos/gotchas (intel.py)
  atlas          atlas.nodes (the graph)
  captures       atlas.scattered_captures (Intel Bridge intake)
  anythingllm    workspace registry + document filenames
  companies      people_unified.people.companies (the ONE table)
  projects       successbrian_os.pm_projects + pm_project_checks

CLI:
    python3 agent_knowledge.py --stores
    python3 agent_knowledge.py --ask "social intelligence"
    python3 agent_knowledge.py --briefing "Aptean"
    python3 agent_knowledge.py --selftest
    python3 agent_knowledge.py --smoke
"""

import os
import sqlite3
import subprocess

TENANT = "brian"
ALLM_DB = os.path.expanduser(
    "~/anything-llm/server/storage/anythingllm.db")

STORES = [
    ("second_brain", "altair.second_brain",
     "The verified knowledge layer: durable facts with "
     "confidence, provenance, and expiry. Active entries only."),
    ("decisions", "altair.brian_decisions",
     "Brian's rulings, with question, context, and answer. The "
     "first place to check before evaluating anything he names."),
    ("learnings", "altair.brian_learnings",
     "Lessons the crew has recorded from doing the work."),
    ("intel", "ecosystem_intel (facts / howtos / gotchas)",
     "Working knowledge agents record once and reuse: facts, "
     "procedures, and traps, by category."),
    ("atlas", "atlas.nodes + atlas.edges",
     "The structure graph: systems, projects, assets, tasks, and "
     "how they connect. Graph, not a tree."),
    ("captures", "atlas.scattered_captures",
     "Intel Bridge intake: raw captures and research results "
     "awaiting or past sorting. Intake is NOT verified knowledge."),
    ("anythingllm", "AnythingLLM workspaces + documents",
     "The document homes (R32): charters, packs, briefs, and "
     "digests, one workspace per body of knowledge."),
    ("companies", "people_unified.people.companies",
     "The ONE companies table: curated company knowledge, "
     "classified by the kind column."),
    ("projects", "successbrian_os.pm_projects + checks",
     "Registered projects and their QA state: what is being "
     "built, and whether it is verified working."),
]


def _like(term):
    return "%" + term.replace("%", "") + "%"


def search_second_brain(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT topic AS title, category, left(content, 600) AS "
        "text, source FROM altair.second_brain WHERE "
        f"expires_at > now() AND (topic ILIKE {q} OR content "
        f"ILIKE {q} OR category ILIKE {q}) ORDER BY updated_at "
        f"DESC LIMIT {limit}")


def search_decisions(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT decision_id AS title, question, left(answer, "
        "600) AS text, answered_at::text AS when_ FROM "
        "altair.brian_decisions WHERE question ILIKE "
        f"{q} OR answer ILIKE {q} OR context ILIKE {q} "
        f"ORDER BY id DESC LIMIT {limit}")


def search_learnings(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT left(content, 600) AS text, source, status FROM "
        f"altair.brian_learnings WHERE content ILIKE {q} "
        f"ORDER BY id DESC LIMIT {limit}")


def search_intel(term, limit=8):
    from intel import find
    return find(TENANT, term)[:limit]


def search_atlas(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT node_key AS title, node_type, name, status FROM "
        "atlas.nodes WHERE name ILIKE "
        f"{q} OR node_key ILIKE {q} OR details::text ILIKE {q} "
        f"ORDER BY node_type, name LIMIT {limit}")


def search_captures(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT id AS title, left(raw_text, 500) AS text, "
        "status, created_at::text AS when_ FROM "
        "atlas.scattered_captures WHERE title ILIKE "
        f"{q} OR raw_text ILIKE {q} OR context ILIKE {q} "
        f"ORDER BY id DESC LIMIT {limit}")


def search_knowledge_index(term, limit=8):
    """The master index (successbrian_os.knowledge_index).
    Every embedded document has a row there -- curated (clerk
    filings, doctrine) or catalog (kind 'embedded-doc', written
    by the embed path) -- so a title/subject hit here is a real
    filed document, including the ones whose AnythingLLM
    filenames are opaque (intel-capture-N.md). Added 2026-11-09
    with the clerk filing-flow repair (Leak 2: embedded docs
    invisible to the gateway)."""
    try:
        from intel import pg_json, lit
        q = lit(_like(term))
        return pg_json(
            "SELECT allm_workspace AS workspace, "
            "title || ' [' || coalesce(allm_filename, '') || "
            "']' AS title, 'knowledge-index' AS kind FROM "
            "successbrian_os.knowledge_index WHERE "
            f"title ILIKE {q} OR subject ILIKE {q} "
            "ORDER BY (kind = 'embedded-doc'), updated_at DESC "
            f"LIMIT {int(limit)}")
    except Exception:
        return []


def search_anythingllm(term, limit=8):
    out = []
    if not os.path.exists(ALLM_DB):
        return out
    db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
    try:
        like = _like(term)
        for slug, name in db.execute(
                "SELECT slug, name FROM workspaces WHERE name "
                "LIKE ? OR slug LIKE ? LIMIT 4", (like, like)):
            out.append({"workspace": slug, "title": name,
                        "kind": "workspace"})
        for slug, filename in db.execute(
                "SELECT w.slug, wd.filename FROM "
                "workspace_documents wd JOIN workspaces w ON "
                "w.id = wd.workspaceId WHERE wd.filename LIKE ? "
                "LIMIT ?", (like, limit)):
            out.append({"workspace": slug, "title": filename,
                        "kind": "document"})
    finally:
        db.close()
    out.extend(search_knowledge_index(term, limit))
    return out[:limit + 4]


def search_companies(term, limit=5):
    env = dict(os.environ)
    env.update({"PGHOST": "localhost", "PGPORT": "5432",
                "PGDATABASE": "people_unified",
                "PGUSER": "successbrian"})
    sql = ("SELECT row_to_json(t) FROM (SELECT name AS title, "
           "kind, sector FROM people.companies WHERE name ILIKE "
           f"'{_like(term).replace(chr(39), chr(39) * 2)}' OR "
           f"sector ILIKE "
           f"'{_like(term).replace(chr(39), chr(39) * 2)}' "
           f"LIMIT {limit}) t;")
    p = subprocess.run(["psql", "-t", "-A", "-c", sql],
                       capture_output=True, text=True, env=env,
                       timeout=60)
    if p.returncode != 0:
        return []
    import json
    return [json.loads(l) for l in p.stdout.strip().split("\n")
            if l.strip()]


def search_projects(term, limit=5):
    from intel import pg_json, lit
    q = lit(_like(term))
    return pg_json(
        "SELECT project_key AS title, title AS name, status "
        "FROM successbrian_os.pm_projects WHERE project_key "
        f"ILIKE {q} OR title ILIKE {q} OR description ILIKE "
        f"{q} ORDER BY project_key LIMIT {limit}")


SEARCHERS = [
    ("second_brain", search_second_brain),
    ("decisions", search_decisions),
    ("learnings", search_learnings),
    ("intel", search_intel),
    ("atlas", search_atlas),
    ("captures", search_captures),
    ("anythingllm", search_anythingllm),
    ("companies", search_companies),
    ("projects", search_projects),
]


STOPWORDS = {"what", "does", "with", "from", "that", "this",
             "have", "about", "know", "want", "should", "would",
             "there", "their", "them", "then", "than", "into"}


def query_terms(term):
    """Full phrase first, then significant words — agents ask in
    sentences, and the record rarely repeats a sentence verbatim."""
    words = [w.strip(".,?!:;'\"").lower() for w in term.split()]
    terms = [term] + [w for w in words
                      if len(w) >= 4 and w not in STOPWORDS]
    seen, out = set(), []
    for t in terms:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:6]


def ask(term):
    """One search across every store. Returns {store: [hits]}."""
    results = {}
    for store, searcher in SEARCHERS:
        merged, seen = [], set()
        try:
            for q in query_terms(term):
                for hit in searcher(q):
                    marker = repr(sorted(
                        (k, str(v)) for k, v in hit.items()))
                    if marker not in seen:
                        seen.add(marker)
                        merged.append(hit)
                if len(merged) >= 8:
                    break
        except Exception as exc:  # a dark store degrades loudly
            merged = [{"error": f"{store} unavailable: "
                                f"{str(exc)[:120]}"}]
        if merged:
            results[store] = merged[:8]
    return results


def briefing(topic):
    """Everything the ecosystem holds on a topic, as one text."""
    results = ask(topic)
    lines = [f"# Briefing: {topic}",
             "(assembled live by agent_knowledge from every "
             "store; store named on each section)"]
    for store, _loc, _desc in STORES:
        hits = results.get(store)
        if not hits:
            continue
        lines.append(f"\n## {store}")
        for hit in hits:
            title = hit.get("title") or hit.get("key") or \
                hit.get("topic") or hit.get("name") or ""
            text = hit.get("text") or hit.get("summary") or ""
            lines.append(f"- {title} {text}".strip()[:700])
    if len(lines) == 2:
        lines.append("\nNo store holds anything on this topic "
                     "yet. That absence is a finding: if the "
                     "work matters, record it (capture -> intel "
                     "-> second brain, by verification).")
    return "\n".join(lines)


def teach_fact(key, value, category, source=None):
    """Verified working knowledge -> ecosystem_intel."""
    from intel import record_fact
    record_fact(TENANT, key, value, category, source)


def teach_gotcha(trap, why, fix):
    from intel import record_gotcha
    record_gotcha(TENANT, trap, why, fix)


def store_counts():
    from intel import pg_query
    counts = {}
    queries = {
        "second_brain": "SELECT count(*) FROM altair.second_brain "
                        "WHERE expires_at > now()",
        "decisions": "SELECT count(*) FROM "
                     "altair.brian_decisions",
        "learnings": "SELECT count(*) FROM altair.brian_learnings",
        "intel": "SELECT (SELECT count(*) FROM "
                 "ecosystem_intel.facts WHERE tenant_id='brian') "
                 "+ (SELECT count(*) FROM ecosystem_intel.howtos "
                 "WHERE tenant_id='brian') + (SELECT count(*) "
                 "FROM ecosystem_intel.gotchas WHERE "
                 "tenant_id='brian')",
        "atlas": "SELECT count(*) FROM atlas.nodes",
        "captures": "SELECT count(*) FROM "
                    "atlas.scattered_captures",
        "projects": "SELECT count(*) FROM "
                    "successbrian_os.pm_projects",
    }
    for store, sql in queries.items():
        try:
            counts[store] = int(pg_query(sql)[0][0])
        except Exception:
            counts[store] = -1
    try:
        counts["companies"] = int(subprocess.run(
            ["psql", "-t", "-A", "-d", "people_unified", "-c",
             "SELECT count(*) FROM people.companies"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PGHOST": "localhost",
                 "PGUSER": "successbrian"}).stdout.strip() or -1)
    except Exception:
        counts["companies"] = -1
    if os.path.exists(ALLM_DB):
        db = sqlite3.connect("file:%s?mode=ro" % ALLM_DB, uri=True)
        counts["anythingllm"] = db.execute(
            "SELECT count(*) FROM workspace_documents").fetchone()[0]
        db.close()
    return counts


def selftest():
    checks = []

    def ck(name, ok):
        checks.append((name, bool(ok)))

    ids = [s[0] for s in STORES]
    ck("store ids unique", len(ids) == len(set(ids)))
    ck("nine stores behind the one door", len(STORES) == 9)
    ck("every store has a searcher",
       {s for s, _f in SEARCHERS} == set(ids))
    ck("the four knowledge layers are present",
       {"second_brain", "intel", "anythingllm", "captures"} <=
       set(ids))
    ck("decisions and companies are present",
       {"decisions", "companies"} <= set(ids))
    ck("write-back gates are explicit in the docstring",
       "Intel Bridge capture" in (__doc__ or "") and
       "Secure Vault" in (__doc__ or ""))
    ck("teach paths delegate to ecosystem_intel",
       callable(teach_fact) and callable(teach_gotcha))
    terms = query_terms("what do my agents know about everything")
    ck("natural questions tokenize to searchable terms",
       terms[0].startswith("what do my agents") and
       "agents" in terms and "everything" in terms and
       "what" not in terms[1:])
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        raise SystemExit(1)


def smoke():
    """Live proof: one query must hit at least four stores."""
    results = ask("social")
    hit_stores = [s for s, hits in results.items()
                  if hits and "error" not in hits[0]]
    print("stores answering for 'social':", ", ".join(hit_stores))
    counts = store_counts()
    for store, _loc, _desc in STORES:
        print(f"  {store:<14} {counts.get(store, '?')} rows/docs")
    ok = len(hit_stores) >= 4
    print("smoke:", "PASS" if ok else "FAIL")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", action="store_true")
    ap.add_argument("--ask", default=None)
    ap.add_argument("--briefing", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if a.stores:
        counts = store_counts()
        for store, location, desc in STORES:
            print(f"{store:<14} {location}")
            print(f"{'':<14} {desc} "
                  f"[live count: {counts.get(store, '?')}]")
    elif a.ask:
        print(json.dumps(ask(a.ask), indent=2, default=str))
    elif a.briefing:
        print(briefing(a.briefing))
    elif a.selftest:
        selftest()
    elif a.smoke:
        smoke()
    else:
        ap.print_help()
