#!/usr/bin/env python3
"""curate_learnings.py — weekly learning hygiene for Lyra workers.
Brian 2026-10-17 (v2 spec): invalidation over deletion; deterministic
dedupe + one V4 semantic curation pass. Called by cron weekly.
"""
import importlib.util
import subprocess
import sys

spec = importlib.util.spec_from_file_location(
    "whw", "/home/successbrian/successbrian-os/tools/v4pro_handoff_worker.py")
whw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(whw)

PSQL, pq = whw.PSQL, whw.pq


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True,
                       timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def deterministic_dedupe():
    """Exact-text duplicates: keep newest, supersede the rest."""
    rows = q("SELECT id, worker_kind, learning FROM "
             "successbrian_os.v4pro_worker_learnings WHERE status = 'active' "
             "ORDER BY id;")
    seen = {}
    dupes = 0
    for ln in rows.split("\n"):
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        lid, kind, text = parts[0].strip(), parts[1].strip(), parts[2].strip()
        key = (kind, text.lower())
        if key in seen:
            q("UPDATE successbrian_os.v4pro_worker_learnings SET status = "
              "'superseded', superseded_by = %s WHERE id = %s;"
              % (seen[key], lid))
            dupes += 1
        else:
            seen[key] = lid
    print("dedupe: %d exact-duplicate learning(s) superseded" % dupes)
    return dupes


def semantic_curation():
    """One V4 pass: merge near-dupes, invalidate stale learnings."""
    rows = q("SELECT id, worker_kind, left(learning, 300) FROM "
             "successbrian_os.v4pro_worker_learnings WHERE status = 'active' "
             "ORDER BY worker_kind, id;")
    items = [ln.strip() for ln in rows.split("\n") if ln.strip()]
    if len(items) < 5:
        print("curation: only %d active learnings — skip semantic pass" % len(items))
        return
    listing = "\n".join("[%s] %s: %s" % tuple(x.split("\t")[:3]) for x in items
                        if len(x.split("\t")) >= 3)
    prompt = ("You curate a worker-learnings table. Below are active learnings "
              "as [id] kind: text. Output actions, one per line:\n"
              "MERGE <id1>,<id2>,... INTO <keep_id> — near-duplicates saying the same thing\n"
              "INVALIDATE <id> — stale, wrong, or no longer applicable (say why after a | )\n"
              "If nothing needs action, output NONE.\n\n" + listing)
    try:
        key = whw.get_key()
        if not key:
            print("curation: no API key — skip")
            return
        out = whw.call_v4pro(key, prompt)
    except Exception as e:
        print("curation: V4 call failed: %s" % str(e)[:150])
        return
    merged = invalidated = 0
    for ln in out.split("\n"):
        t = ln.strip()
        u = t.upper()
        if u.startswith("MERGE"):
            try:
                ids_part = t.split("INTO")[0].replace("MERGE", "").strip()
                keep = t.split("INTO")[1].strip().split()[0]
                ids = [x.strip() for x in ids_part.split(",") if x.strip().isdigit()]
                if keep.isdigit() and ids:
                    for i in ids:
                        if i != keep:
                            q("UPDATE successbrian_os.v4pro_worker_learnings "
                              "SET status = 'superseded', superseded_by = %s "
                              "WHERE id = %s AND status = 'active';" % (keep, i))
                            merged += 1
            except (IndexError, ValueError):
                continue
        elif u.startswith("INVALIDATE"):
            try:
                lid = t.split()[1]
                if lid.isdigit():
                    q("UPDATE successbrian_os.v4pro_worker_learnings "
                      "SET status = 'invalidated' WHERE id = %s AND status = 'active';"
                      % lid)
                    invalidated += 1
            except IndexError:
                continue
    print("curation: %d merged, %d invalidated" % (merged, invalidated))


def main():
    if whw.chain_halted():
        print("chain halted — curation idle")
        return 0
    deterministic_dedupe()
    semantic_curation()
    # Touch last_confirmed on surviving actives
    q("UPDATE successbrian_os.v4pro_worker_learnings SET last_confirmed = now() "
      "WHERE status = 'active';")
    print("curation done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
