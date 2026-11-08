"""The clerk's package writer (Brian 2026-10-31).

Every item the board reads gets a real package, built by the clerk from
the house record — never a bare filing label. Three engines work the
package together:

  Penny    (Qwen2.5-7B,  :11438) — extraction: pulls the concrete facts
           out of the assembled record, faithfully, one per line.
  Morpheus (Qwen2.5-14B, :11437) — drafting: writes the package page in
           plain words (what this is / why it matters / what blocks it /
           facts on record / what is not known) and adds packet-specific
           easy questions for the decide stage.
  Sonic    (Qwen3.6-35B, :11439) — verification: fidelity-checks every
           claim in the draft against the sources, answers the
           always-ask pair (decided before? standing rules?) from the
           record, flags anything unverifiable in the package, and
           names what the board will still need.

The record the engines work from is the WHOLE house, never the web
(Brian 2026-10-31): the item's Atlas node, edges, and linked build
rows; the board's own earlier questions on the item; and a research
pass through the Agent Knowledge Gateway — second brain, Brian's
decisions, learnings, ecosystem intel, Atlas, Intel Bridge captures,
companies, PM projects — plus the matching AnythingLLM document text
and the price-intel table.

The finished package is filed on the item's Atlas node: the page goes
to details.question (the board's first-read page), the decide-stage
questions (standing seven + packet-specific) to details.easy_questions.
The filing title stays a label for the machinery; it is never the
board's reading material. Idempotent: a package is rebuilt only when
its source material changed (or with --force). Any engine failing
degrades the build one step, never blocks it, and the package stamp
says which engines actually worked.

Run from ~/successbrian-os:
  python3 board/package_builder.py --item gate:node-echo-acquired
  python3 board/package_builder.py --gates [--dry-run]
  python3 board/package_builder.py --thin 6 [--dry-run]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), "tools"))
import sbos_common  # noqa: E402

from board.harness.agenda import split_easy_block  # noqa: E402
from board.scatter_clerk import EASY_QUESTIONS  # noqa: E402

ENGINES = {
    "penny": ("http://127.0.0.1:11438", 240),
    "morpheus": ("http://127.0.0.1:11437", 600),
    "sonic": ("http://127.0.0.1:11439", 900),
}
INBOX = os.path.expanduser("~/workspace/altair-brain/inbox")


def llm(engine, system, user, max_tokens=900, temperature=0.3):
    base, timeout = ENGINES[engine]
    # Prompt budget at the one door every engine call passes
    # through (Sonic failure-reduction, Brian 2026-11-08):
    # Penny's extraction is mechanical — the 16K standard
    # automated tier; Morpheus drafting and Sonic verification /
    # fit-check / question-resolving are synthesis-shaped —
    # the 32K deep tier. budget_prompt keeps head+tail with a
    # trim marker when material exceeds the tier, so the cap
    # is a ceiling on prefill, never a silent fact-drop at a
    # random offset. (The per-call source slices below remain
    # as the first, tighter shaping.)
    tier = (sbos_common.SONIC_KV_AUTO if engine == "penny"
            else sbos_common.SONIC_KV_AUTO_DEEP)
    user = sbos_common.budget_prompt(user, tier)
    payload = json.dumps({
        "model": engine,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode(errors="replace"))
    return data["choices"][0]["message"]["content"].strip()


# ------------------------------------------------------------------ assemble
def board_questions_for(key):
    """Every question the board has asked about this item, in order."""
    asked = []
    for path in sorted(glob.glob(os.path.join(
            INBOX, "board-questions-*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("item_key") == key:
                    asked.extend(r.get("questions") or [])
    return asked


def assemble(cur, node):
    """Gather everything the house holds about this item, as text."""
    key, name = node["node_key"], node["name"]
    details = node["details"] or {}
    parts = [f"ITEM LABEL (filing label only): {name}",
             f"ITEM KEY: {key}  TYPE: {node['node_type']}  "
             f"STATUS: {node['status']}"]
    skip = {"question", "easy_questions", "package", "clerk_resolved"}
    for k, v in details.items():
        if k in skip or v in (None, "", [], {}):
            continue
        txt = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        parts.append(f"RECORD FIELD {k}: {txt[:1200]}")
    prior_q = (details.get("question") or "").strip()
    if prior_q and prior_q != name and "package" not in details:
        page, _ = split_easy_block(prior_q)
        parts.append(f"EXISTING PAGE ON THE ITEM:\n{page[:3000]}")
    # Atlas connections (edges store node keys as text)
    cur.execute(
        "SELECT from_node, to_node, edge_type FROM atlas.edges "
        "WHERE from_node = %s OR to_node = %s LIMIT 30", (key, key))
    names = {}
    keys = set()
    edges = cur.fetchall()
    for f, t, _ in edges:
        keys.update((f, t))
    if keys:
        cur.execute("SELECT node_key, name FROM atlas.nodes "
                    "WHERE node_key = ANY(%s)", (list(keys),))
        names = dict(cur.fetchall())
    for f, t, ty in edges:
        other = t if f == key else f
        arrow = "->" if f == key else "<-"
        parts.append(f"CONNECTION: this item {arrow} {ty} "
                     f"{other} ({names.get(other, other)})")
    # DealsDesk build, when the item is a build gate
    build_id = details.get("build_id")
    if build_id:
        try:
            cur.execute("SELECT name, status, total_cost, notes "
                        "FROM dealsdesk.builds WHERE id = %s", (build_id,))
            row = cur.fetchone()
            if row:
                parts.append(f"DEALSDESK BUILD {build_id}: name={row[0]} "
                             f"status={row[1]} total_cost={row[2]} "
                             f"notes={row[3]}")
            cur.execute("SELECT name, spec, price, status "
                        "FROM dealsdesk.build_items WHERE build_id = %s "
                        "LIMIT 12", (build_id,))
            for r in cur.fetchall():
                parts.append(f"BUILD ITEM: {r[0]} | spec={r[1]} | "
                             f"price={r[2]} | status={r[3]}")
        except Exception as e:  # schema drift must not kill the build
            conn.rollback()
            parts.append(f"(build lookup failed: {e})")
    # the workload a gate belongs to
    workload = details.get("workload")
    if workload:
        cur.execute("SELECT name, details FROM atlas.nodes "
                    "WHERE node_key = %s", (workload,))
        w = cur.fetchone()
        if w:
            wd = {k: v for k, v in (w[1] or {}).items()
                  if k not in ("question", "easy_questions", "package")}
            parts.append(f"WORKLOAD {workload}: {w[0]} | "
                         f"{json.dumps(wd)[:800]}")
    # NOTE: the board's earlier questions are NOT drafting material —
    # they are the resolve step's input (build_package). Drafting from
    # them leaked reader-lens noise into the first live package
    # (2026-10-31 dry-run finding).
    return "\n".join(parts)


# ------------------------------------------------------------------ research
def subjects_for(node):
    """Search subjects for the research pass: the item's plain subject
    (label minus bookkeeping suffixes) and its key in words."""
    name = node["name"] or ""
    head = name.split(" — ")[0].split(" (")[0].strip()
    tail = node["node_key"].split(":")[-1].replace("-", " ").strip()
    out = []
    for s in (head, tail):
        if s and len(s) > 3 and s.lower() not in [x.lower() for x in out]:
            out.append(s)
    return out[:2]


def _allm_env():
    env = {}
    path = os.path.expanduser("~/successbrian-os/.env")
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k] = v
    return env


def anythingllm_text(subject, slugs):
    """Deep leg: ask the matching AnythingLLM workspaces directly and
    return the document text they surface. House documents only."""
    env = _allm_env()
    key, base = env.get("ANYTHINGLLM_API_KEY"), env.get(
        "ANYTHINGLLM_URL", "http://127.0.0.1:3000")
    if not key or not slugs:
        return []
    out = []
    for slug in slugs[:2]:
        try:
            payload = json.dumps({"query": subject,
                                  "mode": "query"}).encode()
            req = urllib.request.Request(
                f"{base}/api/v1/workspace/{slug}/query", data=payload,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode(errors="replace"))
            text = (data.get("textResponse") or "").strip()
            if text:
                out.append(f"ANYTHINGLLM DOCUMENT TEXT "
                           f"(workspace {slug}): {text[:1500]}")
        except Exception:
            continue
    return out


_GENERIC_WORDS = {"node", "build", "gate", "online", "priced", "item",
                  "work", "load", "task", "plan", "with", "from"}


def _subject_words(subject):
    return [w for w in re.findall(r"[a-z0-9]+", subject.lower())
            if len(w) >= 4 and w not in _GENERIC_WORDS]


def _relevant(blob, subject):
    """A research hit earns its place in the package only if it is
    actually about the subject: the full phrase, a distinctive
    subject word (echo, zilara, kaspa...), or two subject words
    together. Single generic matches ('node', 'build') are noise —
    the gateway's word search returns them by the page."""
    text = (blob or "").lower()
    if subject.lower() in text:
        return True
    distinctive = _subject_words(subject)
    if any(w in text for w in distinctive):
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", subject.lower())
             if len(w) >= 4]
    return sum(1 for w in words if w in text) >= 2


def research(cur, node):
    """Everything else the house holds on this item's subject: the
    Agent Knowledge Gateway's nine stores, the AnythingLLM document
    text behind the matching filenames, and price intel. No web."""
    parts = []
    subjects = subjects_for(node)
    intel_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ecosystem_intel")
    if intel_dir not in sys.path:
        sys.path.insert(0, intel_dir)
    slugs = []
    try:
        import agent_knowledge as ak
        for subject in subjects:
            lines, seen = [], set()
            for store, hits in ak.ask(subject).items():
                for hit in hits:
                    if store == "anythingllm":
                        if hit.get("workspace"):
                            slugs.append(hit["workspace"])
                        lines.append(f"- [anythingllm] document "
                                     f"'{hit.get('title')}' in "
                                     f"workspace {hit.get('workspace')}")
                        continue
                    title = (hit.get("title") or hit.get("name")
                             or hit.get("topic") or "")
                    text = hit.get("text") or hit.get("summary") or ""
                    blob = f"{title} {text}"
                    if not _relevant(blob, subject):
                        continue
                    line = f"- [{store}] {title}: {text[:500]}".strip()
                    if line not in seen:
                        seen.add(line)
                        lines.append(line)
            if lines:
                parts.append(f"HOUSE RESEARCH on '{subject}' "
                             f"(Agent Knowledge Gateway):\n"
                             + "\n".join(lines)[:5000])
    except Exception as e:
        parts.append(f"(knowledge gateway unavailable: {e})")
    if subjects:
        parts.extend(anythingllm_text(subjects[0],
                                      list(dict.fromkeys(slugs))))
    # price intel on the subject's significant words
    words = [w for w in (subjects[0] if subjects else "").split()
             if len(w) > 4][:3]
    if words:
        try:
            like = " OR ".join(["item ILIKE %s"] * len(words))
            cur.execute(
                f"SELECT item, amount, currency, source_label, "
                f"checked_on, valid_until, in_stock FROM "
                f"successbrian_os.price_intel WHERE {like} "
                f"ORDER BY id DESC LIMIT 4",
                [f"%{w}%" for w in words])
            for r in cur.fetchall():
                parts.append(
                    f"PRICE INTEL: {r[0]} — {r[1]} {r[2]} "
                    f"({r[3]}, checked {r[4]}, valid until {r[5]}, "
                    f"in stock: {r[6]})")
        except Exception:
            conn.rollback()
    return "\n".join(parts)


# ------------------------------------------------------------------ engines
def penny_extract(source):
    out = llm("penny",
              "You extract facts from records. Copy only what the record "
              "actually says — names, numbers, dates, rules, statuses — "
              "one fact per line, each starting with '- '. Never invent, "
              "never round a number, never add a fact that is not there.",
              f"RECORD:\n{source[:20000]}\n\nExtract every concrete fact.",
              max_tokens=800)
    facts = [ln.strip() for ln in out.splitlines()
             if ln.strip().startswith("-") and len(ln.strip()) > 3]
    return facts


def morpheus_draft(name, facts, source):
    system = (
        "You are the clerk of a board of directors, writing the package "
        "the board will read. Plain words, short sentences, no filing "
        "jargon, no bookkeeping labels. Write ONLY from the facts and "
        "record given — never invent a fact, a number, or a name. Use "
        "exactly these sections:\n"
        "WHAT THIS IS:\nWHY IT MATTERS:\nWHAT BLOCKS IT OR WHAT IS BEING "
        "DECIDED:\nFACTS ON RECORD:\nWHAT IS NOT KNOWN:\n"
        "If the record shows this item proceeds or clears only on "
        "a declaration or decision by Brian himself, state plainly "
        "that it waits on Brian — never frame it as something the "
        "board decides. Purchases are for Brian alone.\n"
        "Purchase advice — what to buy and when — belongs to "
        "DealsDesk, not the board; when a purchase question is "
        "open, name DealsDesk as the adviser Brian hears it from.\n"
        "WHAT IS NOT KNOWN means facts about THIS item that the "
        "record does not hold — never other people's questions or "
        "topics. Then a final section EXTRA QUESTIONS: with 3 to 5 "
        "short, easy, specific questions about THIS item (not generic "
        "ones) that would help decide it later.")
    user = (f"ITEM LABEL: {name}\n\nFACTS EXTRACTED FROM THE RECORD:\n"
            + "\n".join(facts)
            + f"\n\nFULL RECORD (for context):\n{source[:16000]}")
    return llm("morpheus", system, user, max_tokens=1100)


def split_draft(draft):
    """Split Morpheus' draft into (page, extra questions)."""
    marker = "EXTRA QUESTIONS:"
    if marker not in draft:
        return draft.strip(), []
    page, tail = draft.split(marker, 1)
    extras = []
    for ln in tail.splitlines():
        ln = ln.strip().lstrip("-0123456789. ").strip()
        if ln.endswith("?") and len(ln) > 10:
            extras.append(ln)
    return page.strip(), extras[:5]


def sonic_verify(page, source):
    system = (
        "You are the senior clerk fact-checking a board package before "
        "the board reads it. Check every claim in the package against "
        "the record. Fix or remove anything the record does not say. "
        "If a claim cannot be verified from the record, keep it only "
        "with '(not verified in the record)' after it. Keep the same "
        "section headings and plain words. Then add one final section:\n"
        "DECIDED BEFORE / STANDING RULES:\n"
        "— answer from the RECORD FIELDS and the RESEARCH FROM THE "
        "HOUSE sections specifically: name the prior decisions and "
        "standing rules found there (an item's own clearing rule "
        "counts as a standing rule). Never summarize questions anyone "
        "asked. If those sections hold no prior decision, write "
        "exactly: No prior decision found in the record.\n"
        "Return ONLY the corrected package.")
    user = f"RECORD:\n{source[:45000]}\n\nPACKAGE TO CHECK:\n{page}"
    return llm("sonic", system, user, max_tokens=1400)


# ------------------------------------------------------------------ build
DESK_SUBJECTS = ["dealsdesk", "campaignsdesk", "contactflowcrm",
                 "trafficstreemz", "clerk", "board", "altair", "meghan",
                 "successbrian os", "package writer", "hiro"]


def fitness_subject(node):
    """Is this item about a desk/plugin/part of the ecosystem itself?
    Brian's improvement watch (2026-10-31) applies to those items."""
    hay = ((node["name"] or "") + " " + node["node_key"]).lower()
    for s in DESK_SUBJECTS:
        if s in hay:
            return s
    return None


def fit_check(subject, source):
    """The clerk's build-and-fitness check (Brian's standing questions,
    2026-10-31): what is the current build, what does Brian need it to
    do, does it do that, is it doing it well, can it do better —
    answered from the record only."""
    system = ("You are the clerk doing a build-and-fitness check on one "
              "part of Brian's ecosystem. Answer ONLY from the record "
              "below, in plain words, under exactly these headings:\n"
              "CURRENT BUILD:\nWHAT BRIAN NEEDS IT TO DO:\n"
              "DOES IT DO THAT:\nIS IT DOING IT WELL:\n"
              "CAN IT DO BETTER:\n"
              "Where the record does not say, write 'not in the "
              "record' — never invent a capability, a version, or a "
              "verdict the record does not support.")
    user = f"SUBJECT: {subject}\n\nRECORD:\n{source[:45000]}"
    return llm("sonic", system, user, max_tokens=800)


def resolve_questions(questions, source):
    """Brian's ruling (2026-10-31): a question the house record already
    answers does not go to the board — the clerk resolves it and writes
    the answer into the item's record, making the ecosystem clearer.
    Returns [{question, answer}] for the questions the record settles;
    the rest stay open for the board."""
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    system = ("You are the clerk resolving board questions from the house "
              "record. For each numbered question, answer ONLY if the "
              "record below settles it directly with facts. Reply with "
              "one line per settled question, exactly: N | the answer, "
              "in plain words, using only facts from the record. If the "
              "record does not settle a question, output nothing for it. "
              "Never guess. Never use outside knowledge.")
    user = f"QUESTIONS:\n{numbered}\n\nRECORD:\n{source[:45000]}"
    out = llm("sonic", system, user, max_tokens=900)
    resolved = []
    for ln in out.splitlines():
        m = re.match(r"\s*(\d+)\s*\|\s*(.+)", ln)
        if m and 1 <= int(m.group(1)) <= len(questions):
            resolved.append({"question": questions[int(m.group(1)) - 1],
                             "answer": m.group(2).strip()})
    return resolved


def _heal(cur):
    """Verify the DB connection is alive before filing; reconnect if
    it dropped during the long engine calls."""
    global conn
    try:
        cur.execute("SELECT 1")
        return cur
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        conn = psycopg2.connect(dbname="ecosystem_central",
                                user="successbrian", host="localhost")
        print("  (db connection had dropped; reconnected)")
        return conn.cursor()


def build_package(cur, node, force=False, dry_run=False):
    global conn
    cur = _heal(cur)  # every item starts on a live connection
    key = node["node_key"]
    details = dict(node["details"] or {})
    source = assemble(cur, node)
    found = research(cur, node)
    if found:
        source += "\n\n===== RESEARCH FROM THE HOUSE =====\n" + found
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]
    stamp = details.get("package") or {}
    if (stamp.get("source_hash") == digest and stamp.get("verified")
            and not force):
        return key, "current (source unchanged)", None
    engines = []
    try:
        facts = penny_extract(source)
        engines.append("penny")
    except Exception as e:
        facts = [ln for ln in source.splitlines()
                 if ln.startswith(("RECORD FIELD", "CONNECTION"))]
        print(f"  penny failed ({e}); facts from record lines")
    if not facts:
        facts = ["- " + ln for ln in source.splitlines()[:14]]
    try:
        draft = morpheus_draft(node["name"], facts, source)
        engines.append("morpheus")
    except Exception as e:
        print(f"  morpheus failed ({e}); code template page")
        draft = ("WHAT THIS IS:\n" + node["name"] + "\n\nFACTS ON RECORD:\n"
                 + "\n".join(facts))
    page, extras = split_draft(draft)
    try:
        page = sonic_verify(page, source)
        engines.append("sonic")
    except Exception as e:
        print(f"  sonic failed ({e}); page ships unverified")
        page += "\n\n(NOT YET FACT-CHECKED — the verifying engine was busy.)"
    easy = list(EASY_QUESTIONS)
    for q in extras:
        if q not in easy:
            easy.append(q)
    # Improvement watch (Brian 2026-10-31): desk/plugin items carry
    # the clerk's build-and-fitness check on their package.
    fsubj = fitness_subject(node)
    if fsubj:
        try:
            fit = fit_check(fsubj, source)
            page += ("\n\nCLERK'S BUILD & FITNESS CHECK (" + fsubj
                     + "):\n" + fit.strip())
            engines.append("sonic-fitcheck")
        except Exception as e:
            print(f"  fit check failed ({e}); package ships without it")
    # Brian's resolve-in-house ruling (2026-10-31): questions the record
    # already answers are settled here, not handed to the board.
    resolved = []
    asked = board_questions_for(key)
    if asked:
        try:
            resolved = resolve_questions(asked[-12:], source)
        except Exception as e:
            print(f"  resolve failed ({e}); questions stay open")
    if resolved:
        lines = ["", "ANSWERED FROM THE RECORD (clerk-resolved — settled "
                 "in the house; no need to ask again):"]
        for r in resolved[:8]:
            lines.append(f"- Q: {r['question']}")
            lines.append(f"  A: {r['answer']}")
        page += "\n" + "\n".join(lines)
    if dry_run:
        return key, "dry-run", (page, easy, engines, resolved)
    details["question"] = page
    details["easy_questions"] = easy
    details["clerk_resolved"] = resolved
    details["package"] = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "engines": engines,
        "source_hash": digest,
        "resolved": len(resolved),
        "verified": "sonic" in engines,
        "builder": "clerk package writer v3 (Brian 2026-10-31)",
    }
    cur = _heal(cur)
    cur.execute("UPDATE atlas.nodes SET details = %s::jsonb "
                "WHERE node_key = %s", (json.dumps(details), key))
    conn.commit()
    return key, f"built ({', '.join(engines)})", (page, easy, engines,
                                                  resolved)


def fetch_nodes(cur, args):
    if args.item:
        cur.execute("SELECT node_key, node_type, name, status, details "
                    "FROM atlas.nodes WHERE node_key = %s", (args.item,))
    elif args.gates:
        cur.execute("SELECT node_key, node_type, name, status, details "
                    "FROM atlas.nodes WHERE node_type = 'gate' "
                    "AND status = 'pending' ORDER BY node_key")
    else:  # thin: agenda items whose page is just their label or tiny
        cur.execute(
            "SELECT node_key, node_type, name, status, details "
            "FROM atlas.nodes WHERE (node_type = 'gate' AND "
            "status = 'pending') OR (node_type = 'atlas_task' AND "
            "status IN ('open', 'queued')) ORDER BY "
            "(node_type = 'gate') DESC, node_key")
    rows = [dict(zip(("node_key", "node_type", "name", "status", "details"), r))
            for r in cur.fetchall()]
    if args.thin:
        def is_thin(n):
            d = n["details"] or {}
            page = (d.get("question") or d.get("about") or "").strip()
            return (not page or page == n["name"].strip()
                    or len(page) < 150) and "package" not in d
        rows = [n for n in rows if is_thin(n)][:args.thin]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item")
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--thin", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    global conn
    conn = psycopg2.connect(dbname="ecosystem_central",
                            user="successbrian", host="localhost")
    cur = conn.cursor()
    if not (args.item or args.gates or args.thin):
        print("package builder: a scope is required (--item KEY, "
              "--gates, or --thin N) — refusing to build the whole "
              "agenda by accident", file=sys.stderr)
        sys.exit(2)
    nodes = fetch_nodes(cur, args)
    print(f"package builder: {len(nodes)} item(s) in scope")
    for node in nodes:
        try:
            key, status, built = build_package(
                cur, node, force=args.force, dry_run=args.dry_run)
            print(f"[{key}] {status}")
            if built and (args.dry_run or args.item):
                page, easy, engines, resolved = built
                print("----- PAGE -----")
                print(page)
                print(f"----- DECIDE-STAGE QUESTIONS ({len(easy)}) -----")
                for q in easy:
                    print(" -", q)
                if resolved:
                    print(f"----- CLERK-RESOLVED FROM THE RECORD "
                          f"({len(resolved)}) -----")
                    for r in resolved:
                        print(" Q:", r["question"])
                        print(" A:", r["answer"])
                print("----------------")
        except Exception as e:
            conn.rollback()
            print(f"[{node['node_key']}] FAILED: {e}")
    conn.close()


if __name__ == "__main__":
    main()
