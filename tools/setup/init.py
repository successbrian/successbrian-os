#!/usr/bin/env python3
"""SuccessBrian OS: onboarding interview — generates a new user's private config.

PURPOSE:
    First-run setup. Interviews the entrepreneur (name, focus limit, the
    streams they're running, Postgres location) and writes their private
    registry files. The "agent" that greets a new user is a deterministic
    script with good questions — no chat model, no guessing, same result
    for the same answers.

WHY:
    Brian 2026-10-04: a downloaded OS that doesn't boot itself is a
    toolbox, not a product. The interview turns a stranger into a
    configured user in five minutes, and it teaches the mental model
    (streams, lanes, focus limit, tested-vs-untested) while doing it.

CALLED BY:
    - Humans, once: python3 tools/setup/init.py
    - Referenced by README quickstart and tools/setup/doctor.py.

NOTES:
    - Writes ONLY to gitignored personal files (tools/focus/user_focus.json).
      Refuses to overwrite an existing registry without explicit confirmation.
    - NEVER writes secrets: Postgres passwords are not collected and not
      stored. The interview prints ~/.pgpass / PGPASSWORD guidance instead.
    - Product-generic: no names, streams, or lanes are pre-filled.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tools/setup/ -> repo root
FOCUS_DIR = os.path.join(REPO, "tools", "focus")
USER_FILE = os.path.join(FOCUS_DIR, "user_focus.json")


def ask(prompt, default=None):
    hint = f" [{default}]" if default not in (None, "") else ""
    try:
        raw = input(f"{prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled. Nothing was written.")
        sys.exit(1)
    return raw if raw else (default if default is not None else "")


def ask_yn(prompt, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        raw = ask(f"{prompt} ({d})", "").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please answer y or n.")


def main():
    print("=== SuccessBrian OS — first-run setup ===\n")
    print("This builds your private stream registry. It takes about five minutes.")
    print("Everything you enter stays on this machine (gitignored, never committed).\n")

    if os.path.exists(USER_FILE):
        print(f"A registry already exists at tools/focus/user_focus.json.")
        if not ask_yn("Overwrite it?", default=False):
            print("Kept the existing registry. Setup cancelled.")
            return 0
        print()

    name = ask("What should the OS call you", "founder")
    print(f"\nNice to meet you, {name}.\n")

    while True:
        raw = ask("How many active pursuits can you truly focus on at once", "5")
        try:
            focus_limit = int(raw)
            if focus_limit >= 1:
                break
        except ValueError:
            pass
        print("  Please enter a whole number, 1 or more.")
    print(f"\nFocus limit set to {focus_limit}. The coach will tax every new")
    print("opportunity once you exceed it. (Change later with --focus-limit.)\n")

    print("Now list what you're pursuing. One per line; blank name when done.")
    print("For each: the lane it owns — the thing it does that nothing else does.\n")
    streams = []
    while True:
        sname = ask("Stream name (blank to finish)", "")
        if not sname:
            break
        lane = ask(f"  Lane for '{sname}' (e.g. weight-management, lead generation)", "")
        status = ask("  Status", "active")
        if status not in ("active", "testing", "dormant", "exiting"):
            print("  Use one of: active, testing, dormant, exiting. Defaulting to active.")
            status = "active"
        promoting = ask_yn("  Are you actively promoting it", default=status == "active")
        tested = ask_yn("  Have you personally used/tested it", default=False)
        streams.append({
            "name": sname,
            "lane": lane or "unassigned",
            "status": status,
            "monthly_income_usd": None,
            "promoting": promoting,
            "personally_tested": tested,
        })
        print()

    if not streams:
        print("No streams entered — writing an empty registry. Add some later and re-run review.\n")

    print("Postgres (Tier 2 modules: ventures, audience). Skip if unsure — Tier 1 works without it.")
    pg_host = ask("  Host", "localhost")
    pg_db = ask("  Database name", "successbrian_os")
    pg_user = ask("  User", os.environ.get("USER", "founder"))
    print("\n  Passwords are NEVER stored by this setup.")
    print("  Set PGPASSWORD in your shell, or add a line to ~/.pgpass:")
    print(f"    {pg_host}:5432:{pg_db}:{pg_user}:YOUR_PASSWORD")
    print("  (chmod 600 ~/.pgpass)\n")

    os.makedirs(FOCUS_DIR, exist_ok=True)
    registry = {
        "_note": f"Private registry for {name}. GITIGNORED — never committed.",
        "_focus_limit": focus_limit,
        "streams": streams,
    }
    with open(USER_FILE, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"Wrote tools/focus/user_focus.json ({len(streams)} "
          f"{'stream' if len(streams) == 1 else 'streams'}, focus limit {focus_limit}).")

    # Persist the focus limit choice where the coach will honor it.
    print("\nNext steps:")
    print("  1. Run the boot check:  python3 tools/setup/doctor.py")
    print("  2. See your grounding:  python3 tools/focus/focus.py review")
    if focus_limit != 5:
        print(f"  3. Your focus limit ({focus_limit}) differs from the default 5 — pass it explicitly:")
        print(f"       python3 tools/focus/focus.py review --focus-limit {focus_limit}")
        print("     or export FOCUS_LIMIT={} in your shell.".format(focus_limit))
    print("\nScores propose. You decide. Welcome aboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
