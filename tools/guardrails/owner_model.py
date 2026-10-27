#!/usr/bin/env python3
"""Owner-model layer — Brian's Tier-2 gap build (2026-10-27).

A durable, evidence-backed store of CONCLUSIONS the system holds about
its owner (Brian) — each conclusion carries its domain, a confidence
(0-1), and evidence refs ({kind, ref, note}). Conclusions are never
silently overwritten: correcting one creates a NEW row that supersedes
the old, and the old row is marked 'corrected'. Retiring marks a row
'retired'. Table starts EMPTY by design: conclusions must arrive with
evidence over time; nothing is seeded.

Table: successbrian_os.owner_model (migration 2026-10-27_owner_model.sql,
also ensured idempotently by ensure_schema()).

CLI:
  owner_model.py add --conclusion TEXT --domain TEXT --confidence 0.8 \\
                     --evidence '[{"kind":"chat","ref":"...","note":"..."}]'
  owner_model.py list [--domain TEXT]
  owner_model.py correct <id> --conclusion TEXT [--domain TEXT] \\
                     [--confidence N] [--evidence JSON]
  owner_model.py retire <id>
  owner_model.py selftest
"""
import argparse
import json
import os
import sys

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS successbrian_os.owner_model (
    id            bigserial PRIMARY KEY,
    conclusion    text NOT NULL,
    domain        text NOT NULL,
    confidence    numeric(3,2) NOT NULL
                  CHECK (confidence >= 0 AND confidence <= 1),
    evidence      jsonb NOT NULL DEFAULT '[]'::jsonb,
    status        text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','corrected','retired')),
    supersedes_id bigint REFERENCES successbrian_os.owner_model(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
"""


def _conn():
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(dbname="ecosystem_central", host="localhost",
                            cursor_factory=psycopg2.extras.RealDictCursor)


def ensure_schema(cur):
    cur.execute(SCHEMA_SQL)


def _check_evidence(evidence):
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a JSON array of {kind, ref, note}")
    for item in evidence:
        if not isinstance(item, dict) or "kind" not in item or "ref" not in item:
            raise ValueError("each evidence ref needs at least kind and ref")
    return json.dumps(evidence)


def add_conclusion(cur, conclusion, domain, confidence, evidence):
    ev = _check_evidence(evidence)
    if not (0 <= float(confidence) <= 1):
        raise ValueError("confidence must be between 0 and 1")
    cur.execute(
        """INSERT INTO successbrian_os.owner_model
             (conclusion, domain, confidence, evidence)
           VALUES (%s, %s, %s, %s::jsonb) RETURNING id""",
        (conclusion, domain, confidence, ev))
    return cur.fetchone()["id"]


def correct_conclusion(cur, old_id, conclusion, domain=None,
                       confidence=None, evidence=None):
    cur.execute("SELECT * FROM successbrian_os.owner_model WHERE id=%s",
                (old_id,))
    old = cur.fetchone()
    if old is None:
        raise ValueError("no owner_model row %s" % old_id)
    if old["status"] != "active":
        raise ValueError("row %s is %s, not active" % (old_id, old["status"]))
    new_id = add_conclusion(
        cur, conclusion,
        domain if domain is not None else old["domain"],
        confidence if confidence is not None else float(old["confidence"]),
        evidence if evidence is not None else old["evidence"])
    cur.execute(
        """UPDATE successbrian_os.owner_model
              SET supersedes_id=%s, updated_at=now() WHERE id=%s""",
        (old_id, new_id))
    cur.execute(
        """UPDATE successbrian_os.owner_model
              SET status='corrected', updated_at=now() WHERE id=%s""",
        (old_id,))
    return new_id


def retire(cur, row_id):
    cur.execute(
        """UPDATE successbrian_os.owner_model
              SET status='retired', updated_at=now()
            WHERE id=%s AND status='active' RETURNING id""", (row_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("no active owner_model row %s" % row_id)
    return row["id"]


def list_rows(cur, domain=None):
    if domain:
        cur.execute(
            "SELECT * FROM successbrian_os.owner_model WHERE domain=%s "
            "ORDER BY id", (domain,))
    else:
        cur.execute("SELECT * FROM successbrian_os.owner_model ORDER BY id")
    return [dict(r) for r in cur.fetchall()]


def selftest():
    checks = 0
    fails = 0

    def check(cond, label):
        nonlocal checks, fails
        checks += 1
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            fails += 1

    conn = _conn()
    cur = conn.cursor()
    ensure_schema(cur)
    conn.commit()
    ids = []
    try:
        fid = add_conclusion(
            cur, "SELFTEST fixture conclusion", "selftest", 0.5,
            [{"kind": "selftest", "ref": "owner_model.py selftest",
              "note": "fixture"}])
        ids.append(fid)
        conn.commit()
        check(isinstance(fid, int) and fid > 0, "fixture row added")

        new_id = correct_conclusion(
            cur, fid, "SELFTEST corrected conclusion",
            evidence=[{"kind": "selftest", "ref": "correction",
                       "note": "fixture"}])
        ids.append(new_id)
        conn.commit()
        check(new_id != fid, "correct creates a new row")

        rows = {r["id"]: r for r in list_rows(cur, "selftest")}
        check(rows[fid]["status"] == "corrected", "old row marked corrected")
        check(rows[new_id]["supersedes_id"] == fid,
              "supersedes chain intact (new -> old)")
        check(rows[new_id]["status"] == "active", "new row is active")

        retire(cur, new_id)
        conn.commit()
        rows = {r["id"]: r for r in list_rows(cur, "selftest")}
        check(rows[new_id]["status"] == "retired", "retire marks retired")
    finally:
        cur.execute(
            "UPDATE successbrian_os.owner_model SET supersedes_id=NULL "
            "WHERE id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM successbrian_os.owner_model "
                    "WHERE id = ANY(%s)", (ids,))
        conn.commit()
        cur.execute("SELECT count(*) AS n FROM successbrian_os.owner_model "
                    "WHERE domain='selftest'")
        check(cur.fetchone()["n"] == 0, "cleanup removed fixture rows")
        conn.close()
    print("SELFTEST %s: %d/%d checks passed"
          % ("OK" if fails == 0 else "FAILED", checks - fails, checks))
    return 0 if fails == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS owner-model layer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--conclusion", required=True)
    a.add_argument("--domain", required=True)
    a.add_argument("--confidence", required=True, type=float)
    a.add_argument("--evidence", required=True,
                   help="JSON array of {kind, ref, note}")
    li = sub.add_parser("list")
    li.add_argument("--domain")
    co = sub.add_parser("correct")
    co.add_argument("id", type=int)
    co.add_argument("--conclusion", required=True)
    co.add_argument("--domain")
    co.add_argument("--confidence", type=float)
    co.add_argument("--evidence")
    re_ = sub.add_parser("retire")
    re_.add_argument("id", type=int)
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    conn = _conn()
    cur = conn.cursor()
    ensure_schema(cur)
    try:
        if args.cmd == "add":
            rid = add_conclusion(cur, args.conclusion, args.domain,
                                 args.confidence, json.loads(args.evidence))
            print("added owner_model row %d" % rid)
        elif args.cmd == "list":
            for r in list_rows(cur, args.domain):
                print("%d [%s] %s :: %s (confidence %s, supersedes %s)"
                      % (r["id"], r["status"], r["domain"], r["conclusion"],
                         r["confidence"], r["supersedes_id"]))
        elif args.cmd == "correct":
            ev = json.loads(args.evidence) if args.evidence else None
            nid = correct_conclusion(cur, args.id, args.conclusion,
                                     args.domain, args.confidence, ev)
            print("corrected: row %d superseded by new row %d"
                  % (args.id, nid))
        elif args.cmd == "retire":
            retire(cur, args.id)
            print("retired owner_model row %d" % args.id)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("error: %s" % e, file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
