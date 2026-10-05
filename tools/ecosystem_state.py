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
    Fleet list comes from tools/fleet_registry.json (single source of truth),
    not from capacity.py's old hard-coded FLEET. live_health["k11-alpha"] is
    measured read-only via kssh: disk pct, queue depths, 1-min CPU load, RAM
    pct (2026-10-04). GPU/temp counters are NOT measured — k11-alpha's GPU is
    the 780M iGPU; no verified telemetry source yet, so they're marked
    not_measured rather than zeroed. bravo/x79/epyc nodes were VERIFIED
    absent from the tailnet 2026-10-04 (not_on_tailnet), which is stronger
    than the old "not yet built" guess. blog_placement and anythingllm are
    explicit NOT-IMPLEMENTED stubs with a `needs` field saying what unblocks
    them.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "decision_sync"))
from sync import get_decisions, get_build_plan  # noqa: E402
from capacity import analyze_inference, analyze_storage  # noqa: E402
from automate.watchers import queue_depths, alpha_disk  # noqa: E402
from automate.engine import kssh  # noqa: E402

STAGING = Path(__file__).parent / "staging"
REGISTRY = Path(__file__).parent / "fleet_registry.json"


def get_fleet() -> list[dict]:
    """Fleet inventory from the canonical registry.

    Reads tools/fleet_registry.json every run so the snapshot can never
    drift behind an edited copy of the list. A missing/corrupt registry is
    a hard failure — a silent hard-coded fallback would be the old bug
    all over again.
    """
    return json.loads(REGISTRY.read_text())["fleet"]


def get_build_plans() -> dict:
    """Pull all *_build_plan tables."""
    plans = {}
    for table in ["x79_cluster_build_plan"]:
        try:
            plans[table] = get_build_plan(table)
        except Exception as e:  # noqa: BLE001
            plans[table] = {"error": str(e)}
    return plans


def _probe_alpha_cpu_ram() -> dict:
    """1-min load average + RAM % on k11-alpha, read-only via kssh.

    Returns {"error": ...} when the probe fails — unknown is reported as
    unknown, never as 0.
    """
    try:
        load = kssh("cat /proc/loadavg | awk '{print $1, $2, $3}'", timeout=20)
        mem = kssh("free -m | awk '/^Mem:/ {print $2, $3}'", timeout=20)
        total_mb, used_mb = (float(x) for x in mem.split())
        return {
            "cpu_load_1m": float(load.split()[0]),
            "ram_pct": round(used_mb / total_mb * 100, 1),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def get_live_health() -> dict:
    """Measured health for nodes we can reach; explicit NOT-IMPLEMENTED
    markers for the rest.

    Statuses: measured | probe_failed | not_on_tailnet | not_implemented.
    A status of not_on_tailnet was verified against `tailscale status` on
    k11-alpha (2026-10-04) — it means no tailnet presence, i.e. the node is
    not reachable, whatever its physical build state.
    """
    schema = {
        "node": "str",
        "cpu_pct": "float", "ram_pct": "float",
        "disk_pct": "float", "gpu_util_pct": "float",
        "vram_used_gb": "float", "temp_c": "float",
        "last_seen": "iso8601",
    }
    verified_note = ("Verified absent from tailnet 2026-10-04 "
                     "(`tailscale status` on k11-alpha).")
    health = {
        "x79-node-1..4": {"status": "not_on_tailnet",
                          "note": verified_note + " Content factory nodes "
                          "not built yet.",
                          "schema": schema},
        "k11-bravo": {"status": "not_on_tailnet",
                      "note": verified_note + " Build runbook drafted "
                      "2026-10-03; build window was Sun 2026-10-04 "
                      "2:00 AM-2:30 PM Idemia shift — no tailnet sign-in yet.",
                      "schema": schema},
        "epyc-rome": {"status": "not_on_tailnet",
                      "note": verified_note + " Evaluating; role TBD after "
                      "the 2026-10-03 Qwen A3B switch scrapped the 150B tier.",
                      "schema": schema},
        "aoostar-1..2": {"status": "not_on_tailnet",
                         "note": verified_note + " Planned rack nodes.",
                         "schema": schema},
    }
    try:
        disks = alpha_disk()
        queues = queue_depths()
        cpu_ram = _probe_alpha_cpu_ram()
        health["k11-alpha"] = {
            "status": "measured",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "disk_pct": disks,
            "queues": queues,
            "cpu_load_1m": cpu_ram.get("cpu_load_1m"),
            "ram_pct": cpu_ram.get("ram_pct"),
            "gpu_util_pct": "not_measured",
            "temp_c": "not_measured",
            "note": ("Disk + queues + CPU load + RAM measured read-only via "
                     "kssh. GPU/temp: no verified telemetry source on "
                     "k11-alpha (780M iGPU) yet — marked not_measured, not 0."),
        }
        if "error" in cpu_ram:
            health["k11-alpha"]["cpu_ram_probe"] = cpu_ram["error"]
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

        # --- Fleet: what exists and what it's for (canonical registry) ---
        "fleet": get_fleet(),

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

        # --- Live node health: measured for k11-alpha, explicit markers else ---
        "live_health": get_live_health(),

        # --- NOT-IMPLEMENTED stubs: schema published, feed not wired ---
        "blog_placement": {
            "status": "not_implemented",
            "needs": ("CMS feed of blog->node assignments. The blog network "
                      "content factory is not built yet (x79 nodes: "
                      "not_on_tailnet), so there is nothing to place."),
            "schema": {
                "domain": "str", "node": "str",
                "plugin_profile": "str", "monthly_visits": "int",
            },
        },
        "anythingllm": {
            "status": "not_implemented",
            "needs": ("AnythingLLM API access (api_key_pending since before "
                      "2026-09-28). Once granted: workspace/document counts, "
                      "embedding backlog, dedup stats."),
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
        "## Fleet (tools/fleet_registry.json)",
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
    lines += ["## Pending Inputs (NOT-IMPLEMENTED)", ""]
    for key in ("blog_placement", "anythingllm"):
        s = state[key]
        lines += [f"- **{key}**: {s['status']} — {s['needs']}", ""]
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
