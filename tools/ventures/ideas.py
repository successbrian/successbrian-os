#!/usr/bin/env python3
"""SuccessBrian OS venture toolkit: idea -> fleshed profile -> score -> goal draft.

PURPOSE: Help a multi-income-stream solopreneur capture a raw business idea,
    flesh it out through a guided questionnaire (with optional local-Morpheus
    follow-up questions), score it on a transparent rubric, document everything
    in the database, and draft it into a goal with milestones.
WHY: Brian 2026-09-30 - successbrian-os should help an entrepreneur flesh out
    business ideas, document them in the database, then help build goals the
    way he and Spencer do it. Python owns the routine; the agent (or Brian)
    runs the conversation on top.
CALLED BY: CLI (`python3 ideas.py <command>`) used by an agent session or
    Brian directly. Library functions importable too.
NOTES:
    - CANONICAL: successbrian-os/tools/ventures/
    - DB: successbrian_os.ventures + successbrian_os.goal_drafts (schema.sql).
    - Scoring PROPOSES, Brian DECIDES: the rubric is deterministic and
      transparent; a low score never kills an idea, it just says why.
    - Goal drafts stay 'draft' until approved; Spencer creates the real
      tracked goal from an approved draft (bridge between product code and
      the assistant's goal tools).
"""
import argparse, json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from scoring import score_profile
from goals import draft_goal

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import pg_password

PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian"}
PG["password"] = pg_password(PG["host"], PG["dbname"], PG["user"])
MORPHEUS_URL = "http://127.0.0.1:11437/v1/chat/completions"


def _psql(sql, variables=None, field_sep="\t"):
    """Run SQL via the psql CLI (k11 has no psycopg2 in its venv python).
    Values go through -v variables + :'var' quoting so nothing is interpolated
    into SQL by hand."""
    env = dict(os.environ, PGPASSWORD=PG["password"])
    cmd = ["psql", "-h", PG["host"], "-U", PG["user"], "-d", PG["dbname"],
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", field_sep]
    for k, v in (variables or {}).items():
        cmd += ["-v", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, input=sql, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("psql failed: " + p.stderr.strip()[-400:])
    return p.stdout


def _one(sql, variables=None):
    out = _psql(sql, variables).strip()
    return out.split("\n")[0] if out else ""

PROFILE_FIELDS = [
    ("problem", "What problem does it solve, for whom?"),
    ("customer", "Who exactly pays? (be specific)"),
    ("offer", "What do they get? (product/service, format)"),
    ("revenue_model", "How does money come in? (one-time, subscription, affiliate, flip margin...)"),
    ("price_point", "What does the customer pay? (number or range)"),
    ("startup_cost_usd", "Startup cost in USD (number only)"),
    ("weekly_hours", "Hours per week it needs from you (number only)"),
    ("stream_fit", "Which of your existing income streams does it fit with? (comma-separated)"),
    ("risks", "Biggest risks, one per line (empty line to finish)"),
    ("first_steps", "First 3 concrete steps, one per line (empty line to finish)"),
    ("notes", "Anything else worth remembering"),
]

STREAMS_FILE = os.path.join(HERE, "streams.json")


def cmd_init_db(_args):
    sql = open(os.path.join(HERE, "schema.sql")).read()
    _psql(sql)
    print("ventures schema ready")


def cmd_capture(args):
    vid = _one(
        "INSERT INTO successbrian_os.ventures (title, raw_pitch, income_streams)"
        " VALUES (:'title', :'pitch', string_to_array(:'streams', ',')) RETURNING id",
        {"title": args.title, "pitch": args.pitch,
         "streams": ",".join(args.streams or [])})
    print("captured idea #%s: %s" % (vid, args.title))
    return vid


def cmd_list(args):
    out = _psql(
        "SELECT id, title, status, COALESCE(score->>'total','-'),"
        " created_at::date FROM successbrian_os.ventures"
        " ORDER BY id DESC LIMIT :lim",
        {"lim": str(args.limit)})
    for line in out.strip().split("\n"):
        if line.strip():
            print("#%s [%s] %s score=%s (%s)" % tuple(line.split("\t")))


def cmd_show(args):
    out = _psql(
        "SELECT id, title, status, raw_pitch, profile::text, score::text,"
        " array_to_string(income_streams, ',')"
        " FROM successbrian_os.ventures WHERE id=:'id'",
        {"id": str(args.id)}).strip()
    if not out:
        print("no idea #%d" % args.id); return
    _id, title, status, pitch, profile, score, streams = out.split("\t")
    print("#%s %s [%s]\nPitch: %s\nStreams: %s\nProfile: %s\nScore: %s" % (
        _id, title, status, pitch, streams,
        json.dumps(json.loads(profile), indent=1),
        json.dumps(json.loads(score), indent=1)))


def _get(vid):
    out = _psql(
        "SELECT id, title, raw_pitch, profile::text,"
        " array_to_string(income_streams, ',')"
        " FROM successbrian_os.ventures WHERE id=:id",
        {"id": str(vid)}).strip()
    if not out:
        return None
    _id, title, pitch, profile, streams = out.split("\t")
    return (int(_id), title, pitch, json.loads(profile),
            [s for s in streams.split(",") if s])


def _prompt_list(question):
    print(question)
    out = []
    while True:
        try:
            ln = input("> ").strip()
        except EOFError:
            break
        if not ln:
            break
        out.append(ln)
    return out


def cmd_flesh(args):
    row = _get(args.id)
    if not row:
        print("no idea #%d" % args.id); return
    _id, title, pitch, profile, streams = row
    profile = dict(profile or {})
    if args.answers_json:
        answers = json.loads(open(args.answers_json).read())
    else:
        answers = {}
        print("Fleshing out #%d: %s\n(Enter to keep existing/skip)\n" % (_id, title))
        for key, question in PROFILE_FIELDS:
            if key in ("risks", "first_steps"):
                if key not in profile:
                    got = _prompt_list(question)
                    if got:
                        answers[key] = got
            else:
                cur = profile.get(key, "")
                try:
                    ln = input("%s%s: " % (question, " [%s]" % cur if cur else "")).strip()
                except EOFError:
                    ln = ""
                if ln:
                    answers[key] = ln
    # normalize numerics / lists
    for numkey in ("startup_cost_usd", "weekly_hours"):
        if numkey in answers:
            try:
                answers[numkey] = float(answers[numkey])
            except ValueError:
                del answers[numkey]
    if "stream_fit" in answers and isinstance(answers["stream_fit"], str):
        answers["stream_fit"] = [s.strip() for s in answers["stream_fit"].split(",") if s.strip()]
    profile.update(answers)
    _psql("UPDATE successbrian_os.ventures SET profile=:'profile'::jsonb,"
          " status='fleshed', updated_at=now() WHERE id=:id",
          {"profile": json.dumps(profile), "id": str(_id)})
    print("idea #%d fleshed out (%d fields)" % (_id, len(profile)))


def cmd_questions(args):
    """Ask local Morpheus for tailored follow-up questions on a raw pitch."""
    row = _get(args.id)
    if not row:
        print("no idea #%d" % args.id); return
    _id, title, pitch, profile, streams = row
    prompt = (
        "A solopreneur with income streams in %s has this raw business idea:\n"
        "TITLE: %s\nPITCH: %s\n\n"
        "Ask the 5 most important clarifying questions that would help flesh "
        "this into a real plan (customer, money, costs, time, risks). One per "
        "line, no numbering, no extra text." %
        (", ".join(streams) if streams else "various online businesses",
         title, pitch))
    req = urllib.request.Request(
        MORPHEUS_URL,
        data=json.dumps({"model": "morpheus",
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 300, "stream": False,
                         "temperature": 0.5}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    print(out["choices"][0]["message"]["content"])


def cmd_score(args):
    row = _get(args.id)
    if not row:
        print("no idea #%d" % args.id); return
    _id, title, pitch, profile, streams = row
    streams_suggest = []
    try:
        streams_suggest = json.load(open(STREAMS_FILE))
    except Exception:
        pass
    result = score_profile(profile, streams or [], streams_suggest)
    _psql("UPDATE successbrian_os.ventures SET score=:'score'::jsonb,"
          " status='scored', updated_at=now() WHERE id=:id",
          {"score": json.dumps(result), "id": str(_id)})
    print("idea #%d score: %d/100 (%s)" % (_id, result["total"], result["band"]))
    for k, v in result["breakdown"].items():
        print("  %s: %s" % (k, v))


def cmd_promote(args):
    row = _get(args.id)
    if not row:
        print("no idea #%d" % args.id); return
    _id, title, pitch, profile, streams = row
    if not profile:
        print("flesh out idea #%d first" % _id); return
    draft = draft_goal(title, pitch, profile, streams or [])
    did = _one(
        "INSERT INTO successbrian_os.goal_drafts (venture_id, title, description, milestones)"
        " VALUES (:id, :'title', :'descr', :'ms'::jsonb) RETURNING id",
        {"id": str(_id), "title": draft["title"],
         "descr": draft["description"], "ms": json.dumps(draft["milestones"])})
    _psql("UPDATE successbrian_os.ventures SET status='drafted',"
          " updated_at=now() WHERE id=:id", {"id": str(_id)})
    print("goal draft #%s from idea #%d: %s" % (did, _id, draft["title"]))
    print("Milestones:")
    for m in draft["milestones"]:
        print("  - %s" % m["title"])


def cmd_streams(_args):
    import streams as streamlib
    for s in streamlib.effective():
        flag = "PERMANENT" if s["permanent"] else ("on" if s["enabled"] else "off")
        print("%-15s %-9s (%s)" % (s["name"], flag, s["source"]))


def main():
    ap = argparse.ArgumentParser(prog="ideas.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p = sub.add_parser("capture")
    p.add_argument("title"); p.add_argument("pitch")
    p.add_argument("--streams", nargs="*", default=[])
    p = sub.add_parser("list"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("show"); p.add_argument("id", type=int)
    p = sub.add_parser("flesh"); p.add_argument("id", type=int)
    p.add_argument("--answers-json")
    p = sub.add_parser("questions"); p.add_argument("id", type=int)
    p = sub.add_parser("score"); p.add_argument("id", type=int)
    p = sub.add_parser("promote"); p.add_argument("id", type=int)
    sub.add_parser("streams")
    args = ap.parse_args()
    {"init-db": cmd_init_db, "capture": cmd_capture, "list": cmd_list,
     "show": cmd_show, "flesh": cmd_flesh, "questions": cmd_questions,
     "score": cmd_score, "promote": cmd_promote,
     "streams": cmd_streams}[args.cmd](args)


if __name__ == "__main__":
    main()
