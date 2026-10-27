#!/bin/bash
# Weekly secrets scan — secrets closure (2026-10-27).
# flock'd; logs to ~/logs/secrets/; files a CampaignsDesk signal ONLY
# when the findings fingerprint changes vs secrets_status.json.
set -u
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
exec 9>/tmp/secrets-weekly.lock
flock -n 9 || exit 0
mkdir -p "$HOME/logs/secrets"
STAMP=$(date +%Y%m%d)
OUT="$HOME/logs/secrets/weekly-$STAMP.jsonl"
python3 "$HOME/successbrian-os/tools/guardrails/secrets_scan.py" run --out "$OUT" >> "$HOME/logs/secrets/weekly.log" 2>&1
python3 "$HOME/successbrian-os/tools/guardrails/secrets_scan.py" load "$OUT" --run "weekly-$STAMP" >> "$HOME/logs/secrets/weekly.log" 2>&1
python3 - <<'PY' >> "$HOME/logs/secrets/weekly.log" 2>&1
import json, hashlib, os, subprocess
import psycopg2
conn = psycopg2.connect(dbname="ecosystem_central", host="localhost")
cur = conn.cursor()
cur.execute("SELECT repo, file_path, line_no, credential_type, verified_live FROM successbrian_os.secret_findings WHERE status='new' ORDER BY 1,2,3,4")
rows = cur.fetchall()
fp = hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]
live = sum(1 for r in rows if r[4])
status_path = os.path.expanduser("~/successbrian-os/tools/guardrails/state/secrets_status.json")
prev = {}
if os.path.exists(status_path):
    prev = json.load(open(status_path))
status = {"total_open": len(rows), "verified_live": live, "fingerprint": fp,
          "last_scan": subprocess.run(["date","-Is"],capture_output=True,text=True).stdout.strip(),
          "rotation_done": False}
json.dump(status, open(status_path,"w"), indent=2)
if prev.get("fingerprint") != fp:
    cur.execute("INSERT INTO campaignsdesk.signals (kind, title, body, source_tag) VALUES (%s,%s,%s,%s)",
        ("security", f"Secrets scan changed: {len(rows)} open findings, {live} verified-live",
         "Weekly TruffleHog verified scan fingerprint changed. See successbrian_os.secret_findings + secrets_status.json. No values in this signal.", "secrets-weekly"))
    conn.commit()
    print(f"SIGNAL_FILED fp={fp} total={len(rows)} live={live}")
else:
    print(f"NO_CHANGE fp={fp}")
conn.close()
PY
