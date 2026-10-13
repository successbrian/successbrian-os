#!/usr/bin/env python3
"""demand_meter.py — successbrian-os side of the demand -> capacity loop.

Measures per-model demand from real tables (zero tokens, deterministic),
writes successbrian_os.model_demand, and files GENERIC need-signals in
successbrian_os.sbos_need_requests when backlog crosses thresholds.
DealsDesk reads those signals and answers with machines + budget priority.

Generic outputs only — never machine-specific. That is DealsDesk's job.

Models on the board:
  penny, chuck, morpheus   — cheap triage tier (free, local)
  sonic                    — workhorse tier (free, local :11439)
  deepseek-v4-pro          — deep tier (paid cloud; tracked for burn, no machine signal)
  deepseek-150b-reap       — deep tier (planned local)
  qwen-3.8-flash           — deep tier (planned local, Strata)
  glm-5.3-flash            — deep tier (planned local, Strata fork)
  shakespeare              — 70B tier (free, local planned): the content factory is
                           one consumer; the ecosystem can also route 70B-class work
                           to it (difficulty='large' harness jobs)
  vision                   — multimodal (planned, supplied somehow)

Usage: demand_meter.py [--dry-run]
Cron: every 30 min, staggered off other jobs.
"""
import argparse, json, math, subprocess, sys
from datetime import datetime, timezone

PSQL = ["psql", "-h", "localhost", "-U", "successbrian", "-d", "ecosystem_central",
        "-t", "-A", "-F", "\x1f"]
TASK_ID = 73219  # standing capacity task
BRIDGE_SENDER = "successbrian-os"

# queue_depth >= threshold -> file/update a generic need-signal
THRESHOLDS = {
    "sonic":  {"queue_ge": 6, "item": "sonic inference capacity", "priority": 7,
               "spec": ("Generic workload spec (interpreting agent selects hardware): "
                        "24/7 local LLM inference, 35B-class (Qwen3.6-35B-A3B Q6_K or equiv), "
                        "OpenAI-compatible endpoint. qty = concurrent workers needed to drain "
                        "trailing backlog at observed throughput.")},
    "shakespeare": {"queue_ge": 12, "item": "shakespeare 70B inference capacity", "priority": 6,
               "spec": ("Generic workload spec (interpreting agent selects hardware): "
                        "local 70B-class LLM inference (Llama-3.3-70B or equiv). Serves TWO "
                        "consumers: (1) the content factory (blog network batch pipeline), "
                        "which is its own system with its own queue; (2) ecosystem 70B-class "
                        "work routed as difficulty='large' harness jobs — work that beats "
                        "35B quality without burning paid cloud tokens. qty = concurrent "
                        "workers to drain trailing backlog at observed throughput.")},
}

def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"PSQL ERROR: {r.stderr.strip()}", file=sys.stderr)
        return []
    rows = [ln.split("\x1f") for ln in r.stdout.strip().split("\n") if ln.strip()]
    return rows

def scalar(sql, default="0"):
    rows = q(sql)
    return rows[0][0] if rows and rows[0][0] not in ("", None) else default

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    now = datetime.now(timezone.utc).isoformat()

    m = {}
    # --- harness coder demand ---
    m["sonic"] = {
        "tier": "workhorse", "paid": False,
        "queue_depth": int(scalar(
            "SELECT count(*) FROM successbrian_os.harness_jobs "
            "WHERE status IN ('queued','working') AND difficulty='easy'")),
        "throughput_per_hr": float(scalar(
            "SELECT round(count(*)::numeric/24,2) FROM successbrian_os.harness_jobs "
            "WHERE status='done' AND difficulty='easy' "
            "AND completed_at > now() - interval '24 hours'")),
        "est_cost_usd_per_hr": 0.0,
        "note": "coder demand: easy harness jobs",
    }
    hard_q = int(scalar(
        "SELECT count(*) FROM successbrian_os.harness_jobs "
        "WHERE status IN ('queued','working') AND difficulty='hard'"))
    hard_tp = float(scalar(
        "SELECT round(count(*)::numeric/24,2) FROM successbrian_os.harness_jobs "
        "WHERE status='done' AND difficulty='hard' "
        "AND completed_at > now() - interval '24 hours'"))
    # --- v4pro deep demand ---
    handoff_q = int(scalar(
        "SELECT count(*) FROM successbrian_os.v4pro_handoffs "
        "WHERE status IN ('queued','working')"))
    handoff_tp = float(scalar(
        "SELECT round(count(*)::numeric/24,2) FROM successbrian_os.v4pro_handoffs "
        "WHERE status='done' AND completed_at > now() - interval '24 hours'"))
    burn = float(scalar(
        "SELECT round(coalesce(max(usd)-min(usd),0)/24,4) "
        "FROM successbrian_os.v4pro_balance_history "
        "WHERE checked_at > now() - interval '24 hours'", "0"))
    burn = max(burn, 0.0)
    m["deepseek-v4-pro"] = {
        "tier": "deep", "paid": True,
        "queue_depth": hard_q + handoff_q,
        "throughput_per_hr": round(hard_tp + handoff_tp, 2),
        "est_cost_usd_per_hr": burn,
        "note": "coder demand: hard harness jobs + v4pro handoffs; burn from balance history",
    }
    # --- cheap triage tier (estimated from heartbeat cadence until real metering lands) ---
    for cheap in ("penny", "chuck", "morpheus"):
        m[cheap] = {
            "tier": "cheap", "paid": False,
            "queue_depth": 0, "throughput_per_hr": 0.0, "est_cost_usd_per_hr": 0.0,
            "note": "estimated: heartbeat triage cadence; real metering pending",
        }
    # --- planned models: no serving capacity yet ---
    for planned, why in (
        ("deepseek-150b-reap", "planned local: MS-02 + dual B70 per 2026-10-07 approval"),
        ("qwen-3.8-flash", "planned local: Strata on Mantis-3/4 dual-V100"),
        ("glm-5.3-flash", "planned local: Strata fork on Mantis-3/4 dual-V100"),
        ("vision", "planned: multimodal supply TBD"),
    ):
        m[planned] = {"tier": "deep", "paid": False, "queue_depth": 0,
                      "throughput_per_hr": 0.0, "est_cost_usd_per_hr": 0.0,
                      "note": why}
    # --- shakespeare: 70B tier — content factory AND ecosystem demand ---
    # Content side: the content system is its own consumer (os_content_queue backlog).
    # Ecosystem side: harness jobs with difficulty='large' (70B-class work that
    # beats sonic quality without burning paid V4 Pro tokens). Routers may assign
    # difficulty='large'; the meter counts it here.
    content_q = int(scalar(
        "SELECT count(*) FROM public.os_content_queue WHERE status='queued'"))
    brief_q = int(scalar(
        "SELECT count(*) FROM public.content_brief_queue WHERE completed_at IS NULL"))
    large_q = int(scalar(
        "SELECT count(*) FROM successbrian_os.harness_jobs "
        "WHERE status IN ('queued','working') AND difficulty='large'"))
    content_tp = float(scalar(
        "SELECT round(count(*)::numeric/24,2) FROM public.os_content_queue "
        "WHERE published_at > now() - interval '24 hours'"))
    large_tp = float(scalar(
        "SELECT round(count(*)::numeric/24,2) FROM successbrian_os.harness_jobs "
        "WHERE status='done' AND difficulty='large' "
        "AND completed_at > now() - interval '24 hours'"))
    m["shakespeare"] = {
        "tier": "large", "paid": False,
        "queue_depth": content_q + brief_q + large_q,
        "throughput_per_hr": round(content_tp + large_tp, 2),
        "est_cost_usd_per_hr": 0.0,
        "note": (f"70B demand: content queue={content_q} briefs={brief_q} "
                 f"ecosystem-large-jobs={large_q}; content factory is one consumer"),
    }

    # --- write measurements ---
    for model, d in m.items():
        note = d["note"].replace("'", "''")
        sql = (f"INSERT INTO successbrian_os.model_demand "
               f"(model, tier, queue_depth, throughput_per_hr, est_cost_usd_per_hr, paid, note) "
               f"VALUES ('{model}','{d['tier']}',{d['queue_depth']},{d['throughput_per_hr']},"
               f"{d['est_cost_usd_per_hr']},{str(d['paid']).lower()},'{note}')")
        if dry:
            print(f"DRY-RUN insert: {model} q={d['queue_depth']} tp/hr={d['throughput_per_hr']} $/hr={d['est_cost_usd_per_hr']}")
        else:
            q(sql)
    print(f"[{now}] measured {len(m)} models")

    # --- threshold -> generic need-signals ---
    signals = []
    for model, th in THRESHOLDS.items():
        depth = m[model]["queue_depth"]
        if depth >= th["queue_ge"]:
            qty = max(1, math.ceil(depth / 4))
            spec = f"{th['spec']} measured_at={now} queue_depth={depth} throughput_per_hr={m[model]['throughput_per_hr']}"
            signals.append((th["item"], spec, qty, th["priority"]))

    for item, spec, qty, prio in signals:
        item_e = item.replace("'", "''"); spec_e = spec.replace("'", "''")
        existing = q(f"SELECT id, qty FROM successbrian_os.sbos_need_requests "
                     f"WHERE item='{item_e}' AND status='new' ORDER BY id DESC LIMIT 1")
        if dry:
            print(f"DRY-RUN signal: {item} qty={qty} prio={prio} (existing={existing})")
            continue
        if existing:
            nid, old_qty = existing[0]
            if int(old_qty) != qty:
                q(f"UPDATE successbrian_os.sbos_need_requests SET qty={qty}, "
                  f"specs='{spec_e}', updated_at=now() WHERE id={nid}")
                print(f"updated need-signal #{nid} {item} qty {old_qty}->{qty}")
            else:
                print(f"need-signal #{nid} {item} unchanged (qty={qty})")
        else:
            nid = scalar(f"INSERT INTO successbrian_os.sbos_need_requests "
                         f"(task_id, item, specs, qty, priority, status) "
                         f"VALUES ({TASK_ID},'{item_e}','{spec_e}',{qty},{prio},'new') RETURNING id")
            print(f"filed need-signal #{nid}: {item} qty={qty} prio={prio}")
            # SCREAM on the live bridge per need-signal rules
            body = (f"NEED SIGNAL #{nid}: {item} (qty={qty}, priority={prio}). "
                    f"{spec}").replace("'", "''")
            q(f"INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
              f"VALUES ('{BRIDGE_SENDER}','dealsdesk','NEED: {item_e}','{body}','important')")
            print("screamed on bridge -> dealsdesk")

    if not signals:
        print("no thresholds crossed — no signals")

if __name__ == "__main__":
    main()
