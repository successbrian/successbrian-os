#!/bin/sh
# tree-tidy pre-commit hook — .bak recurrence prevention guard (B23, 2026-11-24).
#
# Why: QA check 79 (tree-stays-tidy) scans the FILESYSTEM for *.bak*
# files. .gitignore already has *.bak / *.bak-* so a stray backup is
# never committed — but it still sits in the tree and fails check 79.
# That is exactly what happened 2026-11-22: an edit left
# tools/ecosystem_intel/ai_bubble_collect.py.bak-2026-11-22 in the tree,
# commit 6bbab2b landed fine (file ignored), and check 79 failed its
# 2026-11-23 09:12 run. Three manual cleanups followed (improvement_log
# rows 54/72); this hook stops the fourth at the source.
#
# What it does, in order:
#   1. Refuse the commit while ANY *.bak* file exists in the working
#      tree (the exact check-79 pattern). The committer must move the
#      backup to ~/backups or delete it before the commit can land.
#   2. Chain to the gitleaks pre-commit check (canonical source
#      tools/guardrails/gitleaks-pre-commit.sh, behaviour unchanged).
#
# Canonical source: successbrian-os/tools/guardrails/tree-tidy-pre-commit.sh
# Installed as .git/hooks/pre-commit in successbrian-os.
# Selftest: tree-tidy-pre-commit.sh --selftest (temp-dir probes, no repo writes).

# bak_files DIR — print *.bak* files under DIR, one per line.
# The find pattern is check 79's spec verbatim.
bak_files() {
    (cd "$1" && find . -path ./.git -prune -o -type f -name '*.bak*' -print)
}

guard() {
    _root="$1"
    _found="$(bak_files "$_root")"
    if [ -n "$_found" ]; then
        echo ".bak files in the tree — commit refused (check 79 tree-stays-tidy):" >&2
        printf '%s\n' "$_found" >&2
        echo "Move the backup(s) to ~/backups or delete them, then commit again." >&2
        return 1
    fi
    return 0
}

selftest() {
    _tmp="$(mktemp -d)" || return 1
    trap 'rm -rf "$_tmp"' EXIT INT TERM
    # Probe 1: a nested .bak-YYYY-MM-DD file must be found and refuse.
    mkdir -p "$_tmp/tools/x"
    : > "$_tmp/tools/x/collect.py.bak-2026-11-22"
    if guard "$_tmp"; then
        echo "SELFTEST FAIL: probe 1 — .bak file did not refuse" >&2
        return 1
    fi
    # Probe 2: a plain .bak suffix must also refuse.
    : > "$_tmp/tools/x/other.py.bak"
    if guard "$_tmp"; then
        echo "SELFTEST FAIL: probe 2 — .bak suffix did not refuse" >&2
        return 1
    fi
    # Probe 3: with no .bak files the guard passes, and a normal file
    # plus a .bak-named DIRECTORY do not trip it (find is -type f).
    rm "$_tmp/tools/x/collect.py.bak-2026-11-22" "$_tmp/tools/x/other.py.bak"
    : > "$_tmp/tools/x/collect.py"
    mkdir -p "$_tmp/tools/x/archive.bak"
    if ! guard "$_tmp"; then
        echo "SELFTEST FAIL: probe 3 — clean tree refused" >&2
        return 1
    fi
    echo "TREE_TIDY_PRECOMMIT_OK (3 probes)"
    return 0
}

if [ "${1:-}" = "--selftest" ]; then
    selftest
    exit $?
fi

# Real hook path: refuse while any *.bak* file is in the working tree.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || ROOT="."
if ! guard "$ROOT"; then
    exit 1
fi

# Chain: gitleaks pre-commit check (2026-10-27 secrets closure).
GL="$HOME/.local/bin/gitleaks"
if [ ! -x "$GL" ]; then echo "gitleaks not found at $GL — commit blocked (fail closed)" >&2; exit 1; fi
exec "$GL" git --pre-commit --staged --redact --no-banner -v
