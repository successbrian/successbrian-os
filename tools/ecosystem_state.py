"""
Ecosystem State for SuccessBrian OS.

PURPOSE:
    One snapshot of everything Lyra needs to see: fleet, decisions,
    capacity, build plans, and live data as it comes online. Machine-readable
    JSON for Lyra, human-readable markdown for Brian.

WHY:
    Brian's directive: "successbrian-os needs all the inputs so Lyra can
    easily see it all." Lyra is the health monitor and workflow organizer —
    she can't organize what she can't see. This is her input feed.

CALLED BY:
    - tools/sunday_shift.py (weekly)

NOTES:
    Fleet list is still hard-coded; live_health for x79/bravo/epyc nodes,
    blog_placement, and anythingllm sections are stubs until those systems
    feed real data. live_health["k11-alpha"] IS measured (disk + queue
    depths, read-only via kssh) as of 2026-09-28. "Five nodes" includes
    grouped/planned systems. Treat "healthy" verdicts as provisional until
    watchers.py replaces the hard-coded fleet.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "decision_sync"))
from sync import get_decisions, get_build_plan  # noqa: E402
from capacity import FLEET, analyze_inference, analyze_storage  # noqa: E402
from automate.watchers import queue_depths, alpha_disk  # noqa: E402

STAGING = Path(__file__).parent / "staging"


def get_build_plans() -> dict:
    """Pull all *_build_plan tables."""
    plans = {}
    for table in ["x79_cluster_build_plan"]:
        try:
            plans[table] = get_build_plan(table)
        except Exception as e:  # noqa: BLE001
            plans[table] = {"error": str(e)}
    return plans


def get_live_health() -> dict:
    """Measured health for nodes we can reach; stubs for the rest.

    k11-alpha is measured read-only via kssh right now. Other nodes keep
    the published schema until their telemetry feeds come online.
    """
    schema = {
        "node": "str",
        "cpu_pct": "float", "ram_pct": "float",
        "disk_pct": "float", "gpu_util_pct": "float",
        "vram_used_gb": "float", "temp_c": "float",
        "last_seen": "iso8601",
    }
    health = {
        "x79-node-1..4": {"status": "not_yet_available",
                          "note": "Nodes not built yet.",
                          "schema": schema},
        "k11-bravo": {"status": "not_yet_available",
                      "note": "Node not online yet.", "schema": schema},
        "epyc-rome": {"status": "not_yet_available",
                      "note": "Node not online yet.", "schema": schema},
    }
    try:
        disks = alpha_disk()
        queues = queue_depths()
        health["k11-alpha"] = {
            "status": "measured",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "disk_pct": disks,
            "queues": queues,
            "note": ("Disk + queue depths measured read-only via kssh. "
                     "CPU/RAM/GPU counters not yet wired."),
        }
    except Exception as e:  # noqa: BLE001
        health["k11-alpha"] = {"status": "probe_failed",
                               "note": f"kssh probe failed: {e}"}
    return health


def build_state() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    decisions = get_decisions()

    return {
        "generated_at": now,
        "source": "successbrian-os/tools/ecosystem_state.py",

        # --- Fleet: what exists and what it's for ---
        "fleet": FLEET,

        # --- Decisions: what Brian decided, newest first ---
        "decisions": {
            "count": len(decisions),
            "latest": decisions[0]["decision_id"] if decisions else None,
            "by_topic": {},
            "_raw": decisions,  # consumed by main() for grouping, stripped on write
        },

        # --- Build plans: what's planned vs on hand ---
        "build_plans": get_build_plans(),

        # --- Capacity: can we handle the load? ---
        "capacity": {
            "inference": analyze_inference(),
            "storage": analyze_storage(),
        },

        # --- Stubs: Lyra and the CMS feed these as they come online ---
        "live_health": get_live_health(),
        "blog_placement": {
            "status": "not_yet_available",
            "note": "CMS will populate blog->node assignments.",
            "schema": {
                "domain": "str", "node": "str",
                "plugin_profile": "str", "monthly_visits": "int",
            },
        },
        "anythingllm": {
            "status": "api_key_pending",
            "note": "Library stats once AnythingLLM API access lands.",
        },
    }


def render_markdown(state: dict) -> str:
    lines = [
        "# Ecosystem State",
        "",
        f"**Generated:** {state['generated_at']}",
        "",
        "---",
        "",
        "## Fleet",
        "",
    ]
    for f in state["fleet"]:
        lines += [f"- **{f['name']}** ({f['status']}): {f['note']}", ""]
    lines += ["## Recent Decisions", ""]
    # decisions by_topic filled below
    lines += ["## Capacity", ""]
    for key, cap in state["capacity"].items():
        lines += [f"- **{key}**: {cap['verdict']} — "
                  f"{cap['recommendation'][:120]}...", ""]
    lines += ["## Pending Inputs", ""]
    for key in ("blog_placement", "anythingllm"):
        s = state[key]
        lines += [f"- **{key}**: {s['status']} — {s['note']}", ""]
    lines += ["## Node Health", ""]
    for node, h in state["live_health"].items():
        lines += [f"- **{node}**: {h['status']} — {h['note']}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ecosystem state snapshot.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("Building ecosystem state...")
    state = build_state()

    # Group decisions by topic for the JSON (reuses the fetch in build_state
    # instead of querying twice).
    by_topic: dict[str, list] = {}
    decisions = state["decisions"].pop("_raw")
    for d in decisions:
        by_topic.setdefault(d["topic"], []).append({
            "decision_id": d["decision_id"],
            "question": d["question"],
            "answer": d["answer"][:200],
            "answered_at": d["answered_at"],
        })
    state["decisions"]["by_topic"] = {k: len(v) for k, v in by_topic.items()}
    state["decisions"]["topics"] = by_topic

    if args.dry_run:
        print(json.dumps(state, indent=2)[:2000])
        print("\n... (dry run, nothing written)")
        return 0

    STAGING.mkdir(parents=True, exist_ok=True)
    json_path = STAGING / "ecosystem-state.json"
    md_path = STAGING / "ecosystem-state.md"
    json_path.write_text(json.dumps(state, indent=2))
    md_path.write_text(render_markdown(state))
    print(f"Wrote {json_path} ({json_path.stat().st_size} bytes)")
    print(f"Wrote {md_path}")
    print(f"  Fleet: {len(state['fleet'])} nodes, "
          f"Decisions: {state['decisions']['count']}, "
          f"Topics: {list(by_topic.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
