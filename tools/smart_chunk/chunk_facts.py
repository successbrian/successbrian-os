#!/usr/bin/env python3
"""chunk_facts.py -- deterministic facts about chunks to feed Morpheus verdicts.

For each chunk in a chunks JSONL:
  references:      how many OTHER AnythingLLM docs mention this chunk's source title
  duplicate_of:    another chunk with near-identical normalized text
  superseded_by:   newer chunk (same topic, later latest_date)
  workspace:       AnythingLLM workspace holding the source doc
  corpus_refs:     total other docs referencing this source (delete risk flag)

Enriches JSONL -> new file. Pure code, no LLM.
Usage: chunk_facts.py chunks.jsonl [-o chunks-facts.jsonl]
"""
import json, re, os, sys, glob, hashlib, sqlite3
from difflib import SequenceMatcher

DOCS_ROOT = os.environ.get(
    "ANYTHINGLLM_DOCS", "/home/successbrian/anything-llm/storage/documents")
DB = os.environ.get(
    "ANYTHINGLLM_DB",
    "/home/successbrian/anything-llm/server/storage/anythingllm.db")


def norm(t):
    return re.sub(r"\s+", " ", str(t).lower()).strip()


def load_corpus():
    """title -> pageContent for every doc in the corpus."""
    corpus = {}
    for f in glob.glob(os.path.join(DOCS_ROOT, "*", "*.json")):
        try:
            d = json.load(open(f))
            corpus[d.get("title") or os.path.basename(f)] = str(
                d.get("pageContent") or "")
        except Exception:
            continue
    return corpus


def workspace_of(docpath):
    try:
        base = os.path.basename(str(docpath)).split("?")[0]
        con = sqlite3.connect(DB)
        row = con.execute(
            "SELECT w.name FROM workspace_documents d "
            "JOIN workspaces w ON w.id=d.workspaceId "
            "WHERE d.docpath LIKE ? LIMIT 1",
            ("%" + base[:60] + "%",)).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def main():
    src = sys.argv[1]
    outp = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else None
    chunks = [json.loads(l) for l in open(src) if l.strip()]
    print(f"[facts] {len(chunks)} chunks", flush=True)
    corpus = load_corpus()
    print(f"[facts] corpus: {len(corpus)} docs", flush=True)

    # duplicate detection within the run (normalized text hash)
    seen = {}
    for c in chunks:
        h = hashlib.sha256(norm(c.get("text", ""))[:4000].encode()).hexdigest()
        if h in seen:
            c["duplicate_of"] = seen[h].get("source")
        seen.setdefault(h, c)

    # references + workspace + supersession
    for c in chunks:
        title = c.get("source", "")
        refs = 0
        for t2, content in corpus.items():
            if t2 == title:
                continue
            if title and title.lower() in content.lower():
                refs += 1
        c["corpus_refs"] = refs
        ws = workspace_of(c.get("source_file", ""))
        if ws:
            c["workspace"] = ws
        # superseded: same topic, another chunk with later latest_date
        newer = [o for o in chunks
                 if o is not c
                 and o.get("topic") == c.get("topic")
                 and o.get("latest_date") and c.get("latest_date")
                 and o["latest_date"] > c["latest_date"]]
        if newer:
            c["superseded_by"] = sorted(o["latest_date"] for o in newer)[-1]
        print(f"[facts] chunk {c.get('chunk')}: refs={refs} "
              f"dup={bool(c.get('duplicate_of'))} "
              f"superseded={bool(c.get('superseded_by'))} ws={c.get('workspace')}",
              flush=True)

    if outp:
        with open(outp, "w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"[facts] wrote {len(chunks)} -> {outp}")
    else:
        for c in chunks:
            print({k: c.get(k) for k in
                   ("chunk", "corpus_refs", "duplicate_of",
                    "superseded_by", "workspace")})


if __name__ == "__main__":
    main()
