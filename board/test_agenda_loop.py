"""Stub-model test for the 2026-10-21 agenda-loop switch. Run on k11:
   cd ~/successbrian-os && python3 /tmp/test_agenda_loop.py
No real model calls: ModelWorker._post is stubbed. No real sink: jsonl in /tmp.
No Atlas writes: agenda source is a temp jsonl queue; a separate read-only
section exercises AtlasAgenda direct against the live DB.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.expanduser("~/successbrian-os"))

from board.harness import session as session_mod
from board.harness.worker import ModelWorker
from board.harness.seats import load_config

CANNED = ("1. Approve this item and move it forward today "
          "/ Rationale: the queue must drain in order")

ModelWorker._post = lambda self, payload: CANNED

tmp = tempfile.mkdtemp(prefix="board-agenda-test-")
queue_path = os.path.join(tmp, "agenda.jsonl")
with open(queue_path, "w") as f:
    f.write(json.dumps({"key": "gate:test-money", "kind": "gate",
                        "title": "Money gate", "text": "Decide the capital allocation for this gate",
                        "theme": "money-allocation"}) + "\n")
    f.write(json.dumps({"key": "task:test-leads", "kind": "task",
                        "title": "Lead pipeline question",
                        "text": "Should the lead pipeline enrich the backlog leads first?"}) + "\n")
    f.write(json.dumps({"key": "task:test-security", "kind": "task",
                        "title": "Webhook exposure question",
                        "text": "Is public inbound webhook exposure acceptable?",
                        "theme": "security-boundary"}) + "\n")

base_cfg = load_config(os.path.expanduser("~/successbrian-os/board/config/brian.yaml"))

def make_config(deadline_s):
    cfg = dict(base_cfg)
    cfg["sink"] = {"type": "jsonl", "path": os.path.join(tmp, "decisions.jsonl")}
    cfg["minutes_dir"] = tmp
    cfg["agenda"] = {"source": "jsonl", "path": queue_path,
                     "deadline_s": deadline_s,
                     "fallback_seat": "Chief Ecosystem Build Officer"}
    p = os.path.join(tmp, f"cfg-{deadline_s}.yaml")
    import yaml
    with open(p, "w") as f:
        yaml.safe_dump(cfg, f)
    return p

fails = []
def check(name, cond, extra=""):
    print(f"{'PASS' if cond else 'FAIL'}: {name} {extra}")
    if not cond:
        fails.append(name)

# --- Run 1: full loop drains the queue
s = session_mod.BoardSession(make_config(3600))
res = s.run()
check("run1 agenda_total == 3", res.agenda_total == 3, f"(got {res.agenda_total})")
check("run1 ruled == 3", len(res.agenda_results) == 3, f"(got {len(res.agenda_results)})")
check("run1 carried_over == 0", len(res.carried_over) == 0)
routes = {ar.item.key: ar.seat_result.seat_title for ar in res.agenda_results}
check("money gate -> CFO (theme)", routes.get("gate:test-money") == "Chief Financial Officer", f"(got {routes.get('gate:test-money')})")
check("leads task -> People Enrichment (keyword)", routes.get("task:test-leads") == "Chief People Enrichment Officer", f"(got {routes.get('task:test-leads')})")
sec = [ar for ar in res.agenda_results if ar.item.key == "task:test-security"][0]
check("security task notes roster gap", "not in roster" in sec.item.routing_reason, f"({sec.item.routing_reason})")
check("one call per item", all(len(ar.seat_result.calls) == 1 for ar in res.agenda_results))
check("decisions recorded+verified", res.recorded >= 3 and res.verified == res.recorded,
      f"(recorded {res.recorded}, verified {res.verified})")
ledger_keys = set()
with open(os.path.join(tmp, "board-agenda-ledger.jsonl")) as f:
    for line in f:
        ledger_keys.add(json.loads(line)["item_key"])
check("ledger has all 3 items", ledger_keys == {"gate:test-money", "task:test-leads", "task:test-security"}, f"({ledger_keys})")
minutes = open(res.minutes_path).read()
check("minutes show queue counts", "Agenda queue: 3 item(s) at start | ruled: 3" in minutes)
check("minutes show agenda rulings", "## Agenda rulings" in minutes)

# --- Run 2: same queue + ledger -> empty agenda, no free-form calls
s2 = session_mod.BoardSession(make_config(3600))
res2 = s2.run()
check("run2 agenda_total == 0 (ledger drains)", res2.agenda_total == 0, f"(got {res2.agenda_total})")
check("run2 no gated calls", len(res2.gated) == 0)
check("run2 empty-queue note", any("AGENDA QUEUE EMPTY" in n for n in res2.health_notes))

# --- Run 3: deadline already blown -> everything carries over, ledger untouched
os.remove(os.path.join(tmp, "board-agenda-ledger.jsonl"))
s3 = session_mod.BoardSession(make_config(0))
res3 = s3.run()
check("run3 ruled == 0", len(res3.agenda_results) == 0)
check("run3 carried_over == 3", len(res3.carried_over) == 3, f"(got {len(res3.carried_over)})")
check("run3 no ledger written", not os.path.exists(os.path.join(tmp, "board-agenda-ledger.jsonl")))
check("run3 carry-over note", any("AGENDA CAP" in n for n in res3.health_notes))
m3 = open(res3.minutes_path).read()
check("run3 minutes list carried over", "## Carried over" in m3)

# --- Live Atlas pull (read-only, direct psql on k11)
from board.harness.agenda import AtlasAgenda, AgendaLedger, load_agenda
items = AtlasAgenda(via="direct").fetch()
gates = [i for i in items if i.kind == "gate"]
tasks = [i for i in items if i.kind == "task"]
check("atlas gates == 2 pending", len(gates) == 2, f"(got {len(gates)})")
check("atlas tasks == 85 open/queued", len(tasks) == 85, f"(got {len(tasks)})")
check("atlas gates first", items[0].kind == "gate")
check("atlas item text populated", all(i.text for i in items))
inbox = [i for i in items if i.key == "task:inbox-551"]
check("inbox-551 full question text", bool(inbox) and "persistent knowledge graph should support" in inbox[0].text)

print("\n%d FAILURE(S)" % len(fails) if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
