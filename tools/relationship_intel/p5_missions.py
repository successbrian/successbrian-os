#!/usr/bin/env python3
"""P5 request side — mission proposal consumer (new Vera, field capture loop).

Runs ON k11-alpha. Part of the hourly loop (see p5_hourly.sh).

What it does:
  1. Consumes people.capture_mission_proposals rows where status='proposed'
     (created by the P4 builder per the BUILD_NOTES table contract).
  2. Creates a mission row in successbrian_os.podcast_questions with
     kind='mission' and answer_type='free_text'. The mission text names the
     TARGET and exactly what Brian must capture.
  3. Resolves (or creates) the target's people.people row.
  4. Records the mapping in people.field_capture_missions and flips the
     proposal to status='requested'.
  5. Marks missions complete when Brian answers the question row
     (podcast_question_answers.text_value, e.g. "done, 6 screenshots").

Backup channel: if the podcast_questions insert fails, the mission goes to
successbrian_os.pending_questions (asked_by='spencer') and the proposal is
marked 'requested_backup' instead of 'requested'.

Local queue backdoor: --local-queue FILE.json stages ad-hoc proposals
(still written into the proposals table first, so there is ONE consume path).
P4 owns proposals; the local queue is the ops backdoor. If the proposals
table does not exist yet (P4 not landed), --local-queue is the way to feed
missions — and this script creates the table from schema.sql on first run.

DBs: people_unified (people schema) + ecosystem_central (successbrian_os).
Auth: ~/.pgpass on k11. Stdlib + psycopg2 only.
"""
import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

HERE = os.path.dirname(os.path.abspath(__file__))
INTAKE_SCHEMA = os.path.join(HERE, "schema.sql")

NOISE_TAG = "field_capture"


def _conn(dbname):
    return psycopg2.connect(host="localhost", dbname=dbname, user="successbrian")


def _norm_name(s):
    import re
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def ensure_schema():
    """Idempotent: create P5 tables if P4 hasn't yet."""
    if not os.path.exists(INTAKE_SCHEMA):
        return
    with open(INTAKE_SCHEMA) as f:
        sql = f.read()
    with _conn("people_unified") as c:
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute(sql)


def split_name(full):
    full = (full or "").strip()
    if not full:
        return "", ""
    parts = full.split()
    return parts[0], " ".join(parts[1:])


def add_tags(cur, person_id, new_tags):
    """GRAPH NOT TREE: additive tags only. Never overwrite existing tags."""
    if not new_tags:
        return
    cur.execute(
        "UPDATE people.people SET tags = ("
        " SELECT array_agg(DISTINCT t) FROM unnest("
        "   COALESCE(tags, '{}') || %s::text[]) t)"
        " WHERE id = %s AND NOT (COALESCE(tags, '{}') @> %s::text[])",
        (list(new_tags), person_id, list(new_tags)),
    )


def resolve_or_create_target(cur, person_id_hint, target_name, platform):
    """Return people.people id for the mission target. Creates a tagged
    placeholder row if the target is unknown — edges always have a node."""
    if person_id_hint:
        cur.execute("SELECT id FROM people.people WHERE id = %s", (int(person_id_hint),))
        row = cur.fetchone()
        if row:
            add_tags(cur, row[0], ["capture_target", NOISE_TAG])
            return row[0]
    norm = _norm_name(target_name)
    if norm:
        cur.execute(
            "SELECT id FROM people.people "
            "WHERE lower(regexp_replace(first_name || ' ' || last_name, '\\s+', ' ', 'g')) = %s "
            "ORDER BY id LIMIT 3",
            (norm,),
        )
        rows = cur.fetchall()
        if rows:
            add_tags(cur, rows[0][0], ["capture_target", NOISE_TAG])
            return rows[0][0]
    first, last = split_name(target_name)
    cur.execute(
        "INSERT INTO people.people (first_name, last_name, source, tags, extra_data) "
        "VALUES (%s, %s, 'field_capture', %s, %s) RETURNING id",
        (first, last, ["capture_target", NOISE_TAG],
         json.dumps({"captured_from": "mission_target_placeholder", "platform": platform})),
    )
    return cur.fetchone()[0]


def mission_text(proposal_id, target_name, what_to_capture):
    return (
        f"FIELD MISSION: capture {what_to_capture} for {target_name}. "
        "Screenshot each scroll page of the list (names + handles visible). "
        "Upload the screenshots here in chat. When finished, answer this mission "
        'with "done, N screenshots". '
        f"(mission ref: proposal {proposal_id})"
    )


def create_mission_primary(cur_eco, text):
    """podcast_questions row. Returns the new id.
    episode = the Saturday this mission belongs to (missions are issued in
    the weekly podcast cycle; episode is NOT NULL)."""
    import datetime
    today = datetime.date.today()
    days_ahead = (5 - today.weekday()) % 7  # Saturday = 5
    episode = (today + datetime.timedelta(days=days_ahead)).isoformat()
    cur_eco.execute(
        "INSERT INTO successbrian_os.podcast_questions "
        "(episode, kind, question_text, answer_type) "
        "VALUES (%s, 'mission', %s, 'free_text') RETURNING id",
        (episode, text),
    )
    return cur_eco.fetchone()[0]


def create_mission_backup(cur_eco, text):
    cur_eco.execute(
        "INSERT INTO successbrian_os.pending_questions "
        "(asked_by, question, status, priority) "
        "VALUES ('spencer', %s, 'open', 2) RETURNING id",
        (text,),
    )
    return cur_eco.fetchone()[0]


def stage_local_queue(path):
    """Ops backdoor: stage JSON proposals into the proposals table as
    status='proposed' so the normal consume path picks them up."""
    with open(path) as f:
        items = json.load(f)
    if isinstance(items, dict):
        items = [items]
    n = 0
    with _conn("people_unified") as c:
        with c.cursor() as cur:
            for it in items:
                cur.execute(
                    "INSERT INTO people.capture_mission_proposals "
                    "(person_id, target_name, what_to_capture, reason, status) "
                    "VALUES (%s, %s, %s, %s, 'proposed')",
                    (it.get("person_id"),
                     it["target_name"],
                     it["what_to_capture"],
                     it.get("reason", "local queue: %s" % os.path.basename(path))),
                )
                n += 1
        c.commit()
    print(f"staged {n} local proposal(s) from {path}")
    return n


def derive_relation_type(what):
    w = (what or "").lower()
    if "follower" in w:
        return "follower"
    if "following" in w:
        return "following"
    return "friend"


def poll(backup_only=False):
    ensure_schema()
    made = 0
    with _conn("people_unified") as c_pu, _conn("ecosystem_central") as c_eco:
        with c_pu.cursor() as cur, c_eco.cursor() as cur_eco:
            cur.execute(
                "SELECT proposal_id, person_id, target_name, what_to_capture, reason "
                "FROM people.capture_mission_proposals "
                "WHERE status = 'proposed' ORDER BY proposal_id"
            )
            proposals = cur.fetchall()
            for pid, person_id, target_name, what, reason in proposals:
                text = mission_text(pid, target_name, what)
                platform = "unknown"
                rel = derive_relation_type(what)
                mission_id = None
                channel = "podcast_questions"
                status = "requested"
                try:
                    if backup_only:
                        raise RuntimeError("backup channel forced")
                    cur_eco.execute("SAVEPOINT p5_primary")
                    mission_id = create_mission_primary(cur_eco, text)
                    cur_eco.execute("RELEASE SAVEPOINT p5_primary")
                except Exception as e:
                    cur_eco.execute("ROLLBACK TO SAVEPOINT p5_primary")
                    print(f"proposal {pid}: primary channel failed ({e}); trying backup")
                    channel = "pending_questions"
                    status = "requested_backup"
                    mission_id = create_mission_backup(cur_eco, text)
                target_pid = resolve_or_create_target(cur, person_id, target_name, platform)
                cur.execute(
                    "INSERT INTO people.field_capture_missions "
                    "(mission_id, proposal_id, target_person_id, target_name, "
                    " what_to_capture, platform, relation_type, channel, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (mission_id) DO NOTHING",
                    (mission_id, pid, target_pid, target_name, what,
                     platform, rel, channel, status),
                )
                cur.execute(
                    "UPDATE people.capture_mission_proposals SET status = %s "
                    "WHERE proposal_id = %s",
                    (status, pid),
                )
                made += 1
                print(f"proposal {pid} -> mission {mission_id} ({channel}) "
                      f"target_person_id={target_pid}")
        c_pu.commit()
        c_eco.commit()
    print(f"missions created: {made}")
    return made


def check_completions():
    """Brian answers a mission row free_text ('done, N screenshots') ->
    mark the mission complete."""
    ensure_schema()
    done = 0
    with _conn("people_unified") as c_pu, _conn("ecosystem_central") as c_eco:
        with c_pu.cursor() as cur, c_eco.cursor() as cur_eco:
            cur_eco.execute(
                "SELECT DISTINCT a.question_id "
                "FROM successbrian_os.podcast_question_answers a "
                "WHERE a.text_value IS NOT NULL "
                "AND a.text_value ILIKE '%%done%%'"
            )
            answered = {r[0] for r in cur_eco.fetchall()}
            if not answered:
                print("no answered missions")
                return 0
            cur.execute(
                "SELECT mission_id FROM people.field_capture_missions "
                "WHERE channel = 'podcast_questions' AND status IN ('requested', 'open') "
                "AND mission_id = ANY(%s)",
                (list(answered),),
            )
            for (mid,) in cur.fetchall():
                cur.execute(
                    "UPDATE people.field_capture_missions "
                    "SET status = 'complete', completed_at = now() "
                    "WHERE mission_id = %s",
                    (mid,),
                )
                done += 1
                print(f"mission {mid}: complete (Brian answered)")
        c_pu.commit()
    print(f"missions completed: {done}")
    return done


def list_open():
    ensure_schema()
    with _conn("people_unified") as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT mission_id, target_name, what_to_capture, channel, status, created_at "
                "FROM people.field_capture_missions "
                "WHERE status IN ('requested', 'requested_backup', 'open') "
                "ORDER BY mission_id"
            )
            for r in cur.fetchall():
                print(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description="P5 mission request side")
    ap.add_argument("--poll", action="store_true", help="consume proposed missions")
    ap.add_argument("--check-completions", action="store_true")
    ap.add_argument("--local-queue", help="stage JSON proposals from a file")
    ap.add_argument("--list-open", action="store_true")
    ap.add_argument("--backup-only", action="store_true",
                    help="force the pending_questions backup channel")
    args = ap.parse_args(argv)
    if args.local_queue:
        stage_local_queue(args.local_queue)
    if args.check_completions:
        check_completions()
    if args.list_open:
        list_open()
    if args.poll or (not args.check_completions and not args.list_open and not args.local_queue):
        poll(backup_only=args.backup_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
