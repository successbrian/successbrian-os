#!/usr/bin/env python3
"""Live four-seat panel run, TONIGHT 2026-10-24 (Brian: "run this tonight").

Runs ALONGSIDE tonight's official 02:30 session — it does NOT replace it
and does NOT touch the official ledger, minutes, Atlas, or sink.
The official session still runs one seat per item; this run judges the
first N_ITEMS of tonight's queue with the four best seats each, so
tonight produces both a single-seat record and a four-seat comparison.

Feed: same Atlas queue the session sees (load_agenda with the official
ledger, so ledgered items are excluded), enriched + prioritized +
sorted the same way, first N_ITEMS only. Morpheus sequential calls
(via panel.judge_panel), so this queues behind / interleaves with the
official session on Morpheus — it slows both a little, it breaks
neither. Output, appended per item as it completes, to:
  board/minutes/board-panel-20261024.jsonl
  board/minutes/board-panel-20261024.md
No log file: progress is the output files themselves.
"""
import json
import os
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os")
from board.harness.agenda import load_agenda, AgendaLedger
from board.harness.brief import BriefBuilder
from board.harness.panel import judge_panel
from board.harness.seats import Seat
from board.harness.session import load_config, make_worker
from board.harness.enrich import enrich_items
from board.harness.priority import score_item

CFG_PATH = "/home/successbrian/successbrian-os/board/config/brian.yaml"
N_ITEMS = 20


def main():
    cfg = load_config(CFG_PATH)
    seats = [Seat.from_dict(s) for s in cfg.get("seats", [])]
    agenda_cfg = cfg.get("agenda", {})
    minutes_dir = os.path.expanduser(cfg.get("minutes_dir", "~/workspace/altair-brain/inbox"))
    ledger = AgendaLedger(agenda_cfg.get("ledger_path") or os.path.join(minutes_dir, "board-agenda-ledger.jsonl"))
    queue = load_agenda(cfg, ledger)
    print(f"PANEL LIVE: queue after ledger = {len(queue)} items", flush=True)
    if queue:
        enrich_items(queue, via=agenda_cfg.get("via", "direct"))
        for item in queue:
            score_item(item)
        queue.sort(key=lambda i: -i.priority_score)
    brief_keys = sorted({k for s in seats for k in s.brief_keys})
    brief = BriefBuilder().build(brief_keys)
    worker = make_worker(cfg)
    out_jsonl = "/home/successbrian/successbrian-os/board/minutes/board-panel-20261024.jsonl"
    out_md = "/home/successbrian/successbrian-os/board/minutes/board-panel-20261024.md"
    with open(out_md, "w") as f:
        f.write("# Board panel LIVE RUN — 2026-10-24 (Morpheus, 4 best seats per item)\n\n")
        f.write("Runs alongside tonight's official 02:30 session (one seat per item). ")
        f.write("Panel output only: not official minutes, not a ledger, nothing to Atlas or the sink.\n\n")
    for item in queue[:N_ITEMS]:
        result = judge_panel(worker, item, seats, lambda seat: brief.for_seat(seat.brief_keys), deadline_s=300, threshold=0.90)
        row = {"item_key": item.key, "kind": item.kind, "title": item.title,
               "seats": result.seats,
               "rulings": [{"seat": r.seat_title, "call": r.call, "rationale": r.rationale,
                            "confidence": r.confidence, "verdict": r.verdict} for r in result.rulings],
               "split": result.split, "overreach": result.overreach, "directions": result.directions}
        with open(out_jsonl, "a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        with open(out_md, "a") as f:
            f.write(f"## {item.key} — {item.title}\n")
            f.write(f"Seats: {', '.join(result.seats)} | split={result.split} overreach={result.overreach} directions={result.directions}\n")
            for r in result.rulings:
                f.write(f"- **{r.seat_title}** ({r.verdict}, {r.confidence}): {r.call}\n  _{r.rationale}_\n")
            f.write("\n")
        print(f"PANEL LIVE: {item.key} done, {len(result.rulings)} rulings, split={result.split} overreach={result.overreach}", flush=True)
    print(f"PANEL LIVE: complete, {min(N_ITEMS, len(queue))} items", flush=True)


if __name__ == "__main__":
    main()
