#!/usr/bin/env python3
"""Write one conversation capture to the ledger jive reads.

WHY:
    Jive can only synthesize what agents record. This is the single
    sanctioned writer for successbrian_os.conversation_captures: one row
    per conversation turn (user message + agent response). Agents call it
    at the end of a turn; jive's watermark then picks the row up on its
    next run. One writer, one schema, no drift.

CALLED BY:
    - Agent session code (e.g. Altair's Hermes chat loop) after each turn:
      `python3 tools/jive/capture.py --session <id> --agent altair
       --user "..." --assistant "..." --model morpheus`
    - Importable: `from capture import capture; capture(...)`.

NOTES:
    - CANONICAL: successbrian-os/tools/jive/capture.py.
    - Keep captures short and factual: the user_message should be the
      actual request text (or a faithful one-line gist), not a paragraph
      of commentary. Jive's duplicate/link detection reads user_message.
    - Never capture secrets, credentials, or private identifiers in
      either field. The ledger is shared agent infrastructure.
    - Auth: psql CLI over the local socket as the invoking OS user.
"""

import argparse
import os
import subprocess
import sys


def _q(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def capture(session_id, source_agent, user_message, assistant_response=None,
            platform="cli", model=None):
    """Insert one capture row; return the new row id."""
    sql = (
        "INSERT INTO successbrian_os.conversation_captures "
        "(session_id, platform, source_agent, user_message, "
        "assistant_response, model) VALUES (%s,%s,%s,%s,%s,%s) "
        "RETURNING id"
        % (_q(session_id), _q(platform), _q(source_agent),
           _q(user_message), _q(assistant_response), _q(model)))
    cmd = ["psql", "-q", "-h", os.environ.get("ECOSYSTEM_DB_HOST", "localhost"),
           "-U", os.environ.get("ECOSYSTEM_DB_USER",
                               os.environ.get("USER", "successbrian")),
           "-d", os.environ.get("ECOSYSTEM_DB_NAME", "ecosystem_central"),
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", sql]
    env = dict(os.environ)
    if "ECOSYSTEM_DB_PASSWORD" in os.environ:
        env["PGPASSWORD"] = os.environ["ECOSYSTEM_DB_PASSWORD"]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("capture insert failed: " + p.stderr.strip()[-500:])
    return int(p.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description="write a jive conversation capture")
    ap.add_argument("--session", required=True, help="session id")
    ap.add_argument("--agent", required=True, help="source agent name")
    ap.add_argument("--platform", default="cli")
    ap.add_argument("--user", required=True, help="user message text")
    ap.add_argument("--assistant", default=None, help="assistant response text")
    ap.add_argument("--model", default=None, help="model id")
    args = ap.parse_args(argv)
    row_id = capture(args.session, args.agent, args.user,
                     args.assistant, args.platform, args.model)
    print("capture: id=%d" % row_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
