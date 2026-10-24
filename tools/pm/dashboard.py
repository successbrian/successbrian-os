#!/usr/bin/env python3
"""Dashboard proof window — slice 6 of the coded-loop upgrade.

Brian's spec: the dashboard CAN exist, but the flow must never depend on
anyone looking at it. Its job is proof for people who don't believe him —
so it shows PROCESS, not status tiles: the rolling list of the last 100
decisions (ecosystem-originated ones are the headline — decisions made
without Brian), plus the loop's live step activity read from the PM rows.

Renders one static page from PostgreSQL and pushes it to the public web
root (VPS: /var/www/successbrianvps.com/frontend/dist/pm/index.html).
Regenerated every 5 minutes by cron. A failed push never fails the
render — the local copy stays current regardless.
"""
import html
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_core  # noqa: E402

LOCAL_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "state", "dashboard.html")
VPS = "root@100.118.196.66"
VPS_PATH = "/var/www/successbrianvps.com/frontend/dist/pm/index.html"


def render(cur):
    cur.execute(
        """SELECT count(*) AS n FROM successbrian_os.pm_decisions
            WHERE origin='ecosystem'
              AND created_at > now() - interval '24 hours'""")
    eco_24h = cur.fetchone()["n"]
    cur.execute(
        """SELECT id, created_at, decided_by, decision, rationale, origin
             FROM successbrian_os.pm_decisions ORDER BY id DESC LIMIT 100""")
    decisions = cur.fetchall()
    cur.execute(
        """SELECT status, count(*) AS n FROM successbrian_os.pm_steps
            GROUP BY status ORDER BY status""")
    step_counts = cur.fetchall()
    cur.execute(
        """SELECT step_key, title, status, actor, updated_at
             FROM successbrian_os.pm_steps
            WHERE status IN ('running','done','failed','held_brian')
            ORDER BY updated_at DESC LIMIT 15""")
    activity = cur.fetchall()

    def esc(x):
        return html.escape(str(x if x is not None else ""))

    rows = "\n".join(
        f"<tr class='o-{esc(d['origin'])}'><td>{d['created_at']:%m-%d %H:%M}</td>"
        f"<td>{esc(d['origin'])}</td><td>{esc(d['decided_by'])}</td>"
        f"<td>{esc(d['decision'])}"
        + (f"<br><small>{esc(d['rationale'])}</small>" if d["rationale"] else "")
        + "</td></tr>"
        for d in decisions)
    counts = " · ".join(f"{esc(s['status'])}: {s['n']}" for s in step_counts)
    acts = "\n".join(
        f"<tr><td>{a['updated_at']:%m-%d %H:%M}</td><td>{esc(a['status'])}</td>"
        f"<td>{esc(a['title'])}</td><td>{esc(a['actor'])}</td></tr>"
        for a in activity)
    now = datetime.now().strftime("%a %Y-%m-%d %H:%M CT")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="300">
<title>SuccessBrian OS — the loop, live</title>
<style>
body{{background:#0d1117;color:#d6deeb;font-family:Georgia,serif;margin:2em auto;max-width:900px;padding:0 1em}}
h1{{font-size:1.5em}} h2{{font-size:1.15em;margin-top:1.6em}}
.big{{font-size:2.2em;color:#7ee787}}
table{{border-collapse:collapse;width:100%}}
td{{border-top:1px solid #2a3240;padding:.35em .5em;vertical-align:top;font-size:.92em}}
.o-ecosystem td:nth-child(2){{color:#7ee787;font-weight:bold}}
small{{color:#8b98a9}}
</style></head><body>
<h1>SuccessBrian OS — one coded loop, running without its owner</h1>
<p>Decisions the ecosystem made in the last 24 hours <em>without Brian</em>:</p>
<p class="big">{eco_24h}</p>
<p>Loop steps — {counts}</p>
<h2>The last {len(decisions)} decisions (all origins; ecosystem rows are the proof)</h2>
<table>{rows}</table>
<h2>Recent step activity</h2>
<table>{acts}</table>
<p><small>Generated {now} by tools/pm/dashboard.py from successbrian_os.pm_decisions / pm_steps. The flow does not depend on this page being viewed.</small></p>
</body></html>"""


def main():
    import psycopg2.extras
    c = pm_core.psycopg2.connect(
        dbname="ecosystem_central", host="localhost",
        cursor_factory=psycopg2.extras.RealDictCursor)
    cur = c.cursor()
    page = render(cur)
    c.close()
    os.makedirs(os.path.dirname(LOCAL_OUT), exist_ok=True)
    with open(LOCAL_OUT, "w") as f:
        f.write(page)
    print(f"rendered {len(page)} bytes -> {LOCAL_OUT}")
    try:
        subprocess.run(["ssh", "-o", "ConnectTimeout=10", VPS,
                        "mkdir", "-p", os.path.dirname(VPS_PATH)],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(["scp", "-o", "ConnectTimeout=10", LOCAL_OUT,
                        f"{VPS}:{VPS_PATH}"],
                       check=True, capture_output=True, timeout=30)
        print(f"pushed -> https://successbrianvps.com/pm/")
    except Exception as e:
        print(f"push failed ({type(e).__name__}): local copy is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
