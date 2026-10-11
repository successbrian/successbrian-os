"""LLM extraction adapter for the ingest engine.

PURPOSE
    Take content chunks and return candidate income streams, audiences,
    campaigns, and ideas as structured data. The adapter is deliberately
    thin: deterministic code owns ingest/chunk/dedupe/store/review, and the
    model only does the reading-and-proposing step it is good at.

WHY
    Reading hundreds of notes and finding the businesses hiding in them is
    pattern work, not logic work. A local model does it for free; the
    entrepreneur still decides what becomes real.

CALLED BY
    tools/ingest/ingest.py `run` command. Also usable standalone for testing.

BACKENDS (--via)
    sonic : llama.cpp OpenAI-compatible server (Brian's Sonic on k11).
            SONIC_URL default http://localhost:11439/v1,
            SONIC_MODEL default qwen-a3b.
    env   : any OpenAI-compatible endpoint via OPENAI_BASE_URL,
            OPENAI_API_KEY, INGEST_MODEL.
    dry   : no model call; returns [] (pipeline test without tokens).

NOTES
    - stdlib only (urllib): no dependency to install on agent boxes.
    - Temperature is low and the prompt demands strict JSON; the parser is
      defensive anyway (finds the first [...] block, drops malformed rows).
    - Chunk text is truncated per chunk so a batch fits the context window.
"""

import json
import os
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_prompt():
    with open(os.path.join(_HERE, "prompts", "extraction.txt")) as f:
        return f.read()


def _chat(base_url, api_key, model, system, user, timeout=600):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def _parse(raw):
    """Pull the first JSON array out of raw model output; drop bad rows."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return []
    try:
        items = json.loads(raw[start:end + 1])
    except Exception:
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind")
        if kind not in ("income_stream", "audience", "campaign", "idea"):
            continue
        title = str(it.get("title", "")).strip()
        if not title:
            continue
        out.append({"kind": kind,
                    "title": title[:200],
                    "summary": str(it.get("summary", ""))[:2000],
                    "evidence": str(it.get("evidence", ""))[:2000]})
    return out


def extract(chunks, via="sonic", batch_size=10, per_chunk_chars=4000):
    """chunks: list of (label, text). Returns list of candidate dicts."""
    template = _load_prompt()
    cands = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        blob = "\n\n---\n\n".join(
            "[%s]\n%s" % (label, text[:per_chunk_chars])
            for label, text in batch)
        user = template.replace("{CHUNKS}", blob)
        if via == "dry":
            continue
        if via == "sonic":
            base = os.environ.get("SONIC_URL", "http://localhost:11439/v1")
            model = os.environ.get("SONIC_MODEL", "qwen-a3b")
            raw = _chat(base, None, model,
                        "You output strict JSON only, no prose.", user)
        elif via == "env":
            base = os.environ["OPENAI_BASE_URL"]
            key = os.environ.get("OPENAI_API_KEY")
            model = os.environ["INGEST_MODEL"]
            raw = _chat(base, key, model,
                        "You output strict JSON only, no prose.", user)
        else:
            raise SystemExit("unknown --via '%s' (sonic|env|dry)" % via)
        cands.extend(_parse(raw))
    return cands
