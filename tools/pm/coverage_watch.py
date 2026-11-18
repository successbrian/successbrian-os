#!/usr/bin/env python3
"""coverage_watch.py — the project coverage watch.

Brian 2026-11-18: "successbrian os needs to be vastly improved so
it doesnt miss these events anymore" — after the VextorGrid case:
the project's folder and full dossier were copied from his laptop
to alpha, its name was registered, its blog was wired — and its
definition sat at 3/10 for days with NO machinery noticing,
because nothing in the system compares the record against itself.
Same failure family as the rulings census (2026-11-17: "why are
things I ruled dying and no one notices?"), one level down:
registered things silently incomplete or silently dropped.

This watch runs ON ALPHA (daily cron) and compares four surfaces:

1. UNCLASSIFIED FOLDER — a folder in ~/vibecoder-projects that is
   neither a registered project, a part-of component, a candidate,
   nor a ruled classification (company / persona / duplicate /
   non-project folder). The Kimi and Gemini Sites case: a real
   project folder referenced by nothing at all.
2. REGISTRY-ATLAS DRIFT — a vibecoder project folder whose key has
   an Atlas proj node but no registry row (or a registry project
   with no proj node). The HashrateHarbor case: on the Nov 15
   roster, gone from the registry by Nov 18, nobody noticed. The
   CivitasReserve case: node + blog, no registry row.
3. THIN DEFINITION — a registered project whose definition sheet
   is < 8 of 10 defined. The VextorGrid case.
4. UNREAD DOSSIER — a numbered spec doc in
   ~/vibecoder-projects/documentation (NN_NAME.md) belonging to a
   registered-but-thin project: the spec exists on alpha and was
   never read into the record. Reported instead of (not in
   addition to) that project's THIN line — it is the stronger,
   actionable form of the same miss.

Exceptions file as ONE Intel Bridge capture per changed exception
set (rulings-census pattern: hash-compared state file, no repeat
filings for an unchanged set). The watch writes its heartbeat
DIRECTLY into Lyra's table every run (worker 'coverage-watch'),
and the rulings census carries a row probing that heartbeat — if
this watch dies, the census flags the watcher itself.

Classifications that are Brian's rulings live below as coded
constants WITH their sources. Registration is Brian's designation
alone: this watch REPORTS gaps, it never registers anything.

Modes: run | dry-run | selftest. Exit 0 on a completed sweep —
finding exceptions is a success, not a failure.
"""
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.expanduser("~/successbrian-os/tools"))
import sbos_common  # noqa: E402

STATE_FILE = os.path.expanduser("~/logs/.coverage_watch_state.json")
PROJECTS_DIR = os.path.expanduser("~/vibecoder-projects")
THIN_BELOW = 8          # definition items defined, of 10
DEFINITION_TOTAL = 10

# Folder name (normalized) -> registry project_key, where the plain
# normalization does not land on the key.
FOLDER_ALIASES = {
    "success-brian-core": "successbrian-os",
    "projectmanager": "content-command-center",
    "sparkyai-successbrian": "sparkyai",
    "webinarbizs-com": "webinarbizs",
    "successbrian-golden-chassis": "golden-chassis",
}

# Normalized folder -> why it is correctly NOT a registered
# project. Every entry carries its source; a folder not in the
# registry, the candidates, or this map is an exception.
CLASSIFIED_NON_PROJECT = {
    "revo": "MLM company, not a Brian project (Brian, 2026-10-28)",
    "successbrianarchitect": "a persona, not a project "
                               "(Brian, 2026-10-28)",
    "socialops": "a ContactFlowCRM build, not a separate project "
                 "(Brian, 2026-10-28)",
    "documentation": "the spec library folder, not a project",
    "plans": "a planning folder, not a project",
    "tools": "a utility folder, not a project",
    "aoemrankrush-preserved": "preserved copy of AOEMRankRush",
    "cryptostreemz-zip": "an archive file, not a project folder",
}

# Registered projects whose thinness is RULED, not a miss.
PARKED = {
    "mwcsuccessbrian": "on hold by Brian 2026-10-28 — existence "
                       "itself unverified; thin by ruling",
}

# Documentation spec doc name (normalized, number stripped) ->
# registry project_key, where normalization does not land on it.
DOC_ALIASES = {
    "contactflow-crm": "contactflowcrm",
    "novusfere": "novusferre",
    "hasrate-harbor": "hashrateharbor",
}


def norm(name):
    """Folder/doc name -> comparable key form."""
    n = re.sub(r"[_. ]+", "-", name.strip().lower())
    return re.sub(r"-+", "-", n).strip("-")


def folder_key(folder):
    n = norm(folder)
    return FOLDER_ALIASES.get(n, n)


def classify_folder(folder, registry, candidates):
    """-> (kind, key_or_reason). kind in: project, candidate,
    classified, unclassified."""
    if folder.endswith(" - Copy"):
        base = folder[: -len(" - Copy")]
        kind, _ = classify_folder(base, registry, candidates)
        if kind in ("project", "candidate", "classified"):
            return ("classified", f"duplicate folder of {base}")
        return ("unclassified", folder_key(folder))
    key = folder_key(folder)
    if key in registry:
        return ("project", key)
    if key in candidates:
        return ("candidate", key)
    n = norm(folder)
    if n in CLASSIFIED_NON_PROJECT:
        return ("classified", CLASSIFIED_NON_PROJECT[n])
    return ("unclassified", key)


def exceptions_from(folders, registry, candidates, proj_nodes,
                    definitions, spec_docs):
    """Pure. registry: {key: {"part_of": ...}}; definitions:
    {key: defined_count}; spec_docs: set of registry keys that
    have a numbered spec doc. Returns exception lines."""
    out = []
    folder_keys = set()
    for folder in folders:
        kind, val = classify_folder(folder, registry, candidates)
        if kind == "project":
            folder_keys.add(val)
        elif kind == "unclassified" and val not in proj_nodes:
            # A folder whose key HAS a proj node is reported once,
            # as DRIFT below — it is referenced, just unregistered.
            out.append(f"UNCLASSIFIED FOLDER: {folder} "
                       f"(~/vibecoder-projects) — not registered, "
                       f"not a candidate, no ruled classification")
    # Registry <-> Atlas drift, scoped to folder-backed projects
    # plus every registry row (the proj namespace also holds SBOS
    # work projects that are not vibecoder products).
    for key in sorted(registry):
        if key not in proj_nodes:
            out.append(f"DRIFT: registered project {key} has no "
                       f"Atlas proj node")
    for key in sorted(folder_keys):
        if key in registry and key not in proj_nodes:
            continue  # already reported above
    folder_key_set = set()
    for folder in folders:
        folder_key_set.add(folder_key(folder))
    for key in sorted(folder_key_set):
        if key not in registry and key not in candidates \
                and key in proj_nodes:
            # Candidates are tracked by the candidate system (their
            # registration awaits Brian) — not a silent miss.
            out.append(f"DRIFT: {key} has an Atlas proj node but "
                       f"is NOT in the project registry")
    # Thin definitions / unread dossiers.
    for key in sorted(registry):
        if registry[key].get("part_of"):
            continue  # scoped inside the parent (SBOS), by design
        if key in PARKED:
            continue  # thin by Brian's ruling, not a miss
        defined = definitions.get(key, 0)
        if defined < THIN_BELOW:
            if key in spec_docs:
                out.append(f"UNREAD DOSSIER: {key} definition is "
                           f"{defined}/{DEFINITION_TOTAL} but a "
                           f"spec doc sits in documentation/ — the "
                           f"spec was never read into the record")
            else:
                out.append(f"THIN DEFINITION: {key} definition is "
                           f"{defined}/{DEFINITION_TOTAL} defined")
    return out


def load_state():
    registry = {}
    for key, part_of in sbos_common.pg_rows(
            "SELECT project_key, part_of "
            "FROM atlas.version_scope_projects"):
        registry[key] = {"part_of": part_of}
    candidates = {r[0] for r in sbos_common.pg_rows(
        "SELECT candidate_key "
        "FROM atlas.version_scope_project_candidates")}
    proj_nodes = set()
    for (node_key,) in sbos_common.pg_rows(
            "SELECT node_key FROM atlas.nodes "
            "WHERE node_key LIKE 'proj:%'"):
        proj_nodes.add(node_key[len("proj:"):])
    definitions = {}
    for key, cnt in sbos_common.pg_rows(
            "SELECT project_key, count(*) "
            "FROM atlas.version_scope_definition_items "
            "WHERE state = 'defined' GROUP BY project_key"):
        definitions[key] = cnt
    folders = []
    if os.path.isdir(PROJECTS_DIR):
        folders = sorted(os.listdir(PROJECTS_DIR))
    spec_docs = set()
    doc_dir = os.path.join(PROJECTS_DIR, "documentation")
    if os.path.isdir(doc_dir):
        for name in os.listdir(doc_dir):
            m = re.match(r"^\d+_(.+)\.md$", name)
            if m:
                n = norm(m.group(1))
                spec_docs.add(DOC_ALIASES.get(n, n))
    return folders, registry, candidates, proj_nodes, definitions, \
        spec_docs


def heartbeat(summary):
    sbos_common.pg_exec(
        "INSERT INTO successbrian_os.worker_heartbeats "
        "(worker_name, last_heartbeat, last_status, last_error, "
        "is_important, last_run_output) VALUES "
        "('coverage-watch', now(), 'ok', NULL, true, %s) "
        "ON CONFLICT (worker_name) DO UPDATE SET "
        "last_heartbeat = now(), last_status = 'ok', "
        "last_error = NULL, last_run_output = EXCLUDED.last_run_output",
        (summary,))


def file_capture(lines, today):
    body = "\n".join(lines)
    sbos_common.pg_exec(
        "INSERT INTO atlas.scattered_captures (title, raw_text, "
        "context) VALUES (%s, %s, %s)",
        (f"COVERAGE WATCH — exceptions {today.isoformat()}", body,
         "Filed by tools/pm/coverage_watch.py on alpha (Brian's "
         "2026-11-18 order: SBOS must not miss these events "
         "anymore). A vibecoder project folder is unclassified, "
         "the registry and Atlas disagree, a definition sheet is "
         "thin, or a spec doc on alpha was never read into the "
         "record. Registration is Brian's designation alone; "
         "repairs happen in chat with Brian."))


def sweep(dry=False):
    folders, registry, candidates, proj_nodes, definitions, \
        spec_docs = load_state()
    lines = exceptions_from(folders, registry, candidates,
                            proj_nodes, definitions, spec_docs)
    today = date.today()
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            state = {}
    filed = False
    if lines and state.get("hash") != digest and not dry:
        file_capture(lines, today)
        filed = True
    summary = (f"{len(folders)} folders, {len(registry)} registered "
               f"projects, {len(lines)} exceptions"
               + ("; capture filed" if filed else ""))
    if not dry:
        heartbeat(summary)
        state["hash"] = digest if lines else None
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(summary)
    for ln in lines:
        print("  " + ln)
    return 0


def selftest():
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    registry = {
        "alpha-proj": {"part_of": None},
        "beta-proj": {"part_of": None},
        "parked-proj": {"part_of": None},
        "part-proj": {"part_of": "alpha-proj"},
    }
    # PARKED is module-level; use a real parked key for the test.
    registry["mwcsuccessbrian"] = {"part_of": None}
    candidates = {"cand-proj"}
    proj_nodes = {"alpha-proj", "beta-proj", "mwcsuccessbrian",
                  "part-proj", "ghost-proj", "cand-proj"}
    definitions = {"alpha-proj": 9, "beta-proj": 3,
                   "mwcsuccessbrian": 1, "part-proj": 0}
    spec_docs = {"beta-proj"}
    folders = ["Alpha-Proj", "Beta-Proj", "Ghost-Proj", "Cand-Proj",
               "MysteryProj", "revo", "Beta-Proj - Copy",
               "documentation"]
    lines = exceptions_from(folders, registry, candidates,
                            proj_nodes, definitions, spec_docs)
    text = "\n".join(lines)
    check("unclassified flagged", "UNCLASSIFIED FOLDER: MysteryProj"
          in text, True)
    check("revo classified silent", "revo" in text, False)
    check("copy classified silent", "- Copy" in text, False)
    check("docs classified silent",
          "UNCLASSIFIED FOLDER: documentation" in text, False)
    check("candidate silent", "Cand-Proj" in text, False)
    check("candidate with node not drift",
          "DRIFT: cand-proj" in text, False)
    check("ghost drift flagged",
          "DRIFT: ghost-proj has an Atlas proj node" in text, True)
    check("beta unread dossier",
          "UNREAD DOSSIER: beta-proj" in text, True)
    check("beta not double-reported",
          "THIN DEFINITION: beta-proj" in text, False)
    check("parked silent", "mwcsuccessbrian" in text, False)
    check("part_of silent", "part-proj" in text, False)
    check("healthy silent", "alpha-proj" in text, False)
    check("norm", norm("10_VEXTORGRID"), "10-vextorgrid")
    check("folder_key alias", folder_key("success-brian-core"),
          "successbrian-os")
    if failures:
        print("SELFTEST FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("SELFTEST OK (13 checks)")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "selftest":
        sys.exit(selftest())
    elif mode == "dry-run":
        sys.exit(sweep(dry=True))
    elif mode == "run":
        sys.exit(sweep())
    else:
        print(__doc__)
        sys.exit(2)
