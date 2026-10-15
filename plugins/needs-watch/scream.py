#!/usr/bin/env python3
"""scream.py — file a need signal and broadcast it.

This is how an agent makes successbrian-os scream. One call, three destinations:
  1. successbrian_os.sbos_need_requests (OS-owned) — the system of record.
  2. altair.knowledge_bridge — broadcast so interpreting agents see it.
  3. successbrian_os.reports (report_type='need-signal') — dashboard Inbox,
     so Brian sees every scream where he actually looks.

Usage:
  python3 scream.py --item "sonic inference worker" --qty 2 --priority 8 \\
      --specs "generic workload spec..." [--task-id 123] [--why "evidence..."]

If --task-id is omitted, a standalone sbostasks row is created and linked.
Specs must describe the WORKLOAD generically — never a specific machine,
never a price. The interpreting agent selects the hardware.
"""

import argparse
import subprocess
import sys

DB = {"host": "localhost", "user": "successbrian", "dbname": "ecosystem_central"}


def psql(sql, write=False):
    r = subprocess.run(
        ["psql", "-h", DB["host"], "-U", DB["user"], "-d", DB["dbname"],
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"psql failed: {r.stderr.strip()[:300]}", file=sys.stderr)
        return None
    return r.stdout.strip() if not write else True


def esc(s):
    return str(s).replace("'", "''")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True, help="short name of what's needed")
    ap.add_argument("--specs", required=True, help="generic workload spec")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--priority", type=int, default=5, help="1-10")
    ap.add_argument("--task-id", type=int, default=None)
    ap.add_argument("--why", default="", help="evidence driving this signal")
    a = ap.parse_args()

    if not (1 <= a.priority <= 10):
        print("priority must be 1-10", file=sys.stderr)
        sys.exit(2)

    task_id = a.task_id
    if task_id is None:
        row = psql("INSERT INTO sbostasks (task_type, title, status) VALUES "
                   f"('standalone', 'Need signal: {esc(a.item)}', 'pending') "
                   "RETURNING id")
        if not row:
            sys.exit(1)
        task_id = int(row.strip().split("\n")[0])

    body = a.specs + (f"\n\nEvidence: {a.why}" if a.why else "")
    need_id = psql(
        "INSERT INTO successbrian_os.sbos_need_requests "
        "(task_id, item, specs, qty, priority, status) VALUES "
        f"({task_id}, '{esc(a.item)}', '{esc(a.specs)}', {a.qty}, "
        f"{a.priority}, 'new') RETURNING id")
    if not need_id:
        sys.exit(1)
    need_id = int(need_id.strip().split("\n")[0])

    subject = f"[NEED SIGNAL] {a.item} x{a.qty}"
    psql(
        "INSERT INTO altair.knowledge_bridge (sender, target, subject, body, urgency) "
        f"VALUES ('spencer', 'dealsdesk', '{esc(subject)}', "
        f"'successbrian-os need signal #{need_id} (priority {a.priority}/10): "
        f"{esc(body)} Full spec in successbrian_os.sbos_need_requests id={need_id}.', "
        "'important')", write=True)

    # Dashboard Inbox: Brian sees every scream where he actually looks.
    psql(
        "INSERT INTO successbrian_os.reports (report_type, title, body, source, priority) "
        f"VALUES ('need-signal', '{esc(subject)}', "
        f"'{esc(body)}\\n\\nNeed id: {need_id} | Qty: {a.qty} | "
        f"Priority: {a.priority}/10 | Status: new', 'spencer', {a.priority})",
        write=True)

    print(f"screamed: need #{need_id} ({a.item} x{a.qty}, priority {a.priority})")


if __name__ == "__main__":
    main()
