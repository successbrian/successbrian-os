#!/usr/bin/env python3
"""
ecosystem_intel — stop re-deriving the world.

Record once, serve cheaply forever:
    record_fact(tenant, key, value, category, source)
    record_howto(tenant, topic, summary, steps)
    record_gotcha(tenant, trap, why, fix)

Agents fetch by topic before doing discovery work:
    get_digest(tenant, categories=None)  -> dict of facts/howtos/gotchas
    find(tenant, query)                  -> keyword search across all three

CLI:
    python3 intel.py --tenant brian --digest [category]
    python3 intel.py --tenant brian --find "nginx"

stdlib + psql CLI only.
"""
import argparse
import os
import subprocess


def _pg_env():
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("PGHOST", "localhost"),
        "PGPORT": os.environ.get("PGPORT", "5432"),
        "PGDATABASE": os.environ.get("PGDATABASE", "ecosystem_central"),
        "PGUSER": os.environ.get("PGUSER", "successbrian"),
    })
    return env


def pg_query(sql):
    p = subprocess.run(["psql", "-t", "-A", "-F", "\t", "-c", sql],
                       capture_output=True, text=True,
                       env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_query failed: {p.stderr.strip()[:300]}")
    return [l.split("\t") for l in p.stdout.strip().split("\n") if l.strip()]


def pg_exec(sql):
    p = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t"],
                       input=sql, capture_output=True, text=True,
                       env=_pg_env(), timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"pg_exec failed: {p.stderr.strip()[:300]}")


def lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def record_fact(tenant, key, value, category="general", source=None,
                confidence="verified"):
    pg_exec(f"INSERT INTO ecosystem_intel.facts "
            f"(tenant_id, key, value, category, confidence, source) "
            f"VALUES ({lit(tenant)}, {lit(key)}, {lit(value)}, "
            f"{lit(category)}, {lit(confidence)}, {lit(source)}) "
            f"ON CONFLICT (tenant_id, key) DO UPDATE SET "
            f"value=EXCLUDED.value, category=EXCLUDED.category, "
            f"confidence=EXCLUDED.confidence, source=EXCLUDED.source, "
            f"verified_at=now();")


def record_howto(tenant, topic, summary, steps, related=None):
    pg_exec(f"INSERT INTO ecosystem_intel.howtos "
            f"(tenant_id, topic, summary, steps, related) "
            f"VALUES ({lit(tenant)}, {lit(topic)}, {lit(summary)}, "
            f"{lit(steps)}, {lit(related)}) "
            f"ON CONFLICT (tenant_id, topic) DO UPDATE SET "
            f"summary=EXCLUDED.summary, steps=EXCLUDED.steps, "
            f"related=EXCLUDED.related;")


def record_gotcha(tenant, trap, why, fix):
    pg_exec(f"INSERT INTO ecosystem_intel.gotchas "
            f"(tenant_id, trap, why, fix) "
            f"VALUES ({lit(tenant)}, {lit(trap)}, {lit(why)}, {lit(fix)}) "
            f"ON CONFLICT (tenant_id, trap) DO UPDATE SET "
            f"why=EXCLUDED.why, fix=EXCLUDED.fix;")


def pg_json(sql):
    """Run a SELECT and return rows as dicts (newline-safe via row_to_json)."""
    import json as _json
    p = subprocess.run(
        ["psql", "-t", "-A", "-c",
         f"SELECT row_to_json(t) FROM ({sql}) t;"],
        capture_output=True, text=True, env=_pg_env(), timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"pg_json failed: {p.stderr.strip()[:300]}")
    return [_json.loads(l) for l in p.stdout.strip().split("\n") if l.strip()]


def get_digest(tenant, category=None):
    """Everything an agent should know before discovery work."""
    t = lit(tenant)
    cat = f"AND category={lit(category)}" if category else ""
    facts = pg_json(
        "SELECT key, value, category, confidence "
        "FROM ecosystem_intel.facts "
        f"WHERE tenant_id={t} {cat} ORDER BY category, key")
    howtos = pg_json(
        "SELECT topic, summary, steps "
        "FROM ecosystem_intel.howtos "
        f"WHERE tenant_id={t} ORDER BY topic")
    gotchas = pg_json(
        "SELECT trap, why, fix FROM ecosystem_intel.gotchas "
        f"WHERE tenant_id={t} ORDER BY trap")
    return {"facts": facts, "howtos": howtos, "gotchas": gotchas}


def find(tenant, query):
    """Keyword search across facts, howtos, gotchas."""
    t = lit(tenant)
    q = f"%{query}%"
    out = []
    for r in pg_json(
            "SELECT 'fact' AS kind, key, value AS text "
            "FROM ecosystem_intel.facts "
            f"WHERE tenant_id={t} AND (key ILIKE {lit(q)} "
            f"OR value ILIKE {lit(q)} OR category ILIKE {lit(q)})"):
        out.append(r)
    for r in pg_json(
            "SELECT 'howto' AS kind, topic AS key, summary AS text "
            "FROM ecosystem_intel.howtos "
            f"WHERE tenant_id={t} AND (topic ILIKE {lit(q)} "
            f"OR summary ILIKE {lit(q)} OR steps ILIKE {lit(q)})"):
        out.append(r)
    for r in pg_json(
            "SELECT 'gotcha' AS kind, trap AS key, fix AS text "
            "FROM ecosystem_intel.gotchas "
            f"WHERE tenant_id={t} AND (trap ILIKE {lit(q)} "
            f"OR why ILIKE {lit(q)} OR fix ILIKE {lit(q)})"):
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--digest", action="store_true")
    ap.add_argument("--category", default=None)
    ap.add_argument("--find", default=None)
    args = ap.parse_args()
    import json
    if args.digest:
        print(json.dumps(get_digest(args.tenant, args.category), indent=2))
    elif args.find:
        print(json.dumps(find(args.tenant, args.find), indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
