#!/usr/bin/env python3
"""sbos_backup.py — Verified backups for SuccessBrian OS (Tier 1).

PURPOSE: One CLI for the whole verified-backup system:
           pg-backup   pg_dump every database on the local cluster
           file-backup restic backup of the explicit file set to the
                       local repo AND the offsite (node-zero) repo
           check       restic check (rotating --read-data-subset)
           drill       REAL restore drill: restores the newest PG
                       backups into scratch databases and a file-set
                       sample into a scratch dir, verifies counts /
                       checksums, and writes a receipt row into
                       successbrian_os.backup_drills
           status      plain-text status + writes the doctor's
                       state file (guardrails/state/backups_status.json)
           nightly     pg-backup + file-backup (the cron entry point)
           selftest    offline checks of config, tools, tables
WHY:     Brian (2026-10-27 Tier-1 order): no verified backups existed.
         Tool choice: restic (single-binary OSS) for files; pg_dump
         for PostgreSQL. pgBackRest was NOT chosen: it requires
         archive_mode + archive_command changes and a production
         cluster restart to enable WAL archiving; archive_mode is
         'off' on this cluster, so PITR is a needs-Brian item (a
         restart window), recorded in backup_runs detail. pg_dump
         needs no restart and is proven by the drill below.
STATE:   PostgreSQL ecosystem_central, schema successbrian_os,
         tables backup_runs + backup_drills (migration
         2026-10-27_backups.sql; applied by ensure_schema here,
         idempotent).
SECRETS: the restic repository password lives ONLY in
         ~/.config/sbos-backups/restic-password (mode 600). It is
         never printed. ~/.ssh is deliberately EXCLUDED from the
         file set (private keys) — manual item, see backup_sets.json.
CALLED BY: cron (nightly / weekly check / monthly drill, flock'd)
         and operators. Sends nothing, publishes nothing.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.expanduser("~/successbrian-os")
CONFIG = os.path.join(HERE, "backup_sets.json")
STATE_JSON = os.path.join(REPO, "tools/guardrails/state/backups_status.json")
PW_FILE = os.path.expanduser("~/.config/sbos-backups/restic-password")
PG_HOST, PG_USER = "localhost", "postgres"
DRILL_DB_ECO = "drill_restore_ecosystem"
DRILL_DB_PU = "drill_restore_people"

sys.path.insert(0, os.path.join(REPO, "tools", "pm"))
import pm_core  # noqa: E402


def cfg():
    with open(CONFIG) as f:
        return json.load(f)


def conn():
    return pm_core.psycopg2.connect(dbname="ecosystem_central", host="localhost")


def ensure_schema(cur):
    cur.execute("""
CREATE TABLE IF NOT EXISTS successbrian_os.backup_runs (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('pg','files','check')),
    repo TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','ok','fail')),
    snapshot_id TEXT,
    bytes BIGINT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS successbrian_os.backup_drills (
    id BIGSERIAL PRIMARY KEY,
    drilled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pg_backup_at TIMESTAMPTZ,
    file_snapshot_id TEXT,
    checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS','FAIL')),
    notes TEXT
);
""")


def run(cmd, env_extra=None, timeout=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, capture_output=True, text=True,
                          env=env, timeout=timeout)


def restic_env():
    return {"RESTIC_PASSWORD_FILE": PW_FILE}


def list_databases():
    p = run(["psql", "-h", PG_HOST, "-U", PG_USER, "-d", "postgres",
             "-t", "-A", "-c",
             "SELECT datname FROM pg_database WHERE NOT datistemplate "
             "AND datname <> 'postgres' ORDER BY 1"])
    if p.returncode != 0:
        raise RuntimeError("database enumeration failed: " + p.stderr[:300])
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- pg backup
def cmd_pg_backup(args):
    c = cfg()
    stamp = datetime.now().strftime("%Y-%m-%d")
    outdir = os.path.join(os.path.expanduser(c["pg_dump_root"]), stamp)
    os.makedirs(outdir, exist_ok=True)
    dbs = list_databases()
    # Drill-critical databases first, the 293GB one second, rest after.
    order = [d for d in ("ecosystem_central", "people_unified") if d in dbs]
    order += [d for d in dbs if d not in order]
    cn = conn(); cur = cn.cursor(); ensure_schema(cur)
    cur.execute("INSERT INTO successbrian_os.backup_runs (kind, detail) "
                "VALUES ('pg', %s) RETURNING id",
                (json.dumps({"databases": order}),))
    run_id = cur.fetchone()[0]; cn.commit()
    manifest, total, failures = {}, 0, []
    for db in order:
        if db == "people_unified":
            dest = os.path.join(outdir, db + ".dumpdir")
            cmd = ["pg_dump", "-h", PG_HOST, "-U", PG_USER, "-Fd",
                   "-j", "3", "-Z", "3", "-f", dest, db]
        else:
            dest = os.path.join(outdir, db + ".dump")
            cmd = ["pg_dump", "-h", PG_HOST, "-U", PG_USER, "-Fc",
                   "-Z", "3", "-f", dest, db]
        print(f"[pg-backup] {db} -> {dest}", flush=True)
        p = run(cmd, timeout=60 * 60 * 12)
        if p.returncode != 0:
            failures.append({"db": db, "err": p.stderr[-400:]})
            print(f"[pg-backup] FAIL {db}: {p.stderr[-200:]}", flush=True)
            continue
        if os.path.isdir(dest):
            size = sum(os.path.getsize(os.path.join(r, fn))
                       for r, _, fns in os.walk(dest) for fn in fns)
            toc = run(["pg_restore", "-l", dest])
            digest = hashlib.sha256(toc.stdout.encode()).hexdigest()
        else:
            size = os.path.getsize(dest)
            digest = sha256_file(dest)
        manifest[db] = {"path": dest, "bytes": size, "sha256_or_toc": digest}
        total += size
        print(f"[pg-backup] ok {db} bytes={size}", flush=True)
    status = "ok" if not failures else "fail"
    cur.execute("UPDATE successbrian_os.backup_runs SET finished_at=now(), "
                "status=%s, bytes=%s, detail=%s WHERE id=%s",
                (status, total, json.dumps(
                    {"databases": manifest, "failures": failures,
                     "pitr": "unavailable: archive_mode=off (needs-Brian "
                             "restart window to enable WAL archiving)"}),
                 run_id))
    cn.commit(); cn.close()
    latest = os.path.join(os.path.expanduser(c["pg_dump_root"]), "latest")
    try:
        if os.path.islink(latest) or os.path.exists(latest):
            os.remove(latest)
        os.symlink(outdir, latest)
    except OSError:
        pass
    write_status()
    print(f"[pg-backup] run_id={run_id} status={status} total_bytes={total}")
    return 0 if status == "ok" else 1


# ------------------------------------------------------------- file backup
def export_meta():
    c = cfg()
    meta = os.path.expanduser(c["meta_dir"])
    os.makedirs(meta, exist_ok=True)
    p = run(["crontab", "-l"])
    with open(os.path.join(meta, "crontab.txt"), "w") as f:
        f.write(p.stdout if p.returncode == 0 else "")
    with open(os.path.join(meta, "backup_sets.json"), "w") as f:
        json.dump(c, f, indent=2)


def restic_backup(repo):
    c = cfg()
    args = ["restic", "-r", repo, "backup", "--json"] + c["file_sets"]
    for ex in c.get("excludes", []):
        args += ["--exclude", ex]
    p = run(args, env_extra=restic_env(), timeout=60 * 60 * 12)
    snap, total = None, None
    for ln in (p.stdout or "").splitlines():
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if obj.get("message_type") == "summary":
            snap = obj.get("snapshot_id")
            total = obj.get("total_bytes_processed")
    return p, snap, total


def cmd_file_backup(args):
    c = cfg()
    export_meta()
    cn = conn(); cur = cn.cursor(); ensure_schema(cur); cn.commit()
    worst = 0
    for label, repo in (("local", c["restic_repo_local"]),
                        ("offsite", c["restic_repo_offsite"])):
        repo = os.path.expanduser(repo)
        cur.execute("INSERT INTO successbrian_os.backup_runs (kind, repo) "
                    "VALUES ('files', %s) RETURNING id", (label,))
        run_id = cur.fetchone()[0]; cn.commit()
        p, snap, total = restic_backup(repo)
        status = "ok" if p.returncode == 0 and snap else "fail"
        if status != "ok":
            worst = 1
        cur.execute("UPDATE successbrian_os.backup_runs SET finished_at=now(),"
                    " status=%s, snapshot_id=%s, bytes=%s, detail=%s "
                    "WHERE id=%s",
                    (status, snap, total, json.dumps(
                        {"repo_label": label,
                         "stderr_tail": (p.stderr or "")[-400:]}), run_id))
        cn.commit()
        print(f"[file-backup] {label} run_id={run_id} status={status} "
              f"snapshot={snap} bytes={total}", flush=True)
    cn.close()
    write_status()
    return worst


def cmd_check(args):
    c = cfg()
    # Rotating subset: ISO week picks one tenth of the repo data,
    # so every pack is read roughly every 10 weeks.
    subset = args.subset or f"{(datetime.now().isocalendar()[1] % 10) + 1}/10"
    cn = conn(); cur = cn.cursor(); ensure_schema(cur); cn.commit()
    worst = 0
    for label, repo in (("local", c["restic_repo_local"]),
                        ("offsite", c["restic_repo_offsite"])):
        repo = os.path.expanduser(repo)
        cur.execute("INSERT INTO successbrian_os.backup_runs (kind, repo) "
                    "VALUES ('check', %s) RETURNING id", (label,))
        run_id = cur.fetchone()[0]; cn.commit()
        p = run(["restic", "-r", repo, "check",
                 f"--read-data-subset={subset}"],
                env_extra=restic_env(), timeout=60 * 60 * 6)
        status = "ok" if p.returncode == 0 else "fail"
        if status != "ok":
            worst = 1
        cur.execute("UPDATE successbrian_os.backup_runs SET finished_at=now(),"
                    " status=%s, detail=%s WHERE id=%s",
                    (status, json.dumps(
                        {"subset": subset,
                         "tail": ((p.stdout or "") + (p.stderr or ""))[-400:]}),
                     run_id))
        cn.commit()
        print(f"[check] {label} run_id={run_id} status={status} "
              f"subset={subset}", flush=True)
    cn.close()
    write_status()
    return worst


# ------------------------------------------------------------------- drill
def psql(db, sql):
    return run(["psql", "-h", PG_HOST, "-U", PG_USER, "-d", db,
                "-t", "-A", "-c", sql])


def count_in(db, schema_table):
    p = psql(db, f"SELECT count(*) FROM {schema_table}")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:300])
    return int(p.stdout.strip())


def cmd_drill(args):
    c = cfg()
    checks, notes = {}, []
    latest = os.path.join(os.path.expanduser(c["pg_dump_root"]), "latest")
    eco_dump = os.path.join(latest, "ecosystem_central.dump")
    pu_dump = os.path.join(latest, "people_unified.dumpdir")
    for db in (DRILL_DB_ECO, DRILL_DB_PU):
        run(["dropdb", "-h", PG_HOST, "-U", PG_USER, "--if-exists", db])
        p = run(["createdb", "-h", PG_HOST, "-U", PG_USER, db])
        if p.returncode != 0:
            raise RuntimeError(f"createdb {db} failed: {p.stderr[:200]}")
    p = run(["pg_restore", "-h", PG_HOST, "-U", PG_USER, "-d", DRILL_DB_ECO,
             "--no-owner", eco_dump], timeout=60 * 60 * 2)
    checks["pg_restore_ecosystem_exit"] = p.returncode
    prod_events = count_in("ecosystem_central", "life_calendar.events")
    drill_events = count_in(DRILL_DB_ECO, "life_calendar.events")
    checks["life_calendar_events_prod"] = prod_events
    checks["life_calendar_events_drill"] = drill_events
    checks["life_calendar_events_match"] = (prod_events == drill_events)
    # Selective pg_restore does not emit CREATE SCHEMA; pre-create it.
    psql(DRILL_DB_PU, "CREATE SCHEMA IF NOT EXISTS people")
    p = run(["pg_restore", "-h", PG_HOST, "-U", PG_USER, "-d", DRILL_DB_PU,
             "--no-owner", "-n", "people", "-t", "companies", pu_dump],
            timeout=60 * 60 * 2)
    checks["pg_restore_companies_exit"] = p.returncode
    prod_comp = count_in("people_unified", "people.companies")
    drill_comp = count_in(DRILL_DB_PU, "people.companies")
    checks["people_companies_prod"] = prod_comp
    checks["people_companies_drill"] = drill_comp
    checks["people_companies_match"] = (prod_comp == drill_comp)
    notes.append("people_unified restored selectively (people.companies) "
                 "from the full directory-format dump; full-DB restore "
                 "not claimed.")
    scratch = os.path.expanduser("~/backups/drill-restore")
    run(["rm", "-rf", scratch])
    os.makedirs(scratch, exist_ok=True)
    repo = os.path.expanduser(c["restic_repo_local"])
    p = run(["restic", "-r", repo, "restore", "latest", "--target", scratch,
             "--include", "/home/successbrian/mail-archive/brian.homebiz/cur",
             "--include", "/home/successbrian/successbrian-os/AGENTS.md"],
            env_extra=restic_env(), timeout=60 * 60 * 2)
    checks["file_restore_exit"] = p.returncode
    cur_dir = os.path.join(
        scratch, "home/successbrian/mail-archive/brian.homebiz/cur")
    restored = []
    if os.path.isdir(cur_dir):
        restored = sorted(os.listdir(cur_dir))
    checks["mail_files_restored_in_cur"] = len(restored)
    sample = restored[:25]
    ok = True
    src_root = "/home/successbrian/mail-archive/brian.homebiz/cur"
    for fn in sample:
        a = sha256_file(os.path.join(src_root, fn))
        b = sha256_file(os.path.join(cur_dir, fn))
        if a != b:
            ok = False
            checks.setdefault("checksum_mismatch", []).append(fn)
    checks["mail_sample_checksums_match"] = ok and len(sample) == 25
    checks["mail_sample_n"] = len(sample)
    prod_cur = len(os.listdir(src_root))
    checks["mail_cur_prod_count"] = prod_cur
    snap_p = run(["restic", "-r", repo, "snapshots", "--json", "--last", "1"],
                 env_extra=restic_env())
    snap_id = None
    try:
        snap_id = json.loads(snap_p.stdout)[0]["id"][:12]
    except Exception:
        pass
    verdict = "PASS" if all([
        checks["life_calendar_events_match"],
        checks["people_companies_match"],
        checks["mail_sample_checksums_match"],
        checks["file_restore_exit"] == 0,
        checks["pg_restore_ecosystem_exit"] == 0,
    ]) else "FAIL"
    cn = conn(); cur = cn.cursor(); ensure_schema(cur)
    cur.execute("SELECT max(finished_at) FROM successbrian_os.backup_runs "
                "WHERE kind='pg' AND status='ok'")
    pg_at = cur.fetchone()[0]
    cur.execute("INSERT INTO successbrian_os.backup_drills "
                "(pg_backup_at, file_snapshot_id, checks, verdict, notes) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (pg_at, snap_id, json.dumps(checks), verdict,
                 " ".join(notes)))
    drill_id = cur.fetchone()[0]; cn.commit(); cn.close()
    write_status()
    print(json.dumps({"drill_id": drill_id, "verdict": verdict,
                      "checks": checks}, indent=2, default=str))
    return 0 if verdict == "PASS" else 1


# ------------------------------------------------------------------ status
def latest_row(cur, kind, repo=None):
    q = ("SELECT finished_at, status, snapshot_id FROM "
         "successbrian_os.backup_runs WHERE kind=%s AND status='ok'")
    params = [kind]
    if repo:
        q += " AND repo=%s"; params.append(repo)
    q += " ORDER BY finished_at DESC NULLS LAST LIMIT 1"
    cur.execute(q, params)
    r = cur.fetchone()
    if not r:
        return None
    return {"at": str(r[0]), "status": r[1], "snapshot_id": r[2]}


def write_status():
    try:
        cn = conn(); cur = cn.cursor(); ensure_schema(cur); cn.commit()
        st = {
            "generated_at": datetime.now().isoformat(),
            "last_file_backup_local": latest_row(cur, "files", "local"),
            "last_file_backup_offsite": latest_row(cur, "files", "offsite"),
            "last_pg_backup": latest_row(cur, "pg"),
            "last_check": latest_row(cur, "check"),
        }
        cur.execute("SELECT drilled_at, verdict FROM "
                    "successbrian_os.backup_drills ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        st["last_drill"] = ({"at": str(r[0]), "verdict": r[1]} if r
                            else None)
        cn.close()
        os.makedirs(os.path.dirname(STATE_JSON), exist_ok=True)
        with open(STATE_JSON, "w") as f:
            json.dump(st, f, indent=2)
        return st
    except Exception as e:
        print(f"write_status unavailable: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None


def cmd_status(args):
    st = write_status()
    print(json.dumps(st, indent=2, default=str))
    return 0 if st else 1


def cmd_nightly(args):
    rc = cmd_pg_backup(args)
    rc2 = cmd_file_backup(args)
    return rc or rc2


def cmd_selftest(args):
    fails = []
    c = cfg()
    for path in c["file_sets"]:
        if not os.path.exists(os.path.expanduser(path)):
            fails.append(f"file set path missing: {path}")
    for tool in ("restic", "pg_dump", "pg_restore", "psql"):
        if run(["which", tool]).returncode != 0:
            fails.append(f"tool missing: {tool}")
    if not os.path.exists(PW_FILE):
        fails.append("restic password file missing (location only)")
    else:
        if oct(os.stat(PW_FILE).st_mode)[-3:] != "600":
            fails.append("restic password file mode is not 600")
    dbs = []
    try:
        dbs = list_databases()
        if "ecosystem_central" not in dbs or "people_unified" not in dbs:
            fails.append("expected databases not enumerated")
    except Exception as e:
        fails.append(f"db enumeration: {e}")
    try:
        cn = conn(); cur = cn.cursor(); ensure_schema(cur); cn.commit()
        cn.close()
    except Exception as e:
        fails.append(f"state tables: {e}")
    if fails:
        print("SELFTEST FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST PASS ({len(c['file_sets'])} file sets, "
          f"{len(dbs)} databases enumerated)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pg-backup")
    sub.add_parser("file-backup")
    sub.add_parser("drill")
    sub.add_parser("status")
    sub.add_parser("nightly")
    sub.add_parser("selftest")
    chk = sub.add_parser("check")
    chk.add_argument("--subset", default=None)
    args = ap.parse_args(argv)
    fn = {"pg-backup": cmd_pg_backup, "file-backup": cmd_file_backup,
          "check": cmd_check, "drill": cmd_drill, "status": cmd_status,
          "nightly": cmd_nightly, "selftest": cmd_selftest}[args.cmd]
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
