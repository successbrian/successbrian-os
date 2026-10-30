#!/usr/bin/env python3
"""Chat brief — slice 4 of the coded-loop upgrade (SBOS main PM).

Renders the state block Altair chat works from, in code, on a timer —
Brian's per-prompt injection design in its fastest form: the per-prompt
cost is reading one small file. Regenerated every 5 minutes by cron to
~/successbrian-os/tools/pm/state/CHAT_BRIEF.md.

Contents follow Brian's list (2026-10-24): today's schedule, important
upcoming deadlines, blockers (one line), the DeepSeek API value in actual
dollars, open gates — plus the loop's own pressing item and the last
24h decision counts. Every section is defensive: a broken source shows
as a line saying so, never as a crashed brief.

Deterministic code only; no model calls.
"""
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "state", "CHAT_BRIEF.md")


def section(fn, conn):
    try:
        return fn()
    except Exception as e:  # a dead source must not kill the brief
        conn.rollback()  # a failed query poisons the transaction; reset it
        return f"unavailable ({type(e).__name__})"


def build(cur, conn):
    lines = [f"# Ecosystem brief — {datetime.now().strftime('%a %Y-%m-%d %H:%M')}"]

    def schedule():
        cur.execute(
            """SELECT table_name FROM information_schema.tables
                WHERE table_schema='calendar' AND table_name='effective_day'""")
        if not cur.fetchone():
            return "Schedule: no calendar source wired yet (calendar.effective_day absent)"
        cur.execute(
            """SELECT label AS title, start_time AS starts_at
                   FROM calendar.effective_day
                  WHERE date::date = CURRENT_DATE ORDER BY start_time LIMIT 6""")
        rows = cur.fetchall()
        if not rows:
            return "Schedule: nothing on today's calendar"
        items = "; ".join(f"{r['starts_at']:%H:%M} {r['title']}" for r in rows)
        return f"Schedule today: {items}"
    lines.append("- " + section(schedule, conn))

    def deadlines():
        cur.execute(
            """SELECT node_key, details->>'deadline' AS dl FROM atlas.nodes
                WHERE details->>'deadline' IS NOT NULL
                  AND (details->>'deadline')::date BETWEEN CURRENT_DATE
                      AND CURRENT_DATE + 14
                ORDER BY (details->>'deadline')::date LIMIT 4""")
        rows = cur.fetchall()
        if not rows:
            return "Deadlines (14d): none on record"
        return "Deadlines (14d): " + "; ".join(
            f"{r['dl']} {r['node_key']}" for r in rows)
    lines.append("- " + section(deadlines, conn))

    def blockers():
        cur.execute(
            """SELECT step_key, title FROM successbrian_os.pm_steps
                WHERE status='held_brian' ORDER BY priority DESC LIMIT 1""")
        held = cur.fetchall()
        cur.execute(
            """SELECT count(*) AS n FROM successbrian_os.pm_steps
                WHERE status='held_brian'""")
        n = cur.fetchone()["n"]
        if not held:
            return "Blockers: nothing held for Brian"
        return f"Blockers: {n} held for Brian — top: {held[0]['title']}"
    lines.append("- " + section(blockers, conn))

    def deepseek():
        cur.execute(
            """SELECT usd, available, checked_at
                 FROM successbrian_os.v4pro_balance_history
                ORDER BY checked_at DESC LIMIT 1""")
        r = cur.fetchone()
        if not r:
            return "DeepSeek: no balance readings on record"
        state = "available" if r["available"] else "EMPTY — gameplan mode"
        return (f"DeepSeek: ${float(r['usd']):.2f} ({state}, "
                f"checked {r['checked_at']:%H:%M})")
    lines.append("- " + section(deepseek, conn))

    def route():
        cur.execute(
            """SELECT usd, available, checked_at,
                      EXTRACT(EPOCH FROM now() - checked_at)/60 AS age_min
                 FROM successbrian_os.v4pro_balance_history
                ORDER BY checked_at DESC LIMIT 1""")
        r = cur.fetchone()
        rule = ("Do not deliberate routing - this line IS the decision. "
                "For WORK (not a question): write the plan (max 7 steps, "
                "one line each; prefix a step DEEP: only if it needs deep "
                "reasoning), then run ONE command: python3 "
                "~/successbrian-os/tools/chat_work_launch.py "
                "--summary '<one line>' --plan '<steps, one per line>'; "
                "then tell Brian the plan + the launch receipt, "
                "immediately, and stop. Never do the work in chat, never "
                "wait on the background. A question you can answer "
                "directly: just answer - no plan, no launch.")
        if not r:
            return ("ROUTE: DeepSeek NO READING - the launcher sends "
                    "plans to the Sonic background queue. " + rule)
        usd = float(r["usd"])
        fresh = float(r["age_min"]) < 60
        if fresh and r["available"] and usd > 0:
            head = (f"ROUTE: DeepSeek V4 Pro FUNDED (${usd:.2f}) - the "
                    "launcher sends plans to DeepSeek V4 Pro in the "
                    "background. ")
        else:
            head = (f"ROUTE: DeepSeek NOT usable (${usd:.2f}) - the "
                    "launcher sends plans to the Sonic background queue; "
                    "DEEP: steps park for DeepSeek until funded. ")
        return head + rule
    lines.append("- " + section(route, conn))

    def capacity():
        # Brian 2026-10-29: need is judged on MEASURED production.
        # Demonstrated ceiling = busiest measured hour x 24.
        # ADD at >=70% of ceiling on the last full day, or slots
        # saturated >=50% of samples AND utilization >=50%.
        # WATCH at >=50% utilization or >=25% saturation.
        # IDLE WASTE: slots <50% busy over the last hour while
        # >=10 open ends wait - that is a feeder failure (demand in
        # this ecosystem is effectively unlimited; Sonic must never
        # sit idle while work exists).
        cur.execute(
            """SELECT count(*) AS n,
                      avg(CASE WHEN slots_total > 0
                                AND slots_busy >= slots_total
                               THEN 1.0 ELSE 0.0 END) * 100 AS pct_full
                 FROM successbrian_os.sonic_capacity_samples
                WHERE sampled_at > now() - interval '24 hours'""")
        s = cur.fetchone()
        cur.execute(
            """SELECT slots_total, slots_busy, queue_pending,
                      oldest_pending_age_min
                 FROM successbrian_os.sonic_capacity_samples
                ORDER BY sampled_at DESC LIMIT 1""")
        last = cur.fetchone()
        cur.execute(
            """SELECT COALESCE(sum(prompt_tokens + generated_tokens), 0)
                      AS tot,
                      COALESCE(sum(requests), 0) AS req
                 FROM successbrian_os.sonic_token_hourly
                WHERE (hour AT TIME ZONE 'America/Chicago')::date
                      = current_date - 1""")
        y = cur.fetchone()
        cur.execute(
            """SELECT COALESCE(max(prompt_tokens + generated_tokens), 0)
                      AS bh FROM successbrian_os.sonic_token_hourly""")
        bh = float(cur.fetchone()["bh"] or 0)
        cur.execute(
            """SELECT count(DISTINCT
                      (hour AT TIME ZONE 'America/Chicago')::date) AS d
                 FROM successbrian_os.sonic_token_hourly""")
        days = cur.fetchone()["d"]
        cur.execute(
            """SELECT count(*) AS q FROM successbrian_os.pm_steps
                WHERE status = 'queued'""")
        open_q = cur.fetchone()["q"]
        cur.execute(
            """SELECT avg(slots_busy::numeric
                          / NULLIF(slots_total, 0)) AS share
                 FROM successbrian_os.sonic_capacity_samples
                WHERE sampled_at > now() - interval '1 hour'""")
        share = cur.fetchone()["share"]
        if not last:
            return "CAPACITY: no Sonic samples on record yet"
        ceiling = bh * 24
        util = (float(y["tot"]) / ceiling * 100) if ceiling else 0.0
        pct_full = float(s["pct_full"] or 0)
        nums = (f"yesterday {float(y['tot']) / 1e6:.2f}M tokens "
                f"({y['req']} requests) = {util:.0f}% of demonstrated "
                f"ceiling ~{ceiling / 1e6:.1f}M/day (busiest hour "
                f"{bh / 1000:.0f}K); slots fully busy in "
                f"{pct_full:.0f}% of 24h samples; queue "
                f"{last['queue_pending']} pending")
        idle = ""
        if share is not None and float(share) < 0.5 and open_q >= 10:
            idle = (f"IDLE WASTE: Sonic averaged "
                    f"{float(share) * 100:.0f}% busy last hour while "
                    f"{open_q} open ends wait - feeder problem, not "
                    f"capacity. Standing work always exists (Brian "
                    f"2026-10-29): intel to review, income "
                    f"opportunities to find, relationships to crunch, "
                    f"sales angles per person, needs/pains matched "
                    f"to solves, and goal analysis - are goals being "
                    f"met, what is working, what is not, how does it "
                    f"work better. ")
        if days < 2:
            return ("CAPACITY: baseline building "
                    f"({days} days measured) - " + idle + nums)
        if util >= 70 or (pct_full >= 50 and util >= 50):
            return ("CAPACITY: ADD SONIC - Altair, tell Brian in this "
                    "chat: measured production says the flow needs "
                    "another Sonic. Evidence: " + idle + nums)
        if util >= 50 or pct_full >= 25:
            return "CAPACITY: WATCH - " + idle + nums
        return "CAPACITY: OK - " + idle + nums
    lines.append("- " + section(capacity, conn))

    def gates():
        cur.execute(
            """SELECT count(*) AS n FROM atlas.nodes
                WHERE node_key LIKE 'gate:%%' AND status='pending'""")
        line = (f"Open gates: {cur.fetchone()['n']} "
                f"(Atlas; board rules on them)")
        try:
            cur.execute(
                """SELECT count(*) FILTER (WHERE gate_state='open') AS o,
                          count(DISTINCT workload_key)
                            FILTER (WHERE gate_state='open') AS held
                     FROM atlas.workload_gates_v""")
            r = cur.fetchone()
            if r and r["o"]:
                cur.execute(
                    """SELECT gate_name, workload_name
                         FROM atlas.workload_gates_v
                        WHERE gate_state='open' AND source='atlas'
                        ORDER BY gate_name, workload_name LIMIT 1""")
                top = cur.fetchone()
                first = (f" \u2014 first: {top['gate_name']} holds "
                         f"{top['workload_name']}" if top else "")
                line += (f"; workload gates: {r['o']} open holding "
                         f"{r['held']} workloads{first}")
        except Exception:
            conn.rollback()
        return line
    lines.append("- " + section(gates, conn))

    def pressing():
        cur.execute(
            """SELECT title, priority FROM successbrian_os.pm_steps
                WHERE status IN ('queued','held_brian') AND kind <> 'build'
                ORDER BY (priority + LEAST(25, (EXTRACT(EPOCH FROM
                    (now() - created_at)) / 86400)::int * 5)) DESC LIMIT 1""")
        r = cur.fetchone()
        if not r:
            return "Pressing item: none — queue is clear"
        return f"Pressing item: {r['title']} (pri {r['priority']})"
    lines.append("- " + section(pressing, conn))

    def open_ends():
        cur.execute(
            """SELECT
                 (SELECT count(*) FROM successbrian_os.pm_steps
                   WHERE status='queued') AS q,
                 (SELECT count(*) FROM successbrian_os.pm_steps
                   WHERE status='running') AS r,
                 (SELECT COALESCE(EXTRACT(EPOCH FROM (now() - min(created_at)))
                        / 86400, 0) FROM successbrian_os.pm_steps
                   WHERE status='queued') AS age_d""")
        row = cur.fetchone()
        return (f"Open ends: {row['q']} queued, {row['r']} running — "
                f"oldest queued {float(row['age_d']):.1f}d "
                f"(closure auditor hunts these every 15m)")
    lines.append("- " + section(open_ends, conn))

    def decisions():
        cur.execute(
            """SELECT origin, count(*) AS n FROM successbrian_os.pm_decisions
                WHERE created_at > now() - interval '24 hours'
                GROUP BY origin ORDER BY origin""")
        parts = ", ".join(f"{r['origin']} {r['n']}" for r in cur.fetchall())
        return f"Decisions last 24h: {parts or 'none yet'}"
    lines.append("- " + section(decisions, conn))

    def services():
        down = []
        for name, url in (("sonic", "http://127.0.0.1:11439/health"),
                          ("morpheus", "http://127.0.0.1:11437/health"),
                          ("penny", "http://127.0.0.1:11438/health")):
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status != 200:
                        down.append(name)
            except Exception:
                down.append(name)
        return ("Services: DOWN — " + ", ".join(down)) if down else \
            "Services: sonic/morpheus/penny all ok"
    lines.append("- " + section(services, conn))

    return "\n".join(lines) + "\n"


def main():
    import psycopg2.extras
    c = pm_core.psycopg2.connect(
        dbname="ecosystem_central", host="localhost",
        cursor_factory=psycopg2.extras.RealDictCursor)
    cur = c.cursor()
    text = build(cur, c)
    c.close()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
