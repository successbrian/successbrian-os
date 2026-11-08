#!/usr/bin/env python3
"""people_api.py — the alpha-side People endpoint for RoadChat.

SBOS travel kit companion (Brian 2026-11-08): RoadChat looks people
up in the identity layer and files notes back to the ecosystem.

Why this exists, and why it is NOT the Dashboard API on :8000:
eco_status probes 127.0.0.1:8000 for liveness and the travel README
tunnels it — but the service actually on :8000 is ~/dashboard-api,
a FastAPI app outside this repo, bound to 0.0.0.0 with a public
cloudflared twin and no auth on its routes. Person cards carry
birthdays and intel; they do not belong on that surface, and
RoadChat only ever reaches home through localhost tunnel mouths.
So the People endpoint is this shim instead: pure stdlib, bound to
127.0.0.1 ONLY, exactly three routes, no credentials of its own —
it shells to the identity module's proven CLI/--json contract:

    GET  /health                 liveness
    GET  /people?q=<name|handle> identity_resolution.py --lookup --json
    GET  /person?id=<id>         identity_resolution.py --card --json
    POST /people/note            identity_resolution.py --road-note
         {"person_id": <int>|"new"|null, "text": "..."}

Run by the people-api.service user unit on alpha (the dash-actions
service pattern). Start by hand for a look:

    python3 tools/travel/people_api.py     # 127.0.0.1:8011
"""

import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
IDENTITY_CLI = os.path.join(REPO, "tools", "ecosystem_intel",
                            "identity_resolution.py")
PORT = 8011


def run_identity(args, timeout=120):
    """Run the identity CLI; return (rc, stdout, stderr)."""
    proc = subprocess.run([sys.executable, IDENTITY_CLI] + args,
                          cwd=REPO, capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                self._json({"ok": True, "service": "people-api",
                            "port": PORT,
                            "identity_cli": os.path.exists(IDENTITY_CLI)})
            elif parsed.path == "/people":
                q = qs.get("q", [""])[0]
                if len(q.strip()) < 2:
                    return self._json(
                        {"query": q, "results": [],
                         "note": "type at least 2 characters"})
                rc, out, err = run_identity(["--lookup", q, "--json"])
                if rc != 0:
                    return self._json(
                        {"error": "identity lookup failed: %s"
                                  % (err.strip()[-300:] or rc)}, 502)
                self._json({"query": q, "results": json.loads(out)})
            elif parsed.path == "/person":
                raw = qs.get("id", [""])[0]
                try:
                    ref = int(raw)
                except (TypeError, ValueError):
                    return self._json(
                        {"error": "id must be a person_id or "
                                  "profile_id (integer)"}, 400)
                rc, out, err = run_identity(
                    ["--card", str(ref), "--json"])
                try:
                    card = json.loads(out)
                except Exception:
                    return self._json(
                        {"error": "identity card failed: %s"
                                  % (err.strip()[-300:] or rc)}, 502)
                self._json(card, 404 if card.get("error") else 200)
            else:
                self._json({"error": "not found"}, 404)
        except subprocess.TimeoutExpired:
            self._json({"error": "identity module timed out"}, 504)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/people/note":
            return self._json({"error": "not found"}, 404)
        try:
            data = self._read_json()
            text = (data.get("text") or "").strip()
            if not text:
                return self._json({"error": "note text is empty"}, 400)
            pid = data.get("person_id")
            target = "new" if pid in (None, "new") else str(int(pid))
            rc, out, err = run_identity(
                ["--road-note", target, "--text", text])
            if rc != 0:
                return self._json(
                    {"error": "road-note failed: %s"
                              % ((err or out).strip()[-300:])}, 502)
            m = re.search(r"capture #(\d+)", out)
            self._json({"filed": True,
                        "capture_id": int(m.group(1)) if m else None,
                        "message": out.strip()})
        except (TypeError, ValueError):
            self._json({"error": "person_id must be an integer or "
                                 "'new'"}, 400)
        except subprocess.TimeoutExpired:
            self._json({"error": "identity module timed out"}, 504)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def main():
    if "--selftest" in sys.argv:
        assert os.path.exists(IDENTITY_CLI), IDENTITY_CLI
        assert PORT not in (8000, 8799)
        print("selftest: OK (people-api on 127.0.0.1:%d, identity "
              "CLI present)" % PORT)
        return 0
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("people-api on http://127.0.0.1:%d (Ctrl-C to stop)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
