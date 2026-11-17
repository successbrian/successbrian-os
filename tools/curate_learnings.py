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
            # Count only CONFIRMED updates (fixed 2026-11-17: q()
            # returns "" on error and the old code counted phantom
            # merges for weeks — the table had no UPDATE grant, so
            # every apply silently failed while logs said "merged").
            r = q("UPDATE successbrian_os.v4pro_worker_learnings "
                  "SET status = 'superseded', superseded_by = %s "
                  "WHERE id = %s AND status = 'active';"
                  % (seen[key], lid))
            if r.startswith("UPDATE") and not r.endswith(" 0"):
                dupes += 1
            else:
                print("dedupe: UPDATE failed for id %s: %r"
                      % (lid, r))
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
    lines = ["[%s] %s: %s" % tuple(x.split("\t")[:3]) for x in items
             if len(x.split("\t")) >= 3]
    # Rerouted 2026-11-17 (Brian: "do everything you are 100%
    # confident in"): the paid V4 cloud call failed with HTTP 402
    # (empty DeepSeek balance) for weeks — the semantic pass ran and
    # thought nothing. Sonic (local fleet engine) does this pass now;
    # no key, no balance, no cloud. First Sonic run timed out on the
    # full listing in one call, so the pass runs in batches of 40 —
    # same actions, applied per batch.
    sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
    from sbos_common import llm_chat
    merged = invalidated = 0
    for i in range(0, len(lines), 40):
        listing = "\n".join(lines[i:i + 40])
        prompt = ("You curate a worker-learnings table. Below are active learnings "
                  "as [id] kind: text. Output actions, one per line:\n"
                  "MERGE <id1>,<id2>,... INTO <keep_id> — near-duplicates saying the same thing\n"
                  "INVALIDATE <id> — stale, wrong, or no longer applicable (say why after a | )\n"
                  "If nothing needs action, output NONE.\n\n" + listing)
        try:
            out, _usage = llm_chat(prompt=prompt, max_tokens=1200,
                                   timeout=300)
        except Exception as e:
            print("curation: Sonic call failed (batch %d): %s"
                  % (i // 40 + 1, str(e)[:150]))
            continue
        # Apply THIS batch's actions immediately (fixed 2026-11-17:
        # the accumulate-then-apply version lost a full 25-minute
        # run when its timeout killed it before the apply step —
        # zero actions landed. Per-batch apply means progress
        # persists even if a later batch or the run itself dies.)
        for ln in out.split("\n"):
            t = ln.strip()
            u = t.upper()
            if u.startswith("MERGE"):
                try:
                    ids_part = t.split("INTO")[0].replace("MERGE", "").strip()
                    keep = t.split("INTO")[1].strip().split()[0]
                    ids = [x.strip() for x in ids_part.split(",") if x.strip().isdigit()]
                    if keep.isdigit() and ids:
                        for mid in ids:
                            if mid != keep:
                                r = q("UPDATE successbrian_os.v4pro_worker_learnings "
                                      "SET status = 'superseded', superseded_by = %s "
                                      "WHERE id = %s AND status = 'active';" % (keep, mid))
                                if r.startswith("UPDATE") and \
                                        not r.endswith(" 0"):
                                    merged += 1
                                else:
                                    print("curation: MERGE update "
                                          "failed for id %s: %r"
                                          % (mid, r))
                except (IndexError, ValueError):
                    continue
            elif u.startswith("INVALIDATE"):
                try:
                    lid = t.split()[1]
                    if lid.isdigit():
                        r = q("UPDATE successbrian_os.v4pro_worker_learnings "
                              "SET status = 'invalidated' WHERE id = %s AND status = 'active';"
                              % lid)
                        if r.startswith("UPDATE") and \
                                not r.endswith(" 0"):
                            invalidated += 1
                        else:
                            print("curation: INVALIDATE update "
                                  "failed for id %s: %r" % (lid, r))
                except IndexError:
                    continue
        print("curation: batch %d applied (running total: %d merged, "
              "%d invalidated)" % (i // 40 + 1, merged, invalidated),
              flush=True)
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
