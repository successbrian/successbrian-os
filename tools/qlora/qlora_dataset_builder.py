#!/usr/bin/env python3
"""qlora_dataset_builder.py — build ShareGPT-style JSONL training datasets for
Brian's QLoRA adapters (Chuck 2B, Penny 7B, Morpheus 14B).

PURPOSE
    Assemble instruction/response training pairs from the ecosystem's own
    knowledge sources so the local adapters learn Brian's world: his recorded
    decisions, ecosystem learnings, research intel, memory notes, and specs.

WHY
    The QLoRA goal (goals/qlora-training-datasets) defines six task types and
    names the sources, but no builder existed — the goal was description-only.
    Adapters trained on generic internet data don't know Brian's standing
    rules (90% rule, move policy, storage rule, recurring-forever filter, the
    perception test for MLM). This builder turns those recorded facts into
    deterministic, deduped, train/val-split JSONL.

CALLED BY
    Night-shift runs, one-off builds: `python3 qlora_dataset_builder.py --out
    /tmp/qlora_datasets [--dry-run] [--push-k11]`. Training jobs on k11-alpha
    consume the pushed JSONL at /home/successbrian/qlora_datasets/.

NOTES
    - Sources (PostgreSQL on k11-alpha via the kssh pipe pattern; never nest
      single quotes in a kssh -c arg — see AGENTS.md):
        1. public.second_brain      (learnings/decisions, 455+ rows)
        2. altair.brian_decisions   (62+ rows: question/context/answer)
        3. altair.brian_learnings   (77+ rows: content)
        4. altair.research_digest   (100+ rows: topic/title/summary/signal)
        5. ~/memory/YYYY-MM-DD.md   (high-confidence fact/event bullets)
        6. successbrian-os/specs/*.md (spec docs)
    - Task types (six, per the goal): apply-learning, recall-decision,
      summarize-intel, correct-misconception, recall-fact, explain-spec.
      `correct-misconception` is built from second_brain rows whose tags or
      category mark them as stale-intel corrections.
    - Dedupe is by sha256 of the normalized assistant text; train/val split
      is deterministic by content hash (90/10) so rebuilds are stable.
    - Raw assistant text is truncated to a sane length; secrets are never
      written into pairs (rows are filtered for secret-ish patterns).
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
KSSH = os.path.join(HOME, "workspace", "bin", "kssh")
SUCCESSBRIAN_OS = os.path.join(HOME, "workspace", "successbrian-os")
MEMORY_DIR = os.path.join(HOME, "memory")
SPECS_DIR = os.path.join(SUCCESSBRIAN_OS, "specs")
K11_DEST = "/home/successbrian/qlora_datasets"

SECRET_PAT = re.compile(
    r"(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S{4,}", re.IGNORECASE
)
MEM_BULLET = re.compile(r"^-\s*\[(fact|event)\|high\]\s*(.+)$")
MAX_ASSISTANT_CHARS = 1500


def kssh_psql(db, sql):
    """Run SQL on k11-alpha via the kssh pipe pattern. Returns list of dicts.

    Raises RuntimeError if the remote psql fails — a zero exit from the kssh
    wrapper alone is NOT proof the query ran, so the remote script exits
    nonzero on psql failure and we check for it explicitly.

    Rows come back as one JSON object per line (row_to_json), so embedded
    newlines in text columns can't break parsing.
    """
    sql = sql.rstrip().rstrip(";")
    wrapped = "SELECT row_to_json(t) FROM (" + sql + ") t;"
    runner = (
        "import subprocess, sys\n"
        "p = subprocess.run(['sudo','-u','postgres','psql','-d','" + db + "',"
        "'-tA','-v','ON_ERROR_STOP=1','-c',SQL],"
        " capture_output=True,text=True,timeout=120)\n"
        "if p.returncode != 0:\n"
        "    sys.stderr.write('PSQL-FAILED: ' + p.stderr[:500])\n"
        "    sys.exit(42)\n"
        "print(p.stdout, end='')\n"
    )
    script = "import sys\nSQL = " + repr(wrapped) + "\n" + runner
    p = subprocess.run([KSSH, "python3", "-"], input=script,
                       capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError("kssh psql failed: " + p.stderr[:300])
    return p.stdout


def rows(db, sql):
    """Return query results as a list of dicts."""
    out = kssh_psql(db, sql)
    result = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            result.append(json.loads(line))
    return result


def clean(text):
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_ASSISTANT_CHARS]


def looks_secret(text):
    return bool(SECRET_PAT.search(text or ""))


def pair(task_type, source, user, assistant):
    assistant = clean(assistant)
    if not assistant or len(assistant) < 40 or looks_secret(assistant):
        return None
    return {
        "messages": [
            {"role": "user", "content": clean(user)},
            {"role": "assistant", "content": assistant},
        ],
        "task_type": task_type,
        "source": source,
    }


def build_pairs(wanted_sources):
    pairs = []
    source_counts = {}

    def add(p, src):
        if p:
            pairs.append(p)
            source_counts[src] = source_counts.get(src, 0) + 1

    if "second_brain" in wanted_sources:
        for r in rows(
            "ecosystem_central",
            "SELECT id, topic, category, content, confidence, "
            "COALESCE(array_to_string(tags, ','),'') AS tags "
            "FROM public.second_brain ORDER BY id;",
        ):
            rid = str(r["id"])
            topic, content = clean(r["topic"]), clean(r["content"])
            category, tags = r.get("category") or "", r.get("tags") or ""
            if not topic or not content:
                continue
            tag_hit = "stale" in tags.lower() or "correction" in tags.lower()
            if tag_hit or category == "stale-intel":
                p = pair(
                    "correct-misconception", "second_brain#" + rid,
                    "Someone claims: " + topic + ". Is that right?",
                    "That claim is stale. Corrected understanding: " + content,
                )
            else:
                p = pair(
                    "apply-learning", "second_brain#" + rid,
                    "How should a SuccessBrian OS agent apply what is known "
                    "about: " + topic + "?",
                    content,
                )
            if p:
                add(p, 'second_brain')

    if "decisions" in wanted_sources:
        for r in rows(
            "ecosystem_central",
            "SELECT id, question, COALESCE(context,'') AS context, answer "
            "FROM altair.brian_decisions ORDER BY id;",
        ):
            rid = str(r["id"])
            question, answer = clean(r["question"]), clean(r["answer"])
            context = r.get("context") or ""
            if not question or not answer:
                continue
            p = pair(
                "recall-decision", "brian_decisions#" + rid,
                "What did Brian decide about: " + question + "?",
                "Decision: " + answer + " Context: " + clean(context),
            )
            if p:
                add(p, 'decisions')

    if "learnings" in wanted_sources:
        for r in rows(
            "ecosystem_central",
            "SELECT id, content FROM altair.brian_learnings ORDER BY id;",
        ):
            rid = str(r["id"])
            content = r["content"]
            p = pair(
                "apply-learning", "brian_learnings#" + rid,
                "What should a SuccessBrian OS agent remember from this "
                "recorded learning?",
                content,
            )
            if p:
                add(p, 'learnings')

    if "digest" in wanted_sources:
        for r in rows(
            "ecosystem_central",
            "SELECT id, topic, title, summary, signal "
            "FROM altair.research_digest ORDER BY id;",
        ):
            rid = str(r["id"])
            topic = clean(r["topic"])
            title = clean(r["title"])
            summary = clean(r["summary"])
            signal = r.get("signal") or ""
            if not summary:
                continue
            if signal in ("high", "risk", "opportunity", "watch"):
                p = pair(
                    "summarize-intel", "research_digest#" + rid,
                    "This " + signal + "-signal intel came in: " + title
                    + ". Brief me and say what to do with it.",
                    "[" + topic + "] " + summary,
                )
            else:
                p = pair(
                    "summarize-intel", "research_digest#" + rid,
                    "Brief me on this intel item: " + title + ".",
                    "[" + topic + "] " + summary,
                )
            if p:
                add(p, 'digest')

    if "memory" in wanted_sources and os.path.isdir(MEMORY_DIR):
        for fname in sorted(os.listdir(MEMORY_DIR)):
            if not re.match(r"^\d{4}-\d{2}-\d{2}\.md$", fname):
                continue
            try:
                with open(os.path.join(MEMORY_DIR, fname), encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            for line in lines:
                m = MEM_BULLET.match(line.strip())
                if not m:
                    continue
                kind, text = m.group(1), clean(m.group(2))
                if len(text) < 60:
                    continue
                head = text.split(".")[0][:90]
                p = pair(
                    "recall-fact", "memory/" + fname,
                    "What do you remember about: " + head + "?",
                    text,
                )
                if p:
                    add(p, 'memory')

    if "specs" in wanted_sources and os.path.isdir(SPECS_DIR):
        for fname in sorted(os.listdir(SPECS_DIR)):
            if not fname.endswith(".md") or fname.endswith(".bak-20260929"):
                continue
            path = os.path.join(SPECS_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            title = fname[:-3].replace("-", " ").replace("_", " ")
            body = clean("\n".join(text.splitlines()[:40]))
            if len(body) < 120:
                continue
            p = pair(
                "explain-spec", "specs/" + fname,
                "Explain the " + title + " spec in the SuccessBrian OS repo.",
                body,
            )
            if p:
                add(p, 'specs')

    return pairs, source_counts


def dedupe(pairs):
    seen = {}
    for p in pairs:
        h = hashlib.sha256(p["messages"][1]["content"].encode()).hexdigest()
        if h not in seen:
            seen[h] = p
    return list(seen.values())


def split(pairs, val_frac=0.10):
    train, val = [], []
    for p in pairs:
        h = int(hashlib.sha256(p["messages"][1]["content"].encode()).hexdigest(), 16)
        (val if (h % 100) < int(val_frac * 100) else train).append(p)
    return train, val


def push_k11(out_dir):
    """Copy the built JSONL files to k11-alpha via kssh (base64 pipe)."""
    for fname in ("train.jsonl", "val.jsonl"):
        path = os.path.join(out_dir, fname)
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        remote = (
            "mkdir -p " + K11_DEST + " && base64 -d > " + K11_DEST + "/" + fname
        )
        p = subprocess.run([KSSH, remote], input=b64,
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError("push failed for " + fname + ": " + p.stderr[:200])
        print("pushed " + K11_DEST + "/" + fname)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/qlora_datasets")
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap total pairs (0 = no cap)")
    ap.add_argument("--sources", default="second_brain,decisions,learnings,digest,memory,specs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push-k11", action="store_true")
    args = ap.parse_args()

    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    pairs_list, source_counts = build_pairs(wanted)
    pairs = dedupe(pairs_list)
    if args.limit:
        pairs = pairs[: args.limit]
    train, val = split(pairs, args.val_frac)

    missing = [s for s in wanted if not source_counts.get(s)]
    if missing:
        print("WARNING: zero pairs from sources: " + ", ".join(missing))
    print("per-source: " + json.dumps(source_counts, sort_keys=True))

    counts = {}
    for p in pairs:
        counts[p["task_type"]] = counts.get(p["task_type"], 0) + 1
    print("pairs: %d (train %d / val %d)" % (len(pairs), len(train), len(val)))
    for t in sorted(counts):
        print("  %-20s %d" % (t, counts[t]))

    if args.dry_run:
        print("dry-run: wrote nothing")
        return 0

    os.makedirs(args.out, exist_ok=True)
    for name, subset in (("train.jsonl", train), ("val.jsonl", val)):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            for p in subset:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print("wrote " + args.out + "/train.jsonl + val.jsonl")

    if args.push_k11:
        push_k11(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
