#!/usr/bin/env python3
"""atlas_manage — the fleet seats' filing hand into SuccessBrian OS.

PURPOSE:
    Give any agent seat (Altair first, 2026-11-15) the filing moves
    Spencer performs by hand: dump Intel Bridge captures in the same
    pass the learning arises, set/append Atlas node summaries, assert
    typed Atlas edges, append dated notes to registry records, and
    register PM projects / checks / tasks — each datum in its
    sanctioned home, with provenance naming the acting seat.

SEAT-GENERIC BY DESIGN (Brian's location-independent-seats doctrine):
    Nothing here is hardcoded to one seat. The actor is a parameter
    (--actor, else $ATLAS_ACTOR / $SBOS_ACTOR, else the Hermes
    active_profile, else "unknown-seat") and is stamped into every
    provenance line and receipt. Paths point at the fleet's shared
    tools (this file lives beside atlas.py / scattered_brain.py in
    successbrian-os/tools/atlas/), never at a seat's profile dir.
    Any seat with this repo + DB access adopts the package as-is:
    copy the companion skill (atlas-manage-skill/SKILL.md) into its
    profile and, optionally, wire the hooks below.

DOCTRINE ENCODED (Brian's words govern; see the skill for the full
text):
    * Everything dumps (2026-11-14): "chat agents should dump dump
      dump. intel workers dump. everything dumps. the ecosystem
      manages the rest from there." Producers never curate at the
      source; the dump is part of the turn.
    * Atlas summaries carry no sentence limit (Brian's correction,
      2026-11-14): a summary should genuinely summarize; the long-form
      record lives in git docs / captures, Atlas holds structure,
      pointers, and real summaries.
    * Graph, not a tree (2026-10-23): nodes with multiple typed
      edges; one path is never the whole structure.
    * Do not guess (2026-10-27); not knowing is not the same as not
      (2026-10-23): unknowns are recorded as UNKNOWN, never filled in.

OPS:
    capture        dump an Intel Bridge capture (scattered_brain)
    summary-set    replace an Atlas node's summary (atlas.nodes)
    summary-append append a dated, actor-stamped update to a summary
    node-add       create/upsert an Atlas node (via atlas.py)
    edge           assert a typed edge (via atlas.py add-edge)
    task-add       register an Atlas task about a node (blockers)
    note-append    append a dated note to campaignsdesk.blogs (by slug)
    pm-register    register a PM project (via project_qa.py)
    pm-check       add a QA check to a PM project (via project_qa.py)
    selftest       end-to-end round-trip: capture + discard, DB probe
    hook-pre-llm   Hermes shell hook: one filing reminder per session
    hook-post-tool Hermes shell hook: ledger second_brain.py writes
    hook-finalize  Hermes shell hook: sweep — if the seat wrote to the
                   second brain in the window but filed no bridge
                   capture, file a missed-filing FLAG capture so the
                   miss is visible in the bridge, never silent. The
                   hook never invents the intel itself.

STATE (per actor, under $ATLAS_MANAGE_STATE_DIR or
~/.local/state/atlas_manage/): receipts-<actor>.jsonl,
sbwrites-<actor>.jsonl, sweep-<actor>.json, reminded-<actor>.json,
last-selftest-<actor>.json.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent            # successbrian-os/tools/atlas
TOOLS = HERE.parent                               # successbrian-os/tools
ATLAS_PY = HERE / "atlas.py"
PM_QA = TOOLS / "pm" / "project_qa.py"
sys.path.insert(0, str(TOOLS))                    # sbos_common
sys.path.insert(0, str(HERE))                     # scattered_brain

STATE_DIR = Path(os.environ.get(
    "ATLAS_MANAGE_STATE_DIR",
    Path.home() / ".local" / "state" / "atlas_manage"))


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def resolve_actor(cli_actor):
    if cli_actor:
        return cli_actor
    for env in ("ATLAS_ACTOR", "SBOS_ACTOR"):
        if os.environ.get(env):
            return os.environ[env]
    try:
        ap = (Path.home() / ".hermes" / "active_profile").read_text().strip()
        if ap:
            return ap
    except OSError:
        pass
    return "unknown-seat"


def receipt(actor, op, detail):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_DIR / f"receipts-{actor}.jsonl", "a") as f:
            f.write(json.dumps({"ts": now_iso(), "actor": actor,
                                "op": op, "detail": detail}) + "\n")
    except OSError:
        pass


def pg_conn():
    import sbos_common
    return sbos_common.connect(user="postgres")


def run_cli(argv):
    proc = subprocess.run(argv, capture_output=True, text=True,
                          timeout=120)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"command failed ({proc.returncode}): "
                         f"{' '.join(argv)}")
    return proc.stdout.strip()


# ---------------------------------------------------------------- ops

def op_capture(a):
    import scattered_brain
    conn = scattered_brain.pg()
    try:
        prov = (f"provenance: filed by {a.actor} via atlas_manage "
                f"({now_iso()})")
        ctx = (a.context + "\n" if a.context else "") + prov
        cid = scattered_brain.capture(conn, a.title, ctx, a.raw or "")
    finally:
        conn.close()
    receipt(a.actor, "capture", {"id": cid, "title": a.title})
    print(f"captured #{cid}: {a.title}")
    return 0


def _summary_update(a, new_summary):
    conn = pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE atlas.nodes SET summary=%s, updated_at=now() "
                "WHERE node_key=%s", (new_summary, a.node))
            n = cur.rowcount
        if n == 0:
            conn.rollback()
            print(f"ERROR: no atlas node {a.node!r}", file=sys.stderr)
            return 2
        conn.commit()
    finally:
        conn.close()
    return 0


def op_summary_set(a):
    rc = _summary_update(a, a.summary)
    if rc == 0:
        receipt(a.actor, "summary-set", {"node": a.node})
        print(f"summary set on {a.node} ({len(a.summary)} chars)")
    return rc


def op_summary_append(a):
    conn = pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT summary FROM atlas.nodes "
                        "WHERE node_key=%s", (a.node,))
            row = cur.fetchone()
        if row is None:
            print(f"ERROR: no atlas node {a.node!r}", file=sys.stderr)
            return 2
        old = row[0] or ""
    finally:
        conn.close()
    stamp = f"[Update {today()} — filed by {a.actor} via atlas_manage]"
    new = (old.rstrip() + "\n\n" if old.strip() else "") + \
        stamp + " " + a.text
    rc = _summary_update(a, new)
    if rc == 0:
        receipt(a.actor, "summary-append", {"node": a.node})
        print(f"summary appended on {a.node} (now {len(new)} chars)")
    return rc


def op_node_add(a):
    argv = [sys.executable, str(ATLAS_PY), "add-node",
            a.key, a.type, a.name]
    if a.status:
        argv += ["--status", a.status]
    if a.ref:
        argv += ["--ref", a.ref]
    if a.details:
        argv += ["--details", a.details]
    run_cli(argv)
    receipt(a.actor, "node-add", {"node": a.key})
    if a.summary:
        ns = argparse.Namespace(actor=a.actor, node=a.key,
                                summary=a.summary)
        return op_summary_set(ns)
    return 0


def op_edge(a):
    argv = [sys.executable, str(ATLAS_PY), "add-edge",
            a.from_, a.to, a.edge_type]
    if a.notes:
        argv += ["--notes", a.notes]
    run_cli(argv)
    receipt(a.actor, "edge", {"from": a.from_, "to": a.to,
                              "type": a.edge_type})
    return 0


def op_task_add(a):
    argv = [sys.executable, str(ATLAS_PY), "task-add", a.node, a.title]
    if a.about:
        argv += ["--about", a.about]
    argv += ["--found-by", a.actor]
    run_cli(argv)
    receipt(a.actor, "task-add", {"node": a.node, "title": a.title})
    return 0


def op_note_append(a):
    stamped = f" NOTE ({a.actor}, {today()}): {a.note}"
    conn = pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE campaignsdesk.blogs "
                "SET note = COALESCE(note, '') || %s, updated_at=now() "
                "WHERE slug=%s", (stamped, a.slug))
            n = cur.rowcount
        if n == 0:
            conn.rollback()
            print(f"ERROR: no campaignsdesk.blogs row slug={a.slug!r}",
                  file=sys.stderr)
            return 2
        conn.commit()
    finally:
        conn.close()
    receipt(a.actor, "note-append", {"slug": a.slug})
    print(f"note appended to blog {a.slug}")
    return 0


def op_pm_register(a):
    argv = [sys.executable, str(PM_QA), "register",
            "--key", a.key, "--title", a.title,
            "--requested-by", a.requested_by, "--owner", a.owner,
            "--registrar", a.actor]
    if a.description:
        argv += ["--description", a.description]
    run_cli(argv)
    receipt(a.actor, "pm-register", {"project": a.key})
    return 0


def op_pm_check(a):
    spec = {"cmd": a.cmd, "timeout_s": a.timeout}
    if a.contains:
        spec["contains"] = a.contains
    argv = [sys.executable, str(PM_QA), "add-check",
            "--project", a.project, "--key", a.key,
            "--title", a.title, "--type", a.type,
            "--interval-min", str(a.interval_min),
            "--spec", json.dumps(spec)]
    run_cli(argv)
    receipt(a.actor, "pm-check", {"project": a.project, "check": a.key})
    return 0


def op_selftest(a):
    problems = []
    for p in (ATLAS_PY, HERE / "scattered_brain.py", PM_QA):
        if not p.exists():
            problems.append(f"missing {p}")
    cid = nodes = None
    if not problems:
        try:
            import scattered_brain
            conn = scattered_brain.pg()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM atlas.nodes")
                    nodes = cur.fetchone()[0]
                cid = scattered_brain.capture(
                    conn, f"ATLAS_MANAGE SELFTEST {now_iso()}",
                    f"selftest round-trip by {a.actor} via atlas_manage",
                    "selftest capture; discarded immediately")
                scattered_brain.rule(conn, cid, "discard",
                                     f"atlas_manage selftest ({a.actor})")
            finally:
                conn.close()
        except Exception as e:
            problems.append(f"{type(e).__name__}: {e}")
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / f"last-selftest-{a.actor}.json").write_text(
            json.dumps({"ts": now_iso(), "actor": a.actor,
                        "ok": not problems, "problems": problems}))
    except OSError:
        pass
    if problems:
        print("ATLAS_MANAGE_SELFTEST_FAIL " + "; ".join(problems))
        return 1
    receipt(a.actor, "selftest", {"capture_id": cid})
    print(f"ATLAS_MANAGE_SELFTEST_OK actor={a.actor} "
          f"capture_id={cid} nodes={nodes}")
    return 0


# -------------------------------------------------------------- hooks

def _read_payload():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _load_jsonl(path):
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _ts(rec):
    try:
        return datetime.fromisoformat(rec["ts"]).timestamp()
    except Exception:
        return 0


def op_hook_pre_llm(a):
    p = _read_payload()
    sid = p.get("session_id") or (p.get("extra") or {}).get("session_id")
    if not sid:
        return 0
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        f = STATE_DIR / f"reminded-{a.actor}.json"
        seen = []
        if f.exists():
            seen = json.loads(f.read_text() or "[]")
        if sid in seen:
            return 0
        seen.append(sid)
        f.write_text(json.dumps(seen[-500:]))
    except Exception:
        return 0
    ctx = (
        "ATLAS FILING — standing rule (Brian, 2026-11-14): when this "
        "session surfaces substantive intel (facts, decisions, people, "
        "dates, open items), dump it to the Intel Bridge IN THE SAME "
        "PASS, via the atlas-manage skill: python3 "
        f"{HERE}/atlas_manage.py capture --actor {a.actor} "
        "--title \"<title>\" --context \"<context>\" --raw \"<raw>\". "
        "Dump, don't curate — the ecosystem manages the rest. Atlas "
        "summaries, edges, and registry notes go through the same tool.")
    print(json.dumps({"context": ctx}))
    return 0


def op_hook_post_tool(a):
    p = _read_payload()
    if p.get("tool_name") != "terminal":
        return 0
    ti = p.get("tool_input") or {}
    cmd = ti.get("command", "") if isinstance(ti, dict) else ""
    if "second_brain.py" in cmd:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with open(STATE_DIR / f"sbwrites-{a.actor}.jsonl",
                      "a") as f:
                f.write(json.dumps(
                    {"ts": now_iso(), "actor": a.actor,
                     "session_id": p.get("session_id")}) + "\n")
        except OSError:
            pass
    return 0


def op_hook_finalize(a):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        sf = STATE_DIR / f"sweep-{a.actor}.json"
        st = {}
        if sf.exists():
            st = json.loads(sf.read_text() or "{}")
        last = float(st.get("last_sweep_ts", 0) or 0)
        now = time.time()
        start = max(last, now - 86400)
        writes = [r for r in _load_jsonl(
            STATE_DIR / f"sbwrites-{a.actor}.jsonl")
            if start < _ts(r) <= now]
        caps = [r for r in _load_jsonl(
            STATE_DIR / f"receipts-{a.actor}.jsonl")
            if r.get("op") == "capture" and start < _ts(r) <= now]
        flagged = False
        if writes and not any(_ts(c) >= _ts(writes[0]) - 300
                              for c in caps):
            import scattered_brain
            conn = scattered_brain.pg()
            try:
                title = (f"Missed-filing flag ({a.actor}): second-brain "
                         f"writes without a bridge dump")
                ctx = (
                    "Filed automatically by the atlas_manage "
                    "on_session_finalize hook sweep "
                    f"({now_iso()}). The seat wrote to the second "
                    "brain in this window but no atlas_manage bridge "
                    "capture was receipted in the same window. The "
                    "hook does not read transcripts — the substance "
                    "must be re-filed by the seat or surfaced by the "
                    "clerk. Standing rule (Brian, 2026-11-14): "
                    "everything dumps; the ecosystem manages the "
                    f"rest. provenance: hook sweep for {a.actor}")
                raw = ("second-brain writes (local times):\n" +
                       "\n".join(r["ts"] for r in writes))
                cid = scattered_brain.capture(conn, title, ctx, raw)
            finally:
                conn.close()
            receipt(a.actor, "capture",
                    {"id": cid, "title": title, "hook_flag": True})
            flagged = True
        sf.write_text(json.dumps({"last_sweep_ts": now,
                                  "last_run": now_iso(),
                                  "flagged": flagged}))
    except Exception as e:  # hooks must never break the agent
        print(f"atlas_manage hook-finalize: {e}", file=sys.stderr)
    return 0


# --------------------------------------------------------------- main

def build_parser():
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--actor",
                        help="seat name for provenance (default: "
                             "$ATLAS_ACTOR, else Hermes active_profile)")
    p = argparse.ArgumentParser(
        prog="atlas_manage.py",
        description="Fleet seats' filing hand into SuccessBrian OS "
                    "(bridge captures, Atlas, registry notes, PM).")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("capture", parents=[parent],
                       help="dump an Intel Bridge capture")
    s.add_argument("--title", required=True)
    s.add_argument("--context", default="")
    s.add_argument("--raw", default="")
    s.set_defaults(fn=op_capture)

    s = sub.add_parser("summary-set", parents=[parent],
                       help="replace an Atlas node's summary")
    s.add_argument("--node", required=True)
    s.add_argument("--summary", required=True)
    s.set_defaults(fn=op_summary_set)

    s = sub.add_parser("summary-append", parents=[parent],
                       help="append a dated update to a node's summary")
    s.add_argument("--node", required=True)
    s.add_argument("--text", required=True)
    s.set_defaults(fn=op_summary_append)

    s = sub.add_parser("node-add", parents=[parent],
                       help="create/upsert an Atlas node (atlas.py)")
    s.add_argument("--key", required=True)
    s.add_argument("--type", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--status")
    s.add_argument("--ref")
    s.add_argument("--details")
    s.add_argument("--summary")
    s.set_defaults(fn=op_node_add)

    s = sub.add_parser("edge", parents=[parent],
                       help="assert a typed Atlas edge (atlas.py)")
    s.add_argument("--from", dest="from_", required=True)
    s.add_argument("--to", required=True)
    s.add_argument("--type", dest="edge_type", required=True)
    s.add_argument("--notes")
    s.set_defaults(fn=op_edge)

    s = sub.add_parser("task-add", parents=[parent],
                       help="register an Atlas task about a node")
    s.add_argument("--node", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--about")
    s.set_defaults(fn=op_task_add)

    s = sub.add_parser("note-append", parents=[parent],
                       help="append a dated note to a campaignsdesk "
                            "blog registry row")
    s.add_argument("--slug", required=True)
    s.add_argument("--note", required=True)
    s.set_defaults(fn=op_note_append)

    s = sub.add_parser("pm-register", parents=[parent],
                       help="register a PM project (project_qa.py)")
    s.add_argument("--key", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--requested-by", default="brian")
    s.add_argument("--owner", default="")
    s.add_argument("--description", default="")
    s.set_defaults(fn=op_pm_register)

    s = sub.add_parser("pm-check", parents=[parent],
                       help="add a QA check to a PM project")
    s.add_argument("--project", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--type", default="command",
                   choices=["command", "http", "judgment"])
    s.add_argument("--cmd", nargs="+", required=True,
                   help="argv for a command check")
    s.add_argument("--contains")
    s.add_argument("--timeout", type=int, default=300)
    s.add_argument("--interval-min", type=int, default=1440)
    s.set_defaults(fn=op_pm_check)

    s = sub.add_parser("selftest", parents=[parent],
                       help="end-to-end round-trip verification")
    s.set_defaults(fn=op_selftest)

    s = sub.add_parser("hook-pre-llm", parents=[parent],
                       help="Hermes shell hook: per-session reminder")
    s.set_defaults(fn=op_hook_pre_llm)

    s = sub.add_parser("hook-post-tool", parents=[parent],
                       help="Hermes shell hook: ledger second-brain "
                            "writes")
    s.set_defaults(fn=op_hook_post_tool)

    s = sub.add_parser("hook-finalize", parents=[parent],
                       help="Hermes shell hook: missed-filing sweep")
    s.set_defaults(fn=op_hook_finalize)

    return p


def main():
    a = build_parser().parse_args()
    a.actor = resolve_actor(getattr(a, "actor", None))
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
