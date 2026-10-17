#!/usr/bin/env python3
"""Seed cron_registry from the live crontab (unenriched), then hand-enrich
the key dependency chains."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scheduler import live_crontab, register, pg_exec  # noqa: E402


def main():
    pg_exec(open(os.path.join(os.path.dirname(__file__),
                              "schema.sql")).read())
    live = live_crontab()
    seen = set()
    for sched, name, cmd in live:
        if name in seen:
            continue
        seen.add(name)
        register(name, sched, purpose="", weight="unknown",
                 command=cmd[:500])
    print(f"imported {len(seen)} jobs")

    # --- hand-enriched chains (verified 2026-10-17) ---
    chains = [
        # signals -> screams -> deals
        ("collect_watchdog.py", "3,18,33,48 * * * *",
         "fast infra signal collection", "light", [], ["derive_needs.py"],
         "signals"),
        ("collect_infra.py", "13 * * * *",
         "slow infra signal collection", "light", [], ["derive_needs.py"],
         "signals"),
        ("derive_needs.py", "8,23,38,53 * * * *",
         "signals -> screams in sbos_need_requests", "light",
         ["collect_watchdog.py", "collect_infra.py"],
         ["replan_deals.py", "need_reader.py"], "signals", 5),
        ("replan_deals.py", "40 * * * *",
         "score deal candidates per need", "light",
         ["derive_needs.py"], ["need_reader.py"], "deals", 2),
        ("need_reader.py", "50 * * * *",
         "claim needs, budget-check via pm_bridge", "light",
         ["derive_needs.py", "replan_deals.py"], [], "deals"),
        # pm master
        ("pm_loop.py", "22,52 * * * *",
         "autonomous PM event loop", "light", [], [], "pm"),
        ("build_pm_master_fragment.py", "45 5 * * *",
         "dashboard PM Master tab fragment", "light", ["pm_loop.py"],
         [], "pm"),
        # business memory
        ("core.py", "47 * * * *",
         "business_core context packet builder (hourly)", "light",
         [], [], "memory"),
        ("gap_watch.py", "12 4 * * * / 27 4 * * *",
         "business map gap + staleness watch", "light", [], [], "memory"),
        # dashboard
        ("build_unified_inbox.py", "15 * * * *",
         "unified inbox fragment builder", "light", [], [], "dashboard"),
    ]
    for chain in chains:
        name, sched, purpose, weight, up, down, area = chain[:7]
        gap = chain[7] if len(chain) > 7 else 10
        register(name, sched, purpose=purpose, weight=weight,
                 upstream=up, downstream=down, area=area, enriched=True,
                 min_gap=gap)
    print(f"enriched {len(chains)} chain jobs")


if __name__ == "__main__":
    main()
