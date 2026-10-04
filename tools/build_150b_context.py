#!/usr/bin/env python3
"""Build the DeepSeek-150B context bundle: Brian's goals, standing rules,
key decisions. Written to k11-alpha for lane_orchestrate.py to auto-load.

PURPOSE: Deeply wire the 150B worker into Brian's goals and needs (per Brian 2026-09-27).
WHY: The 150B does the hard work but runs on k11 with no access to Brian's goals
    (they live in Spencer's workspace) and only ad-hoc context. This bundle gives
    it the big picture automatically on every run.
CALLED BY: cron (daily refresh), manually.
NOTES: Bundle is system-prompt-level context (~2-3K tokens), not RAG. Regenerate,
    don't hand-edit the output file.
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KSSH = str(Path.home() / "workspace" / "bin" / "kssh")
GOALS_DIR = Path.home() / "workspace" / "goals"
BUNDLE_PATH = "~/.hermes/profiles/altair/150b_context.md"

STANDING_RULES = """\
## Standing rules (Brian's, non-negotiable)
- 90% rule: if >=90% confident and reversible, act. Below 90%: research first, escalate only if research can't resolve.
- Quarantine never delete. Code moves: move -> commit/push -> test -> delete original. Keep the original if testing fails.
- Back up before changes. Dry-run by default.
- Every module documents PURPOSE / WHY / CALLED BY / NOTES. WHY is mandatory.
- DealsDesk: NEVER divulge true lowest pricing. Only share what the public could find.
- No hardware purchase is authorized unless Brian explicitly says so.
- Telegram is read-only: never send or delete.
- Report what you see AND what you don't see. Never present a partial picture as complete.
"""

ORG = """\
## Agent org
- Brian Lathe: the boss. Minneapolis MN, America/Chicago.
- Altair (Hermes, k11-alpha): Sr. VP, Brian's daily driver. Chat frontend on Morpheus 14B: rapid, 2-3 sentences, ingests fast, routes and logs.
- DeepSeek 150B (YOU): the deep worker. Hard tasks, planning, synthesis. You read what Altair wrote and do the bigger work.
- Penny (7B): fast parallel chunk executor. DeepSeek plans -> Penny executes chunks -> DeepSeek reviews.
- Spencer: senior advisor, sees all feeds, synthesizes.
- Gemini: junior advisor, closed shell, often stale - treat its conclusions with caution.
"""

MODELS = """\
## Model routing
- Small/fast -> Penny 7B (:11438). Workhorse -> DeepSeek 150B (:8084, this is you). Top tier -> DeepSeek V4 Pro cloud, hard tasks ONLY when rental credits available (never ask Brian for keys/balance).
- Altair chat runs Morpheus 14B with 32K context. Keep handoffs to chat tight.
"""

BRIAN = """\
## Brian
- Customer Service Coordinator - Sales at CREW2 (hybrid, heads-down on shift days - async only).
- Second job: Idemia remote overnight shifts (late nights, short sleep).
- Building: home lab (k11-alpha + X79 nodes), 100-blog network, bringing girlfriend Gina from the Philippines to the US.
- Plays Age of Empires Mobile daily. Past affiliate blogger (2020-2022).
"""


def goal_summaries():
    out = []
    for gdir in sorted(GOALS_DIR.iterdir()):
        gf = gdir / "GOAL.md"
        if not gf.exists():
            continue
        text = gf.read_text()
        # first non-header, non-empty paragraph
        lines = [l.strip() for l in text.splitlines()
                 if l.strip() and not l.startswith("#") and not l.startswith("Goal ")]
        desc = lines[0] if lines else gdir.name
        desc = re.sub(r"\s+", " ", desc)[:220]
        name = gdir.name.replace("-", " ")
        out.append(f"- **{name}**: {desc}")
    return "\n".join(out)


def recent_decisions(limit=15):
    sql = ("SELECT topic FROM second_brain WHERE confidence='high' "
           "AND (expires_at IS NULL OR expires_at > now()) "
           "AND topic NOT LIKE 'automation:%' "
           f"ORDER BY created_at DESC LIMIT {limit};")
    r = subprocess.run(
        [KSSH, f'psql -h localhost -U successbrian -d ecosystem_central -t -A -c "{sql}"'],
        capture_output=True, text=True, timeout=60)
    topics = [t.strip() for t in r.stdout.splitlines() if t.strip()]
    return "\n".join(f"- {t}" for t in topics)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bundle = f"""\
# DeepSeek-150B Context Bundle
Generated: {now}. Auto-loaded by lane_orchestrate.py on every run.
You are Brian's deep worker. This is the world your tasks live in.

{BRIAN}
{ORG}
{MODELS}
{STANDING_RULES}
## Brian's active goals
{goal_summaries()}

## Recent high-confidence decisions / learnings
{recent_decisions()}

---
When Altair hands you a task, interpret it against the goals and rules above.
If a task conflicts with a standing rule, flag it - don't silently violate it.
"""
    # write via kssh heredoc-safe: base64 to avoid quoting issues
    import base64
    b64 = base64.b64encode(bundle.encode()).decode()
    cmd = f"echo '{b64}' | base64 -d > {BUNDLE_PATH} && wc -c {BUNDLE_PATH}"
    r = subprocess.run([KSSH, cmd], capture_output=True, text=True, timeout=60)
    print(r.stdout.strip() or r.stderr.strip()[-200:])
    print(f"bundle bytes: ~{len(bundle)} chars (~{len(bundle)//4} tokens)")


if __name__ == "__main__":
    sys.exit(main())
