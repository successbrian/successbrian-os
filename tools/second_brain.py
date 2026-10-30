#!/usr/bin/env python3
"""
Second-brain writer for SuccessBrian OS.

PURPOSE:
    Record durable learnings to the agent second brain
    (ecosystem_central.second_brain on k11-alpha): every fact carries
    confidence, expiry, and verification so stale knowledge can't silently
    poison agent reasoning.

WHY:
    Agents accumulate knowledge fast and it rots fast. The Sunday shift,
    night shift, and automation engine all learn things (what worked, what
    broke, crew behavior patterns). Without a structured store those lessons
    evaporate between runs. This is the write path; the schema lives in
    successbrian/second-brain-for-agents.

CALLED BY:
    - Sunday/night shift workers, heartbeat check-ins, automation engine
    - Humans: python3 second_brain.py --topic ... --content ... --tags ...

NOTES:
    Durable facts ONLY. Operational noise (who reported what at 3:15) stays
    in the shift log — the schema README is explicit about this. Confidence:
    high = directly observed, medium = inferred/research-backed, low = hunch.
"""
import argparse
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"


def pg_exec(sql: str) -> str:
    # On k11 (or anywhere with a local postgres): run psql directly.
    # From Hatch: shell through kssh (base64 keeps &, $, backticks, quotes
    # from being interpreted by the remote shell — 2026-09-28 lesson).
    import base64
    import os
    b64 = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    if KSSH.exists():
        out = subprocess.run(
            [str(KSSH), "psql -h localhost -U successbrian -d ecosystem_central "
                        f"-t -A -c \"$(echo {b64} | base64 -d)\""],
            capture_output=True, text=True, timeout=60,
        )
    else:
        # local psql: no shell involved, pass SQL directly
        env = dict(os.environ)
        env.setdefault("PGHOST", "localhost")
        env.setdefault("PGDATABASE", "ecosystem_central")
        env.setdefault("PGUSER", "successbrian")
        out = subprocess.run(
            ["psql", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True, text=True, timeout=60, env=env,
        )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout.strip()


# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.dirname(_os_c.path.abspath(__file__)))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)


def record(topic: str, content: str, category: str = "learning",
           confidence: str = "medium", source: str = "sunday-shift",
           verification: str = "", expires_days: int | None = 90,
           tags: list[str] | None = None) -> None:
    pg_exec(_build_sql(topic, content, category, confidence, source,
                       verification, expires_days, tags))
    print(f"Recorded: {topic} [{confidence}]")


def _build_sql(topic: str, content: str, category: str = "learning",
               confidence: str = "medium", source: str = "sunday-shift",
               verification: str = "", expires_days: int | None = 90,
               tags: list[str] | None = None) -> str:
    expires = (f"now() + interval '{int(expires_days)} days'"
               if expires_days else "NULL")
    tags_sql = ("ARRAY[" + ",".join(f"'{esc(t)}'" for t in (tags or [])) + "]"
                if tags else "NULL")
    return (
        "INSERT INTO second_brain "
        "(topic, category, content, confidence, source, verification, "
        "expires_at, tags) VALUES "
        f"('{esc(topic)}', '{esc(category)}', '{esc(content)}', "
        f"'{esc(confidence)}', '{esc(source)}', '{esc(verification)}', "
        f"{expires}, {tags_sql});"
    )


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
    p.add_argument("--dry-run", action="store_true",
                   help="print the SQL that would run; write nothing")
    a = p.parse_args()
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    if a.dry_run:
        print(_build_sql(a.topic, a.content, a.category, a.confidence,
                         a.source, a.verification, a.expires_days, tags))
        print("(dry run: nothing written)")
        return 0
    record(a.topic, a.content, a.category, a.confidence, a.source,
           a.verification, a.expires_days, tags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
