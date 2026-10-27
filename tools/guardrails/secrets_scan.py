#!/usr/bin/env python3
"""secrets_scan — TruffleHog verified scan, SANITIZED inventory.

Streams TruffleHog JSON and discards Raw/RawV2/Redacted values in
memory. Only repo/file/line, credential TYPE, verified-live flag and
first-seen ever reach disk or PG. Never prints a secret value.
CLI + selftest style, fleet pattern.
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone

BIN = os.path.expanduser("~/.local/bin/trufflehog")
REPOS = [
    ("successbrian-os", os.path.expanduser("~/successbrian-os")),
    ("campaignsdesk", os.path.expanduser("~/campaignsdesk")),
    ("tradesdesk", os.path.expanduser("~/tradesdesk")),
    ("vera-repo", os.path.expanduser("~/vera-repo")),
    ("twenty", os.path.expanduser("~/twenty")),
    ("dealsdesk", "/home/dealsdesk"),
]
FS_TARGETS = [
    ("crontab-stage", "/tmp/secrets-fs-stage"),
    ("systemd-user", os.path.expanduser("~/.config/systemd/user")),
    ("home-scripts", os.path.expanduser("~/scripts")),
    ("home-bin", os.path.expanduser("~/bin")),
    ("cron.d", "/etc/cron.d"),
]

def sanitize(rec, source_kind, repo_label):
    """Keep ONLY safe fields. Raw values are never copied out."""
    meta = (rec.get("SourceMetadata") or {}).get("Data") or {}
    git = meta.get("Git") or {}
    fs = meta.get("Filesystem") or {}
    return {
        "source_kind": source_kind,
        "repo": repo_label,
        "file_path": git.get("file") or fs.get("file") or "",
        "line_no": git.get("line") or fs.get("line"),
        "commit_hash": git.get("commit") or None,
        "credential_type": rec.get("DetectorName") or "unknown",
        "verified_live": bool(rec.get("Verified")),
        "first_seen": git.get("timestamp") or None,
        "hash_prefix": None,  # trufflehog emits no hash; never derive/store value material
    }

def run_trufflehog(args, source_kind, repo_label, out, timeout=1800):
    cmd = [BIN] + args + ["--json", "--no-update", "--concurrency", "4"]
    n = 0
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            out.write(json.dumps(sanitize(rec, source_kind, repo_label)) + "\n")
            n += 1
        p.wait(timeout=timeout)
    except Exception as e:
        print(f"WARN scan {repo_label}: {type(e).__name__}", file=sys.stderr)
    return n

def cmd_run(a):
    os.makedirs("/tmp/secrets-fs-stage", exist_ok=True)
    ct = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    with open("/tmp/secrets-fs-stage/crontab.txt", "w") as f:
        f.write(ct.stdout or "")
    total = 0
    with open(a.out, "w") as out:
        for name, path in REPOS:
            if a.repos and name not in a.repos.split(","):
                continue
            if not os.path.isdir(os.path.join(path, ".git")):
                print(f"SKIP {name}: no .git")
                continue
            n = run_trufflehog(["git", "file://" + path], "git", name, out)
            print(f"REPO {name}: {n} findings")
            total += n
        if not a.no_fs:
            for label, path in FS_TARGETS:
                if not os.path.isdir(path):
                    continue
                n = run_trufflehog(["filesystem", path], "filesystem", label, out)
                print(f"FS {label}: {n} findings")
                total += n
    print(f"TOTAL {total}")

def cmd_load(a):
    import psycopg2
    run_id = a.run or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    rows = [json.loads(l) for l in open(a.jsonl) if l.strip()]
    conn = psycopg2.connect(dbname="ecosystem_central", host="localhost")
    cur = conn.cursor()
    ins = 0
    for r in rows:
        cur.execute(
            """INSERT INTO successbrian_os.secret_findings
                 (scan_run, source_kind, repo, file_path, line_no, commit_hash,
                  credential_type, finding_type, verified_live, hash_prefix,
                  first_seen, source, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'trufflehog-verified','new')
               ON CONFLICT DO NOTHING""",
            (run_id, r["source_kind"], r["repo"], r["file_path"], r["line_no"],
             r["commit_hash"], r["credential_type"], r["credential_type"],
             r["verified_live"], r["hash_prefix"], r["first_seen"]))
        ins += cur.rowcount
    conn.commit()
    cur.execute("SELECT credential_type, verified_live, count(*) FROM successbrian_os.secret_findings GROUP BY 1,2 ORDER BY 3 DESC")
    print("BY_TYPE_VERIFIED:")
    for t, v, c in cur.fetchall():
        print(f"  {t} verified={v} count={c}")
    cur.execute("SELECT count(*), count(*) FILTER (WHERE verified_live) FROM successbrian_os.secret_findings")
    tot, live = cur.fetchone()
    print(f"PG_TOTAL {tot} PG_LIVE {live} INSERTED {ins} RUN {run_id}")
    conn.close()

def cmd_selftest(a):
    fake = {"DetectorName": "FakeType", "Verified": True, "Raw": "SHOULD_NEVER_APPEAR",
            "RawV2": "ALSO_NEVER", "SourceMetadata": {"Data": {"Git": {"file": "x.py", "line": 7, "commit": "abc", "timestamp": "2026-01-01T00:00:00Z"}}}}
    s = sanitize(fake, "git", "selftest")
    blob = json.dumps(s)
    assert "SHOULD_NEVER_APPEAR" not in blob and "ALSO_NEVER" not in blob, "LEAK"
    assert s["credential_type"] == "FakeType" and s["verified_live"] and s["line_no"] == 7
    print("selftest green")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--out", required=True); r.add_argument("--repos", default=""); r.add_argument("--no-fs", action="store_true"); r.set_defaults(fn=cmd_run)
    l = sub.add_parser("load"); l.add_argument("jsonl"); l.add_argument("--run", default=""); l.set_defaults(fn=cmd_load)
    s = sub.add_parser("selftest"); s.set_defaults(fn=cmd_selftest)
    a = ap.parse_args(); a.fn(a)
