#!/usr/bin/env python3
"""road_inbox_drain.py — alpha's drain for the road inbox.

GOAL.md build-list item 2 (RoadChat coordination design, Brian
2026-11-05): road captures spool to ~/sbos-road/outbox/ on the road
machine, road_sync carries them to the hub's
~/sbos-road/inbox/<host>/, and SOMETHING on alpha must file them
into the record. This is that something.

What it does:
  - Scans ~/sbos-road/inbox/<host>/*.json envelopes (top level only;
    each host dir has a processed/ subfolder for drained files).
  - kind == "people_note" envelopes are filed into
    atlas.scattered_captures through the ecosystem's EXISTING
    writer — tools/atlas/scattered_brain.py capture(), imported,
    never forked — with the people/identity context stamped in, so
    the clerk's hourly sweep files them like any other capture.
  - An envelope that already carries filed_capture_id (the People
    room files immediately via the people-api endpoint when alpha
    is linked) is NEVER filed twice: the drain records it as
    already-filed and just retires the envelope.
  - Drained envelopes MOVE to <host>/processed/ — append-only
    doctrine: nothing is ever deleted.
  - Idempotency is tracked by envelope id in
    ~/sbos-road/inbox/.drain-state.json; a re-run files nothing
    twice, even if an envelope reappears.
  - Envelopes of other kinds are left in place and reported —
    this drain's scope is people_note only.
  - Malformed envelopes are retired to processed/ with the parse
    error recorded in the state file (visible, never dropped).

    python3 road_inbox_drain.py [--dry-run]

Cron (user crontab, two minutes ahead of the clerk's :50 sweep):
    48 * * * * flock -n /tmp/road-inbox-drain.lock \
      python3 /home/successbrian/successbrian-os/tools/travel/road_inbox_drain.py \
      >> /home/successbrian/logs/road-inbox-drain.log 2>&1
"""

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ROAD_HOME = os.path.join(os.path.expanduser("~"), "sbos-road")
INBOX = os.path.join(ROAD_HOME, "inbox")
STATE_PATH = os.path.join(INBOX, ".drain-state.json")


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_PATH)


def file_people_note(env, host):
    """File one people_note envelope via scattered_brain.capture —
    the same writer the identity module's --road-note uses."""
    atlas_dir = os.path.join(REPO, "tools", "atlas")
    if atlas_dir not in sys.path:
        sys.path.insert(0, atlas_dir)
    import scattered_brain
    name = env.get("canonical_name")
    pid = env.get("person_id")
    if pid is not None and name:
        title = "RoadChat note — %s" % name
    elif pid is not None:
        title = "RoadChat note — person %s" % pid
    else:
        title = "RoadChat note — new person (not yet in identity layer)"
    ctx = "\n".join([
        "source: RoadChat road inbox (drained %s)"
        % datetime.now(timezone.utc).date().isoformat(),
        "kind: people/identity road note",
        "transport: road outbox -> road_sync -> hub inbox -> "
        "road_inbox_drain",
        "origin_host: %s" % (env.get("origin_host") or host),
        "envelope_id: %s" % env.get("id"),
        "person_id: %s" % (pid if pid is not None else "new"),
        "canonical_name: %s" % (name or "unknown"),
        "created_at: %s" % (env.get("created_at") or "unknown"),
    ])
    conn = scattered_brain.pg()
    try:
        return scattered_brain.capture(conn, title, ctx,
                                       env.get("text") or "")
    finally:
        conn.close()


def drain(dry=False):
    counts = {"filed": 0, "already": 0, "skipped_kind": 0,
              "errors": 0, "would_file": 0}
    if not os.path.isdir(INBOX):
        print("drain: no inbox at %s — nothing to do" % INBOX)
        return counts
    state = load_state()
    dirty = False
    for host in sorted(os.listdir(INBOX)):
        hdir = os.path.join(INBOX, host)
        if host.startswith(".") or not os.path.isdir(hdir):
            continue
        processed = os.path.join(hdir, "processed")
        for fn in sorted(os.listdir(hdir)):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(hdir, fn)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    env = json.load(f)
                eid = env.get("id") or fn[:-5]
            except Exception as e:
                counts["errors"] += 1
                print("drain: MALFORMED %s/%s (%s)%s"
                      % (host, fn, e, " [dry-run: left in place]"
                         if dry else " — retired to processed/"))
                if not dry:
                    os.makedirs(processed, exist_ok=True)
                    os.replace(path, os.path.join(processed, fn))
                    state.setdefault(fn[:-5], {})["error"] = (
                        "malformed envelope: %s" % e)
                    dirty = True
                continue
            if eid in state:
                counts["already"] += 1
                print("drain: already recorded %s/%s envelope %s "
                      "(capture %s)"
                      % (host, fn, eid,
                         state[eid].get("capture_id")))
                if not dry:
                    os.makedirs(processed, exist_ok=True)
                    os.replace(path, os.path.join(processed, fn))
                continue
            if env.get("kind") != "people_note":
                counts["skipped_kind"] += 1
                print("drain: skip %s/%s — kind %r is not "
                      "people_note; left in inbox"
                      % (host, fn, env.get("kind")))
                continue
            if env.get("filed_capture_id"):
                counts["already"] += 1
                print("drain: %s/%s envelope %s was filed via the "
                      "endpoint as capture #%s — retiring envelope "
                      "only" % (host, fn, eid,
                                env["filed_capture_id"]))
                if not dry:
                    state[eid] = {
                        "capture_id": env["filed_capture_id"],
                        "via": "people-api endpoint",
                        "drained_at": datetime.now(
                            timezone.utc).isoformat()}
                    dirty = True
                    os.makedirs(processed, exist_ok=True)
                    os.replace(path, os.path.join(processed, fn))
                continue
            if dry:
                counts["would_file"] += 1
                print("drain: WOULD file %s/%s envelope %s "
                      "(person_id %s)"
                      % (host, fn, eid, env.get("person_id")))
                continue
            cid = file_people_note(env, host)
            counts["filed"] += 1
            print("drain: filed %s/%s envelope %s -> capture #%d"
                  % (host, fn, eid, cid))
            state[eid] = {"capture_id": cid, "via": "drain",
                          "drained_at": datetime.now(
                              timezone.utc).isoformat()}
            dirty = True
            os.makedirs(processed, exist_ok=True)
            os.replace(path, os.path.join(processed, fn))
    if dirty and not dry:
        save_state(state)
    print("drain: filed %d, already %d, skipped-kind %d, errors %d"
          "%s" % (counts["filed"], counts["already"],
                  counts["skipped_kind"], counts["errors"],
                  ", would-file %d" % counts["would_file"] if dry
                  else ""))
    return counts


def main():
    if "--selftest" in sys.argv:
        assert os.path.isdir(REPO)
        print("selftest: OK (road_inbox_drain; inbox %s)" % INBOX)
        return 0
    drain(dry="--dry-run" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
