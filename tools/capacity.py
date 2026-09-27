"""
Capacity recommendations for SuccessBrian OS.

The ecosystem watches its own capacity vs demand and tells Brian what to
buy, build, or repurpose — before he hits the wall.

Usage:
    python3 capacity.py --dry-run    # preview, touch nothing
    python3 capacity.py              # generate report to staging/
    python3 capacity.py --to-altair  # also drop report in altair-brain inbox

Capacity dimensions (v1):
  1. Inference  — tok/s available vs content generation demand
  2. Storage    — NVMe/SATA/HDD provisioned vs model library + data growth
  3. Build      — Brian's time is the scarcest resource (two jobs); flag
                  when planned work exceeds realistic build bandwidth

Demand sources (v1, hard-coded estimates — refine as real data arrives):
  - 100-blog network: articles/day target -> tok/s needed
  - AnythingLLM nightly maintenance: CPU-hours/night
  - Goal queue depth: pending compute-heavy goals

Fleet sources: build plans + brian_decisions + known live systems.
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "decision_sync"))
from sync import get_decisions, get_build_plan, kssh, pg_query  # noqa: E402


STAGING = Path(__file__).parent / "staging"

# ---------------------------------------------------------------------------
# Fleet inventory — known live + planned systems
# Topic: keep this in sync with brian_decisions as the fleet changes.
# ---------------------------------------------------------------------------

FLEET = [
    {
        "name": "k11-alpha",
        "status": "live",
        "batch_tok_s": 0,      # interactive node, not batch
        "note": "Altair/Morpheus/Penny/DeepSeek 150B. Interactive + goal loop.",
    },
    {
        "name": "k11-bravo",
        "status": "in_pieces",
        "batch_tok_s": 0,
        "note": "96GB RAM in wrapping. Future QLoRA training for small models.",
    },
    {
        "name": "x79-node-1..4",
        "status": "planned",
        "batch_tok_s": 40,     # 4 nodes x ~10 tok/s Shakespeare-class
        "note": "Dual M40 per node (48GB VRAM), 2x striped NVMe for Colibri, "
                "M.2 + threads for web/scraping. Content factory.",
    },
    {
        "name": "epyc-rome",
        "status": "evaluating",
        "batch_tok_s": 0,
        "note": "$48 chip at Core 4. 256GB build for dual 150B + QLoRA.",
    },
    {
        "name": "aoostar-glm-1..2",
        "status": "planned",
        "batch_tok_s": 0,
        "note": "GLM 5.3 on triple-striped NVMe. Not batch content nodes.",
    },
]

# ---------------------------------------------------------------------------
# Demand estimates — articles/day -> tok/s
# ---------------------------------------------------------------------------

# 100-blog network: even a modest 2 articles/blog/day = 200 articles/day.
# Avg 2,700 tokens/article -> 540k tokens/day -> ~6.25 tok/s sustained 24/7.
# Reality: batch overnight (8h window) -> ~19 tok/s needed in-window.
DEMAND = {
    "blog_network": {
        "articles_per_day": 200,
        "tokens_per_article": 2700,
        "batch_window_hours": 8,
        "tok_s_needed": 200 * 2700 / (8 * 3600),  # ~18.75
        "note": "100 blogs x 2 articles/day, 8h overnight batch window.",
    },
    "anythingllm_maintenance": {
        "cpu_hours_per_night": 4,
        "note": "Dedup, embeddings, hygiene. Offload target: X79s.",
    },
}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_inference() -> dict:
    planned_batch = sum(f["batch_tok_s"] for f in FLEET
                        if f["status"] in ("planned", "live"))
    needed = DEMAND["blog_network"]["tok_s_needed"]
    headroom = planned_batch - needed
    if headroom >= needed * 0.5:
        verdict = "healthy"
        rec = ("Capacity covers demand with 50%+ headroom. No action needed.")
    elif headroom >= 0:
        verdict = "tight"
        rec = ("Capacity covers demand but headroom is thin. "
               "Prioritize X79 build completion; defer new content targets "
               "until nodes are online.")
    else:
        verdict = "gap"
        rec = (f"Shortfall of {-headroom:.1f} tok/s. Options: "
               f"(a) extend batch window beyond 8h, "
               f"(b) reduce articles/day target, "
               f"(c) accelerate EPYC build for additional throughput.")
    return {
        "dimension": "inference",
        "available_tok_s": planned_batch,
        "needed_tok_s": round(needed, 1),
        "headroom_tok_s": round(headroom, 1),
        "verdict": verdict,
        "recommendation": rec,
    }


def analyze_storage() -> dict:
    # X79 plan: 4 nodes x (3x 2TB NVMe) = 24TB NVMe planned
    # Model library estimate: Shakespeare 40GB + DeepSeek 150B 80GB +
    #   assorted 7B/14B (~100GB) = ~220GB hot. 24TB is ample.
    nvme_tb = 4 * 3 * 2
    model_hot_gb = 220
    verdict = "healthy"
    rec = (f"{nvme_tb}TB NVMe planned vs ~{model_hot_gb}GB hot models. "
           f"Ample. SATA tier sizes still open (see X79 Q3 for Brian).")
    return {
        "dimension": "storage",
        "nvme_tb_planned": nvme_tb,
        "model_hot_gb": model_hot_gb,
        "verdict": verdict,
        "recommendation": rec,
    }


def analyze_build_bandwidth() -> dict:
    # Brian's scarcest resource is his own time (CREW2 + Idemia shifts).
    # Count planned-but-not-live systems as build queue.
    queue = [f["name"] for f in FLEET if f["status"] in ("planned", "in_pieces",
                                                         "evaluating")]
    rec = (f"{len(queue)} systems in build queue: {', '.join(queue)}. "
           f"Brian is heads-down at two jobs. Recommendation: sequence builds "
           f"one at a time (X79s first — parts on hand, highest content ROI), "
           f"don't parallelize hardware builds against limited shop time.")
    return {
        "dimension": "build_bandwidth",
        "queue_depth": len(queue),
        "verdict": "watch" if len(queue) > 3 else "healthy",
        "recommendation": rec,
    }


def render_report(results: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Ecosystem Capacity Report",
        "",
        f"**Generated:** {now}",
        "",
        "The ecosystem's read on capacity vs demand. "
        "Verdicts: `healthy` / `tight` / `gap` / `watch`.",
        "",
        "---",
        "",
        "## Fleet",
        "",
    ]
    for f in FLEET:
        lines += [f"- **{f['name']}** ({f['status']}): {f['note']}", ""]
    lines += ["## Demand", ""]
    for key, d in DEMAND.items():
        lines += [f"- **{key}**: {d['note']}", ""]
    lines += ["---", "", "## Analysis", ""]
    for r in results:
        emoji = {"healthy": "OK", "tight": "TIGHT",
                 "gap": "GAP", "watch": "WATCH"}.get(r["verdict"], "?")
        lines += [
            f"### [{emoji}] {r['dimension']}",
            "",
            f"**Verdict:** {r['verdict']}",
            "",
        ]
        for k, v in r.items():
            if k not in ("dimension", "verdict", "recommendation"):
                lines += [f"- {k}: {v}"]
        lines += ["", f"**Recommendation:** {r['recommendation']}", "",
                  "---", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ecosystem capacity recommendations.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to-altair", action="store_true",
                    help="Drop report in altair-brain inbox for Brian.")
    args = ap.parse_args()

    results = [analyze_inference(), analyze_storage(),
               analyze_build_bandwidth()]
    report = render_report(results)

    if args.dry_run:
        print(report[:2000])
        print("\n... (dry run, nothing written)")
        return 0

    STAGING.mkdir(parents=True, exist_ok=True)
    path = STAGING / "capacity-report-latest.md"
    path.write_text(report)
    print(f"Wrote {path}")
    for r in results:
        print(f"  [{r['verdict'].upper()}] {r['dimension']}: "
              f"{r['recommendation'][:80]}...")

    if args.to_altair:
        dest = Path("/tmp/altair-brain-inbox/inbox")
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            (dest / f"{ts}-capacity-report.md").write_text(
                "# For Brian\n\n" + report)
            print("Dropped in altair-brain inbox.")
        else:
            print("Inbox not cloned; skipping.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
