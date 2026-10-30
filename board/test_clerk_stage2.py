#!/usr/bin/env python3
"""Self-test for clerk.py stage two (deepen + factcheck), 2026-10-25.
Fabricates a questions file + rulings ledger + rules file in a temp
dir, runs both jobs against them via env overrides (CLERK_MINUTES_DIR,
CLERK_RULE_FILES), and asserts the outputs. Run anywhere; it drives
the real clerk.py by absolute path."""
import json
import os
import subprocess
import sys
import tempfile

CLERK = os.path.expanduser("~/successbrian-os/board/clerk.py")
ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + name)
    ok, fail = ok + bool(cond), fail + (not cond)


def run_job(job, env):
    r = subprocess.run([sys.executable, CLERK, job], env=env,
                       capture_output=True, text=True)
    return r


def write_jsonl(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, CLERK_MINUTES_DIR=td,
               CLERK_RULE_FILES=os.path.join(td, "rules.md"))
    with open(os.path.join(td, "rules.md"), "w") as f:
        f.write("# Test rules\n\n"
                "Rule T1: ecosystem purchases require a receipt on "
                "file before approval.\n"
                "Rule T2: pricing claims must cite a checked price.\n")

    # prior ruling on the alpha item, in an older session's ledger
    write_jsonl(os.path.join(td, "board-rulings-board-20261020.jsonl"), [
        {"event": "ruled", "session_tag": "board-20261020",
         "item_key": "task:alpha-1", "kind": "task",
         "title": "Alpha pilot renewal for ecosystem purchases",
         "seat": "Chief Test Officer", "call": "Approve the pilot.",
         "rationale": "Grounded.", "confidence": 0.99,
         "verdict": "binding"},
        {"event": "initial_read", "session_tag": "board-20261020",
         "item_key": "task:alpha-1", "seat": "Chief Test Officer",
         "questions": ["ignored by prior-decision search"]},
    ])

    # earlier session already carried the duplicate item
    write_jsonl(os.path.join(td, "board-questions-board-20261026.jsonl"), [
        {"event": "questions", "item_key": "task:dup-1", "kind": "task",
         "title": "Duplicate me please", "seat": "Chief Test Officer",
         "session_tag": "board-20261026",
         "questions": ["What is this about?"],
         "readers_reason": "panel best-four"},
    ])

    # latest session: alpha (dup questions across seats + pair + an
    # outside question + a due date) and the duplicate item again
    write_jsonl(os.path.join(td, "board-questions-board-20261027.jsonl"), [
        {"event": "questions", "item_key": "task:alpha-1", "kind": "task",
         "title": "Alpha pilot renewal for ecosystem purchases by Oct 31",
         "seat": "Chief Test Officer", "session_tag": "board-20261027",
         "questions": ["What is the current budget?",
                       "Has this been decided before?"],
         "readers_reason": "panel best-four"},
        {"event": "questions", "item_key": "task:alpha-1", "kind": "task",
         "title": "Alpha pilot renewal for ecosystem purchases by Oct 31",
         "seat": "Chief Second Officer", "session_tag": "board-20261027",
         "questions": ["what is the current budget",
                       "What standing rules touch this?",
                       "What is the vendor's phone number?"],
         "readers_reason": "panel best-four"},
        {"event": "questions", "item_key": "task:dup-1", "kind": "task",
         "title": "Duplicate me please", "seat": "Chief Test Officer",
         "session_tag": "board-20261027",
         "questions": ["What is this about?"],
         "readers_reason": "panel best-four"},
    ])

    r = run_job("deepen", env)
    print(r.stdout.strip())
    check("deepen exits 0", r.returncode == 0)
    deep = {row["item_key"]: row for row in read_jsonl(
        os.path.join(td, "board-deepened-board-20261027.jsonl"))}
    a = deep["task:alpha-1"]
    check("merged questions deduped across seats (5 raw -> 4)",
          len(a["merged_questions"]) == 4)
    check("prior decision found from the ledger",
          len(a["prior_decisions"]) == 1
          and a["prior_decisions"][0]["call"] == "Approve the pilot.")
    check("standing rules matched (receipt/purchase rule)",
          any("receipt" in r["excerpt"] for r in a["standing_rules"]))
    check("always-ask pair answered from the house",
          len(a["house_answers"]) >= 2
          and a["house_answers"][0]["answer"].startswith("1 prior"))
    check("outside requests split out (budget + vendor phone)",
          a["outside_requests"] ==
          [{"question": "What is the current budget?"},
           {"question": "What is the vendor's phone number?"}])
    check("due hint extracted (Oct 31 -> 2026-10-31)",
          a["due_hint"] and a["due_hint"]["date"] == "2026-10-31")
    check("duplicate flagged with the earlier tag",
          deep["task:dup-1"]["duplicate_of"] == "board-20261026")
    reqs = read_jsonl(os.path.join(td, "board-requests-board-20261027.jsonl"))
    check("requests file carries the outside question",
          any(x["item_key"] == "task:alpha-1"
              and "phone" in x["question"] for x in reqs))

    # factcheck on the clean deepened output
    r = run_job("factcheck", env)
    print(r.stdout.strip())
    check("factcheck exits 0", r.returncode == 0)
    fc = {row["item_key"]: row for row in read_jsonl(
        os.path.join(td, "board-factcheck-board-20261027.jsonl"))}
    check("clean packet: prior decision verified, no conflicts",
          any("prior decision" in v["claim"]
              for v in fc["task:alpha-1"]["verified"])
          and fc["task:alpha-1"]["source_conflicts"] == [])

    # tamper: mutate the recorded call + add an invented packet whose
    # prior decision and price exist nowhere in the house
    rows = read_jsonl(os.path.join(td, "board-deepened-board-20261027.jsonl"))
    for row in rows:
        if row["item_key"] == "task:alpha-1":
            row["prior_decisions"][0]["call"] = \
                "Approve the pilot immediately, no conditions."
    rows.append({
        "item_key": "task:fake-9", "title": "Fake item priced at $9,999.99",
        "due_hint": None, "duplicate_of": None,
        "prior_decisions": [{
            "source": "rulings-ledger", "item_key": "task:fake-9",
            "seat": "Chief Nobody", "call": "Invented call.",
            "confidence": 0.99, "session_tag": "board-20261020"}],
        "standing_rules": [], "merged_questions": ["Is this real?"],
        "house_answers": [], "outside_requests": []})
    write_jsonl(os.path.join(td, "board-deepened-board-20261027.jsonl"), rows)
    r = run_job("factcheck", env)
    print(r.stdout.strip())
    fc = {row["item_key"]: row for row in read_jsonl(
        os.path.join(td, "board-factcheck-board-20261027.jsonl"))}
    check("mutated call caught as a source conflict",
          len(fc["task:alpha-1"]["source_conflicts"]) == 1
          and fc["task:alpha-1"]["source_conflicts"][0]["source_says"]
          == "Approve the pilot.")
    check("invented prior decision flagged, not dropped",
          any("not found" in f["reason"]
              for f in fc["task:fake-9"]["flagged"]))
    check("invented price flagged as unverified",
          any(f["claim"] == "price $9,999.99"
              for f in fc["task:fake-9"]["flagged"]))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
