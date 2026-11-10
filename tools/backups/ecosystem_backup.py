#!/usr/bin/env python3
"""ecosystem_backup.py — Offsite artifact backups for Brian's ecosystem.

PURPOSE: One dated, self-describing artifact set per run:
           * pg_dump of every production database on the local cluster
             (custom format, compressed; people_unified in parallel
             directory format, same as the nightly system)
           * `git bundle --all` of every core git repository
           * tarballs of the AnythingLLM knowledge stores (R32 home)
           * manifest.json — every artifact with size + sha256 + the
             inventory it came from
         The set is staged locally, then shipped to the
         successbrianvps.com VPS (srv1485029, root@100.118.196.66)
         under /root/sbos-ecosystem-backups/<date>/ — OFF the alpha
         box, per Brian's VPS-survives-Chaska doctrine.

WHY THIS EXISTS ALONGSIDE tools/backups/sbos_backup.py:
         sbos_backup.py (2026-10-27 Tier-1) runs nightly and is
         HEALTHY locally: pg dumps + restic local snapshots succeed
         every night. But its offsite leg has been dead since the VPS
         disk filled: every offsite run row sits in 'running' forever
         and last_file_backup_offsite is null. Every backup in the
         ecosystem therefore lives on the SAME box it protects.
         This tool is the missing offsite artifact layer: portable,
         hash-manifested sets that do not depend on restic, plus a
         restore test on EVERY run (a backup that has never been
         restored is a hope, not a backup). Work order: Intel Bridge
         capture #1148 (catch-up agenda #1145 item 5).

RETENTION (MACHINERY DEFAULT — set by the builder 2026-11-09, NOT a
         Brian ruling; Brian overrides by saying so):
         keep the newest 7 daily sets plus the newest 4 Sunday
         (weekly-anchor) sets, in each holding location. Pruning only
         ever touches dated directories THIS tool created under its
         own roots (local staging root / remote VPS root).

KNOWN GAPS, stated plainly:
         * The home repository (~/.git, 44 GB — it tracks dealsdesk
           and much of $HOME) is NOT bundled: a bundle would be ~44 GB.
           It is covered only by sbos_backup's restic file snapshots.
         * git bundles capture COMMITTED history only. Uncommitted
           working-tree changes are counted per repo in the manifest
           (dirty_files) so the exposure is visible, not hidden; the
           restic file backup covers working trees for the main repos.
         * drill_restore_* databases are restore scratch (recreated
           by drills) and the `postgres` maintenance DB is excluded,
           mirroring sbos_backup's enumeration.
         * PITR/WAL archiving remains off (needs-Brian restart
           window) — see sbos_backup.py.

STATE:   ~/backups/ecosystem_backup_status.json (outside the repo so
         nightly runs never dirty the working tree) + one manifest
         per run dir. Restore receipts are also inserted into
         successbrian_os.backup_drills (additive rows only).

CALLED BY: user cron daily 04:30 CT (flock'd) and operators.
         Sends nothing, publishes nothing, deletes nothing outside
         its own dated backup directories.
"""
import argparse
import calendar as _stdlib_calendar  # noqa: F401  pin BEFORE path insert:
# ~/successbrian-os/tools contains a calendar/ directory that shadows
# the stdlib calendar module for lazily-imported users (strptime) once
# tools/ is on sys.path — that shadow crashed the first run's prune.
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
SBOS_TOOLS = os.path.dirname(HERE)  # ~/successbrian-os/tools
sys.path.insert(0, SBOS_TOOLS)
try:
    import sbos_common as C  # noqa: E402  (shared helpers, defined once)
except Exception:  # pragma: no cover — fall back to plain prints
    C = None


def log(msg):
    if C is not None:
        C.log(msg)
    else:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}",
              flush=True)


CT = ZoneInfo("America/Chicago")
HOME = os.path.expanduser("~")
STAGING_ROOT = os.path.join(HOME, "backups", "ecosystem-offsite-staging")
STATE_JSON = os.path.join(HOME, "backups", "ecosystem_backup_status.json")
VPS_HOST = "root@100.118.196.66"
VPS_ROOT = "/root/sbos-ecosystem-backups"
PG_HOST, PG_USER = "localhost", "postgres"
RESTORE_SCRATCH_DB = "ecosystem_backup_restore_test"

# Core git repositories (discovered on alpha 2026-11-09). Third-party
# clone farms (forex_run6/clones, options_scout clones, ~/repos) are
# re-clonable and deliberately excluded. dealsdesk has no .git of its
# own — it is tracked by the home repository (see KNOWN GAPS).
CORE_REPOS = [
    "successbrian-os",
    "campaignsdesk",
    "tradesdesk",
    "colibri",
    "vera-repo",
    "anything-llm",
    "inbox-zero",
    "altair-brain-inbox",
    "second-brain-for-agents",
    "ceo-agent",
    "mantis-coding-harness",
    "MT5-SMC-trading-bot",
]
EXCLUDED_DBS = {"postgres", "drill_restore_ecosystem",
                "drill_restore_people"}
ALLM_DIRS = [
    ("anythingllm-storage", os.path.join(HOME, "anything-llm", "storage")),
    ("anythingllm-server-storage",
     os.path.join(HOME, "anything-llm", "server", "storage")),
]
KEEP_DAILY = 7    # MACHINERY DEFAULT (see header)
KEEP_WEEKLY = 4   # MACHINERY DEFAULT (see header)


def run(cmd, timeout=None, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, capture_output=True, text=True,
                          env=env, timeout=timeout)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_size(path):
    total = 0
    for root, _, fns in os.walk(path):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


def parse_date_prefix(name):
    """'YYYY-MM-DD...' -> date, parsed manually (never strptime: see
    the calendar-shadowing note at the imports)."""
    try:
        y, m, d = name[:10].split("-")
        from datetime import date
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def dir_sha256(path):
    """Stable digest over a directory-format dump: sha256 of the
    sorted (relpath, size, sha256) lines."""
    lines = []
    for root, _, fns in os.walk(path):
        for fn in sorted(fns):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, path)
            lines.append(f"{rel} {os.path.getsize(p)} {sha256_file(p)}")
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def load_state():
    try:
        with open(STATE_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE_JSON), exist_ok=True)
    tmp = STATE_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE_JSON)


# ---------------------------------------------------------------- inventory
def list_databases():
    p = run(["psql", "-h", PG_HOST, "-U", PG_USER, "-d", "postgres",
             "-t", "-A", "-c",
             "SELECT datname FROM pg_database WHERE NOT datistemplate "
             "ORDER BY 1"])
    if p.returncode != 0:
        raise RuntimeError("database enumeration failed: "
                           + p.stderr[:300])
    all_dbs = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    return [d for d in all_dbs if d not in EXCLUDED_DBS], all_dbs


def db_sizes(dbs):
    out = {}
    for db in dbs:
        p = run(["psql", "-h", PG_HOST, "-U", PG_USER, "-d", "postgres",
                 "-t", "-A", "-c",
                 f"SELECT pg_database_size('{db}')"])
        try:
            out[db] = int(p.stdout.strip())
        except Exception:
            out[db] = None
    return out


# ------------------------------------------------------------------- backup
def cmd_run(args):
    started = datetime.now(CT)
    stamp = started.strftime("%Y-%m-%d")
    run_dir = os.path.join(STAGING_ROOT, stamp)
    if os.path.exists(run_dir) and not args.force:
        # Same-day re-run: version the directory rather than clobber.
        run_dir = os.path.join(
            STAGING_ROOT, started.strftime("%Y-%m-%d-%H%M%S"))
    pg_dir = os.path.join(run_dir, "pg")
    git_dir = os.path.join(run_dir, "git")
    files_dir = os.path.join(run_dir, "files")
    for d in (pg_dir, git_dir, files_dir):
        os.makedirs(d, exist_ok=True)

    manifest = {
        "tool": "ecosystem_backup.py",
        "run_started_at": started.isoformat(),
        "host": os.uname().nodename,
        "artifacts": {},
        "failures": [],
    }

    # ---- PostgreSQL -------------------------------------------------
    dbs, all_dbs = list_databases()
    manifest["databases_all"] = all_dbs
    manifest["databases_excluded"] = sorted(EXCLUDED_DBS)
    manifest["databases"] = dbs
    manifest["database_sizes_bytes"] = db_sizes(dbs)
    for db in dbs:
        if db == "people_unified":
            dest = os.path.join(pg_dir, db + ".dumpdir")
            cmd = ["pg_dump", "-h", PG_HOST, "-U", PG_USER, "-Fd",
                   "-j", "3", "-Z", "3", "-f", dest, db]
        else:
            dest = os.path.join(pg_dir, db + ".dump")
            cmd = ["pg_dump", "-h", PG_HOST, "-U", PG_USER, "-Fc",
                   "-Z", "3", "-f", dest, db]
        log(f"[pg] {db} -> {dest}")
        p = run(cmd, timeout=60 * 60 * 6)
        if p.returncode != 0:
            manifest["failures"].append(
                {"kind": "pg", "name": db, "err": p.stderr[-400:]})
            log(f"[pg] FAIL {db}: {p.stderr[-200:]}")
            continue
        if os.path.isdir(dest):
            size, digest = dir_size(dest), dir_sha256(dest)
        else:
            size, digest = os.path.getsize(dest), sha256_file(dest)
        manifest["artifacts"][f"pg/{os.path.basename(dest)}"] = {
            "bytes": size, "sha256": digest}
        log(f"[pg] ok {db} bytes={size}")

    # ---- git bundles -------------------------------------------------
    manifest["repos"] = {}
    for name in CORE_REPOS:
        path = os.path.join(HOME, name)
        if not os.path.isdir(os.path.join(path, ".git")):
            manifest["repos"][name] = {"status": "absent"}
            continue
        head = run(["git", "-C", path, "rev-parse", "HEAD"]).stdout.strip()
        dirty = run(["git", "-C", path, "status", "--porcelain"]).stdout
        dirty_n = len([ln for ln in dirty.splitlines() if ln.strip()])
        dest = os.path.join(git_dir, name + ".bundle")
        p = run(["git", "-C", path, "bundle", "create", dest, "--all"],
                timeout=60 * 30)
        if p.returncode != 0:
            manifest["failures"].append(
                {"kind": "git", "name": name, "err": p.stderr[-400:]})
            manifest["repos"][name] = {"status": "bundle_failed",
                                       "head": head,
                                       "dirty_files": dirty_n}
            log(f"[git] FAIL {name}: {p.stderr[-200:]}")
            continue
        manifest["artifacts"][f"git/{name}.bundle"] = {
            "bytes": os.path.getsize(dest), "sha256": sha256_file(dest)}
        manifest["repos"][name] = {"status": "ok", "head": head,
                                   "dirty_files": dirty_n}
        log(f"[git] ok {name} head={head[:9]} dirty={dirty_n}")
    manifest["repos"]["(home repo ~/.git)"] = {
        "status": "not_bundled",
        "reason": "44 GB repository (tracks dealsdesk + much of $HOME); "
                  "covered by sbos_backup restic file snapshots only"}

    # ---- AnythingLLM knowledge stores --------------------------------
    for label, src in ALLM_DIRS:
        if not os.path.isdir(src):
            manifest["failures"].append(
                {"kind": "files", "name": label, "err": "missing dir"})
            continue
        dest = os.path.join(files_dir, label + ".tar.gz")
        log(f"[files] {label} -> {dest}")
        with tarfile.open(dest, "w:gz", compresslevel=6) as tf:
            tf.add(src, arcname=label)
        manifest["artifacts"][f"files/{label}.tar.gz"] = {
            "bytes": os.path.getsize(dest), "sha256": sha256_file(dest)}
        log(f"[files] ok {label} bytes={os.path.getsize(dest)}")

    total = sum(a["bytes"] for a in manifest["artifacts"].values())
    manifest["total_bytes"] = total
    manifest["run_finished_at"] = datetime.now(CT).isoformat()
    mpath = os.path.join(run_dir, "manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2)

    # ---- offsite ship (VPS), space-checked BEFORE writing ------------
    offsite = ship_to_vps(run_dir, total)
    manifest["offsite"] = offsite
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2)

    # ---- restore test (every run) ------------------------------------
    restore = do_restore_test(run_dir, manifest)
    with open(os.path.join(run_dir, "restore-test.json"), "w") as f:
        json.dump(restore, f, indent=2)

    # ---- retention (own dated dirs only) ------------------------------
    # A prune failure must never eat the state save (first-run lesson,
    # 2026-11-09: a prune crash left a completed run unrecorded).
    try:
        pruned = prune(STAGING_ROOT)
        if offsite.get("status") == "ok":
            prune_remote()
        manifest["pruned_local"] = pruned
    except Exception as e:
        manifest["prune_error"] = f"{type(e).__name__}: {e}"[:300]
        log(f"[prune] ERROR recorded, continuing: {e}")

    ok = not manifest["failures"]
    st = load_state()
    st["last_run"] = {
        "at": datetime.now(CT).isoformat(),
        "status": "ok" if ok else "fail",
        "dir": run_dir,
        "total_bytes": total,
        "artifacts": len(manifest["artifacts"]),
        "failures": manifest["failures"],
        "offsite": offsite,
    }
    st["last_restore"] = restore
    st["retention_policy"] = (f"keep {KEEP_DAILY} daily + {KEEP_WEEKLY} "
                              "weekly (Sunday) sets per location — "
                              "MACHINERY DEFAULT, not a Brian ruling")
    save_state(st)
    log(f"[run] done status={'ok' if ok else 'fail'} total_bytes={total} "
        f"offsite={offsite.get('status')}")
    return 0 if ok else 1


def vps_free_bytes():
    p = run(["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
             VPS_HOST, "df -Pk / | tail -1"], timeout=30)
    if p.returncode != 0:
        return None, (p.stderr or p.stdout)[-300:]
    parts = p.stdout.split()
    try:
        return int(parts[3]) * 1024, ""
    except Exception:
        return None, "unparsable df output: " + p.stdout[:200]


def ship_to_vps(run_dir, total_bytes):
    free, err = vps_free_bytes()
    if free is None:
        return {"status": "unreachable", "detail": err}
    needed = int(total_bytes * 1.15)
    base = os.path.basename(run_dir)
    if free < needed:
        return {"status": "blocked_vps_disk_full",
                "vps_free_bytes": free, "needed_bytes": needed,
                "detail": "VPS root filesystem has less free space "
                          "than the artifact set needs; set held in "
                          "local staging only"}
    remote_dir = f"{VPS_ROOT}/{base}"
    run(["ssh", "-o", "BatchMode=yes", VPS_HOST,
         f"mkdir -p {remote_dir}"], timeout=30)
    p = run(["rsync", "-a", "--timeout=120", "-e",
             "ssh -o BatchMode=yes", run_dir + "/", f"{VPS_HOST}:{remote_dir}/"],
            timeout=60 * 60 * 3)
    if p.returncode != 0:
        return {"status": "rsync_failed", "vps_free_bytes": free,
                "detail": p.stderr[-300:]}
    # Verify: remote manifest hash must match the local one.
    local_hash = sha256_file(os.path.join(run_dir, "manifest.json"))
    p = run(["ssh", "-o", "BatchMode=yes", VPS_HOST,
             f"sha256sum {remote_dir}/manifest.json | cut -d' ' -f1"],
            timeout=30)
    remote_hash = p.stdout.strip()
    if remote_hash != local_hash:
        return {"status": "verify_failed", "vps_free_bytes": free,
                "detail": "remote manifest sha256 mismatch"}
    return {"status": "ok", "remote_dir": remote_dir,
            "vps_free_bytes_before": free, "manifest_sha256": local_hash}


def prune(root):
    """Retention over THIS tool's dated dirs under `root` only."""
    if not os.path.isdir(root):
        return []
    dated = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        d = parse_date_prefix(name)
        if d is None:
            continue
        dated.append((d, name, p))
    dated.sort(reverse=True)
    keep, sundays = set(), 0
    for i, (d, name, p) in enumerate(dated):
        if i < KEEP_DAILY:
            keep.add(name)
        elif d.weekday() == 6 and sundays < KEEP_WEEKLY:
            keep.add(name)
            sundays += 1
    pruned = []
    for d, name, p in dated:
        if name not in keep:
            shutil.rmtree(p)
            pruned.append(name)
    return pruned


def prune_remote():
    p = run(["ssh", "-o", "BatchMode=yes", VPS_HOST,
             f"ls -1 {VPS_ROOT} 2>/dev/null"], timeout=30)
    if p.returncode != 0:
        return
    names = []
    for ln in p.stdout.splitlines():
        ln = ln.strip()
        d = parse_date_prefix(ln)
        if d is None:
            continue
        names.append((d, ln))
    names.sort(reverse=True)
    keep, sundays = set(), 0
    for i, (d, ln) in enumerate(names):
        if i < KEEP_DAILY:
            keep.add(ln)
        elif d.weekday() == 6 and sundays < KEEP_WEEKLY:
            keep.add(ln)
            sundays += 1
    for d, ln in names:
        if ln not in keep:
            run(["ssh", "-o", "BatchMode=yes", VPS_HOST,
                 f"rm -rf {VPS_ROOT}/{ln}"], timeout=120)


# -------------------------------------------------------------- restore test
def do_restore_test(run_dir, manifest):
    res = {"at": datetime.now(CT).isoformat(), "checks": {}}
    # --- one database: try single-file dumps smallest-first until one
    # restores >0 tables. (First-run lesson, 2026-11-09: the smallest
    # dump, email_analytics, is a genuinely empty database — a 0-table
    # restore proved nothing and the FAIL was the selector's fault.)
    pg_artifacts = {k: v for k, v in manifest["artifacts"].items()
                    if k.startswith("pg/") and k.endswith(".dump")}
    db_name = None
    attempts = []
    for db_rel in sorted(pg_artifacts,
                         key=lambda k: pg_artifacts[k]["bytes"])[:5]:
        cand = os.path.basename(db_rel)[:-len(".dump")]
        dump_path = os.path.join(run_dir, db_rel)
        run(["dropdb", "-h", PG_HOST, "-U", PG_USER, "--if-exists",
             RESTORE_SCRATCH_DB])
        p = run(["createdb", "-h", PG_HOST, "-U", PG_USER,
                 RESTORE_SCRATCH_DB])
        if p.returncode != 0:
            attempts.append({"db": cand, "createdb_exit": p.returncode})
            continue
        p = run(["pg_restore", "-h", PG_HOST, "-U", PG_USER,
                 "-d", RESTORE_SCRATCH_DB, "--no-owner", dump_path],
                timeout=60 * 30)
        q = run(["psql", "-h", PG_HOST, "-U", PG_USER, "-d",
                 RESTORE_SCRATCH_DB, "-t", "-A", "-c",
                 "SELECT count(*) FROM information_schema.tables "
                 "WHERE table_schema NOT IN ('pg_catalog',"
                 "'information_schema')"])
        try:
            n_tables = int(q.stdout.strip())
        except Exception:
            n_tables = None
        attempts.append({"db": cand, "pg_restore_exit": p.returncode,
                         "restored_tables": n_tables})
        run(["dropdb", "-h", PG_HOST, "-U", PG_USER, "--if-exists",
             RESTORE_SCRATCH_DB])
        if p.returncode == 0 and (n_tables or 0) > 0:
            db_name = cand
            res["checks"]["pg_restore_exit"] = p.returncode
            res["checks"]["restored_tables"] = n_tables
            res["checks"]["restored_db"] = cand
            break
    res["checks"]["db_attempts"] = attempts
    if db_name is None and attempts:
        res["checks"]["pg_restore_exit"] = attempts[-1].get(
            "pg_restore_exit")
        res["checks"]["restored_tables"] = attempts[-1].get(
            "restored_tables")
        res["checks"]["restored_db"] = attempts[-1].get("db")
    # --- one git bundle: tradesdesk (small, core)
    bundle = os.path.join(run_dir, "git", "tradesdesk.bundle")
    src_head = run(["git", "-C", os.path.join(HOME, "tradesdesk"),
                    "rev-parse", "HEAD"]).stdout.strip()
    if os.path.exists(bundle) and src_head:
        scratch = tempfile.mkdtemp(prefix="eco-backup-restore-")
        try:
            p = run(["git", "clone", "-q", bundle,
                     os.path.join(scratch, "clone")], timeout=120)
            res["checks"]["git_clone_exit"] = p.returncode
            clone_head = run(["git", "-C", os.path.join(scratch, "clone"),
                              "rev-parse", "HEAD"]).stdout.strip()
            res["checks"]["bundle_head"] = clone_head
            res["checks"]["source_head"] = src_head
            res["checks"]["heads_match"] = (clone_head == src_head)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    ok = (res["checks"].get("pg_restore_exit") == 0
          and (res["checks"].get("restored_tables") or 0) > 0
          and res["checks"].get("heads_match") is True)
    res["verdict"] = "PASS" if ok else "FAIL"
    # Additive receipt in the shared drills table (best-effort).
    try:
        if C is not None:
            C.pg_exec(
                "INSERT INTO successbrian_os.backup_drills "
                "(checks, verdict, notes) VALUES (%s::jsonb, %s, %s)",
                (json.dumps(res["checks"]), res["verdict"],
                 "ecosystem_backup.py per-run restore test: "
                 f"{db_name} dump -> scratch DB; tradesdesk bundle "
                 "-> scratch clone"))
            res["drill_row_written"] = True
    except Exception as e:
        res["drill_row_written"] = False
        res["drill_row_error"] = f"{type(e).__name__}: {e}"[:200]
    log(f"[restore-test] verdict={res['verdict']} checks={res['checks']}")
    return res


# ------------------------------------------------------------------ QA cmds
def _age_hours(iso):
    try:
        return (datetime.now(CT)
                - datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:
        return None


def qa_freshness():
    st = load_state()
    lr = st.get("last_run") or {}
    age = _age_hours(lr.get("at", ""))
    if lr.get("status") != "ok" or age is None or age >= 26:
        print(f"qa-fail: last ecosystem backup run status="
              f"{lr.get('status')} age_h={age}")
        return 1
    print("qa-ok")
    return 0


def qa_manifest():
    st = load_state()
    lr = st.get("last_run") or {}
    run_dir = lr.get("dir", "")
    mpath = os.path.join(run_dir, "manifest.json")
    if not run_dir or not os.path.exists(mpath):
        print("qa-fail: no manifest for latest run")
        return 1
    with open(mpath) as f:
        m = json.load(f)
    dbs, _ = list_databases()
    for db in dbs:
        key_file = f"pg/{db}.dump"
        key_dir = f"pg/{db}.dumpdir"
        if key_file not in m["artifacts"] and key_dir not in m["artifacts"]:
            print(f"qa-fail: manifest missing artifact for db {db}")
            return 1
    for name in CORE_REPOS:
        if m.get("repos", {}).get(name, {}).get("status") not in (
                "ok", "absent"):
            print(f"qa-fail: repo {name} not accounted in manifest")
            return 1
    for rel, a in m["artifacts"].items():
        p = os.path.join(run_dir, rel)
        if not os.path.exists(p):
            print(f"qa-fail: artifact file missing: {rel}")
            return 1
        actual = dir_size(p) if os.path.isdir(p) else os.path.getsize(p)
        if actual != a["bytes"]:
            print(f"qa-fail: size mismatch {rel}: {actual} != {a['bytes']}")
            return 1
    print("qa-ok")
    return 0


def qa_restore():
    st = load_state()
    r = st.get("last_restore") or {}
    age = _age_hours(r.get("at", ""))
    if r.get("verdict") != "PASS" or age is None or age >= 24 * 8:
        print(f"qa-fail: last restore verdict={r.get('verdict')} "
              f"age_h={age}")
        return 1
    print("qa-ok")
    return 0


def cmd_status(args):
    st = load_state()
    print(json.dumps(st, indent=2))
    return 0


def cmd_selftest(args):
    fails = []
    for tool in ("pg_dump", "pg_restore", "git", "tar", "ssh", "rsync"):
        if shutil.which(tool) is None:
            fails.append(f"missing tool: {tool}")
    try:
        list_databases()
    except Exception as e:
        fails.append(f"db enumeration: {e}")
    free, err = vps_free_bytes()
    print(f"vps_free_bytes={free} probe_err={err!r}")
    os.makedirs(STAGING_ROOT, exist_ok=True)
    if fails:
        print("SELFTEST FAIL: " + "; ".join(fails))
        return 1
    print("SELFTEST OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--force", action="store_true",
                    help="allow writing into an existing dated dir name")
    sub.add_parser("restore-test")
    sub.add_parser("qa-freshness")
    sub.add_parser("qa-manifest")
    sub.add_parser("qa-restore")
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = ap.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "restore-test":
        st = load_state()
        run_dir = (st.get("last_run") or {}).get("dir", "")
        if not run_dir or not os.path.exists(
                os.path.join(run_dir, "manifest.json")):
            # Discover the newest staged run from its own manifest
            # (e.g. state lost to a bookkeeping crash after the
            # artifacts completed — the manifest is the run's record).
            cands = []
            if os.path.isdir(STAGING_ROOT):
                for name in os.listdir(STAGING_ROOT):
                    mp = os.path.join(STAGING_ROOT, name,
                                      "manifest.json")
                    if os.path.exists(mp):
                        cands.append((os.path.getmtime(mp),
                                      os.path.join(STAGING_ROOT, name)))
            if not cands:
                print("no staged run with a manifest found")
                return 1
            run_dir = sorted(cands)[-1][1]
        with open(os.path.join(run_dir, "manifest.json")) as f:
            m = json.load(f)
        r = do_restore_test(run_dir, m)
        st["last_restore"] = r
        if not st.get("last_run"):
            st["last_run"] = {
                "at": m.get("run_finished_at"),
                "status": "ok" if not m.get("failures") else "fail",
                "dir": run_dir,
                "total_bytes": m.get("total_bytes"),
                "artifacts": len(m.get("artifacts", {})),
                "failures": m.get("failures"),
                "offsite": m.get("offsite"),
                "backfilled_from_manifest": True,
            }
        save_state(st)
        return 0 if r["verdict"] == "PASS" else 1
    if args.cmd == "qa-freshness":
        return qa_freshness()
    if args.cmd == "qa-manifest":
        return qa_manifest()
    if args.cmd == "qa-restore":
        return qa_restore()
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
