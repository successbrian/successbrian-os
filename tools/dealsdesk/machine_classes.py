#!/usr/bin/env python3
"""machine_classes.py — the fleet's machine-class registry.

Brian 2026-10-20: "what we are building now is 'ai inference machines'...
we will have other classes of machines: 'web hosting', 'database
hosting', 'scrapers', 'code runners'... and others."

A machine is never good or bad in the abstract — it is MATCHED or
MISMATCHED to a class. Each class is defined by the physics of its
workload, and each gets its own gates and scorer. The inference class's
rejects (an i5 mini, a tower with a small PSU) are first-class citizens
in another class. When the classes disagree with a prose doc, this
module wins.

ONE LAYER SITS ABOVE THE CLASSES: hardware_traps.py. Some hardware is
a hard fail of nature, not of fit — the Tesla K80, the Intel burn-out
class — and it fails in EVERY class, at any price, forever (Brian
2026-10-20: "never never never"). Class scorers run under the trap
registry, never over it.

Each class card: mission, the deciding physics, hard-gate summary,
scorer (module path or None), status. Add a class by adding a card;
write its gates when Brian sets them — do not invent gates for a class
he has not specced.
"""

CLASSES = {
    "ai_inference": {
        "name": "AI inference machines",
        "mission": "Run Colibri / Strata and systems like them: frontier "
                   "MoE models streamed from local NVMe, as owned "
                   "inference lanes (the REAP 150B fleet is this class).",
        "deciding_physics": [
            "NVMe bandwidth: slot count, lane width, controller — experts "
            "stream from disk, so storage IS the memory bus",
            "CPU vector width: AVX2 + FMA + F16C baseline (Colibri is "
            "portable C, ARCH=native); streaming is CPU-bound",
            "best-in-class CPUs only; RAM ceiling sets the expert-cache "
            "endgame; iGPU/Vulkan lanes where the engine supports them",
            "towers double as GPU hosts: V100-class 24GB+ cards, ~150W "
            "power cap, true PCIe Gen3+ x16",
            "network topology: inference machines live on their OWN "
            "network(s) — cluster/expert traffic never touches the main "
            "network; the wider ecosystem feeds jobs in and receives "
            "final answers over the main network, and that is the only "
            "traffic that crosses (Brian 2026-10-20)",
            "access doctrine: outsiders (anyone not on our Tailscale) "
            "must find it HARD to use the inference machines — services "
            "bind tailnet/fabric interfaces only, tailnet ACLs limit "
            "inference ports to feeder/operator devices, COLI_API_KEY "
            "always set, no Funnel, fabric segments carry no internet "
            "route (Brian 2026-10-20; full doctrine in fleet-map.md)",
        ],
        "hard_gates": "mini_node_scorer.py — price caps per form factor "
                      "(1L $199 / SFF $249 / tower $299), best-CPU gate, "
                      "Raptor Lake + trap registry, tower GPU-host gates",
        "scorer": "tools/dealsdesk/mini_node_scorer.py (+ rack_server_scorer.py)",
        "status": "active — specced 2026-10-20",
    },
    "database_hosting": {
        "name": "Database hosting",
        "mission": "PostgreSQL and friends — ecosystem_central today lives "
                   "on k11-alpha; this class is its dedicated future home.",
        "deciding_physics": [
            "RAM is cache: the working set should live in memory",
            "NVMe endurance (TBW) and power-loss protection — write "
            "durability is the whole job",
            "ECC memory earns its keep here (silent corruption is a "
            "database's worst failure)",
            "cores for connections; storage redundancy over raw size",
        ],
        "hard_gates": "not yet specced",
        "scorer": None,
        "status": "defined — gates await Brian",
    },
    "web_hosting": {
        "name": "Web hosting",
        "mission": "Serve sites and APIs quietly, cheaply, forever.",
        "deciding_physics": [
            "modest CPU is fine — this class ABSORBS the inference "
            "class's rejects (i5 minis are ideal here)",
            "low idle power and small footprint beat peak anything",
            "NIC reliability and uptime over bandwidth bursts",
            "deployment pattern: stateless over the fabric — web roots "
            "and data mounted via NVMe-oF (or NFS) from storage/database-"
            "class nodes; the node is disposable, its local disk barely "
            "matters (Brian 2026-10-20: 'web hosting over fabric' — yes, "
            "it is a thing, and it is this class's natural shape)",
        ],
        "hard_gates": "not yet specced",
        "scorer": None,
        "status": "defined — gates await Brian",
    },
    "scrapers": {
        "name": "Scrapers",
        "mission": "Fetch the web at scale: crawl, monitor, harvest.",
        "deciding_physics": [
            "threads for parallel fetch; RAM per headless-browser "
            "instance is the real ceiling",
            "network throughput and connection churn, not FLOPs",
            "cheap and replaceable beats strong — nodes are expendable",
            "bulk HDD for crawl archives (sourcing floors apply)",
        ],
        "hard_gates": "not yet specced",
        "scorer": None,
        "status": "defined — gates await Brian",
    },
    "code_runners": {
        "name": "Code runners",
        "mission": "Build, test and execute code — CI workers, sandboxes, "
                   "agent tool-runners.",
        "deciding_physics": [
            "single-core burst speed for builds and interpreters",
            "fast NVMe for checkouts, caches and artifacts",
            "RAM for parallel builders; isolation is a feature, "
            "persistence is not (ephemeral by design)",
        ],
        "hard_gates": "not yet specced",
        "scorer": None,
        "status": "defined — gates await Brian",
    },
}


def get_class(class_id):
    """Return the class card dict, or None."""
    return CLASSES.get(str(class_id).strip().lower().replace(" ", "_")
                       .replace("-", "_"))


def class_ids():
    return sorted(CLASSES)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        assert len(CLASSES) >= 5
        assert get_class("ai inference") is CLASSES["ai_inference"]
        assert get_class("code-runners") is CLASSES["code_runners"]
        active = [k for k, v in CLASSES.items() if v["scorer"]]
        assert active == ["ai_inference"], active
        for card in CLASSES.values():
            assert card["mission"] and card["deciding_physics"]
        print("selftest: %d classes, %d active scorer(s) — OK"
              % (len(CLASSES), len(active)))
    else:
        for cid in class_ids():
            card = CLASSES[cid]
            print("%-18s %s [%s]" % (cid, card["name"], card["status"]))
            print("%-18s %s" % ("", card["mission"][:100]))
