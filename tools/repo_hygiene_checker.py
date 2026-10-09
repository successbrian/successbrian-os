#!/usr/bin/env python3
"""
repo_hygiene_checker.py — Daily repo hygiene probe.

PURPOSE: Catch repo messes (staged-but-uncommitted work piling up,
         commit-blocking conflicts) within a day, before they become
         week-old tangles nobody understands.
WHY: 2026-10-07: a week of staged-but-uncommitted work (including accidental
     doc deletions swept up by a broad `git add`) piled up in successbrian-os
     behind two unmerged paths nobody fixed. Brian 2026-10-08: every coder
     (Spencer, Altair, the Coding Box, all future coders) needs this checker.
CALLED BY: system cron daily 07:00 CDT (successbrian on k11-alpha).
NOTES:
  - Follows the checker pattern: deterministic probe -> history table ->
    agents read the table. It REPORTS; it never fixes anything itself.
  - Healthy = no unmerged paths AND no staged-but-uncommitted changes.
    Unstaged work-in-progress, untracked files, and ahead/behind counts are
    informational only — normal coder activity, not a mess.
  - On healthy->unhealthy transition it sends a knowledge_bridge message to
    altair so the mess gets fixed the same day, not discovered a week later.
  - TRACKED_REPOS: add (name, path) tuples as new repos come online
    (DealsDesk monolith, Coding Box harness, ...). Missing paths are reported,
    not fatal.
"""

import subprocess
import sys

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]

TRACKED_REPOS = [
    # (name, absolute path on k11-alpha)
    ("successbrian-os", "/home/successbrian/successbrian-os"),
    # Add as they come online:
    # ("dealsdesk", "/home/successbrian/dealsdesk"),
    # ("mantis-coding-harness", "/home/successbrian/mantis-coding-harness"),
]


def pq(s):
    return "'" + str(s or "").replace("'", "''") + "'"


def git(repo_path, *args, timeout=30):
    r = subprocess.run(["git", "-C", repo_path] + list(args),
                       capture_output=True, text=True, timeout=timeout)
    return r


def check_repo(name, path):
    """Probe one repo. Returns dict; never raises."""
    import os
    if not os.path.isdir(os.path.join(path, ".git")):
        return {"name": name, "path": path, "missing": True, "healthy": True,
                "notes": "not a git checkout (skipped)"}
    out = {"name": name, "path": path, "missing": False}

    # Unmerged paths (the commit blocker)
    r = git(path, "ls-files", "-u")
    unmerged = set()
    if r.returncode == 0:
        for ln in r.stdout.splitlines():
            parts = ln.split("\t")
            if len(parts) == 2:
                unmerged.add(parts[1])
    out["unmerged_count"] = len(unmerged)
    out["unmerged_files"] = sorted(unmerged)[:10]

    # Index vs HEAD (staged but uncommitted) and worktree vs index
    staged, unstaged, untracked = 0, 0, 0
    r = git(path, "status", "--porcelain=v1", "-uall")
    if r.returncode == 0:
        for ln in r.stdout.splitlines():
            if len(ln) < 2:
                continue
            x, y = ln[0], ln[1]
            if x == "?" or y == "?":
                untracked += 1
            else:
                if x not in (" ", "?"):
                    staged += 1
                if y not in (" ", "?"):
                    unstaged += 1
    out["staged_count"] = staged
    out["unstaged_count"] = unstaged
    out["untracked_count"] = untracked

    # Ahead/behind upstream (informational)
    behind = ahead = None
    r = git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if r.returncode == 0 and r.stdout.strip():
        b = git(path, "rev-list", "--count", "HEAD..@{u}")
        a = git(path, "rev-list", "--count", "@{u}..HEAD")
        behind = int(b.stdout.strip()) if b.returncode == 0 else None
        ahead = int(a.stdout.strip()) if a.returncode == 0 else None
    out["behind_origin"] = behind
    out["ahead_of_origin"] = ahead

    # Last commit
    r = git(path, "log", "-1", "--format=%ci%x09%s")
    if r.returncode == 0 and r.stdout.strip():
        ts, subj = (r.stdout.strip().split("\t") + [""])[:2]
        out["last_commit_at"] = ts
        out["last_commit_subject"] = subj[:200]
    else:
        out["last_commit_at"] = None
        out["last_commit_subject"] = ""

    healthy = out["unmerged_count"] == 0 and out["staged_count"] == 0
    notes = []
    if out["unmerged_count"]:
        notes.append("UNMERGED (commit blocked): %s"
                     % ", ".join(out["unmerged_files"]))
    if out["staged_count"]:
        notes.append("%d file(s) staged but uncommitted" % out["staged_count"])
    out["healthy"] = healthy
    out["notes"] = "; ".join(notes)
    return out


def write_row(c):
    sql = (
        "INSERT INTO successbrian_os.repo_hygiene_history "
        "(repo_name, repo_path, unmerged_count, staged_count, unstaged_count, "
        "untracked_count, behind_origin, ahead_of_origin, last_commit_at, "
        "last_commit_subject, healthy, notes) VALUES (%s, %s, %d, %d, %d, %d, "
        "%s, %s, %s, %s, %s, %s);"
        % (pq(c["name"]), pq(c["path"]), c.get("unmerged_count", 0),
           c.get("staged_count", 0), c.get("unstaged_count", 0),
           c.get("untracked_count", 0),
           str(c["behind_origin"]) if c.get("behind_origin") is not None else "NULL",
           str(c["ahead_of_origin"]) if c.get("ahead_of_origin") is not None else "NULL",
           pq(c["last_commit_at"]) if c.get("last_commit_at") else "NULL",
           pq(c.get("last_commit_subject", "")),
           "true" if c["healthy"] else "false", pq(c.get("notes", ""))))
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print("db write failed for %s: %s" % (c["name"], r.stderr.strip()[:200]),
              file=sys.stderr)


def was_healthy_before(name):
    """Previous row's healthy flag (None if no previous row)."""
    sql = ("SELECT healthy FROM successbrian_os.repo_hygiene_history "
           "WHERE repo_name = %s AND checked_at < now() - interval '1 minute' "
           "ORDER BY checked_at DESC LIMIT 1;" % pq(name))
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    v = r.stdout.strip().lower()
    if v == "t":
        return True
    if v == "f":
        return False
    return None


def alert_altair(c):
    msg = ("[repo-hygiene] %s is UNHEALTHY: %s "
           "(staged=%d unmerged=%d unstaged=%d untracked=%d). "
           "Fix today: commit or unstage the staged work; resolve unmerged paths "
           "immediately — never leave them. Contract: docs/CODE-STANDARDS.md "
           "'Commit hygiene (all coders)'." % (
               c["name"], c["notes"] or "see table",
               c.get("staged_count", 0), c.get("unmerged_count", 0),
               c.get("unstaged_count", 0), c.get("untracked_count", 0)))
    sql = ("INSERT INTO public.knowledge_bridge "
           "(source_agent, target_agent, message, urgency, created_at) VALUES "
           "('repo-hygiene-checker', 'altair', %s, 'high', now());" % pq(msg))
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print("bridge alert failed: %s" % r.stderr.strip()[:200], file=sys.stderr)
    else:
        print("alerted altair via knowledge_bridge")


def main():
    for name, path in TRACKED_REPOS:
        c = check_repo(name, path)
        if c.get("missing"):
            print("%s: %s" % (name, c["notes"]))
            continue
        prev = was_healthy_before(name)
        write_row(c)
        state = "HEALTHY" if c["healthy"] else "UNHEALTHY"
        print("%s: %s (staged=%d unmerged=%d unstaged=%d untracked=%d)%s" % (
            name, state, c["staged_count"], c["unmerged_count"],
            c["unstaged_count"], c["untracked_count"],
            (" — " + c["notes"]) if c["notes"] else ""))
        if not c["healthy"] and prev is not False:
            # New mess (or first-ever check): alert once, not every day.
            alert_altair(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
