#!/usr/bin/env python3
"""dash-actions — action API behind the successbrian-os dashboard.

PURPOSE: turn the dashboard from read-only into operable. The inbox has
         rendered answer buttons for months calling answerQuestion(), which
         exists nowhere — this API finally implements them, plus task
         completion and on-demand runs of safe watcher jobs.

CALLED BY: systemd user service dash-actions.service (port 5057); nginx on
           Node Zero proxies /successbrian-os/dash-actions/ ->
           100.118.53.47:5057/.

AUTH: shared token in X-Dash-Token header. Token lives in
      /home/successbrian/.dash_actions_token (chmod 600); fragment builders
      embed it in dashboard JS at build time. The token is visible in page
      source to anyone who looks — the real safety is that every endpoint
      is narrow: fixed SQL by integer id, and /api/run only executes an
      explicit allowlist (no shell, no arbitrary commands).

NOTES: stdlib + flask + psycopg2. Uses ~/.pgpass for DB auth (no passwords
       in code), same as podcast-api.
"""
import os
import subprocess

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request

app = Flask(__name__)

TOKEN_FILE = os.path.expanduser("~/.dash_actions_token")


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except OSError:
        return ""


def _authed():
    tok = _token()
    return bool(tok) and request.headers.get("X-Dash-Token") == tok


def db():
    return psycopg2.connect(host="localhost", user="successbrian",
                            dbname="ecosystem_central",
                            cursor_factory=RealDictCursor)


@app.before_request
def _gate():
    if request.path == "/api/health":
        return None
    if not _authed():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


def _input():
    """Merge JSON body + form fields (HTMX posts form-encoded by default)."""
    d = {}
    try:
        d.update(request.get_json(force=True, silent=True) or {})
    except Exception:
        pass
    d.update(request.form.to_dict() or {})
    try:
        d.update(request.values.to_dict() or {})
    except Exception:
        pass
    return d


def _frag(body, ok=True):
    color = "#4caf50" if ok else "#ff5f56"
    return (f'<span style="color:{color};font-size:.85em">{body}</span>',
            200, {"Content-Type": "text/html"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "dash-actions"})


@app.route("/api/questions/answer", methods=["POST"])
def answer_question():
    """Record Brian's answer to an inbox pending_question.

    Returns an HTML snippet for HTMX to swap into the button row."""
    import html as _html
    d = _input()
    try:
        qid = int(d.get("id"))
    except (TypeError, ValueError):
        return _frag("id required", ok=False)
    answer = (d.get("answer") or "")[:2000]
    if not answer:
        return _frag("answer required", ok=False)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE successbrian_os.pending_questions "
                "SET answer=%s, status='answered', updated_at=now() "
                "WHERE id=%s AND status='open' RETURNING id", (answer, qid))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not row:
        return _frag("not found or not open", ok=False)
    return _frag(f"✓ Answered: {_html.escape(answer)}")


@app.route("/api/tasks/done", methods=["POST"])
def task_done():
    """Complete a task from the dashboard.

    source 'pm' -> successbrian_os.tasks id
    source 'life_ops' -> life_ops.event_tasks id (mirrors to PM too)
    Returns an HTML snippet for HTMX.
    """
    d = _input()
    try:
        tid = int(d.get("id"))
    except (TypeError, ValueError):
        return _frag("id required", ok=False)
    source = d.get("source", "pm")
    conn = db()
    cur = conn.cursor()
    if source == "life_ops":
        cur.execute("UPDATE life_ops.event_tasks SET status='done' "
                    "WHERE id=%s RETURNING pm_task_id", (tid,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close(); conn.close()
            return _frag("not found", ok=False)
        if row["pm_task_id"]:
            cur.execute("UPDATE successbrian_os.tasks SET status='completed', "
                        "completed_at=now() WHERE id=%s", (row["pm_task_id"],))
    else:
        cur.execute("UPDATE successbrian_os.tasks SET status='completed', "
                    "completed_at=now() WHERE id=%s RETURNING id", (tid,))
        if not cur.fetchone():
            conn.rollback()
            cur.close(); conn.close()
            return _frag("not found", ok=False)
    conn.commit()
    cur.close()
    conn.close()
    return _frag("✓ Done")


# job name -> argv (no shell, ever). Only safe, idempotent watchers.
RUN_ALLOWLIST = {
    "personal_os_watch": ["/usr/bin/python3",
                          "/home/successbrian/successbrian-os/tools/"
                          "personal_os_watch/watch.py"],
    "life_ops_watch": ["/usr/bin/python3",
                       "/home/successbrian/successbrian-os/tools/life_ops/"
                       "plan.py", "--watch"],
    "ops_console_rebuild": ["/usr/bin/python3",
                            "/home/successbrian/successbrian-os/tools/"
                            "dashboard/build_ops_console.py"],
}


@app.route("/api/run", methods=["POST"])
def run_job():
    """Run an allowlisted watcher job on demand. Returns an HTML snippet."""
    d = _input()
    job = d.get("job")
    argv = RUN_ALLOWLIST.get(job)
    if not argv:
        return _frag(f"unknown job; allowed: {sorted(RUN_ALLOWLIST)}",
                     ok=False)
    env = dict(os.environ)
    env.update({"PGHOST": "localhost", "PGDATABASE": "ecosystem_central",
                "PGUSER": "successbrian"})
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           env=env, timeout=300)
    except subprocess.TimeoutExpired:
        return _frag("timed out after 300s", ok=False)
    if p.returncode == 0:
        tail = p.stdout.strip().split("\n")[-1][:120] if p.stdout.strip() \
            else "done"
        return _frag(f"✓ {job}: {tail}")
    err = (p.stderr.strip().split("\n")[-1][:120]
           if p.stderr.strip() else f"exit {p.returncode}")
    return _frag(f"{job} failed: {err}", ok=False)


@app.route("/api/run/allowed", methods=["GET"])
def run_allowed():
    return jsonify({"ok": True, "jobs": sorted(RUN_ALLOWLIST)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5057)
