"""
Capacity recommendations for SuccessBrian OS.

PURPOSE:
    Watch ecosystem capacity vs demand and tell Brian what to buy, build,
    or repurpose — before he hits the wall.

WHY:
    Brian is building a 100-blog network plus local AI inference on a
    hardware budget. The scarcest resources are GPU time, NVMe streaming
    bandwidth, and Brian's own build hours (two jobs). Guessing wrong means
    buying hardware he doesn't need or stalling content on a bottleneck.
    This tool turns "do we have enough?" into a number.

CALLED BY:
    - tools/sunday_shift.py (weekly, feeds the 7:30 briefing)
    - tools/ecosystem_state.py (capacity section of the state snapshot)

NOTES:
    Fleet inventory and demand figures come from tools/fleet_registry.json —
    the single source of truth. Every number carries a *_source tag
    (measured / by_design / plan_target / plan_stated / estimate_unverified);
    the report prints the tags, so Brian can see which verdicts rest on
    measurements and which rest on guesses. Verdicts are directional.
    Source tags marked estimate_unverified list what would verify them in
    the registry's *_verifies_when notes.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


STAGING = Path(__file__).parent / "staging"
REGISTRY = Path(__file__).parent / "fleet_registry.json"


def _load_registry() -> dict:
    """Read the canonical fleet registry. Raises if missing/corrupt —
    a hard-coded fallback list would silently drift, which is exactly the
    bug this registry exists to kill."""
    return json.loads(REGISTRY.read_text())


_REG = _load_registry()

# ---------------------------------------------------------------------------
# Fleet inventory + demand — read from the registry, kept as module-level
# names because ecosystem_state.py imports them.
# ---------------------------------------------------------------------------
FLEET: list[dict] = _REG["fleet"]


def _demand_blog_network(reg: dict) -> dict:
    d = reg["demand"]["blog_network"]
    articles_per_day = d["blogs"] * d["articles_per_blog_per_day"]
    tok_s_needed = (articles_per_day * d["tokens_per_article"]
                    / (d["batch_window_hours"] * 3600))
    return {
        "articles_per_day": articles_per_day,
        "tokens_per_article": d["tokens_per_article"],
        "batch_window_hours": d["batch_window_hours"],
        "tok_s_needed": tok_s_needed,
        "source": ("plan_stated (blog count) + plan_target (articles/day, "
                   "batch window) + estimate_unverified (tokens/article)"),
        "note": (f"{d['blogs']} blogs x {d['articles_per_blog_per_day']} "
                 f"articles/day, {d['batch_window_hours']}h overnight batch "
                 f"window."),
    }


DEMAND = {
    "blog_network": _demand_blog_network(_REG),
    "anythingllm_maintenance": _REG["demand"]["anythingllm_maintenance"],
}

STORAGE_PLAN = _REG["storage_plan"]


def _x79_node_count() -> tuple[int, str]:
    """Planned X79 node count, parsed from the registry fleet name."""
    for f in FLEET:
        if f["name"].startswith("x79"):
            m = re.search(r"(\d+)\.\.(\d+)", f["name"])
            if m:
                return int(m.group(2)) - int(m.group(1)) + 1, "derived_from_registry"
    return 4, "fallback_default"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_inference() -> dict:
    planned_batch = sum(f["batch_tok_s"] for f in FLEET
                        if f["status"] in ("planned", "live"))
    needed = DEMAND["blog_network"]["tok_s_needed"]
    headroom = planned_batch - needed
    sources = sorted({f.get("batch_tok_s_source", "UNKNOWN") for f in FLEET
                      if f["status"] in ("planned", "live")})
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
        "available_source": "+".join(sources),
        "needed_tok_s": round(needed, 1),
        "needed_source": DEMAND["blog_network"]["source"],
        "headroom_tok_s": round(headroom, 1),
        "verdict": verdict,
        "recommendation": rec,
    }


def analyze_storage() -> dict:
    nvme_tb = STORAGE_PLAN["x79_nvme_tb"]
    model_hot_gb = STORAGE_PLAN["model_hot_gb"]
    verdict = "healthy"
    rec = (f"{nvme_tb}TB NVMe planned ({STORAGE_PLAN['x79_nvme_tb_note']}) vs "
           f"~{model_hot_gb}GB hot models. Ample. SATA tier sizes still open "
           f"(see X79 Q3 for Brian).")
    return {
        "dimension": "storage",
        "nvme_tb_planned": nvme_tb,
        "nvme_tb_source": STORAGE_PLAN["x79_nvme_tb_source"],
        "model_hot_gb": model_hot_gb,
        "model_hot_gb_source": STORAGE_PLAN["model_hot_gb_source"],
        "verdict": verdict,
        "recommendation": rec,
    }


def analyze_web_serving() -> dict:
    blogs = _REG["demand"]["blog_network"]["blogs"]
    x79_count, x79_src = _x79_node_count()
    sites_per_node = blogs // x79_count if x79_count else None
    # Static vs WordPress load reasoning is architectural (by_design), not
    # measured — the verdict stays "watch" until Brian picks the stack.
    verdict = "watch"
    rec = ("Architecture decision needed: static-site generator (Hugo/Jekyll "
           "-> nginx) vs WordPress. Static: "
           f"{sites_per_node} sites/node is trivial, near-zero maintenance, "
           "perfect for SEO content blogs. WordPress: "
           f"{sites_per_node} PHP pools + {sites_per_node} DBs per node "
           "strains 64GB DDR3 and creates 100 installs to patch. "
           "Recommendation: static unless a specific blog needs WP features. "
           "This is a question for Brian.")
    return {
        "dimension": "web_serving",
        "sites_per_node": sites_per_node,
        "sites_per_node_source": (f"derived: {blogs} plan_stated blogs / "
                                  f"{x79_count} x79 nodes ({x79_src})"),
        "stack_options": "static (Hugo->nginx) vs WordPress",
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
        "Numbers carry source tags (measured / by_design / plan_target / "
        "plan_stated / estimate_unverified) — trust measured and by_design, "
        "treat the rest as planning figures.",
        "",
        "---",
        "",
        "## Fleet (from tools/fleet_registry.json)",
        "",
    ]
    for f in FLEET:
        src = f.get("batch_tok_s_source")
        tag = f" [throughput: {src}]" if src and src != "by_design" else ""
        ver = f.get("verified", "")
        ver_tag = f" (verified: {ver})" if ver else ""
        lines += [f"- **{f['name']}** ({f['status']}){tag}: {f['note']}{ver_tag}", ""]
    lines += ["## Demand", ""]
    for key, d in DEMAND.items():
        src = d.get("source", "")
        lines += [f"- **{key}** [source: {src}]: {d['note']}", ""]
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

    results = [analyze_inference(), analyze_storage(), analyze_web_serving(),
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
        # /tmp/altair-brain-inbox is dead on this VM (fixed 2026-09-27):
        # the durable clone lives at ~/workspace/altair-brain.
        dest = Path.home() / "workspace" / "altair-brain" / "inbox"
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
