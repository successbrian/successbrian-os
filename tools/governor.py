#!/usr/bin/env python3
"""Lyra governor — the coded logic loop (Brian 2026-10-17).

SENSE → DECIDE → ACT → OBSERVE, every heartbeat tick. Deterministic.
Model-aware: V4 Pro when funded, Sonic keeps sonic-capable work moving
when V4 is dry. The machine never idles; it degrades gracefully.
"""
import json
import subprocess
import urllib.request

PSQL = ["psql", "-h", "localhost", "-U", "postgres", "-d", "ecosystem_central",
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]
ENV = {"PATH": "/usr/bin:/bin", "PGPASSWORD": "postgres"}
SONIC_URL = "http://127.0.0.1:11439/v1/chat/completions"


def q(sql):
    r = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True,
                       timeout=30, env=ENV)
    return r.stdout.strip() if r.returncode == 0 else ""


def sense():
    """Read the machine's vital signs. Returns a dict."""
    s = {}
    # V4 availability
    bal = q("SELECT usd, available FROM successbrian_os.v4pro_balance_history "
            "ORDER BY checked_at DESC LIMIT 1;")
    if "\t" in bal:
        usd, avail = bal.split("\t")
        s["v4_usd"] = float(usd or 0)
        s["v4_usable"] = avail.strip().lower() == "t" and float(usd or 0) > 0
    else:
        s["v4_usd"], s["v4_usable"] = 0.0, False
    # Queue depth by kind
    s["queue"] = {}
    for ln in q("SELECT task_kind, count(*) FROM successbrian_os.v4pro_handoffs "
                "WHERE status = 'queued' GROUP BY task_kind;").split("\n"):
        if "\t" in ln:
            k, c = ln.split("\t")
            s["queue"][k.strip()] = int(c.strip())
    # Worker backlog
    s["processing"] = int(q("SELECT count(*) FROM successbrian_os.v4pro_handoffs "
                            "WHERE status = 'processing';") or 0)
    oldest = q("SELECT EXTRACT(EPOCH FROM (now() - min(claimed_at)))/60 "
               "FROM successbrian_os.v4pro_handoffs "
               "WHERE status = 'processing';").strip()
    s["oldest_processing_min"] = float(oldest) if oldest and oldest != "" else 0
    # Escalation backlog (Brian's inbox pressure)
    s["brian_open"] = int(q("SELECT count(*) FROM successbrian_os.worker_escalations "
                            "WHERE tier = 'brian' AND status = 'open';") or 0)
    # Recent errors
    s["errors_1h"] = int(q("SELECT count(*) FROM successbrian_os.chain_controls "
                           "WHERE key LIKE 'lyra_err_%' "
                           "AND updated_at > now() - interval '1 hour';") or 0)
    # Current mode
    s["mode"] = q("SELECT value FROM successbrian_os.chain_controls "
                  "WHERE key = 'lyra_mode';").strip() or "v4"
    s["halted"] = q("SELECT value FROM successbrian_os.chain_controls "
                    "WHERE key = 'lyra_chain_halted';").strip() == "true"
    return s


def decide(s):
    """Deterministic policy. Returns (mode, actions, reasons)."""
    actions, reasons = [], []
    if s["halted"]:
        return "halted", [], ["kill-switch engaged — no action"]
    # Model routing: V4 when funded, Sonic when dry
    if s["v4_usable"] and s["mode"] != "v4":
        actions.append(("mode", "v4"))
        reasons.append("V4 funded ($%.2f) — full capability restored" % s["v4_usd"])
    elif not s["v4_usable"] and s["mode"] != "sonic":
        actions.append(("mode", "sonic"))
        reasons.append("V4 dry ($%.2f) — Sonic takes sonic-capable work, "
                       "V4 queue holds" % s["v4_usd"])
    mode = "sonic" if not s["v4_usable"] else "v4"
    # Backpressure: inbox flooding
    if s["brian_open"] >= 5:
        actions.append(("slow_brian_tier", True))
        reasons.append("%d open Brian escalations — new brian-tier filings pause "
                       "until he catches up" % s["brian_open"])
    # Stuck workers: flag, don't kill (they may be in long V4 calls)
    if s["oldest_processing_min"] > 90:
        reasons.append("oldest processing handoff is %.0f min old — watch, "
                       "not kill (may be deep in V4 calls)" % s["oldest_processing_min"])
    # Error watch
    if s["errors_1h"] >= 3:
        reasons.append("%d worker errors in the last hour — approaching "
                       "auto-halt threshold" % s["errors_1h"])
    return mode, actions, reasons


def act(mode, actions, dry_run=False):
    """Apply decisions. Writes to chain_controls."""
    for key, val in actions:
        if key == "mode":
            if not dry_run:
                q("UPDATE successbrian_os.chain_controls SET value = '%s', "
                  "updated_at = now() WHERE key = 'lyra_mode';" % val)
            print("governor: mode -> %s" % val)
        elif key == "slow_brian_tier":
            if not dry_run:
                q("UPDATE successbrian_os.chain_controls SET value = 'true', "
                  "updated_at = now() WHERE key = 'lyra_slow_brian_tier';")
            print("governor: brian-tier filing slowed")


def observe(s, mode, actions, reasons, dry_run=False):
    """Log the loop's sense/decide/act for audit."""
    entry = {"mode": mode,
             "actions": [a[0] + "=" + str(a[1]) for a in actions],
             "reasons": reasons,
             "sense": {"v4_usd": s.get("v4_usd"), "v4_usable": s.get("v4_usable"),
                       "queue": s.get("queue"), "processing": s.get("processing"),
                       "brian_open": s.get("brian_open"),
                       "errors_1h": s.get("errors_1h")}}
    if not dry_run:
        q("INSERT INTO successbrian_os.governor_log (entry) VALUES ('%s');"
          % json.dumps(entry).replace("'", "''"))
    return entry


def main(dry_run=False):
    # Ensure control keys + log table exist
    q("CREATE TABLE IF NOT EXISTS successbrian_os.governor_log "
      "(id SERIAL PRIMARY KEY, at TIMESTAMPTZ DEFAULT now(), entry JSONB);")
    q("INSERT INTO successbrian_os.chain_controls (key, value) "
      "VALUES ('lyra_mode', 'v4'), ('lyra_slow_brian_tier', 'false') "
      "ON CONFLICT (key) DO NOTHING;")
    s = sense()
    mode, actions, reasons = decide(s)
    act(mode, actions, dry_run)
    entry = observe(s, mode, actions, reasons, dry_run)
    print("governor: mode=%s queue=%s brian_open=%d" %
          (mode, s.get("queue"), s.get("brian_open")))
    for r in reasons:
        print("  -", r)
    return entry


if __name__ == "__main__":
    import sys
    main(dry_run="--dry-run" in sys.argv)
