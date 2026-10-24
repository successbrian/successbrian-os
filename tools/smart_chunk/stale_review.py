#!/usr/bin/env python3
"""stale_review.py -- Morpheus judges chunk staleness + deletion safety.

Reads a chunks JSONL produced by smart_chunk.py. For each chunk, Morpheus
judges:
  1. stale: is the information no longer current/true TODAY (not merely old)?
  2. delete_safe: if stale, would deleting it lose anything of lasting value?
Writes an enriched JSONL of verdicts. PROPOSES ONLY -- never deletes.
Usage: stale_review.py chunks.jsonl [-o verdicts.jsonl]
"""
import json, re, sys, os, urllib.request
from datetime import date

MORPHEUS_URL = os.environ.get(
    "MORPHEUS_URL", "http://127.0.0.1:11437/v1/chat/completions")

SYS = ("You audit knowledge-base chunks for staleness. Respond with ONLY a "
       "JSON object on one line, no other text.")

USER = """Today is {today}. This chunk comes from document "{source}" in workspace "{workspace}".
Latest date mentioned in the text: {latest} ({age} days ago).

CODE-CHECKED FACTS about this data:
- Other documents that mention this document's title by name: {refs}
- Exact duplicate in the corpus: {dup}
- A newer chunk covers the same topic (dated {superseded}): {has_superseded}
Trust these facts over the text when they conflict.

TEXT:
{text}

Judge two things:
1. stale: Is this information no longer current or no longer true TODAY?
   Old does not mean stale -- a past decision, record, or architecture note
   can still be current. Expired events, superseded settings, wrong facts,
   and old status reports ARE stale.
2. delete_safe: IF stale, would deleting lose anything of lasting value?
   Delete-safe: expired notices, superseded or wrong facts, transient
   status, duplicates. NOT safe: decisions and their reasons, financial /
   legal / health records, personal history, anything other work may cite.

Output exactly:
{{"stale": true, "stale_reason": "one sentence", "delete_safe": true, "delete_reason": "one sentence"}}"""


def ask(chunk):
    user = USER.format(today=date.today().isoformat(),
                       source=chunk.get("source", ""),
                       workspace=chunk.get("workspace") or "unknown",
                       latest=chunk.get("latest_date") or "none",
                       age=chunk.get("age_days"),
                       refs=chunk.get("corpus_refs", 0),
                       dup=bool(chunk.get("duplicate_of")),
                       superseded=chunk.get("superseded_by") or "n/a",
                       has_superseded=bool(chunk.get("superseded_by")),
                       text=str(chunk.get("text", ""))[:4500])
    body = json.dumps({"model": "morpheus",
                       "messages": [{"role": "system", "content": SYS},
                                    {"role": "user", "content": user}],
                       "temperature": 0.1, "max_tokens": 250}).encode()
    req = urllib.request.Request(MORPHEUS_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    raw = d["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"stale": None, "stale_reason": "unparsed: " + raw[:120],
                "delete_safe": False, "delete_reason": "unparsed verdict"}


def main():
    src = sys.argv[1]
    outp = None
    if "-o" in sys.argv:
        outp = sys.argv[sys.argv.index("-o") + 1]
    rows = []
    for line in open(src):
        c = json.loads(line)
        v = ask(c)
        c.update(v)
        rows.append(c)
        print(f"[review] chunk {c.get('chunk')}: stale={v.get('stale')} "
              f"delete_safe={v.get('delete_safe')} -- "
              f"{str(v.get('stale_reason'))[:80]}", flush=True)
    if outp:
        with open(outp, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"[review] wrote {len(rows)} verdicts -> {outp}")
    kills = [r for r in rows if r.get("stale") and r.get("delete_safe")]
    print(f"[review] delete candidates: {len(kills)} of {len(rows)}")


if __name__ == "__main__":
    main()
