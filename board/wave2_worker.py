#!/usr/bin/env python3
"""Wave-2 all-day worker (Brian, 2026-10-24): CFO on Sonic, all day.

WHY: Morpheus wave-1 judges write rulings faster than one in-session
closer can close them, and the in-session closer gets skipped when the
2-hour cap hits. So wave 2 is decoupled from the session window: this
worker drains the wave-1 rulings ledger continuously, in batches, with
the CFO running on Sonic (Qwen3.6-35B-A3B Q6_K, :11439, 98k context),
while Sonic stays up.

FEED: board-rulings-<tag>.jsonl files written per decision by the
session harness (RulingsLedger, fsync on write), in both minutes dirs:
  ~/successbrian-os/board/minutes/
  ~/workspace/altair-brain/inbox/
Only rows with event == "ruled" are closed here; "stuck" rows are noted
but not closed (they re-present in a later session).

OUTPUT (v1, REVIEW ONLY): one batch row per run in
  board/minutes/board-wave2-closer-<YYYYMMDD>.jsonl
plus a readable append in board-wave2-closer-<YYYYMMDD>.md,
AND one row in PostgreSQL successbrian_os.board_wave2_closer
(Brian, 2026-10-24: "write to postgresql"; no log file).
Nothing is written to Atlas, nothing to the second_brain sink, nothing
to the official agenda ledger, and nothing to official minutes, until
Brian approves sink recording for wave-2 batches. The in-session
Morpheus closer still runs (or is skipped) as configured; this worker
does not replace it, it catches what it leaves behind.

STATE: board/minutes/board-wave2-state.json maps each rulings file to
the number of lines already processed. State advances ONLY after a
successful Sonic call, a successful PostgreSQL insert, and successful
file writes; any failure leaves the batch unprocessed for the next run.
FIX 2026-10-24: batch_files now counts NEW lines only (was seeded
with seen, which double-counted and skipped rulings 41-60 after
batch 2; state was corrected back to 40, the lines actually closed).

RUN: intended as a cron every 30 minutes, all day:
  */30 * * * * python3 ~/successbrian-os/board/wave2_worker.py
       >> ~/logs/board-wave2.log 2>&1
A flock on the state lock file prevents overlapping runs.
"""
import fcntl
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime

BASE = "/home/successbrian/successbrian-os"
MINUTES_DIRS = [
    os.path.join(BASE, "board/minutes"),
    os.path.expanduser("~/workspace/altair-brain/inbox"),
]
STATE_PATH = os.path.join(BASE, "board/minutes/board-wave2-state.json")
LOCK_PATH = os.path.join(BASE, "board/minutes/board-wave2-state.lock")
SONIC_URL = "http://127.0.0.1:11439/v1/chat/completions"
SONIC_MODEL = "qwen-a3b"
BATCH_MAX = 20
TIMEOUT_S = 300

CFO_SYSTEM = (
    "You are the Chief Financial Officer, wave-2 closer for Brian's Board "
    "of Directors. You do NOT rule on individual agenda items one by one. "
    "You close over wave-1 chiefs' rulings, all day, in batches. Your job: "
    "(1) consolidate the money picture from this batch — revenue streams "
    "together, spending, runway, capital allocation; (2) make financial "
    "calls ONLY on money items in this batch; (3) flag any ruling that "
    "conflicts with another, overreaches (e.g. approving a purchase when "
    "only a spec was proposed), or needs a human. Return your calls as a "
    "numbered list, each as 'call / Rationale: ...'. Never approve a "
    "purchase, contract, or irreversible move on the board's word alone — "
    "flag those for Brian."
)


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


def call_sonic(batch):
    items_text = "\n".join(
        f"- [{r['seat']}] {r['item_key']}: {r['call']} (why: {r['rationale']})"
        for r in batch
    )
    user = (
        "WAVE-1 RULINGS IN THIS BATCH (close over these, do not re-rule "
        "each item from scratch):\n\n" + items_text + "\n\n"
        "Your calls (money synthesis + financial calls on money items + "
        "conflict/overreach flags):"
    )
    payload = json.dumps({
        "model": SONIC_MODEL,
        "messages": [
            {"role": "system", "content": CFO_SYSTEM},
            {"role": "user", "content": user},
        ],
        "max_tokens": 800,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        SONIC_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


PG_CONN = {"host": "localhost", "dbname": "ecosystem_central", "user": "successbrian"}
PG_TABLE = "successbrian_os.board_wave2_closer"


def write_postgres(row, batch):
    """Insert one closed batch row. Raises on failure (batch retries)."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(**PG_CONN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {PG_TABLE} "
                "(batch_id, session_tags, item_keys, n_rulings, sonic_calls, "
                " sonic_raw_head, rulings) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (batch_id) DO NOTHING",
                (
                    row["batch_id"],
                    row["session_tags"],
                    row["item_keys"],
                    row["n_rulings"],
                    psycopg2.extras.Json(row["sonic_calls"]),
                    row["sonic_raw_head"],
                    psycopg2.extras.Json(batch),
                ),
            )
        conn.commit()
    finally:
        conn.close()



def salvage_calls(raw):
    """Salvage CFO synthesis written as 'N. call / Rationale: <text>'.

    Live evidence 2026-10-24: Sonic sometimes echoes the format
    placeholder literally, so parse_calls yields a degenerate call
    ('call') or nothing, while the synthesis prose itself is real.
    In that shape the text after 'Rationale:' IS the content: its
    first sentence becomes the call, the full text the rationale.
    """
    import re

    out = []
    parts = re.split(r"(?m)^\s*\d+\.\s*call\s*/\s*Rationale:\s*", raw or "")
    for part in parts[1:]:
        text = " ".join(part.split()).strip()
        if not text:
            continue
        first = text.split(". ")[0].strip()
        call = (first + ".") if not first.endswith(".") else first
        out.append((call[:300], text[:600]))
    return out


def main():
    os.makedirs(os.path.join(BASE, "board/minutes"), exist_ok=True)
    lock_f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("wave2: another run is already active, exiting")
        return 0
    state = load_state()
    files = sorted(set(
        p for d in MINUTES_DIRS for p in glob.glob(os.path.join(d, "board-rulings-*.jsonl"))
    ))
    batch = []
    batch_files = {}  # path -> lines consumed in this batch
    for path in files:
        try:
            with open(path) as f:
                lines = f.readlines()
        except OSError:
            continue
        seen = int(state.get(path, 0))
        for line in lines[seen:]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            batch_files[path] = batch_files.get(path, 0) + 1
            if row.get("event") != "ruled":
                continue
            batch.append(row)
            if len(batch) >= BATCH_MAX:
                break
        if len(batch) >= BATCH_MAX:
            break
    if not batch:
        print("wave2: no new rulings")
        return 0
    print(f"wave2: closing batch of {len(batch)} rulings from "
          + ", ".join(f"{os.path.basename(p)}" for p in batch_files), flush=True)
    try:
        raw = call_sonic(batch)
    except Exception as e:  # Sonic failure: state NOT advanced, batch retries
        print(f"wave2: Sonic call failed ({e}); batch left unprocessed")
        return 1
    # Reuse the harness parser so call format matches the session's.
    sys.path.insert(0, BASE)
    try:
        from board.harness.worker import parse_calls
        calls = parse_calls(raw)
    except Exception:
        calls = []
    degenerate = (not calls
                  or all(c.strip().lower() == "call" for c, _ in calls)
                  or all(r.strip() == "(no rationale given)" for _, r in calls))
    if degenerate:
        salvaged = salvage_calls(raw)
        if salvaged:
            calls = salvaged
    today = datetime.now().strftime("%Y%m%d")
    out_jsonl = os.path.join(BASE, f"board/minutes/board-wave2-closer-{today}.jsonl")
    out_md = os.path.join(BASE, f"board/minutes/board-wave2-closer-{today}.md")
    batch_id = f"wave2-{today}-{datetime.now().strftime('%H%M%S')}"
    row = {
        "batch_id": batch_id,
        "session_tags": sorted({r.get("session_tag", "") for r in batch}),
        "item_keys": [r.get("item_key") for r in batch],
        "sonic_calls": [{"call": c, "rationale": r} for c, r in calls],
        "sonic_raw_head": raw[:2000],
        "n_rulings": len(batch),
    }
    try:
        write_postgres(row, batch)
    except Exception as e:  # PG failure: state NOT advanced, batch retries
        print(f"wave2: PostgreSQL insert failed ({e}); batch left unprocessed")
        return 1
    with open(out_jsonl, "a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())
    with open(out_md, "a") as f:
        f.write(f"\n## Wave-2 batch {batch_id} ({len(batch)} rulings, CFO on Sonic, REVIEW ONLY)\n")
        for c, r in calls:
            f.write(f"- {c}\n  _{r}_\n")
        if not calls:
            f.write(f"_No parsed calls; raw head:_ {raw[:500]}\n")
    # Advance state only now, after Sonic + PG + files all succeeded.
    for path, consumed in batch_files.items():
        state[path] = int(state.get(path, 0)) + consumed
    save_state(state)
    print(f"wave2: batch {batch_id} closed, {len(calls)} Sonic calls, state advanced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
