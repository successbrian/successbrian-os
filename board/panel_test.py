#!/usr/bin/env python3
"""Stub test for the four-seat wave-1 panel. NO Morpheus, NO Atlas,
NO official ledger, NO sink. Writes only board/minutes/board-panel-test-20261024.jsonl/.md.
"""
import json
import os
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os")
from board.harness.agenda import AgendaItem
from board.harness.panel import best_four, judge_panel
from board.harness.seats import Seat

SEATS = [
    Seat("Chief Ecosystem Build Officer", "ecosystem architecture", "build the ecosystem", wave=1),
    Seat("Chief MLM Officer", "mlm network marketing", "mlm companies", wave=1),
    Seat("Chief Affiliate Marketing Officer", "affiliate marketing", "affiliate income", wave=1),
    Seat("Chief Marketing Officer", "marketing email", "marketing campaigns", wave=1),
    Seat("Chief Trading Desk Officer", "trading desk", "trading decisions", wave=1),
    Seat("Chief Blog Content Officer", "blog content", "blog network", wave=1),
    Seat("Chief Hardware Flipping Officer", "hardware flipping", "hardware resale", wave=1),
    Seat("Chief People Enrichment Officer", "people enrichment", "people and contacts", wave=1),
    Seat("Chief Financial Officer", "money allocation finance", "financial calls", wave=2, depends_on=["all"]),
]


class StubResult:
    def __init__(self, calls):
        self.calls = calls
        self.ok = True
        self.latency_s = 1.0
        self.attempts = 1


class StubWorker:
    """Canned calls per seat title, per item key."""
    def __init__(self, script):
        self.script = script

    def run_agenda_item(self, seat, item, brief_text, deadline_s=300):
        return StubResult([self.script[(item.key, seat.title)]])


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name


# Item A: unanimous approve, no theme.
item_a = AgendaItem(key="task:test-bigger-packets", kind="task",
                    title="Build bigger ruling packets for board seats",
                    text="Items are filed as bare titles; bigger packets carry stakes and evidence.")
four_a = best_four(item_a, SEATS)
check("A: four seats", len(four_a) == 4)
check("A: distinct profiles", len({s.title for s, _, _ in four_a}) == 4)
check("A: no CFO (wave-2 excluded)", all(s.wave == 1 for s, _, _ in four_a))
stub_a = StubWorker({(item_a.key, s.title): ("Approve building bigger packets", "More context improves decisions")
                     for s, _, _ in four_a})
res_a = judge_panel(stub_a, item_a, SEATS, lambda seat: "")
check("A: four rulings recorded", len(res_a.rulings) == 4)
check("A: unanimous, no split", res_a.split is False)
check("A: no overreach", res_a.overreach is False)

# Item B: clerk-box spec, theme -> Ecosystem first, purchase approvals present.
item_b = AgendaItem(key="task:test-clerk-box", kind="task",
                    title="SPEC: a dedicated mini that ticks all day on ecosystem decisions",
                    text="Mused as a need, NOT an approved purchase. Duties: curate, frame, assign chairs.",
                    theme="architecture-direction")
four_b = best_four(item_b, SEATS)
check("B: theme seat first", four_b[0][0].title == "Chief Ecosystem Build Officer")
check("B: four distinct, no CFO", len({s.title for s, _, _ in four_b}) == 4 and all(s.wave == 1 for s, _, _ in four_b))
script_b = {}
for i, (s, _, _) in enumerate(four_b):
    if i % 2 == 0:
        script_b[(item_b.key, s.title)] = ("Approve the SPEC for the dedicated mini", "Spec only, no purchase yet")
    else:
        script_b[(item_b.key, s.title)] = ("Approve the purchase of the dedicated mini", "Efficiency gains")
res_b = judge_panel(StubWorker(script_b), item_b, SEATS, lambda seat: "")
check("B: four rulings recorded", len(res_b.rulings) == 4)
check("B: overreach flagged (purchase on a spec item)", res_b.overreach is True)

# Item C: direction split, 3 approve / 1 reject.
item_c = AgendaItem(key="task:test-split", kind="task",
                    title="Approve a new spending program for marketing",
                    text="A spending program that costs money every month.")
four_c = best_four(item_c, SEATS)
script_c = {}
for i, (s, _, _) in enumerate(four_c):
    script_c[(item_c.key, s.title)] = (("Reject the spending program", "Cost exceeds benefit") if i == 3
                                        else ("Approve the spending program", "Growth is worth it"))
res_c = judge_panel(StubWorker(script_c), item_c, SEATS, lambda seat: "")
check("C: direction split flagged", res_c.split is True)
check("C: directions counted", res_c.directions == {"approve": 3, "reject": 1})

# Item D: same decision, different opening verbs (live v1 failure:
# inbox-552/554 were flagged split though all four seats agreed).
item_d = AgendaItem(key="task:test-synonyms", kind="task",
                    title="Tag the source document as extracted after rows become canonical",
                    text="Tag or archive the source document once its rows are canonical.")
four_d = best_four(item_d, SEATS)
verbs = ["Allow the source document to be tagged as extracted",
         "Approve tagging the source document as extracted",
         "Prepare tagging of the source document as extracted",
         "Keep tagging the source document as extracted after rows land"]
script_d = {(item_d.key, s.title): (verbs[i], "Rows are canonical") for i, (s, _, _) in enumerate(four_d)}
res_d = judge_panel(StubWorker(script_d), item_d, SEATS, lambda seat: "")
check("D: synonym wordings, one direction family", res_d.directions == {"approve": 4})
check("D: synonym unanimity, no split", res_d.split is False)

# Item E: all four escalate — unanimous escalate, not a split.
item_e = AgendaItem(key="task:test-escalate", kind="task",
                    title="Decide the intended consumer of the supports edge",
                    text="The intended consumer is unclear from the record.")
four_e = best_four(item_e, SEATS)
script_e = {(item_e.key, s.title): ("Escalate this to the architecture team for clarification", "Consumer unclear")
            for s, _, _ in four_e}
res_e = judge_panel(StubWorker(script_e), item_e, SEATS, lambda seat: "")
check("E: all escalate counted as escalate", res_e.directions == {"escalate": 4})
check("E: unanimous escalate, no split", res_e.split is False)

out_jsonl = "/home/successbrian/successbrian-os/board/minutes/board-panel-test-20261024.jsonl"
with open(out_jsonl, "w") as f:
    for res in (res_a, res_b, res_c, res_d, res_e):
        f.write(json.dumps({"item_key": res.item_key, "seats": res.seats,
                            "rulings": [{"seat": r.seat_title, "call": r.call} for r in res.rulings],
                            "split": res.split, "overreach": res.overreach,
                            "directions": res.directions}) + "\n")
print("ALL PANEL TESTS PASSED; test output:", out_jsonl)
