#!/usr/bin/env python3
"""ownership_guard.py — the ownership rule, in code.

THE RULE (Brian 2026-11-24): "you cannot plan that we own anything
UNTIL I tell you we own it."

THE CONCEPT: the fleet records (public.owned_hardware,
public.ai_inventory, the roadmaps, the architecture docs) mix three
different things — machines Brian has, machines on paper, and build
specs — and their own status columns do not attest ownership. On
2026-11-24 a Dell R630 that exists only as an unclosed roadmap
purchase from Aaron was written into a plan as a landing zone,
because a roadmap line named it as one. This module exists so that
can never happen silently again: Brian will forget what he attested,
and the code must not.

THE SECOND AXIS (Brian 2026-11-24, later): "I can feel strongly
about a buy and tell the system I'm ready to make the buy. But the
buy is not owned until I specifically state the item is owned...
you can add levels of decision, but ownership is a clear change.
owned is owned." So this module tracks TWO axes that never touch:
DECISION LEVEL (watching -> interested -> planning -> ready_to_buy
-> parts_ordered -> ordered) records how strong the intent is, and
OWNERSHIP (the verdict) records whether Brian has stated the item
is owned. No decision level, however strong — not 'ready_to_buy',
not parts ordered, not money spent — moves the ownership axis one
millimetre. The only crossing is Brian's explicit statement, which
is why attest() below refuses to run without his words. DealsDesk
already speaks this way (trend_engine.py: a fired buy_trigger flips
a build to buy_timing='buy_now' and notes 'Brian still makes every
purchase decision'); this module makes the separation universal.

THE REGISTRY BELOW is the enforceable source of truth for ownership.
An item is PLANNING-ELIGIBLE only if it appears here as
attested_owned, on the strength of Brian's own statement (quoted or
cited in the entry's source). Everything else — unconfirmed claims,
planned/paper machines, and names the registry has never heard of —
is NOT eligible. Unknown is not a soft yes: not knowing is not
owning, and the default is deny.

An entry changes only on Brian's ruling: his attestation adds an
item to attested_owned; his word moves or removes anything else.
Corrections to the registry cite the ruling, the way the register
doc does.

CALLED BY: any planner, in code:
             from ownership_guard import require_planning_eligible
             require_planning_eligible("Mantis-9")   # raises if not
           Manually:
             python3 ownership_guard.py Mantis-9 R630   (check mode)
             python3 ownership_guard.py --list
             python3 ownership_guard.py --audit   (scan the live tables)
             python3 ownership_guard.py --selftest

NOTES:   - Prose rationale and the full audit live in
           docs/ownership-register-2026-11-24.md; this file wins on
           conflict, per the hardware_traps.py precedent.
         - DealsDesk builds (dealsdesk.builds) are plans by
           construction — their statuses are plan vocabulary — so
           they need no registry entries; the audit reports them as
           plans and never as machines.
         - CANONICAL SOURCE: successbrian-os/tools/ownership_guard.py
"""

import argparse
import re
import sys

ATTESTED = "attested_owned"
UNCONFIRMED = "unconfirmed"
PLANNED = "planned_not_owned"
UNKNOWN = "unknown"

# Decision levels: the INTENT axis, weakest to strongest. This axis
# is real and worth recording — and it is not the ownership axis.
# An entry may carry a decision level OR an attested verdict, never
# both: when Brian attests ownership, the decision field comes off
# in the same edit (selftest enforces this).
DECISION_LEVELS = ["watching", "interested", "planning",
                   "ready_to_buy", "parts_ordered", "ordered"]
HIGH_INTENT = {"ready_to_buy", "parts_ordered", "ordered"}

# --- The registry -------------------------------------------------------------
# Each entry: id, verdict, names (every spelling the item carries in any
# system — owned_hardware names, ai_inventory node_ids, seat machine
# names, doc names), source (Brian's attestation, or where the claim
# lives), and a note. Names are matched normalized (case/punct-insensitive).

REGISTRY = [
    # -- Brian-attested owned: the only planning-eligible set -----------------
    {"id": "dl380_gen8_1", "verdict": ATTESTED,
     "names": ["DL380-Gen8-1", "Mantis-9", "dl380-g8-01", "HPE DL380 Gen8-01"],
     "source": "Brian, session 2026-11-23: dual CPUs, dual 750W PSUs, 8x SFF bays attested in detail",
     "note": "DL380p Gen8, Proxmox, Colibri slices (Mantis-9)."},
    {"id": "dl380_gen8_2", "verdict": ATTESTED,
     "names": ["DL380-Gen8-2", "Mantis-10", "dl380-g8-02", "HPE DL380 Gen8-02"],
     "source": "Brian, session 2026-11-23: same attestation as Gen8-1",
     "note": "DL380p Gen8, Proxmox, Colibri slices (Mantis-10)."},
    {"id": "k11_alpha", "verdict": ATTESTED,
     "names": ["K11-Alpha", "k11-alpha"],
     "source": "Brian's working machine throughout the record",
     "note": "GMKtec K11, Ryzen 9 8945HS, 96GB (owned_hardware CPU corrected 2026-11-24)."},
    {"id": "k11_bravo", "verdict": ATTESTED,
     "names": ["K11-Bravo", "K11 Bravo", "K11-BRAVO"],
     "source": "Brian, 2026-11-24 rack-population statement ('bravo')",
     "note": "GMKtec K11, Ryzen 9 8945HS, 96GB."},
    {"id": "k11_gmktec_units", "verdict": ATTESTED,
     "names": ["gmk-k11-01", "gmk-k11-02", "GMKtec K11-01", "GMKtec K11-02"],
     "source": "Brian attested the two K11 units (Alpha and Bravo); these are ai_inventory spellings of them",
     "note": "1:1 mapping of gmk-k11-01/02 to Alpha/Bravo is NOT established; the pair is attested, the mapping is not."},
    {"id": "aoostar_6850h_1", "verdict": ATTESTED,
     "names": ["MACO-6850H-001", "Aoostar-Charlie1", "Aoostar MACO R7 6850H #1"],
     "source": "Brian, 2026-11-24 ('the two aoostars'); matches his standing description (680M, 24GB)",
     "note": "Aoostar MACO, Ryzen 7 6850H, 24GB."},
    {"id": "aoostar_6850h_2", "verdict": ATTESTED,
     "names": ["MACO-6850H-002", "Aoostar-Charlie2", "Aoostar MACO R7 6850H #2"],
     "source": "Brian, 2026-11-24 ('the two aoostars')",
     "note": "Aoostar MACO, Ryzen 7 6850H, 24GB."},
    {"id": "gertoli_1", "verdict": ATTESTED,
     "names": ["Gertoli-1", "Gertoli 1"],
     "source": "Brian, 2026-10-25 and 2026-11-24 ('the two gertolis')",
     "note": "Attested but recorded in NO table — identity/specs unconfirmed (register D6, residue R6)."},
    {"id": "gertoli_2", "verdict": ATTESTED,
     "names": ["Gertoli-2", "Gertoli 2"],
     "source": "Brian, 2026-10-25 and 2026-11-24",
     "note": "Attested but recorded in NO table — identity/specs unconfirmed (register D6, residue R6)."},
    {"id": "tesla_m40_one", "verdict": ATTESTED,
     "names": ["Tesla M40 24GB", "Tesla M40", "M40 24GB", "M40"],
     "source": "Brian has confirmed owning an M40 (record, 2026-11)",
     "note": "EXACTLY ONE attested. Any count above one is unconfirmed, however many build specs claim M40s."},

    # -- Claimed in the records, never attested by Brian ----------------------
    {"id": "veriton_sff_1", "verdict": UNCONFIRMED,
     "names": ["Veriton SFF-1"],
     "source": "owned_hardware 'active' (bulk-seeded 2026-07-19); hardware-2026-10-07 lists Veriton SFFs as fleet",
     "note": "Residue R1. i5-8500T, RTX A2000 12GB per the table."},
    {"id": "veriton_sff_2", "verdict": UNCONFIRMED,
     "names": ["Veriton SFF-2"],
     "source": "owned_hardware 'active' (bulk-seeded 2026-07-19)",
     "note": "Residue R1. i5-8500T, RTX A2000 6GB per the table."},
    {"id": "x79_node_1", "verdict": UNCONFIRMED,
     "names": ["X79-Node-1"],
     "source": "owned_hardware 'active'",
     "note": "Residue R2 — see the X79 three-way conflict, register D4."},
    {"id": "x79_node_2", "verdict": UNCONFIRMED,
     "names": ["X79-Node-2"],
     "source": "owned_hardware 'active'",
     "note": "Residue R2 — register D4."},
    {"id": "b250_mining_1", "verdict": UNCONFIRMED,
     "names": ["B250-Mining-1"],
     "source": "owned_hardware 'active'",
     "note": "Residue R3."},
    {"id": "m1_mac_mini", "verdict": UNCONFIRMED,
     "names": ["M1 Mac Mini", "M1-MAC-MINI"],
     "source": "owned_hardware 'active'; ai_inventory 'active'; hardware-2026-10-07 lists it",
     "note": "Residue R4."},
    {"id": "aoostar_7840hs_1", "verdict": UNCONFIRMED,
     "names": ["aoostar-maco-01", "Aoostar MACO-01"],
     "source": "ai_inventory 'maintenance'; hardware-2026-10-07 lists '2x Aoostar 7840HS' as fleet",
     "note": "Residue R5 — Brian attests two Aoostars (the 6850H pair); a second pair is unconfirmed."},
    {"id": "aoostar_7840hs_2", "verdict": UNCONFIRMED,
     "names": ["aoostar-maco-02", "Aoostar MACO-02"],
     "source": "ai_inventory 'maintenance'; hardware-2026-10-07",
     "note": "Residue R5."},
    {"id": "x79_build_01", "verdict": UNCONFIRMED,
     "names": ["x79-01", "X79 Build-01"],
     "source": "ai_inventory 'maintenance' — a build SPEC (128GB, 2x M40)",
     "note": "A spec is not a machine. Register D4."},
    {"id": "x79_build_02", "verdict": UNCONFIRMED,
     "names": ["x79-02", "X79 Build-02"],
     "source": "ai_inventory 'maintenance' — a build SPEC",
     "note": "Register D4."},
    {"id": "x79_build_03", "verdict": UNCONFIRMED,
     "names": ["x79-03", "X79 Build-03"],
     "source": "ai_inventory 'maintenance' — a build SPEC",
     "note": "Register D4."},
    {"id": "x79_build_04", "verdict": UNCONFIRMED,
     "names": ["x79-04", "X79 Build-04"],
     "source": "ai_inventory 'maintenance' — a build SPEC",
     "note": "Register D4."},
    {"id": "node_echo", "verdict": UNCONFIRMED, "decision": "planning",
     "names": ["Node Echo", "node-echo"],
     "source": "Split records: owned_hardware 'planned' vs ai_inventory 'active' (set to 'unconfirmed' 2026-11-24); roadmap 0.2 frames it as a purchase. Components attested by Brian 2026-11-24.",
     "attested_components": ["Supermicro X11SAE-F motherboard", "Intel Xeon E3-1245 v6 CPU"],
     "note": "Residue R8. The MACHINE is not owned. COMPONENTS ATTESTED by Brian 2026-11-24 ('i already own the board and the cpu -- i just need memory, drives'): the board and CPU are Brian-attested owned. Memory and drives are the stated need, not owned. Chassis, PSUs, Noctua cooling and rails are not individually attested \u2014 register D1."},

    # -- Planned / paper: the records themselves agree these are not owned ----
    {"id": "k11_zeus", "verdict": PLANNED, "decision": "planning",
     "names": ["K11-Zeus"],
     "source": "owned_hardware status 'planned', location 'planned'",
     "note": "A paper EPYC/MI50 design in a table named owned_hardware — the trap this guard exists for."},
    {"id": "precision_3620", "verdict": PLANNED, "decision": "parts_ordered",
     "names": ["Precision 3620"],
     "source": "owned_hardware status 'planned'",
     "note": "Residue R9. DealsDesk is assigned to it in its workload_profile — an assignment to a planned machine (register D5)."},
    {"id": "smc_4u_1", "verdict": PLANNED,
     "names": ["smc-4u-e5v2-01", "Supermicro 4U E5-2650v2-01"],
     "source": "ai_inventory source 'planned', details 'PENDING BUILD'",
     "note": ""},
    {"id": "smc_4u_2", "verdict": PLANNED,
     "names": ["smc-4u-e5v2-02", "Supermicro 4U E5-2650v2-02"],
     "source": "ai_inventory source 'planned', details 'PENDING BUILD'",
     "note": ""},
    {"id": "smc_4u_3", "verdict": PLANNED,
     "names": ["smc-4u-e5v2-03", "Supermicro 4U E5-2650v2-03"],
     "source": "ai_inventory source 'planned', details 'PENDING BUILD'",
     "note": ""},
    {"id": "smc_4u_4", "verdict": PLANNED,
     "names": ["smc-4u-e5v2-04", "Supermicro 4U E5-2650v2-04"],
     "source": "ai_inventory source 'planned', details 'PENDING BUILD'",
     "note": ""},
    {"id": "smc_2027tr_1", "verdict": PLANNED, "decision": "watching",
     "names": ["smc-2027tr-01", "Supermicro 2027TR-01 (4-Node)"],
     "source": "ai_inventory source 'ebay', details 'PENDING_PURCHASE'",
     "note": ""},
    {"id": "smc_2027tr_2", "verdict": PLANNED, "decision": "watching",
     "names": ["smc-2027tr-02", "Supermicro 2027TR-02 (4-Node)"],
     "source": "ai_inventory source 'ebay', details 'PENDING_PURCHASE'",
     "note": ""},
    {"id": "dell_r630", "verdict": PLANNED, "decision": "planning",
     "names": ["Dell R630", "R630", "PowerEdge R630"],
     "source": "fleet-roadmap 0.1 only: an unclosed purchase from Aaron; no table row anywhere",
     "note": "The 2026-11-24 specimen: planned on as a landing zone before this guard existed."},
]


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _build_index():
    index = {}
    for entry in REGISTRY:
        for name in entry["names"]:
            key = _norm(name)
            if key in index and index[key]["id"] != entry["id"]:
                raise ValueError(
                    f"ownership registry: name {name!r} claimed by both "
                    f"{index[key]['id']} and {entry['id']}")
            index[key] = entry
    return index


_INDEX = _build_index()


def verdict(name):
    """Return (verdict, entry-or-None) for any spelling of an item."""
    entry = _INDEX.get(_norm(name))
    if entry is None:
        return UNKNOWN, None
    return entry["verdict"], entry


def planning_eligible(name):
    """True only for Brian-attested ownership. Default is deny."""
    return verdict(name)[0] == ATTESTED


def is_owned(name):
    """Ownership, full stop. Decision level is never consulted here:
    feeling strongly about a buy, planning it, ordering parts, and
    spending the money are all intent. Owned is owned (Brian,
    2026-11-24) — and owned means Brian stated it."""
    return verdict(name)[0] == ATTESTED


def decision_level(name):
    """The INTENT axis: how strong the decision is, or None. Reading
    this can never substitute for is_owned() — the axes do not touch."""
    _, entry = verdict(name)
    if entry is None:
        return None
    return entry.get("decision")


def attest(item_id, names, statement, note=""):
    """The ONLY sanctioned crossing from intent to ownership.

    Brian's rule makes ownership a clear change that happens when he
    specifically states the item is owned — so this function refuses
    to build an attested entry without his statement, verbatim, to
    cite as the source. It returns the registry entry to commit; the
    human or agent making the edit still makes it deliberately, in
    the open, with the statement attached.
    """
    if not statement or "brian" not in statement.lower():
        raise ValueError(
            "attest() requires Brian's own statement that the item is "
            "owned, quoted or cited. Intent, however strong, is not "
            "ownership, and no other evidence crosses this line.")
    return {"id": item_id, "verdict": ATTESTED, "names": list(names),
            "source": statement, "note": note}


class OwnershipError(Exception):
    pass


def require_planning_eligible(name):
    """The gate planners call. Returns the registry entry or raises."""
    v, entry = verdict(name)
    if v != ATTESTED:
        detail = entry["source"] if entry else "not in the ownership registry"
        raise OwnershipError(
            f"{name!r} is not planning-eligible (verdict: {v}). "
            f"Brian's rule (2026-11-24): plan only on what he says we "
            f"own. Source: {detail}")
    return entry


# --- Audit: the registry against the live record ------------------------------

EXISTENCE_STATUSES_AI = {"active", "standby", "idle", "maintenance"}


def audit(conn):
    """Scan the live tables. Returns (violations, claims, notes, intent).

    Violations = planning or an existence claim resting on an
    unattested machine, or the two tables contradicting each other
    about the same machine. Claims = existence-flavored rows Brian
    has not attested (the known residue — reported, not failed).
    """
    cur = conn.cursor()
    violations, claims, notes = [], [], []

    cur.execute("SELECT name, status FROM public.owned_hardware ORDER BY id")
    oh = {r["name"]: r["status"] for r in cur.fetchall()}
    cur.execute("SELECT node_id, node_name, status FROM public.ai_inventory "
                "ORDER BY id")
    ai = {r["node_id"]: r for r in cur.fetchall()}

    oh_by_entry, ai_by_entry = {}, {}
    for name, status in oh.items():
        v, entry = verdict(name)
        if entry:
            oh_by_entry[entry["id"]] = (name, status)
        if status == "active" and v != ATTESTED:
            claims.append(f"owned_hardware: {name} is 'active' but "
                          f"verdict is {v} (unattested claim)")
        if status == "planned" and v == ATTESTED:
            violations.append(f"owned_hardware: {name} is 'planned' but "
                              f"Brian has attested it — table contradicts "
                              f"the attestation")
    for node_id, row in ai.items():
        v, entry = verdict(row["node_name"]) 
        if entry is None:
            v, entry = verdict(node_id)
        if entry:
            ai_by_entry[entry["id"]] = (node_id, row["status"])
        if row["status"] in EXISTENCE_STATUSES_AI and v != ATTESTED:
            claims.append(f"ai_inventory: {node_id} is "
                          f"'{row['status']}' but verdict is {v} "
                          f"(unattested claim)")
        if row["status"] == "unconfirmed" and v == ATTESTED:
            violations.append(f"ai_inventory: {node_id} marked "
                              f"'unconfirmed' but Brian has attested it")

    for eid in sorted(set(oh_by_entry) & set(ai_by_entry)):
        oh_name, oh_status = oh_by_entry[eid]
        ai_id, ai_status = ai_by_entry[eid]
        if oh_status == "planned" and ai_status in EXISTENCE_STATUSES_AI:
            violations.append(
                f"cross-table contradiction on {eid}: owned_hardware "
                f"says 'planned' ({oh_name}) while ai_inventory asserts "
                f"existence ('{ai_status}', {ai_id})")

    cur.execute("SELECT machine_name, model_name, status FROM "
                "successbrian_os.model_seats ORDER BY machine_name")
    for r in cur.fetchall():
        v, _ = verdict(r["machine_name"])
        if r["status"] == "current" and v != ATTESTED:
            violations.append(
                f"model_seats: CURRENT seat '{r['model_name']}' sits on "
                f"{r['machine_name']}, verdict {v} — live planning on an "
                f"unattested machine")

    cur.execute("SELECT status, count(*) AS n FROM dealsdesk.builds "
                "GROUP BY status ORDER BY status")
    build_counts = ", ".join(f"{r['status']}={r['n']}"
                             for r in cur.fetchall())
    notes.append(f"dealsdesk.builds are plans, never machines "
                 f"({build_counts})")
    cur.execute("SELECT name FROM dealsdesk.builds WHERE status = 'active'")
    for r in cur.fetchall():
        notes.append(f"dealsdesk.builds: '{r['name']}' carries status "
                     f"'active' — a plan wearing an existence word; it "
                     f"is still a plan, not a machine")

    intent = []
    for entry in REGISTRY:
        if entry.get("decision") in HIGH_INTENT:
            intent.append(
                f"{entry['id']}: decision={entry['decision']} (strong "
                f"intent) — verdict={entry['verdict']}. Intent is not "
                f"ownership; this changes only when Brian states the "
                f"item is owned")

    recorded = set(oh_by_entry) | set(ai_by_entry)
    for entry in REGISTRY:
        if entry["verdict"] == ATTESTED and entry["id"] not in recorded:
            notes.append(f"attested but in no table: {entry['id']} "
                         f"({entry['note']})")
    return violations, claims, notes, intent


def _connect():
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(dbname="ecosystem_central", host="localhost",
                            cursor_factory=psycopg2.extras.RealDictCursor)


# --- Selftest (logic only; the live check is --audit) --------------------------

def selftest():
    checks = []

    def ok(label, cond):
        checks.append((label, bool(cond)))

    ok("alias match: 'Mantis-9' attested",
       verdict("Mantis-9")[0] == ATTESTED)
    ok("messy spelling: '  dl380-g8-02 ' attested",
       verdict("  dl380-g8-02 ")[0] == ATTESTED)
    ok("R630 planned, not eligible",
       verdict("R630")[0] == PLANNED and not planning_eligible("R630"))
    ok("Node Echo unconfirmed, not eligible",
       verdict("node-echo")[0] == UNCONFIRMED
       and not planning_eligible("Node Echo"))
    ok("K11-Zeus planned, not eligible",
       verdict("K11-Zeus")[0] == PLANNED)
    ok("unknown name defaults to deny",
       verdict("Some Machine Nobody Mentioned")[0] == UNKNOWN
       and not planning_eligible("Some Machine Nobody Mentioned"))
    try:
        require_planning_eligible("Precision 3620")
        ok("require_planning_eligible raises on planned", False)
    except OwnershipError:
        ok("require_planning_eligible raises on planned", True)
    ok("require_planning_eligible passes attested",
       require_planning_eligible("DL380-Gen8-1")["id"] == "dl380_gen8_1")
    att = [e for e in REGISTRY if e["verdict"] == ATTESTED]
    unc = [e for e in REGISTRY if e["verdict"] == UNCONFIRMED]
    pln = [e for e in REGISTRY if e["verdict"] == PLANNED]
    ok(f"registry counts (attested={len(att)}, unconfirmed={len(unc)}, "
       f"planned={len(pln)})",
       (len(att), len(unc), len(pln)) == (10, 13, 9))
    ok("every attested entry cites Brian's statement",
       all("Brian" in e["source"] for e in att))
    ok("decision axis: 3620 is parts_ordered AND still not owned",
       decision_level("Precision 3620") == "parts_ordered"
       and not is_owned("Precision 3620")
       and not planning_eligible("Precision 3620"))
    ok("no entry carries both a decision level and an attested verdict",
       all(not (e.get("decision") and e["verdict"] == ATTESTED)
           for e in REGISTRY))
    ok("every decision level is a known level",
       all(e.get("decision") in DECISION_LEVELS
           for e in REGISTRY if e.get("decision")))
    try:
        attest("x", ["X"], "")
        ok("attest() refuses without Brian's statement", False)
    except ValueError:
        ok("attest() refuses without Brian's statement", True)
    try:
        attest("x", ["X"], "the price dropped and we feel ready")
        ok("attest() refuses on intent dressed as a statement", False)
    except ValueError:
        ok("attest() refuses on intent dressed as a statement", True)
    ok("attest() builds an attested entry from Brian's statement",
       attest("x", ["X"], "Brian, 2026-11-24: 'we own X'")["verdict"]
       == ATTESTED)
    ok("no normalized name maps to two entries", len(_INDEX) ==
       len({k for k in _INDEX}))
    failed = [label for label, passed in checks if not passed]
    for label, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Ownership guard — Brian's rule (2026-11-24): plan "
                    "only on what he says we own.")
    ap.add_argument("names", nargs="*", help="items to check")
    ap.add_argument("--list", action="store_true",
                    help="list the registry")
    ap.add_argument("--audit", action="store_true",
                    help="scan the live tables against the registry")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.list:
        for e in REGISTRY:
            dec = f"  [decision: {e['decision']}]" if e.get("decision") \
                else ""
            print(f"{e['verdict']:18s} {e['id']:20s} "
                  f"{', '.join(e['names'])}{dec}")
        return 0
    if args.audit:
        conn = _connect()
        violations, claims, notes, intent = audit(conn)
        conn.close()
        print(f"VIOLATIONS ({len(violations)}):")
        for v in violations:
            print(f"  ! {v}")
        print(f"UNATTESTED CLAIMS ({len(claims)}) — residue, not failures:")
        for c in claims:
            print(f"  ? {c}")
        print(f"STRONG INTENT — STILL NOT OWNED ({len(intent)}):")
        for i in intent:
            print(f"  > {i}")
        print(f"NOTES ({len(notes)}):")
        for n in notes:
            print(f"  - {n}")
        return 1 if violations else 0
    if args.names:
        worst = 0
        for name in args.names:
            v, entry = verdict(name)
            src = entry["source"] if entry else "not in the registry"
            dec = decision_level(name)
            dec_txt = f" [decision: {dec}]" if dec else ""
            print(f"{name}: {v}{dec_txt} — {src}")
            if v != ATTESTED:
                worst = 1
        return worst
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
