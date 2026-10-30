#!/usr/bin/env python3
"""agent_brief.py — agent context pack (WS-CAP item 12).

PURPOSE: Render, live from the systems of record, the markdown an
         arriving agent reads at session start:
         tools/guardrails/state/AGENT_BRIEF.md (chat_brief pattern).
WHY:     Brian (2026-10-27): an arriving agent should not have to
         reconstruct the operating model, live capacity, open gates,
         or Brian's newest corrections from chat. The machine carries
         the remembering; this file is the arrival pack.
CALLED BY: cron */15 (flock-guarded, ~/logs/agent-brief.log), operator.
         Every section is defensive: a failed source renders as
         'unavailable: <why>' and the rest still renders.
         Read-only except the rendered file; nothing publishes/sends.

Sections: (a) operating model (declarative, from the record)
          (b) live capacity state (capacity_* tables)
          (c) open gates + held-for-Brian count
              (atlas gate nodes + atlas.workload_gates_v +
               successbrian_os.project_gates pending +
               pm_steps held_brian — the real sources chat_brief uses)
          (d) doctrine deltas: newest altair.brian_decisions answers
          (e) where things live (sanctioned homes + arrival map)

CLI: render | selftest
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guardrails_common as gc  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "AGENT_BRIEF.md")

OPERATING_MODEL = [
    "Inference is LOCAL — scarcity is horsepower, not dollars. There are no budget circuit-breakers; if local capacity is short, SuccessBrian OS files a need into the SBOS->DealsDesk loop (capacity.py). Never solve a shortage by buying cloud.",
    "Owner-absent design: Brian works in bursts and sleeps rarely; the machine carries the remembering and keeps moving while he is away.",
    "Certainty/escalation: act at >=95% certainty; escalate only true owner decisions.",
    "Nothing publishes, sends, buys, or contacts anyone without Brian's explicit go for that action. Approval of an idea is not approval to execute.",
    "Doctrine becomes code: a ruling is not done until machinery runs it.",
    "A suggestion stays a labeled proposal until Brian explicitly agrees.",
    "Not knowing is UNKNOWN — never record an unknown as a negative fact.",
    "Sanctioned homes (R32): logic -> code in this repo; structure -> Atlas; words -> git docs; state/judgment -> PostgreSQL; knowledge/documents -> AnythingLLM; automation -> n8n.",
    "One companies table (people.companies); real estate belongs to TradesDesk; marketing assets are their own nodes, never merged with the program they market.",
    "Graph, not a tree: people/companies/networks are nodes with typed edges.",
]


def _g(r, k, i):
    return r[k] if isinstance(r, dict) else r[i]


def build(conn, force_fail_section=False):
    cur = conn.cursor()
    parts = [f"# Agent brief — {datetime.now().strftime('%a %Y-%m-%d %H:%M')} (live from systems of record)",
             "", "## (a) Operating model"]
    parts.extend("- " + ln for ln in OPERATING_MODEL)

    def wrap(title, fn):
        parts.append("")
        parts.append(f"## {title}")
        try:
            lines = fn()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            lines = [f"unavailable: {type(e).__name__}: {e}"]
        parts.extend(lines)

    def cap():
        if force_fail_section:
            cur.execute("SELECT * FROM successbrian_os.__missing_selftest_table__")
        lines = []
        cur.execute("SELECT name, kind FROM successbrian_os.capacity_nodes ORDER BY name")
        for node in cur.fetchall():
            name = _g(node, "name", 0)
            cur.execute(
                """SELECT reachable, slots_total, slots_busy, saturated, taken_at
                     FROM successbrian_os.capacity_snapshots WHERE node_name=%s
                    ORDER BY taken_at DESC, id DESC LIMIT 1""", (name,))
            s = cur.fetchone()
            if not s:
                lines.append(f"- {name}: no snapshots yet")
            else:
                lines.append(f"- {name}: reachable={_g(s,'reachable',0)} slots={_g(s,'slots_busy',2)}/{_g(s,'slots_total',1)} saturated={_g(s,'saturated',3)} at {_g(s,'taken_at',4)}")
        cur.execute("SELECT item FROM successbrian_os.capacity_needs WHERE status='open'")
        needs = [_g(r, "item", 0) for r in cur.fetchall()]
        lines.append(f"- Open DealsDesk capacity needs: {len(needs)}" + (": " + "; ".join(needs) if needs else ""))
        return lines
    wrap("(b) Live capacity state", cap)

    def gates():
        lines = []
        cur.execute("SELECT count(*) AS n FROM atlas.nodes WHERE node_key LIKE 'gate:%%' AND status='pending'")
        lines.append(f"- Open Atlas gates: {_g(cur.fetchone(), 'n', 0)}")
        try:
            cur.execute("SELECT count(*) AS n FROM successbrian_os.project_gates WHERE status='pending'")
            lines.append(f"- Pending project gates: {_g(cur.fetchone(), 'n', 0)}")
        except Exception:
            conn.rollback()
            lines.append("- Pending project gates: unavailable")
        cur.execute("SELECT count(*) AS n FROM successbrian_os.pm_steps WHERE status='held_brian'")
        held = _g(cur.fetchone(), "n", 0)
        cur.execute("SELECT title FROM successbrian_os.pm_steps WHERE status='held_brian' ORDER BY priority DESC LIMIT 3")
        tops = [_g(r, "title", 0) for r in cur.fetchall()]
        lines.append(f"- Held for Brian (pm_steps): {held}" + (": " + "; ".join(tops) if tops else ""))
        return lines
    wrap("(c) Open gates + held-for-Brian", gates)

    def doctrine():
        cur.execute("SELECT to_regclass('altair.brian_decisions') AS reg")
        if not cur.fetchone()['reg']:
            return ["- unavailable: altair.brian_decisions absent"]
        cur.execute(
            """SELECT decision_id, question, answer, answered_at
                 FROM altair.brian_decisions
                WHERE answered_at IS NOT NULL AND answer IS NOT NULL
                ORDER BY answered_at DESC LIMIT 10""")
        rows = cur.fetchall()
        if not rows:
            return ["- no answered decisions on record"]
        lines = []
        for r in rows:
            ans = str(_g(r, "answer", 2)).replace("\n", " ")
            if len(ans) > 180:
                ans = ans[:177] + "..."
            lines.append(f"- [{_g(r,'decision_id',0)}] {_g(r,'question',1)} -> {ans}")
        return lines
    wrap("(d) Doctrine deltas — newest Brian decisions", doctrine)

    def where():
        return [
            "- Repo: ~/successbrian-os (k11-alpha). Arrival map: AGENTS.md at repo root — read this brief first, then AGENTS.md.",
            "- PM plane: tools/pm/ (pm_core, project_qa, chat_brief, repair_ladder). Guardrails: tools/guardrails/ (capacity, autonomy, doctor, this brief).",
            "- Atlas: tools/atlas/. Capacity loop (demand): tools/capacity/. ERP/DealsDesk seam: tools/erp/ + successbrian_os.sbos_need_requests -> /home/dealsdesk/scripts/needs_intake.py.",
            "- CampaignsDesk code: ~/campaignsdesk/code/ (content_pm.py).",
            "- State: PostgreSQL ecosystem_central (successbrian_os / atlas / altair / dealsdesk schemas). Knowledge: AnythingLLM. Automation: n8n.",
            "- QA: python3 tools/pm/project_qa.py list / run-due — every project registers there with checks.",
        ]
    wrap("(e) Where things live", where)
    return "\n".join(parts) + "\n"


def render(out_path=OUT, force_fail_section=False):
    c = gc.conn(dict_cursor=True)
    try:
        text = build(c, force_fail_section=force_fail_section)
    finally:
        c.close()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(text)
    return text


def selftest():
    passed = total = 0

    def check(cond, label):
        nonlocal passed, total
        total += 1
        assert cond, label
        passed += 1
        print(f"PASS {label}")

    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "AGENT_BRIEF.md")
    text = render(out_path=tmp)
    for marker in ("## (a) Operating model", "## (b) Live capacity state",
                   "## (c) Open gates", "## (d) Doctrine deltas",
                   "## (e) Where things live", "LOCAL"):
        check(marker in text, f"render contains section/marker: {marker}")
    broken = render(out_path=tmp, force_fail_section=True)
    check("unavailable:" in broken and "## (e) Where things live" in broken
          and "## (a) Operating model" in broken,
          "forced failure of one source (missing table) still renders the rest")
    real = render()
    check(os.path.exists(OUT) and "Operating model" in real, "real brief renders to state/AGENT_BRIEF.md")
    print(f"SELFTEST OK: agent_brief {passed}/{total}")
    return 0


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="SBOS agent context pack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    text = render()
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
