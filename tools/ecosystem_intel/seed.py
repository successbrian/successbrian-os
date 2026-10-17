#!/usr/bin/env python3
"""Seed ecosystem_intel with hard-won facts from 2026-10-17 builds."""
from intel import record_fact, record_howto, record_gotcha

T = "brian"

FACTS = [
    ("k11.tailnet_ip", "100.118.53.47", "network",
     "k11-alpha tailnet IP (changed; 100.118.196.66 is Node Zero)"),
    ("nodezero.tailnet_ip", "100.118.196.66", "network",
     "Node Zero VPS: dashboard host, public nginx, scp target"),
    ("nodezero.ssh", "from k11: ssh root@100.118.196.66 works (k11 key); "
     "from Hatch it does not", "network", None),
    ("nodezero.nginx_public_ingress",
     "location /hooks/<name>/ -> proxy_pass http://100.118.53.47:<port>/ "
     "over tailnet; config backup before edit; nginx -t then reload",
     "network", None),
    ("systeme.api_base", "https://api.systeme.io", "systeme.io", None),
    ("systeme.api_auth", "X-API-Key header; key from Settings -> Public API "
     "keys (max 2, copy once)", "systeme.io", None),
    ("systeme.api_contacts",
     "POST /api/contacts (create); PATCH /api/contacts/{id} with "
     "Content-Type: application/merge-patch+json (update); "
     "GET /api/contacts?email= (lookup)", "systeme.io", None),
    ("flexifunnels.webhook",
     "Form -> gear icon -> settings -> integrations -> paste webhook URL; "
     "fires on every submission (JSON or form-encoded)", "flexifunnels",
     None),
    ("flexifunnels.cost", "$699 lifetime, paid in full. NEVER re-litigate "
     "the cost.", "flexifunnels", None),
    ("people.people.db", "people_unified DB on k11, schema people, table "
     "people. SYSTEM OF RECORD. Dedup by primary_email.", "people", None),
    ("people.vera_trigger",
     "INSERT into people.tasks (person_id, vera_enrich, pending) — Vera's "
     "pollers/n8n pick it up. Filing IS triggering.", "people", None),
    ("k11.db_auth",
     "successbrian role via PGPASSWORD env; pg_hba needs the password. "
     "Bridge services load it from a chmod-600 EnvironmentFile.",
     "database", None),
    ("k11.psql_t_flag",
     "psql helpers MUST pass -t (tuples-only) or headers/footers pollute "
     "output and break truthiness checks", "database", None),
    ("marketing.bridge_port", "18923 on k11 (marketing-bridge.service)",
     "marketing", None),
    ("marketing.webhook_url",
     "https://successbrianvps.com/hooks/flexifunnels/<token>",
     "marketing", None),
]

HOWTOS = [
    ("deploy a webhook bridge",
     "Public webhook -> Node Zero nginx -> k11 service -> downstream APIs.",
     "1. Write stdlib-only Python (http.server). Token-in-URL-path auth.\n"
     "2. config.json chmod 600 (API keys, per-funnel tokens).\n"
     "3. systemd unit (User=successbrian, Restart=always, EnvironmentFile "
     "for DB creds).\n"
     "4. Node Zero nginx: location /hooks/<name>/ -> "
     "proxy_pass http://100.118.53.47:<port>/  (backup config first, "
     "nginx -t, reload).\n"
     "5. Test: curl POST through the PUBLIC url, verify downstream + logs.",
     "marketing, network, systemd"),
    ("push code to a private repo",
     "Secret-scan first, .env check, then push.",
     "1. grep for sk-live/ghp_/AKIA/private keys/service_role tokens.\n"
     "2. git check-ignore .env (must be ignored).\n"
     "3. Fresh clone of the empty repo to /tmp, rsync files in "
     "(excludes: .git, node_modules, dist, .env, *.log), commit, push.\n"
     "4. Verify via gh api repos/<org>/<repo>/contents.",
     "github"),
    ("edit Node Zero nginx safely",
     "Shell interpolation eats $vars through double-ssh — base64 the script.",
     "1. cp config to .bak.<date>-<reason> first.\n"
     "2. base64-encode the python edit script locally; pipe "
     "`echo <b64> | base64 -d | python3` through the ssh chain.\n"
     "3. nginx -t MUST pass before reload.\n"
     "4. systemctl reload nginx; verify with grep.",
     "network, nginx"),
]

GOTCHAS = [
    ("$vars eaten by double-ssh",
     "kssh wraps in double quotes; the inner ssh does too — $host becomes "
     "empty and nginx fails to reload.",
     "Base64 the whole script; no $ ever touches a shell."),
    ("grep -v masks scp failures",
     "grep returns 1 when it filters everything out, so `scp ... | grep -v` "
     "reports rc=1 even when scp succeeded.",
     "Verify with ls on the remote instead of trusting the pipeline rc."),
    ("marketing tools are not the record",
     "Treating systeme.io (or any marketing tool) as the system of record "
     "inverts the architecture.",
     "people.people first, always. Marketing tools are downstream sync."),
    ("subtree push silent no-op",
     "git subtree push can report 'no new revisions' against an empty repo.",
     "Use the fresh-clone + rsync method instead."),
]


def seed():
    for key, value, cat, source in FACTS:
        record_fact(T, key, value, cat, source)
    for topic, summary, steps, related in HOWTOS:
        record_howto(T, topic, summary, steps, related)
    for trap, why, fix in GOTCHAS:
        record_gotcha(T, trap, why, fix)
    print(f"seeded {len(FACTS)} facts, {len(HOWTOS)} howtos, "
          f"{len(GOTCHAS)} gotchas")


if __name__ == "__main__":
    seed()
