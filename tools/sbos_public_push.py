#!/usr/bin/env python3
"""sbos_public_push.py — the daily public push, living in SBOS.

Brian's standing rule (2026-11-16): SuccessBrian OS pushes to its
public GitHub daily, scan-guarded. The job ran as a cloud-agent
cron until 2026-11-17; Brian's placement ruling (rulings census
row 22: write into the ecosystem, not into Muse) moved it here.

What it does, deterministically:
1. fetch; count unpushed commits on main. Zero -> heartbeat, exit.
2. Scan the unpushed diff (exactly what would be published) for
   credential shapes: key assignments with long quoted values,
   os.environ.get(...) with a quoted FALLBACK (the 2026-11-16
   defect), eBay PRD- app ids, PGPASSWORD, GitHub tokens, private
   key headers. Fixture-looking lines (FAKE / example /
   placeholder / your-) are ignored. Also verifies .env is not
   tracked and is git-ignored.
3. Any hit: DO NOT PUSH. File an Intel Bridge capture naming the
   file and the KIND of credential (never the value), heartbeat
   'held'. A held push is a report, never a repair job: no code,
   .env, or history is edited here, and force-push never happens.
4. Clean: push origin main, verify origin/main == HEAD,
   heartbeat 'ok'.

Modes: run | dry-run | selftest.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

REPO = os.path.expanduser("~/successbrian-os")
WORKER = "sbos-public-push"

PATTERNS = [
    ("credential assignment",
     re.compile(r"(?i)\b(password|passwd|api_key|client_secret|"
                r"app_secret)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]")),
    ("client_id assignment",
     re.compile(r"(?i)\bclient_id\b\s*[:=]\s*['\"][^'\"]{16,}['\"]")),
    ("token assignment",
     re.compile(r"(?i)\b\w*token\w*\b\s*[:=]\s*['\"][^'\"]{20,}['\"]")),
    ("env fallback value",
     re.compile(r"os\.environ\.get\(\s*['\"][^'\"]+['\"]\s*,"
                r"\s*['\"][^'\"]{8,}['\"]")),
    ("PGPASSWORD assignment",
     re.compile(r"PGPASSWORD\s*=\s*\S+")),
    ("eBay PRD app id",
     re.compile(r"PRD-[A-Za-z0-9]{4,}-[A-Za-z0-9-]{6,}")),
    ("GitHub token",
     re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("private key header",
     re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY")),
]
FIXTURE_HINTS = ("fake", "example", "placeholder", "your-", "your_",
                 "xxxx", "test-only", "dummy")


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args],
                          capture_output=True, text=True, timeout=300)


def scan_diff(diff_text):
    """Return hits as (file, kind) — never values."""
    hits = []
    current_file = "?"
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        low = body.lower()
        if any(h in low for h in FIXTURE_HINTS):
            continue
        for kind, rx in PATTERNS:
            if rx.search(body):
                hits.append((current_file, kind))
                break
    return hits


def heartbeat(status, summary, error=None):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.worker_heartbeats "
        "(worker_name, last_heartbeat, last_status, last_error, "
        "is_important, last_run_output) VALUES "
        "(%s, now(), %s, %s, true, %s) "
        "ON CONFLICT (worker_name) DO UPDATE SET "
        "last_heartbeat = now(), last_status = EXCLUDED.last_status, "
        "last_error = EXCLUDED.last_error, "
        "last_run_output = EXCLUDED.last_run_output",
        (WORKER, status, error, summary))


def capture(title, body):
    sbos_common.pg_exec(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s)",
        (title, body,
         "Filed by tools/sbos_public_push.py on alpha (the daily "
         "public push, moved into SBOS 2026-11-17). Repairs are "
         "Brian's call; the push job never edits code or history."))


def run(dry=False):
    git("fetch", "origin")
    n = int(git("rev-list", "--count", "origin/main..HEAD")
            .stdout.strip() or 0)
    if n == 0:
        print("public push: nothing unpushed")
        if not dry:
            heartbeat("ok", "0 unpushed commits; public copy current")
        return 0
    # .env hygiene: must be ignored and untracked.
    tracked = git("ls-files", "--error-unmatch", ".env").returncode == 0
    ignored = git("check-ignore", ".env").returncode == 0
    hits = []
    if tracked or not ignored:
        hits.append((".env", "env file hygiene (tracked or not ignored)"))
    diff = git("diff", "origin/main..HEAD").stdout
    hits.extend(scan_diff(diff))
    if hits:
        lines = [f"{f}: {k}" for f, k in hits]
        print(f"public push HELD: {len(hits)} scan hit(s)")
        for ln in lines:
            print("  " + ln)
        if not dry:
            heartbeat("held",
                      f"push held: {len(hits)} scan hit(s) in "
                      f"{n} unpushed commit(s)",
                      "; ".join(lines)[:400])
            capture("PUBLIC PUSH HELD — credential pattern found",
                    "The daily public push was held by the scan.\n"
                    + "\n".join(lines)
                    + "\nNo values are shown. The push job does not "
                      "repair; Brian decides.")
        return 0
    if dry:
        print(f"public push dry-run: {n} unpushed, scan clean")
        return 0
    push = git("push", "origin", "main")
    if push.returncode != 0:
        err = (push.stderr or push.stdout).strip().splitlines()
        cause = err[-1][:200] if err else "unknown push failure"
        print(f"public push FAILED: {cause}")
        heartbeat("error", f"push failed for {n} commit(s)", cause)
        capture("PUBLIC PUSH FAILED",
                f"git push failed: {cause}\nThe job does not retry "
                "or work around blocks.")
        return 0
    git("fetch", "origin")
    head = git("rev-parse", "HEAD").stdout.strip()
    origin = git("rev-parse", "origin/main").stdout.strip()
    if head != origin:
        print("public push UNVERIFIED: origin/main != HEAD after push")
        heartbeat("error", "push unverified: origin/main != HEAD",
                  "post-push verify mismatch")
        return 0
    print(f"public push: pushed {n} commit(s); public copy current")
    heartbeat("ok", f"pushed {n} commit(s); public copy current")
    return 0


def selftest():
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"  [{'ok' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    sample = (
        "+++ b/tools/x.py\n"
        "+API_KEY = 'abcd1234efgh5678ijkl'\n"
        "+name = os.environ.get('EBAY_ID', 'fallback-value-99')\n"
        "+pw = 'fake-password-for-tests'\n"
        "+note = 'this token is mentioned in prose only'\n"
        "+-----BEGIN PRIVATE KEY-----\n"
        " context line with password = 'not-added-123456'\n")
    hits = scan_diff(sample)
    kinds = sorted(k for _, k in hits)
    check("assignment caught", "credential assignment" in kinds, True)
    check("env fallback caught", "env fallback value" in kinds, True)
    check("private key caught", "private key header" in kinds, True)
    check("fixture ignored", len([k for k in kinds
                                  if k == "credential assignment"]), 1)
    check("prose token ignored", "token assignment" in kinds, False)
    check("context line ignored", len(hits), 3)
    check("clean diff passes", scan_diff("+++ b/a.py\n+x = 1\n"), [])
    print("PUBLIC PUSH SELFTEST:", "OK" if not failures
          else f"FAILED: {failures}")
    return 0 if not failures else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "selftest":
        return selftest()
    if mode == "dry-run":
        return run(dry=True)
    if mode == "run":
        return run()
    print("usage: sbos_public_push.py [run|dry-run|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
