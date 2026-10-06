#!/usr/bin/env python3
"""Meme idea box — Brian's political meme idea pipeline on k11-alpha.

PURPOSE:
    Intake, store, and generate daily political meme ideas. Raw ideas flow
    in all day (midday feeder, Brian himself); every evening at 18:30 the
    k11 cron runs `generate`, which feeds the day's RSS headlines + raw
    ideas to Sonic (qwen-a3b, localhost:11439) and stores EXACTLY 4 final
    "magausnavyvet style contrasts" for the evening. The Hatch side reads
    them at 18:45 via `export` and delivers them to chat.

WHY:
    Brian's standing split: data and logic live on his own nodes, not the
    Hatch VM. The idea queue, the generation, and the model call all run on
    k11-alpha; Hatch only triggers and delivers. This keeps the meme desk
    working even when the VM is down, and keeps his data in his Postgres.

CALLED BY:
    - k11 crontab: `meme_idea_box.py generate` daily 18:30 (America/Chicago)
    - Hatch midday feeder cron: `meme_idea_box.py add ...` (raw intake)
    - Hatch evening cron: `meme_idea_box.py export` (deliver finals)
    - Brian / Spencer, ad hoc: add / list / export

NOTES:
    - DB is ecosystem_central (NOT successbrian_os — the successbrian role
      has no CREATE privilege there; ecosystem_central is also the sanctioned
      data store per AGENTS.md). Table: public.meme_ideas.
    - generate() NEVER invents poll numbers. If Sonic returns no real data,
      the angle must say so.
    - FULLY AUTONOMOUS: k11 needs nothing from Hatch. generate() retries
      Sonic once after 60s; if it still yields zero finals it writes a
      dated fallback note (never fails silently). Every run also writes
      /home/successbrian/meme-ideas/YYYY-MM-DD.md and posts the 4 ideas
      to Brian's Telegram via scripts/tg_post.py — so Brian gets the ideas
      even if the Hatch link is dead. The Hatch 18:45 chat read is the
      primary interactive path (he picks numbers in chat); duplicates
      across Telegram + chat are acceptable, missing the ideas is not.
    - TWO-STAGE GENERATION (Brian's routing principle: Sonic does what it
      can, V4 Pro assists): step 1, Sonic drafts the 4 contrasts;
      step 2, maybe_sharpen_with_v4pro() sends the drafts for a polish
      pass ONLY when tools/state/model-tiers.json says v4pro_credits=true
      (rental live as of 2026-10-06). Any V4 Pro failure returns
      the Sonic drafts unchanged — the job never fails because V4 Pro
      is missing.
    - RSS parsing is dependency-free (urllib + ElementTree). Feeds die;
      failures are skipped, never fatal.
    - Sonic JSON is parsed defensively (code fences, brace matching) —
      a sloppy model reply must not crash the run.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DBNAME = os.environ.get("MEME_IDEA_DB", "ecosystem_central")
SONIC_URL = os.environ.get("SONIC_URL", "http://localhost:11439/v1/chat/completions")
SONIC_MODEL = os.environ.get("SONIC_MODEL", "qwen-a3b")
IDEAS_DIR = os.environ.get("MEME_IDEAS_DIR", "/home/successbrian/meme-ideas")
TG_POST = os.environ.get("TG_POST", "/home/successbrian/scripts/tg_post.py")

RSS_FEEDS = [
    ("FoxNews-Politics", "http://feeds.foxnews.com/foxnews/politics"),
    ("CNN-Politics", "http://rss.cnn.com/rss/cnn_allpolitics.rss"),
    ("NPR-Politics", "https://feeds.npr.org/1014/rss.xml"),
    ("PBS-NewsHour", "https://www.pbs.org/newshour/feeds/rss/headlines"),
    ("BBC-US", "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
]

UA = {"User-Agent": "Mozilla/5.0 (meme-idea-box/1.0)"}


# ---------------------------------------------------------------- DB layer
def _have_psycopg2():
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


def _pg_conn():
    import psycopg2
    conn = psycopg2.connect(dbname=DBNAME)
    conn.autocommit = True
    return conn


def _psql(sql, tuples=False):
    """Fallback when psycopg2 is missing: local psql subprocess."""
    cmd = ["psql", "-d", DBNAME, "-tA"]
    if tuples:
        cmd += ["-F", "\x1f"]
    cmd += ["-c", sql]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def db_add(headline, angle="", punchline="", why="", sources="",
           kind="raw", idea_date=None, status="new", metadata=None):
    idea_date = idea_date or dt.date.today().isoformat()
    metadata = metadata or {}
    if _have_psycopg2():
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO meme_ideas
               (idea_date, kind, status, headline, angle, punchline,
                why_it_works, sources, metadata)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (idea_date, kind, status, headline, angle, punchline,
             why, sources, json.dumps(metadata)))
        new_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        return new_id
    # psql fallback — escape single quotes by doubling
    q = lambda s: (s or "").replace("'", "''")
    sql = (f"INSERT INTO meme_ideas (idea_date,kind,status,headline,angle,"
           f"punchline,why_it_works,sources,metadata) VALUES "
           f"('{q(idea_date)}','{q(kind)}','{q(status)}','{q(headline)}',"
           f"'{q(angle)}','{q(punchline)}','{q(why)}','{q(sources)}',"
           f"'{q(json.dumps(metadata))}'::jsonb) RETURNING id")
    return int(_psql(sql))


def db_list(idea_date=None, kind=None):
    idea_date = idea_date or dt.date.today().isoformat()
    if _have_psycopg2():
        conn = _pg_conn()
        cur = conn.cursor()
        sql = ("SELECT id, kind, status, headline FROM meme_ideas "
               "WHERE idea_date=%s")
        params = [idea_date]
        if kind:
            sql += " AND kind=%s"
            params.append(kind)
        sql += " ORDER BY id"
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    where = f"idea_date='{idea_date}'"
    if kind:
        where += f" AND kind='{kind}'"
    out = _psql(f"SELECT id,kind,status,headline FROM meme_ideas "
                f"WHERE {where} ORDER BY id", tuples=True)
    return [tuple(r.split("\x1f")) for r in out.splitlines() if r]


def db_get_finals(idea_date=None):
    """Full rows for today's finals, ordered."""
    idea_date = idea_date or dt.date.today().isoformat()
    if _have_psycopg2():
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, headline, angle, punchline, why_it_works, sources
               FROM meme_ideas
               WHERE idea_date=%s AND kind='final' AND status='new'
               ORDER BY id""", (idea_date,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    out = _psql(
        "SELECT id,headline,angle,punchline,why_it_works,sources FROM meme_ideas "
        f"WHERE idea_date='{idea_date}' AND kind='final' AND status='new' "
        "ORDER BY id", tuples=True)
    return [tuple(r.split("\x1f")) for r in out.splitlines() if r]


def db_delete(ids):
    if not ids:
        return
    if _have_psycopg2():
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM meme_ideas WHERE id = ANY(%s)", (list(ids),))
        cur.close()
        conn.close()
    else:
        _psql(f"DELETE FROM meme_ideas WHERE id IN ({','.join(map(str, ids))})")


# ------------------------------------------------------------ RSS intake
def fetch_rss_headlines(limit_per_feed=8):
    """Dependency-free RSS headline scrape. Dead feeds are skipped."""
    headlines = []
    for name, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read(1_000_000)
            root = ET.fromstring(data)
            count = 0
            for item in root.iter("item"):
                if count >= limit_per_feed:
                    break
                title = item.findtext("title")
                if title:
                    headlines.append(f"[{name}] {title.strip()}")
                    count += 1
        except Exception as e:
            print(f"RSS skip {name}: {e}", file=sys.stderr)
    return headlines


# ------------------------------------------------------------ Sonic call
def sonic_chat(system, user, max_tokens=2200):
    body = json.dumps({
        "model": SONIC_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        SONIC_URL, data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    return payload["choices"][0]["message"]["content"]


def extract_json_array(text):
    """Defensively pull a JSON array of idea objects out of model output."""
    # prefer a fenced code block
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    candidate = m.group(1) if m else None
    if candidate is None:
        # brace/bracket matching from the first '['
        start = text.find("[")
        if start == -1:
            raise ValueError("no JSON array found in model output")
        depth = 0
        instr = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
            else:
                if ch == '"':
                    instr = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        break
        if candidate is None:
            raise ValueError("unbalanced JSON array in model output")
    data = json.loads(candidate)
    if isinstance(data, dict):
        for key in ("ideas", "memes", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("model output is not a list")
    return data


# ------------------------------------------------------------ generate
SYSTEM_PROMPT = """You write political meme concepts for Brian, a MAGA Navy \
veteran (enlisted MMN, USS George Washington). His brand voice: blunt, \
plain-spoken, accusatory toward the left, data-backed, maximalist. \
His crowd: MAGA, veterans, people feeling it at the gas pump.

Work in three phases before writing:

1. TRUTH OF THE DAY: from the headlines and fed ideas, separate verified \
facts from partisan narrative. Note what the left claims, what the right \
claims, and what is actually established. Flag anything unverified.
2. GAPS: identify what the left is ignoring, what the right is ignoring, \
and what NO ONE is covering. A gap is an opportunity — an uncovered angle \
is a meme only Brian can own.
3. ENGAGEMENT HEAT: score each candidate angle 1-10 on raw engagement \
potential (controversy, tribal identity, shareability, comment-bait). \
The hottest fodder wins.

Then return EXACTLY 4 ideas as a JSON array, ordered hottest first. Each \
idea is an object with: "headline" (short, punchy, meme-headline style), \
"angle" (2-4 sentences: the contrast — their narrative vs the truth, or \
the gap nobody is covering), "punchline" (one hard-hitting line in \
Brian's voice), "why_it_works" (one sentence on why this will spark \
engagement), "sources" (where the facts came from, or "no fresh data — \
angle is commentary" if none), "heat" (your 1-10 engagement score).

Rules:
- EXACTLY 4 ideas. No more, no fewer.
- At least ONE idea must exploit a gap — an angle the other side is not \
covering.
- NEVER invent poll numbers, statistics, or quotes. If you have no real \
data for a claim, say so in the angle and keep the idea commentary-driven.
- Vary the 4 angles — not 4 versions of the same story.
- Output ONLY the JSON array, no prose before or after."""


# ------------------------------------------------- V4 Pro polish
# NOTE (2026-10-06): the InstantlyClaw proxy path (api.b.ai, model
# "deepseek-v4-pro") currently 401s with the rental key, so we call
# DeepSeek's own chat endpoint instead — same key, validated live by
# tools/v4pro_balance.py against api.deepseek.com/user/balance.
V4PRO_URL = "https://api.deepseek.com/chat/completions"
V4PRO_MODEL = "deepseek-chat"
V4PRO_ENV_FILE = "/home/successbrian/.hermes/.env"
V4PRO_KEY_NAME = "DEEPSEEK_API_KEY"


def _tiers_flag_path():
    # <repo>/tools/audience/meme_idea_box.py -> <repo>/tools/state/model-tiers.json
    return (Path(__file__).resolve().parent.parent
            / "state" / "model-tiers.json")


def v4pro_available():
    """Source of truth: tools/state/model-tiers.json v4pro_credits flag."""
    try:
        return bool(json.loads(_tiers_flag_path().read_text())
                    .get("v4pro_credits"))
    except Exception:
        return False


def _read_v4pro_key():
    """Rental key from k11's .env — in memory only, never logged."""
    try:
        with open(V4PRO_ENV_FILE) as f:
            for line in f:
                s = line.strip()
                if s.startswith(V4PRO_KEY_NAME + "="):
                    return (s.split("=", 1)[1].strip()
                            .strip('"').strip("'") or None)
    except Exception:
        pass
    return None


SHARPEN_SYSTEM = """You sharpen political meme concepts drafted by a smaller \
model for Brian, a MAGA Navy veteran (enlisted MMN, USS George Washington). \
His brand voice: blunt, plain-spoken, accusatory toward the left, \
data-backed, maximalist. His crowd: MAGA, veterans, people feeling it at \
the gas pump.

You will receive EXACTLY 4 draft ideas as a JSON array. Return EXACTLY 4 \
sharpened ideas as a JSON array with the same keys: "headline", "angle", \
"punchline", "why_it_works", "sources", "heat" (keep each idea's heat \
score, adjusting only if your sharpening clearly raises or lowers it).

Rules:
- Keep every fact from the drafts. NEVER invent poll numbers, statistics, \
or quotes. If a draft says data was unavailable, keep it that way.
- Make headlines punchier, punchlines harder, angles tighter. Cut filler.
- Do not soften the voice or hedge the accusations — sharpen, don't tame.
- Output ONLY the JSON array, no prose before or after."""


def maybe_sharpen_with_v4pro(ideas):
    """Optional V4 Pro polish pass over Sonic's drafts.

    Returns (ideas, sharpened_bool). On ANY failure — flag off, no key,
    API error, bad JSON — returns the original Sonic drafts unchanged.
    The job must never fail because V4 Pro is missing.
    """
    if not ideas:
        return ideas, False
    if not v4pro_available():
        print("V4 Pro skipped (rental flag off) — shipping Sonic drafts")
        return ideas, False
    key = _read_v4pro_key()
    if not key:
        print("V4 Pro skipped (no rental key on this host) "
              "— shipping Sonic drafts")
        return ideas, False
    try:
        body = json.dumps({
            "model": V4PRO_MODEL,
            "messages": [
                {"role": "system", "content": SHARPEN_SYSTEM},
                {"role": "user",
                 "content": "Sharpen these 4 drafts. Return EXACTLY 4 "
                            "as a JSON array:\n\n"
                            + json.dumps(ideas, indent=1)},
            ],
            "temperature": 0.6,
            "max_tokens": 2200,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            V4PRO_URL, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode())
        sharpened = extract_json_array(
            payload["choices"][0]["message"]["content"])[:4]
        if not sharpened:
            raise ValueError("empty sharpened list")
        print(f"V4 Pro sharpened {len(sharpened)} ideas")
        return sharpened, True
    except Exception as e:
        print(f"V4 Pro sharpen skipped ({type(e).__name__}) "
              "— shipping Sonic drafts")
        return ideas, False


def write_ideas_file(idea_date, ideas, headlines, raw_lines,
                     failed=False, fail_reason=""):
    """Dated markdown archive — Brian's fallback read if chat is down."""
    os.makedirs(IDEAS_DIR, exist_ok=True)
    path = os.path.join(IDEAS_DIR, f"{idea_date}.md")
    lines = [f"# Meme ideas — {idea_date}", ""]
    if failed:
        lines += ["**Generation failed** — Sonic unreachable or returned "
                  "no usable ideas after 2 attempts.",
                  f"Reason: {fail_reason}", "",
                  "Raw intake below so the evening is not a total loss.", ""]
    else:
        try:
            days = (dt.date(2026, 11, 3)
                    - dt.date.fromisoformat(idea_date)).days
            lines += [f"{days} days until election day (2026-11-03).", ""]
        except ValueError:
            pass
    for i, it in enumerate(ideas, 1):
        lines += [f"## {i}. {it.get('headline', '')}", "",
                  f"**Angle:** {it.get('angle', '')}", "",
                  f"**Punchline:** \"{it.get('punchline', '')}\"", "",
                  f"**Why it works:** {it.get('why_it_works', '')}", "",
                  f"**Sources:** {it.get('sources', '')}", ""]
    if raw_lines:
        lines += ["---", "", "### Raw intake", ""] + raw_lines + [""]
    if headlines:
        lines += (["### Headlines scanned", ""]
                  + [f"- {h}" for h in headlines[:40]] + [""])
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}")
    return path


def deliver_telegram(idea_date, ideas, failed=False):
    """k11-native delivery — no Hatch involvement. Uses the established
    tg_post.py pattern (token from file, never logged)."""
    if failed:
        text = (f"Meme ideas {idea_date}: tonight's generation failed "
                f"(Sonic unreachable). Raw intake saved to {IDEAS_DIR}/"
                f"{idea_date}.md — check it for the raw hooks.")
    else:
        parts = [f"Tonight's 4 meme ideas ({idea_date}):", ""]
        for i, it in enumerate(ideas, 1):
            parts.append(f"{i}. {it.get('headline', '')}")
            if it.get("punchline"):
                parts.append(f"   \"{it['punchline']}\"")
        parts += ["", "Reply with the number(s) to render."]
        text = "\n".join(parts)
    try:
        p = subprocess.run(["/usr/bin/python3", TG_POST], input=text,
                           capture_output=True, text=True, timeout=60)
        out = p.stdout.strip() or p.stderr.strip()
        print(f"telegram: {out}")
    except Exception as e:
        print(f"telegram delivery failed: {e}", file=sys.stderr)


def synthesize_with_sonic(idea_date, headlines, raw_lines, log):
    """STAGE 1 — Sonic drafts the 4 contrasts. Returns (ideas, last_err).
    Distinct step so the optional V4 Pro polish pass has clean input."""
    user_prompt = (
        f"Today is {idea_date}. Election day is 2026-11-03."
        "\n\nTODAY'S HEADLINES:\n" +
        ("\n".join(headlines[:40]) if headlines else "(no headlines fetched)") +
        "\n\nRAW IDEAS FED IN TODAY:\n" +
        ("\n".join(raw_lines) if raw_lines else "(none)") +
        "\n\nMN SENATE RACE (real published data, do not alter): Peggy "
        "Flanagan (D) vs Michele Tafoya (R); recent September polls have it "
        "a toss-up, RCP average Flanagan +1.6."
        "\n\nReturn EXACTLY 4 magausnavyvet style contrasts as a JSON array."
    )

    ideas = []
    last_err = None
    for attempt in (1, 2):
        try:
            log(f"calling Sonic ({SONIC_MODEL}), attempt {attempt}...")
            reply = sonic_chat(SYSTEM_PROMPT, user_prompt)
            ideas = extract_json_array(reply)[:4]
            if ideas:
                break
            last_err = "model returned empty idea list"
        except Exception as e:
            last_err = e
            log(f"Sonic attempt {attempt} failed: {e}")
        if attempt == 1:
            log("retrying in 60s...")
            time.sleep(60)
    return ideas, last_err


def cmd_generate(args):
    idea_date = args.date or dt.date.today().isoformat()

    def log(msg):
        print(f"[{idea_date}] {msg}", flush=True)

    log("fetching RSS headlines...")
    headlines = fetch_rss_headlines()
    log(f"got {len(headlines)} headlines")

    try:
        raw = db_list(idea_date, kind="raw")
    except Exception as e:
        log(f"DB read failed ({e}) — continuing without raw ideas")
        raw = []
    raw_lines = [f"- {r[3]}" for r in raw]
    log(f"got {len(raw_lines)} raw ideas from the box")

    # STAGE 1: Sonic drafts
    drafts, last_err = synthesize_with_sonic(idea_date, headlines,
                                             raw_lines, log)

    if not drafts:
        # Never silently fail: dated fallback note + telegram, then stop.
        log(f"GENERATION FAILED after 2 attempts: {last_err}")
        write_ideas_file(idea_date, [], headlines, raw_lines,
                         failed=True, fail_reason=str(last_err))
        deliver_telegram(idea_date, [], failed=True)
        return []

    # STAGE 2: V4 Pro sharpens Sonic's drafts (active while the rental is
    # live; degrades gracefully to Sonic-only if it dries up again)
    ideas, sharpened = maybe_sharpen_with_v4pro(drafts)
    gen_tag = "sonic+v4pro" if sharpened else "sonic"
    if sharpened:
        log("finals sharpened by DeepSeek V4 Pro")

    if len(ideas) != 4:
        log(f"WARNING: model returned {len(ideas)} ideas, expected 4")

    ids = []
    for it in ideas:
        try:
            nid = db_add(
                headline=it.get("headline", "")[:300],
                angle=it.get("angle", ""),
                punchline=it.get("punchline", "")[:300],
                why=it.get("why_it_works", ""),
                sources=it.get("sources", ""),
                kind="final", status="new", idea_date=idea_date,
                metadata={"generator": gen_tag,
                          "heat": it.get("heat"),
                          "model": SONIC_MODEL +
                          (V4PRO_MODEL if sharpened else "")})
            ids.append(nid)
        except Exception as e:
            log(f"DB insert failed ({e}) — delivering from memory")
            break
    log(f"stored {len(ids)} finals: {ids}")

    # k11-native delivery paths (no Hatch needed)
    write_ideas_file(idea_date, ideas, headlines, raw_lines)
    deliver_telegram(idea_date, ideas)

    for i, it in enumerate(ideas, 1):
        print(f"\n{i}. {it.get('headline', '')}")
        print(f"   {it.get('punchline', '')}")
    return ids


def cmd_export(args):
    idea_date = args.date or dt.date.today().isoformat()
    rows = db_get_finals(idea_date)
    if not rows:
        print(f"No final ideas for {idea_date}.")
        return
    print(f"Political meme ideas for {idea_date} — pick one (or more):\n")
    for i, (_id, headline, angle, punchline, why, sources) in enumerate(rows, 1):
        print(f"{i}. {headline}")
        if angle:
            print(f"   Angle: {angle}")
        if punchline:
            print(f"   Punchline: \"{punchline}\"")
        if why:
            print(f"   Why: {why}")
        print()


def main():
    ap = argparse.ArgumentParser(description="Meme idea box")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="insert an idea")
    a.add_argument("--headline", required=True)
    a.add_argument("--angle", default="")
    a.add_argument("--punchline", default="")
    a.add_argument("--why", default="")
    a.add_argument("--sources", default="")
    a.add_argument("--kind", default="raw", choices=["raw", "final"])
    a.add_argument("--date", default=None)
    a.add_argument("--status", default="new")

    l = sub.add_parser("list", help="list ideas")
    l.add_argument("--date", default=None)
    l.add_argument("--kind", default=None, choices=["raw", "final"])

    g = sub.add_parser("generate", help="generate tonight's 4 finals")
    g.add_argument("--date", default=None)

    e = sub.add_parser("export", help="print today's finals, chat-ready")
    e.add_argument("--date", default=None)

    args = ap.parse_args()
    if args.cmd == "add":
        nid = db_add(args.headline, args.angle, args.punchline, args.why,
                     args.sources, kind=args.kind, idea_date=args.date,
                     status=args.status)
        print(f"added id={nid}")
    elif args.cmd == "list":
        for r in db_list(args.date, args.kind):
            print(f"{r[0]} [{r[1]}/{r[2]}] {r[3]}")
    elif args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "export":
        cmd_export(args)


if __name__ == "__main__":
    main()
