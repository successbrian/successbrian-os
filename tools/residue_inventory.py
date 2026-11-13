#!/usr/bin/env python3
"""residue_inventory.py - READ-ONLY residue inventory (BUILD_QUEUE B6).

One unified query gathering everything genuinely waiting on Brian:
  held_brian_step - successbrian_os.pm_steps where status='held_brian'
  unruled_capture - atlas.scattered_captures where depth='brian_decision'
                    and ruled_at is null (B8b-2: the stream draws ONLY
                    from brian_decision. Unruled means never ruled by
                    Brian: ruled_at is set only by the B8 write-back.
                    ruling_why is NOT the test - gamma classify notes
                    land there with ruled_at null, e.g. capture 1551.
                    Raw captures carry depth NULL until the clerk
                    triages them, so they enter the stream only once
                    classified - unclassified is never silently
                    Brian-facing.)
  compile_residue - successbrian_os.knowledge_index where kind='compile'
                    (the B15 standing-compile contract: compiles file
                    their residue-bearing rows to knowledge_index with
                    kind 'compile'. No such rows exist yet - B15 is
                    unbuilt - so this leg reads 0 today and lights up
                    automatically when B15 lands.)

Read-only: SELECTs only, oldest-first so the next decision for Brian is
the first row. assembly_status.py shows the count + oldest item from
--summary. Plan: builds/sbos-assembly/PLAN.md Phase 2.

Usage: residue_inventory.py [--summary] [--selftest]
"""
import subprocess
import sys
from datetime import datetime, timezone

DB = ["psql", "-d", "ecosystem_central", "-At", "-F", "\x1f"]

# The B6 contract: one UNION, five columns, oldest first. assembly_status.py
# consumes --summary; keep the SQL here as the single source of truth.
UNION_SQL = """
select 'held_brian_step' as source,
       'pm_steps:' || id::text as ref,
       coalesce(title, '') as title,
       created_at,
       coalesce(origin, '') as context
  from successbrian_os.pm_steps where status = 'held_brian'
union all
select 'unruled_capture',
       'capture:' || id::text,
       coalesce(title, ''),
       created_at,
       coalesce(cluster_key, '')
  from atlas.scattered_captures
 where depth = 'brian_decision' and ruled_at is null
   and status <> 'discarded'
union all
select 'compile_residue',
       'ki:' || canonical_id,
       coalesce(title, subject, canonical_id),
       created_at,
       coalesce(kind, '')
  from successbrian_os.knowledge_index where kind = 'compile'
 order by created_at asc
"""

SOURCES = ("held_brian_step", "unruled_capture", "compile_residue")

WRITE_WORDS = ("insert ", "update ", "delete ", "drop ", "truncate ",
               "alter ", "create ", "grant ", "revoke ")


def run(sql):
    out = subprocess.run(DB + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [l for l in out.stdout.splitlines() if l.strip()]


def fetch_rows():
    rows = []
    for line in run(UNION_SQL):
        parts = line.split("\x1f")
        assert len(parts) == 5, f"bad row shape: {line!r}"
        source, ref, title, created_raw, context = parts
        created = datetime.fromisoformat(created_raw)
        rows.append({"source": source, "ref": ref, "title": title,
                     "created": created, "context": context})
    return rows


def age_days(created):
    now = datetime.now(timezone.utc)
    return max(0, (now - created).days)


def summarize(rows):
    counts = {s: sum(1 for r in rows if r["source"] == s) for s in SOURCES}
    oldest = rows[0] if rows else None
    return counts, len(rows), oldest


def selftest():
    # the SQL is read-only by construction
    lowered = UNION_SQL.lower()
    for word in WRITE_WORDS:
        assert word not in lowered, f"write word in SQL: {word!r}"
    rows = fetch_rows()
    counts, total, oldest = summarize(rows)
    assert total == sum(counts.values()), "counts do not reconcile"
    assert all(v >= 0 for v in counts.values())
    assert all(r["source"] in SOURCES for r in rows)
    if rows:
        assert oldest["created"] == min(r["created"] for r in rows), \
            "oldest row is not the minimum created_at"
        assert rows == sorted(rows, key=lambda r: r["created"]), \
            "rows are not oldest-first"
    # a guaranteed-empty probe stays empty (queries are scoped)
    assert run("select 1 where 1=0") == []
    # B8b-2: the capture leg draws ONLY from brian_decision, unruled -
    # its count reconciles with the depth directly, not with raw status.
    bd = run("select count(*) from atlas.scattered_captures "
             "where depth = 'brian_decision' and ruled_at is null "
             "and status <> 'discarded'")
    assert counts["unruled_capture"] == int(bd[0]), \
        f"capture leg {counts['unruled_capture']} != brian_decision " \
        f"unruled {bd[0]}"
    print("RESIDUE_INVENTORY_OK")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    rows = fetch_rows()
    counts, total, oldest = summarize(rows)
    if "--summary" in sys.argv:
        print(f"residue total: {total}")
        for s in SOURCES:
            print(f"{s}: {counts[s]}")
        if oldest:
            print(f"oldest: {oldest['source']} {oldest['ref']} "
                  f"\"{oldest['title']}\" created "
                  f"{oldest['created']:%Y-%m-%d %H:%M:%S%z} "
                  f"({age_days(oldest['created'])} days ago)")
        else:
            print("oldest: none")
        return 0
    for r in rows:
        ctx = f" [{r['context']}]" if r["context"] else ""
        print(f"{r['source']} | {r['ref']} | {age_days(r['created'])}d | "
              f"{r['created']:%Y-%m-%d %H:%M} | {r['title']}{ctx}")
    print(f"residue total: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
