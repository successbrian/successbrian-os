#!/usr/bin/env python3
"""
Intel classifier + business idea vetting for SuccessBrian OS.

PURPOSE:
    Take any input (md file content, pasted text) and answer two questions:
    (1) what IS this intel? (2) if it is a business idea, how does it vet
    against the existing income portfolio (income_streams) and the idea
    pipeline (ventures)?

WHY:
    Brian 2026-10-02: the OS should accept raw intel in any form — a file, a
    paste — and turn it into "what is this intel?" Is it a business idea?
    Then: can it be vetted against the income ideas we already use or are
    considering? Duplicates must die as ideas, not as projects.

CALLED BY:
    - Intake drivers, heartbeat workers, Altair:
        intel_classifier.py --classify --file notes.md
        intel_classifier.py --classify --text "I want to start a dog walking MLM"
        intel_classifier.py --vet --text "a cloud backup MLM"
    - Humans: --dry-run previews actions without DB writes; --json for drivers.

NOTES:
    - Deterministic keyword scoring (no model call): fast, testable, runs on
      CPU. Escalation path: swap _score_types() for a local 14B/32B classifier
      when keyword tables grow unwieldy.
    - business_idea with confidence > 0.7 auto-inserts into
      successbrian_os.ventures (status='raw'). prospect_insight prints a
      suggested INSERT for prospect_angles but NEVER auto-inserts — Brian
      approves angles.
    - DB access: psycopg2 direct (peer auth as successbrian on k11-alpha
      localhost) first; falls back to the kssh+base64 pattern from
      tools/second_brain.py when run off-box (the kssh binary only exists on
      the hatch VM, not on k11-alpha).
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"

AUTO_INSERT_CONFIDENCE = 0.7
DUPLICATE_THRESHOLD = 0.5

STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "i", "we",
    "you", "they", "he", "she", "my", "our", "your", "their", "this",
    "that", "these", "those", "at", "as", "by", "from", "into", "want",
    "just", "very", "also", "than", "then", "so", "but", "not", "no",
}

# type -> [(phrase, weight)] — phrases matched case-insensitively, once each.
TYPE_KEYWORDS = {
    "business_idea": [
        ("income stream", 3), ("mlm", 3), ("downline", 3), ("business idea", 3),
        ("commission", 2), ("affiliate", 2), ("side hustle", 2),
        ("make money", 2), ("passive income", 2), ("reseller", 2),
        ("white label", 2), ("startup", 1), ("saas", 1), ("launch", 1),
    ],
    "prospect_insight": [
        ("good prospects for", 3), ("target audience", 2), ("prospects", 2),
        ("ideal customer", 2), ("prospect", 1), ("avatar", 1), ("pitch", 1),
        ("angle", 1),
    ],
    "decision": [
        ("decided", 2), ("going with", 2), ("go with", 2), ("we're doing", 2),
        ("approved", 2), ("on hold", 2), ("dropping", 2), ("locked in", 2),
    ],
    "research_finding": [
        ("research shows", 2), ("data shows", 2), ("benchmark", 2),
        ("according to", 1), ("study", 1), ("found that", 1),
    ],
    "task": [
        ("todo", 2), ("action item", 2), ("reminder", 2), ("need to", 1),
        ("follow up", 1),
    ],
    "news": [
        ("breaking", 2), ("announced", 2), ("launches", 1), ("released", 1),
    ],
}

# category -> keywords (must cover the categories present in income_streams)
CATEGORY_KEYWORDS = {
    "wellness": ["wellness", "nutrition", "supplement", "health", "diet",
                 "weight", "fitness", "vitamin"],
    "tech": ["backup", "cloud", "software", "app", "tech", "data",
             "storage", "saas"],
    "lead-gen": ["lead", "leads", "traffic", "prospect", "prospects",
                 "solo", "mailer", "safelist", "capture"],
    "crypto": ["crypto", "bitcoin", "btc", "trading", "defi", "token",
               "blockchain", "wallet"],
    "affiliate": ["affiliate", "jv", "launch", "commission"],
    "content": ["blog", "content", "seo", "newsletter", "youtube",
                "video", "podcast"],
    "hardware": ["pc", "hardware", "flip", "ebay", "server", "computer"],
    "real_estate": ["real estate", "property", "rental", "housing"],
    "mlm": ["mlm", "downline", "network marketing", "distributor"],
    "saas": ["saas", "crm"],
    "service": ["service", "agency", "consulting", "coaching"],
}

# (keyword list, skin) — first matching rule wins per category hit.
SKIN_RULES = [
    (["wellness", "nutrition", "supplement", "health", "diet", "weight"],
     "AegeanVedaFlow"),
    (["crypto", "bitcoin", "trading", "defi", "token"], "CryptoStreemz"),
    (["traffic", "leads", "lead", "prospect", "mailer", "safelist",
      "affiliate"], "TrafficStreemz"),
    (["backup", "cloud", "software", "saas"], "all-skins"),
]

SKIN_NOTE = {
    "all-skins": "backup/tech pattern: consider all skins like GotBackup "
                 "(in every skin + standalone)",
}


# ---------------------------------------------------------------- DB layer

# SBOS common routines - Batch C migration (2026-10-27).
import os as _os_c, sys as _sys_c
_sys_c.path.insert(0, _os_c.path.dirname(_os_c.path.abspath(__file__)))
import sbos_common  # noqa: E402


def esc(s):
    # Batch C migration (2026-10-27): delegates to sbos_common.esc -
    # the one SQL-escape definition for the ecosystem.
    return sbos_common.esc(s)


def _pg_psycopg2_rows(sql: str):
    import psycopg2
    conn = psycopg2.connect(host="localhost", dbname="ecosystem_central",
                            user="successbrian")
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall() if cur.description else []
        conn.commit()
        return [tuple(r) for r in rows]
    finally:
        conn.close()


def _pg_kssh_rows(sql: str):
    # second_brain.py base64 pattern, verbatim: moves SQL through the remote
    # shell opaquely so metacharacters stay literal for psql.
    b64 = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    out = subprocess.run(
        [str(KSSH), "psql -h localhost -U successbrian -d ecosystem_central "
                    f"-t -A -c \"$(echo {b64} | base64 -d)\""],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return [tuple(line.split("|"))
            for line in out.stdout.strip().split("\n") if line.strip()]


def pg_rows(sql: str):
    """SELECT helper: psycopg2 direct on k11-alpha, kssh fallback off-box."""
    try:
        return _pg_psycopg2_rows(sql)
    except Exception:
        return _pg_kssh_rows(sql)


def pg_exec(sql: str) -> None:
    """Write helper: psycopg2 direct on k11-alpha, kssh fallback off-box."""
    try:
        _pg_psycopg2_rows(sql)
    except Exception:
        _pg_kssh_rows(sql)


def get_income_streams():
    rows = pg_rows(
        "SELECT name, type, category, status, notes "
        "FROM successbrian_os.income_streams ORDER BY name;")
    return [{"name": r[0], "type": r[1] or "", "category": r[2] or "",
             "status": r[3] or "", "notes": r[4] or ""} for r in rows]


def get_ventures(status=None):
    where = f"WHERE status = '{esc(status)}'" if status else ""
    rows = pg_rows(
        f"SELECT id, title, status FROM successbrian_os.ventures "
        f"{where} ORDER BY id DESC LIMIT 200;")
    return [{"id": r[0], "title": r[1], "status": r[2]} for r in rows]


def insert_venture(title: str, raw_pitch: str) -> int:
    rows = pg_rows(
        "INSERT INTO successbrian_os.ventures (title, raw_pitch, status) "
        f"VALUES ('{esc(title)}', '{esc(raw_pitch)}', 'raw') "
        "RETURNING id;")
    return int(rows[0][0])


# ---------------------------------------------------------------- classify

def tokenize(text: str):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in STOPWORDS]


def _score_types(text: str):
    low = text.lower()
    scores = {}
    for ttype, phrases in TYPE_KEYWORDS.items():
        s = 0
        for phrase, w in phrases:
            if phrase in low:
                s += w
        if s:
            scores[ttype] = s
    return scores


def classify_intel(text: str) -> dict:
    """Classify raw intel text. Returns {type, confidence, summary, scores}."""
    text = (text or "").strip()
    if not text:
        return {"type": "noise", "confidence": 1.0,
                "summary": "", "scores": {}}
    scores = _score_types(text)
    total = sum(scores.values())
    if total == 0:
        return {"type": "noise", "confidence": 0.6,
                "summary": text[:120], "scores": {}}
    best = max(scores, key=scores.get)
    confidence = round(scores[best] / total, 2)
    return {"type": best, "confidence": confidence,
            "summary": text[:120], "scores": scores}


# ---------------------------------------------------------------- vet

def _idea_categories(idea_text: str):
    low = idea_text.lower()
    cats = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in low for k in kws):
            cats.append(cat)
    return cats


def _stream_overlap(idea_tokens, idea_lower, stream):
    """Returns (token_norm, combined).

    token_norm: pure lexical evidence, normalized by idea length.
    combined: token_norm + category-alignment bonus (0.3).
    A token that is a substring of the stream NAME scores strong (+1.0):
    that is usually the product itself (e.g. "backup" in "GotBackup").
    """
    name_lower = stream["name"].lower()
    blob = " ".join([name_lower, stream["type"],
                     stream["category"], stream["notes"]]).lower()
    blob_tokens = set(tokenize(blob))
    score = 0.0
    for t in idea_tokens:
        if len(t) < 3:
            continue
        if t in blob_tokens:
            score += 1.0
        elif t in name_lower or name_lower in t:
            score += 1.0  # product-name hit
        elif t in blob:
            score += 0.5
    for w in re.findall(r"[a-z0-9]+", name_lower):
        if len(w) >= 5 and w in idea_lower and w not in blob_tokens:
            score += 1.5
    token_norm = score / max(len(idea_tokens), 1)
    combined = token_norm + (0.3 if stream["category"] and
                             stream["category"] in _idea_categories(" ".join(idea_tokens)) else 0)
    return token_norm, combined


def vet_business_idea(idea_text: str) -> dict:
    """Vet a business idea against income_streams + ventures.

    Returns {is_duplicate, overlaps, category_fit, skin_suggestions,
    vetting_notes}.
    """
    idea_text = (idea_text or "").strip()
    idea_tokens = tokenize(idea_text)
    idea_lower = idea_text.lower()
    idea_cats = set(_idea_categories(idea_text))

    overlaps = []
    for s in get_income_streams():
        token_norm, combined = _stream_overlap(idea_tokens, idea_lower, s)
        # List only with real lexical evidence: one generic token
        # ("service") plus a category match must NOT count as overlap.
        if combined >= 0.4 and token_norm >= 0.2:
            overlaps.append({"name": s["name"], "status": s["status"],
                             "score": round(combined, 2),
                             "_tok": token_norm})
    dup = [o for o in overlaps
           if o["score"] >= DUPLICATE_THRESHOLD and o["_tok"] >= 0.3]
    for o in overlaps:
        o.pop("_tok", None)
    for v in get_ventures():
        vtext = v["title"].lower()
        hits = sum(1 for t in idea_tokens
                   if len(t) >= 4 and t in vtext)
        sc = hits / max(len(idea_tokens), 1)
        if sc >= 0.3:
            overlaps.append({"name": f"venture: {v['title']}",
                             "status": v["status"],
                             "score": round(sc, 2)})
    overlaps.sort(key=lambda o: o["score"], reverse=True)

    existing_cats = {s["category"] for s in get_income_streams()
                     if s["category"]}
    fit = sorted(idea_cats & existing_cats)
    category_fit = ("fits existing: " + ", ".join(fit)) if fit else \
        "new category — no existing stream covers this"

    skins = []
    for kws, skin in SKIN_RULES:
        if any(k in idea_lower for k in kws) and skin not in skins:
            skins.append(skin)
    if not skins:
        skins = ["standalone"]
    notes = [SKIN_NOTE[s] for s in skins if s in SKIN_NOTE]

    is_dup = bool(dup)
    if is_dup:
        vetting_notes = (f"Likely duplicate of '{overlaps[0]['name']}' "
                         f"(score {overlaps[0]['score']}). Do not start a "
                         f"new project — fold into the existing stream.")
    elif overlaps:
        vetting_notes = ("Partial overlap with: " +
                         ", ".join(o["name"] for o in overlaps[:3]) +
                         ". Differentiate or partner before proceeding.")
    else:
        vetting_notes = ("No overlap with the current portfolio. " +
                         ("New category — blue ocean for this ecosystem. "
                          if category_fit.startswith("new") else
                          "Fits an existing lane without duplicating a stream."))
    vetting_notes += " Suggested skin(s): " + ", ".join(skins) + "."
    vetting_notes += " " + " ".join(notes)

    return {"is_duplicate": is_dup, "overlaps": overlaps,
            "category_fit": category_fit, "skin_suggestions": skins,
            "vetting_notes": vetting_notes}


# ---------------------------------------------------------------- routing

def _venture_title(text: str) -> str:
    t = " ".join(text.split())
    return t[:60] + ("…" if len(t) > 60 else "")


def classify_and_route(text: str, dry_run: bool = False) -> dict:
    """Classify intel; auto-insert business_idea>0.7 into ventures (raw)."""
    result = classify_intel(text)
    action = "none"
    if result["type"] == "business_idea" and \
            result["confidence"] > AUTO_INSERT_CONFIDENCE:
        title = _venture_title(text)
        sql = ("INSERT INTO successbrian_os.ventures (title, raw_pitch, status) "
               f"VALUES ('{esc(title)}', '{esc(text)}', 'raw');")
        if dry_run:
            action = "would_insert_venture"
            result["dry_run_sql"] = sql
        else:
            vid = insert_venture(title, text)
            action = f"inserted_venture:{vid}"
    elif result["type"] == "prospect_insight":
        # NEVER auto-insert angles — Brian approves them.
        seg = result["summary"]
        sql = ("INSERT INTO successbrian_os.prospect_angles "
               "(prospect_segment, product, angle, why) VALUES "
               f"('{esc(seg)}', '<PRODUCT>', '<ANGLE>', '<WHY>');")
        action = "suggested_angle_sql"
        result["suggested_sql"] = sql
        if dry_run:
            result["dry_run"] = True
    result["action"] = action
    return result


# ---------------------------------------------------------------- CLI

def _read_input(args) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return args.text or ""


def main() -> int:
    p = argparse.ArgumentParser(
        description="Classify intel and vet business ideas for "
                    "SuccessBrian OS.")
    p.add_argument("--classify", action="store_true",
                   help="Classify the input text/file.")
    p.add_argument("--vet", action="store_true",
                   help="Vet a business idea against the portfolio.")
    p.add_argument("--file", help="Path to a .md/.txt file to read.")
    p.add_argument("--text", help="Raw text to process.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would happen; no DB writes.")
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON.")
    args = p.parse_args()

    if not args.classify and not args.vet:
        p.error("choose --classify or --vet")
    if not args.file and not args.text:
        p.error("provide --file or --text")

    text = _read_input(args)
    out = classify_and_route(text, dry_run=args.dry_run) if args.classify \
        else vet_business_idea(text)

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        if args.classify:
            r = out
            print(f"type: {r['type']} (confidence {r['confidence']})")
            print(f"summary: {r['summary']}")
            print(f"action: {r['action']}")
            if "dry_run_sql" in r:
                print(f"would run: {r['dry_run_sql']}")
            if "suggested_sql" in r:
                print("Suggested angle SQL (needs Brian's product/angle/why "
                      "filled in):")
                print(f"  {r['suggested_sql']}")
        else:
            print(f"is_duplicate: {out['is_duplicate']}")
            print(f"category_fit: {out['category_fit']}")
            print(f"skin_suggestions: {', '.join(out['skin_suggestions'])}")
            if out["overlaps"]:
                print("overlaps:")
                for o in out["overlaps"]:
                    print(f"  - {o['name']} [{o['status']}] "
                          f"score {o['score']}")
            print(f"notes: {out['vetting_notes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# --- V4 Pro enhancement (Brian 2026-10-02) ---
# When DeepSeek V4 Pro API is available, use it for classification (better
# than keywords). When not available, stage items in intel_staging for later.

def _v4pro_available() -> bool:
    """Check if V4 Pro credits are available via model_tiers."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from model_tiers import get_tiers
        return get_tiers().get("v4pro_cloud", {}).get("available", False)
    except Exception:
        return False

def stage_intel(raw_text: str, source: str = "manual") -> int:
    """Stage intel for later V4 Pro processing. Returns staging id."""
    sql = (
        "INSERT INTO successbrian_os.intel_staging (raw_text, source) "
        f"VALUES ('{esc(raw_text)}', '{esc(source)}') RETURNING id;"
    )
    out = pg_exec(sql).strip()
    return int(out.split()[0]) if out else -1

V4PRO_CLASSIFY_PROMPT = """Classify this intel into exactly one type.
Types: business_idea, prospect_insight, decision, research_finding, task, news, noise.
Reply with ONLY a JSON object: {"type": "<type>", "confidence": 0.0-1.0, "summary": "<one sentence>"}.
Intel: """

V4PRO_CLASSIFY_PROMPT = (
    "Classify this intel into exactly one type.\n"
    "Types: business_idea, prospect_insight, decision, research_finding, "
    "task, news, noise.\n"
    'Reply with ONLY a JSON object: {"type": "<type>", '
    '"confidence": 0.0-1.0, "summary": "<one sentence>"}.\nIntel: '
)

# Remote script path on k11-alpha (written once, reused)
V4PRO_REMOTE_SCRIPT = "/tmp/sbos_v4pro_classify.py"

V4PRO_REMOTE_CODE = """import json, sys, urllib.request
key = None
with open('/home/successbrian/.hermes/.env') as f:
    for line in f:
        s = line.strip()
        if s.startswith('DEEPSEEK_API_KEY='):
            key = s.split('=', 1)[1]
if not key:
    print(json.dumps({'error': 'no key'}))
    sys.exit(1)
prompt = sys.stdin.read()
body = json.dumps({
    'model': 'deepseek-chat',
    'messages': [{'role': 'user', 'content': prompt}],
    'max_tokens': 200, 'temperature': 0.1,
}).encode()
req = urllib.request.Request(
    'https://api.deepseek.com/chat/completions', data=body,
    headers={'Authorization': 'Bearer ' + key,
             'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    print(data['choices'][0]['message']['content'].strip())
except Exception as e:
    print(json.dumps({'error': str(e)[:100]}))
"""


def _on_k11alpha() -> bool:
    """True if running directly on k11-alpha (no kssh needed)."""
    from pathlib import Path
    return (Path("/home/successbrian/.hermes/.env").exists()
            and not (Path.home() / "workspace" / "bin" / "kssh").exists())


def _ensure_v4pro_remote():
    """Write the remote script to k11-alpha if not present."""
    import subprocess
    from pathlib import Path
    if _on_k11alpha():
        # Running on k11-alpha: write directly
        Path(V4PRO_REMOTE_SCRIPT).write_text(V4PRO_REMOTE_CODE)
        return
    kssh = Path.home() / "workspace" / "bin" / "kssh"
    import base64
    b64 = base64.b64encode(V4PRO_REMOTE_CODE.encode()).decode()
    subprocess.run(
        [str(kssh),
         f"echo {b64} | base64 -d > {V4PRO_REMOTE_SCRIPT}"],
        capture_output=True, timeout=15)


def classify_with_v4pro(text):
    """Use V4 Pro for classification if available, else None.

    Runs ON k11-alpha via kssh so the rental key never leaves that
    machine (same pattern as tools/v4pro_balance.py).
    """
    if not _v4pro_available():
        return None
    try:
        _ensure_v4pro_remote()
        from pathlib import Path
        prompt = V4PRO_CLASSIFY_PROMPT + text[:2000]
        if _on_k11alpha():
            cmd = ["python3", V4PRO_REMOTE_SCRIPT]
        else:
            kssh = Path.home() / "workspace" / "bin" / "kssh"
            cmd = [str(kssh), f"python3 {V4PRO_REMOTE_SCRIPT}"]
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=45)
        out = proc.stdout.strip()
        m = re.search(r'\{[^{}]*"type"[^{}]*\}', out)
        if not m:
            return None
        result = json.loads(m.group(0))
        return result if "type" in result else None
    except Exception:
        return None


def smart_classify(text: str, source: str = "manual") -> dict:
    """Classify with V4 Pro if available; otherwise keyword-classify and stage
    for V4 Pro re-processing later."""
    v4pro_result = classify_with_v4pro(text)
    if v4pro_result:
        v4pro_result["method"] = "v4pro"
        return v4pro_result
    # Fallback: keyword classification + stage for later
    result = classify_intel(text)
    result["method"] = "keyword+staged"
    result["staged_id"] = stage_intel(text, source)
    return result
