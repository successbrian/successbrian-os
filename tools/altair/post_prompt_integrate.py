#!/usr/bin/env python3
"""Post-prompt integration for Altair (Hermes, NOT board).

Runs at the end of a prompt, after Altair gives its output (and after
post-turn micro-compaction). It extracts only genuine new material from
that one prompt/output pair, deduplicates it, and files it:

  - discovery -> altair.second_brain (direct, agent curriculum)
  - decision  -> altair.brian_decisions (direct, Brian's ruling)
  - action_draft -> altair.post_prompt_drafts ONLY (draft, never an Atlas
    task, never a people/company edit, never a board ledger/minute)

It NEVER sends, buys, deploys, executes a decision, promotes a scattered
idea, or writes to any board table, ledger, or minutes file. Those need
their own explicit go from Brian.

Extraction uses Sonic (:11439, qwen-a3b) with max_tokens 1000, because
Sonic spends up to 256 tokens on reasoning first; a smaller budget
returns empty content. If extraction fails or returns no JSON, nothing
is written and the run reports the failure.

Usage:
  python3 post_prompt_integrate.py --input prompt.json [--apply]
  python3 post_prompt_integrate.py --prompt "..." --output "..." [--apply]
  Default is dry-run: extract and report what WOULD be written.
  --apply actually writes to Postgres.

Input JSON: {"prompt": str, "output": str, "session": str}
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import date

SONIC_URL = "http://127.0.0.1:11439/v1/chat/completions"
SYSTEM = (
    "Extract only genuine new material from this prompt/output pair. "
    "Return JSON ONLY, no other text, in this shape: "
    '{"items": [{"type": "discovery|decision|action_draft", '
    '"title": "short title", "content": "one or two sentences", '
    '"confidence": "low|medium|high"}]} '
    "A discovery is a new fact, finding, or rule. A decision is a ruling "
    "Brian made in the prompt. An action_draft is a follow-up task or a "
    "candidate update to Atlas/people, filed as a draft only. "
    "Skip greetings, restatements, routine status, and anything already "
    "stated as known. If there is nothing new, return {\"items\": []}."
)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "untitled"


def extract(prompt, output):
    body = json.dumps({
        "model": "qwen-a3b",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"PROMPT:\n{prompt}\n\nOUTPUT:\n{output}"},
        ],
        "max_tokens": 1000,
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(SONIC_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.load(resp)
    content = data["choices"][0]["message"].get("content") or ""
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError(f"Sonic returned no JSON object: {content[:200]!r}")
    parsed = json.loads(m.group(0))
    items = parsed.get("items", [])
    out = []
    for it in items:
        t = it.get("type")
        if t not in ("discovery", "decision", "action_draft"):
            continue
        title = (it.get("title") or "").strip()
        cont = (it.get("content") or "").strip()
        if not title or not cont:
            continue
        conf = it.get("confidence") or "medium"
        if conf not in ("low", "medium", "high"):
            conf = "medium"
        out.append({"type": t, "title": title, "content": cont,
                    "confidence": conf})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--prompt")
    ap.add_argument("--output")
    ap.add_argument("--session", default="post-prompt")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.input:
        with open(args.input) as f:
            data = json.load(f)
        prompt = data.get("prompt", "")
        output = data.get("output", "")
        session = data.get("session", args.session)
    else:
        prompt = args.prompt or ""
        output = args.output or ""
        session = args.session
    if not prompt and not output:
        print("error: need --input or --prompt/--output", file=sys.stderr)
        return 2
    try:
        items = extract(prompt, output)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:500],
                          "written": [], "skipped": [], "drafts": []}))
        return 1
    report = {"ok": True, "extracted": len(items),
              "written": [], "skipped": [], "drafts": []}
    if not args.apply:
        report["mode"] = "dry-run"
        report["would_write"] = items
        print(json.dumps(report, indent=2))
        return 0
    import psycopg2
    conn = psycopg2.connect(host="localhost", user="successbrian",
                            dbname="ecosystem_central")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS altair.post_prompt_drafts (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            session_id TEXT, kind TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
            source_prompt TEXT
        )
    """)
    today = date.today().strftime("%Y%m%d")
    cur.execute("SELECT decision_id FROM altair.brian_decisions "
                "WHERE decision_id LIKE %s ORDER BY decision_id DESC LIMIT 1",
                (f"dec-{today}-%",))
    row = cur.fetchone()
    seq = 0
    if row:
        m = re.search(r"-pp(\d+)$", row[0])
        if m:
            seq = int(m.group(1))
    for it in items:
        if it["type"] == "discovery":
            topic = slugify(it["title"])
            cur.execute("SELECT id FROM altair.second_brain WHERE topic=%s",
                        (topic,))
            if cur.fetchone():
                report["skipped"].append({"title": it["title"],
                                          "reason": "topic already in second_brain"})
                continue
            cur.execute(
                "INSERT INTO altair.second_brain "
                "(topic, category, content, confidence, source, verification, "
                "expires_at, session_id, tags) VALUES "
                "(%s,%s,%s,%s,%s,%s, now() + interval '90 days', %s, %s) "
                "RETURNING id",
                (topic, "learning", it["content"], it["confidence"],
                 "post_prompt_integrate", "agent_extraction", session,
                 ["post-prompt"]))
            report["written"].append({"type": "discovery",
                                      "topic": topic,
                                      "id": cur.fetchone()[0]})
        elif it["type"] == "decision":
            seq += 1
            did = f"dec-{today}-pp{seq:02d}"
            if len(did) > 20:
                did = did[:20]
            cur.execute("SELECT id FROM altair.brian_decisions "
                        "WHERE decision_id=%s", (did,))
            if cur.fetchone():
                report["skipped"].append({"title": it["title"],
                                          "reason": "decision_id exists"})
                continue
            cur.execute(
                "INSERT INTO altair.brian_decisions "
                "(decision_id, question, context, answer, answered_at) "
                "VALUES (%s,%s,%s,%s, now()) RETURNING id",
                (did, it["title"], prompt[:500], it["content"]))
            report["written"].append({"type": "decision",
                                      "decision_id": did,
                                      "id": cur.fetchone()[0]})
        else:  # action_draft, drafts table only
            cur.execute(
                "INSERT INTO altair.post_prompt_drafts "
                "(session_id, kind, title, content, status, source_prompt) "
                "VALUES (%s,%s,%s,%s,'draft',%s) RETURNING id",
                (session, "action_draft", it["title"], it["content"],
                 prompt[:500]))
            report["drafts"].append({"title": it["title"],
                                     "id": cur.fetchone()[0]})
    conn.commit()
    report["mode"] = "apply"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
