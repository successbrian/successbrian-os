#!/usr/bin/env python3
"""
second_brain.py — write learnings to the agent second brain.

The second brain lives in ecosystem_central.second_brain on k11-alpha.
Schema: topic, category, content, confidence (low|medium|high|expired),
        source, verification, expires_at, tags[].

Durable facts only — operational noise stays in the shift log.
Usage:
    python3 second_brain.py --topic "..." --content "..." \
        --category learning --confidence medium --tags a,b,c \
        --source "sunday-shift-checkin" --verification "..." \
        --expires-days 90
"""
import argparse
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"


def pg_exec(sql: str) -> str:
    out = subprocess.run(
        [str(KSSH), f"psql -h localhost -U successbrian -d ecosystem_central "
                    f"-t -A -c \"{sql}\""],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout.strip()


def esc(s: str) -> str:
    return s.replace("'", "''")


def record(topic: str, content: str, category: str = "learning",
           confidence: str = "medium", source: str = "sunday-shift",
           verification: str = "", expires_days: int | None = 90,
           tags: list[str] | None = None) -> None:
    expires = (f"now() + interval '{int(expires_days)} days'"
               if expires_days else "NULL")
    tags_sql = ("ARRAY[" + ",".join(f"'{esc(t)}'" for t in (tags or [])) + "]"
                if tags else "NULL")
    sql = (
        "INSERT INTO second_brain "
        "(topic, category, content, confidence, source, verification, "
        "expires_at, tags) VALUES "
        f"('{esc(topic)}', '{esc(category)}', '{esc(content)}', "
        f"'{esc(confidence)}', '{esc(source)}', '{esc(verification)}', "
        f"{expires}, {tags_sql});"
    )
    pg_exec(sql)
    print(f"Recorded: {topic} [{confidence}]")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--category", default="learning")
    p.add_argument("--confidence", default="medium",
                   choices=["low", "medium", "high"])
    p.add_argument("--source", default="sunday-shift")
    p.add_argument("--verification", default="")
    p.add_argument("--expires-days", type=int, default=90)
    p.add_argument("--tags", default="",
                   help="comma-separated")
    a = p.parse_args()
    record(a.topic, a.content, a.category, a.confidence, a.source,
           a.verification, a.expires_days,
           [t.strip() for t in a.tags.split(",") if t.strip()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
