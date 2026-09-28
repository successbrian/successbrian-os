"""
Decision Sync for SuccessBrian OS.

PURPOSE:
    Propagate Brian's decisions from altair.brian_decisions (PostgreSQL, the
    system of record) to AnythingLLM (the searchable view), and flag
    conflicts between decisions and build plans.

WHY:
    Decisions made in conversation evaporate. PostgreSQL is authoritative but
    not searchable by the agents; AnythingLLM is searchable but not
    authoritative. This bridge keeps them in sync, and the conflict check
    catches the dangerous case: a decision that contradicts what we're
    building (e.g. the false "buy 7 more M40s" record).

CALLED BY:
    - tools/sunday_shift.py (step 1, weekly)

NOTES:
    Conflict checks are still hard-coded — they don't scale to new plan
    tables. AnythingLLM upload needs ANYTHINGLLM_API_KEY and is untested
    against the real workspace. Erroneous decisions propagate downstream
    unless corrected at the source; see the X79-20260927-03 correction.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STAGING_DIR = Path(os.environ.get(
    "DECISION_SYNC_STAGING",
    str(Path.home() / "workspace" / "successbrian-os" / "tools" /
        "decision_sync" / "staging"),
))
ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://100.118.53.47:3001")
ANYTHINGLLM_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "")
WORKSPACE_SLUG = "home-lab"  # AnythingLLM workspace for ecosystem docs

PG = dict(host="localhost", user="successbrian", dbname="ecosystem_central")


def kssh(cmd: str) -> str:
    """Run a command on k11-alpha via the kssh helper."""
    out = subprocess.run(
        [str(Path.home() / "workspace" / "bin" / "kssh"), cmd],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"kssh failed: {out.stderr.strip()}")
    return out.stdout


def pg_query(sql: str) -> list[dict]:
    """Run a read query against ecosystem_central, return list of dicts."""
    # Use json output for reliable parsing
    wrapped = (
        f"psql -h {PG['host']} -U {PG['user']} -d {PG['dbname']} "
        f"-t -A -F'\x1f' -c \"{sql}\""
    )
    raw = kssh(wrapped)
    # Caller parses; we return raw lines and let each query define columns
    return [line.split("\x1f") for line in raw.strip().split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# Step 1: Pull decisions
# ---------------------------------------------------------------------------

def get_decisions() -> list[dict]:
    rows = pg_query(
        "SELECT decision_id, question, context, answer, "
        "to_char(answered_at,'YYYY-MM-DD HH24:MI') "
        "FROM altair.brian_decisions ORDER BY answered_at DESC"
    )
    return [
        {
            "decision_id": r[0],
            "question": r[1],
            "context": r[2] or "",
            "answer": r[3],
            "answered_at": r[4] if len(r) > 4 else "",
            "topic": r[0].split("-")[0] if "-" in r[0] else "general",
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Step 2: Generate the decisions digest doc
# ---------------------------------------------------------------------------

def render_digest(decisions: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Brian's Decisions — System of Record Digest",
        "",
        f"**Generated:** {now}",
        f"**Source:** `altair.brian_decisions` ({len(decisions)} decisions)",
        "**Note:** The PostgreSQL table is the source of truth. "
        "This document is the searchable view.",
        "",
        "---",
        "",
    ]
    current_topic = None
    for d in decisions:
        if d["topic"] != current_topic:
            current_topic = d["topic"]
            lines += [f"## Topic: {current_topic}", ""]
        lines += [
            f"### {d['decision_id']}: {d['question']}",
            f"**Decided:** {d['answered_at']}",
            "",
        ]
        if d["context"]:
            lines += [f"**Context:** {d['context']}", ""]
        lines += [f"**Decision:** {d['answer']}", "", "---", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: Conflict detection — decisions vs build plans
# ---------------------------------------------------------------------------

def get_build_plan(table: str) -> list[dict]:
    rows = pg_query(
        f"SELECT component, qty_needed, qty_on_hand, qty_to_buy, status "
        f"FROM public.{table}"
    )
    return [
        {
            "component": r[0], "qty_needed": r[1],
            "qty_on_hand": r[2], "qty_to_buy": r[3],
            "status": r[4] if len(r) > 4 else "",
        }
        for r in rows
    ]


def detect_x79_conflicts(decisions: list[dict]) -> list[dict]:
    """Hard-coded cross-checks for X79. Code owns the workflow."""
    conflicts = []
    plan = {p["component"]: p for p in get_build_plan("x79_cluster_build_plan")}
    answers = " ".join(d["answer"] for d in decisions if d["topic"] == "X79")

    def flag(kind, detail, severity="review"):
        conflicts.append({
            "kind": kind, "detail": detail, "severity": severity,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })

    # 1. GPU count: plan says 8x M40 total, decision says 2x per node x4 = 8. Consistent.
    gpu = plan.get("GPU Tesla M40 24GB", {})
    if gpu and int(gpu.get("qty_needed") or 0) != 8:
        flag("gpu_count_mismatch",
             f"Plan wants {gpu.get('qty_needed')}x M40, decisions say 8x (2/node x4).")

    # 2. PSU oversized: 2x150W GPUs + 2x95W CPUs + overhead ~= 600W; 1200W is 2x over.
    psu = plan.get("PSU 1200W 80+ Gold Server", {})
    decided_w = re.search(r"\b(750|850)\s?W\b", answers, re.IGNORECASE)
    if psu and "150W" in answers and "power-limit" in answers and not decided_w:
        flag("psu_oversized",
             "Plan specs 1200W PSU but decisions power-limit M40s to 150W each "
             "(~300W GPUs + ~190W CPUs + overhead ~= 600W). 1200W is oversized; "
             "consider 750-850W to save cost.",
             severity="info")
    # (2026-09-28: once Brian's PSU decision is recorded in brian_decisions
    # — e.g. X79 Q1 = 850W on 2026-09-27 — decided_w matches and this check
    # auto-resolves instead of re-flagging a settled question.)

    # 3. Missing from plan: NVMe adapters (2/node x4 = 8)
    low = answers.lower()
    if ("PCIe NVMe" not in " ".join(plan.keys())
            and "pcie" in low and "adapter" in low):
        flag("plan_gap",
             "Decisions add 2x PCIe NVMe adapters per node (8 total) for the "
             "striped Gen 2 model volume, but no adapter line exists in the build plan.")

    # 4. Missing from plan: SATA SSD/HDD tiering
    if "SATA" not in " ".join(plan.keys()) and "SATA" in answers:
        flag("plan_gap",
             "Decisions add SATA SSD + HDD tiering per node, but no SATA drives "
             "exist in the build plan.")

    # 5. Stale phase language: plan notes may still say "Phase 1/Phase 2"
    if "phase transition" in answers.lower() or "no phase" in answers.lower():
        flag("stale_notes",
             "Decisions killed the Phase 1/Phase 2 split (dual-role from day one). "
             "Check plan notes/source_type fields for stale phase language.",
             severity="info")

    return conflicts


def render_conflict_report(conflicts: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Decision Conflict Report",
        "",
        f"**Generated:** {now}",
        f"**Conflicts/gaps found:** {len(conflicts)}",
        "",
        "These are flags for Brian's review — nothing is auto-changed. "
        "Quarantine, never delete.",
        "",
        "---",
        "",
    ]
    for c in conflicts:
        lines += [
            f"### [{c['severity'].upper()}] {c['kind']}",
            "",
            c["detail"],
            "",
            f"_Checked: {c['checked_at']}_",
            "",
            "---",
            "",
        ]
    if not conflicts:
        lines += ["No conflicts detected. Plans and decisions are consistent.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 4: AnythingLLM push (graceful when no API key)
# ---------------------------------------------------------------------------

def push_to_anythingllm(title: str, content: str, slug: str) -> bool:
    """Push a document to AnythingLLM. Returns True on success."""
    if not ANYTHINGLLM_KEY:
        print("  [skip] No ANYTHINGLLM_API_KEY — doc stays in staging.")
        return False
    try:
        import urllib.request
        # Upload as a raw text doc via the document upload endpoint
        boundary = "----decisionsync"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{slug}.md"\r\n'
            f"Content-Type: text/markdown\r\n\r\n"
            f"{content}\r\n--{boundary}--\r\n"
        ).encode()
        req = urllib.request.Request(
            f"{ANYTHINGLLM_URL}/api/v1/document/upload",
            data=body,
            headers={
                "Authorization": f"Bearer {ANYTHINGLLM_KEY}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        print(f"  [ok] Uploaded {slug}: {result}")
        return True
    except Exception as e:  # noqa: BLE001 — report, don't crash the sync
        print(f"  [error] AnythingLLM push failed for {slug}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Sync Brian's decisions to AnythingLLM.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change, touch nothing.")
    ap.add_argument("--push", action="store_true",
                    help="Also push docs to AnythingLLM (needs API key).")
    args = ap.parse_args()

    print("Pulling decisions from altair.brian_decisions...")
    decisions = get_decisions()
    print(f"  Found {len(decisions)} decisions.")

    digest = render_digest(decisions)
    digest_hash = hashlib.sha256(digest.encode()).hexdigest()[:12]

    print("Checking X79 decisions vs build plan...")
    conflicts = detect_x79_conflicts(decisions)
    print(f"  {len(conflicts)} conflicts/gaps flagged.")
    report = render_conflict_report(conflicts)

    if args.dry_run:
        print("\n--- DRY RUN: digest preview (first 40 lines) ---")
        print("\n".join(digest.split("\n")[:40]))
        print("\n--- DRY RUN: conflicts ---")
        for c in conflicts:
            print(f"  [{c['severity']}] {c['kind']}: {c['detail'][:100]}...")
        print("\nDry run complete. Nothing written.")
        return 0

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = STAGING_DIR / f"decisions-digest-{digest_hash}.md"
    report_path = STAGING_DIR / "conflict-report-latest.md"
    digest_path.write_text(digest)
    report_path.write_text(report)
    # Stable symlink for "latest digest"
    latest = STAGING_DIR / "decisions-digest-latest.md"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(digest_path.name)
    print(f"  Wrote {digest_path}")
    print(f"  Wrote {report_path}")

    if args.push:
        print("Pushing to AnythingLLM...")
        push_to_anythingllm("Brian's Decisions — Digest", digest,
                            "decisions-digest")
        push_to_anythingllm("Decision Conflict Report", report,
                            "decision-conflicts")
    else:
        print("Skipping AnythingLLM push (use --push with API key).")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
