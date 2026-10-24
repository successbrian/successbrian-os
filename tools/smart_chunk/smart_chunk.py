#!/usr/bin/env python3
"""smart_chunk.py -- Smart-chunk AnythingLLM documents with Morpheus.

Pipeline:
  1. Read an AnythingLLM document JSON (pageContent/title/published).
  2. Split deterministically on markdown headers -> pieces <= ~6000 chars (free).
  3. Morpheus (127.0.0.1:11437) labels each piece: topic, 1-line summary,
     calendar dates mentioned in the text.
  4. Emit dated chunks as JSONL. Each chunk carries: summary, topic, dates,
     latest_date, age_days, stale flag (>180 days).

Usage: smart_chunk.py <doc.json> [-o out.jsonl]
"""
import json, re, sys, os, urllib.request
from datetime import datetime, date

MORPHEUS_URL = os.environ.get("MORPHEUS_URL", "http://127.0.0.1:11437/v1/chat/completions")
STALE_DAYS = int(os.environ.get("STALE_DAYS", "180"))
MAX_PIECE = 6000

def call_morpheus(system, user, max_tokens=300, timeout=600):
    body = json.dumps({"model": "morpheus",
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}],
                       "temperature": 0.1, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(MORPHEUS_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]

def split_pieces(text):
    # split on markdown headers, keep the header with its section
    parts = re.split(r"(?m)(?=^#{1,4}\s)", text)
    pieces = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) <= MAX_PIECE:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                pieces.append(buf)
            # hard-split oversized piece on paragraphs
            while len(p) > MAX_PIECE:
                cut = p.rfind("\n\n", 0, MAX_PIECE)
                cut = cut if cut > 1000 else MAX_PIECE
                pieces.append(p[:cut].strip())
                p = p[cut:].strip()
            buf = p
    if buf:
        pieces.append(buf)
    return pieces

PROMPT_SYS = ("You read documents for a knowledge system. Respond with ONLY a "
              "JSON object on one line, no other text.")

def label_piece(text, published_ctx):
    user = (f"Document published: {published_ctx}\n\n"
            f"For the text below, output {{\"topic\":\"short label\","
            f"\"summary\":\"one sentence, max 25 words\","
            f"\"dates\":[\"YYYY-MM-DD\",...]}}. "
            f"Extract every calendar date mentioned; resolve relative dates "
            f"(yesterday, last week) against the published date. "
            f"Empty list if none.\n\nTEXT:\n{text[:5500]}")
    raw = call_morpheus(PROMPT_SYS, user)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {"topic": "", "summary": raw[:120], "dates": []}
    except Exception:
        return {"topic": "", "summary": raw[:120], "dates": []}

def parse_published(s):
    if not s:
        return None
    for fmt in ("%m/%d/%Y, %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except Exception:
            continue
    return None

def chunk_doc(path):
    d = json.load(open(path))
    text = str(d.get("pageContent") or "")
    if not text.strip():
        return []
    pub = parse_published(str(d.get("published") or ""))
    today = date.today()
    out = []
    for i, piece in enumerate(split_pieces(text)):
        lab = label_piece(piece, str(d.get("published") or "unknown"))
        dates = []
        for ds in (lab.get("dates") or []):
            try:
                dates.append(datetime.strptime(ds, "%Y-%m-%d").date())
            except Exception:
                pass
        if pub:
            dates.append(pub)
        latest = max(dates) if dates else None
        age = (today - latest).days if latest else None
        out.append({
            "source": d.get("title") or os.path.basename(path),
            "source_file": path,
            "chunk": i + 1,
            "text": piece,
            "topic": lab.get("topic", ""),
            "summary": lab.get("summary", ""),
            "dates": sorted(str(x) for x in dates),
            "latest_date": str(latest) if latest else None,
            "age_days": age,
            "stale": (age is not None and age > STALE_DAYS),
        })
        print(f"[chunker] piece {i+1}: {lab.get('topic','')[:50]} | dates={len(dates)} | age={age}d",
              flush=True)
    return out

if __name__ == "__main__":
    src = sys.argv[1]
    outp = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "-o" else None
    chunks = chunk_doc(src)
    if outp:
        with open(outp, "w") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        print(f"[chunker] wrote {len(chunks)} chunks -> {outp}")
    else:
        print(json.dumps(chunks, indent=1)[:3000])
