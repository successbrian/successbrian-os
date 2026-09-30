#!/usr/bin/env python3
"""Morpheus listing vet: second pair of eyes on DealsDesk deal candidates.

PURPOSE: A rules engine flags ~hundreds of listings as STEAL / EXCELLENT_DEAL /
    SNATCH / GREAT_DEAL. Rules are blind to deception: an I/O shield listed as
    a "motherboard", a caddy listed as a "hard drive", a dropdown scam priced
    as a hot deal, a wildly wrong market_value. Morpheus reads the listing
    text and flags what the scorer got wrong - free, local, zero AI credits.
WHY: Brian 2026-09-30: "this isn't a motherboard, it's an I/O shield. this
    isn't a hard drive, it's a hard drive caddy. this is a drop down scam,
    not a hot deal. this one the market value is not right."
CALLED BY: Hermes --no-agent cron job dealsdesk-listing-vet on the dealsdesk
    profile, every 4 hours (17 */4 * * * - offset from the 4hr sweep).
NOTES:
    - CANONICAL SOURCE: successbrian-os/tools/dealsdesk/listing_vet.py
    - DEPLOYED COPY: /home/successbrian/.hermes/profiles/dealsdesk/scripts/listing_vet.py
    - Reads marketplace_listings (top 4 deal tiers, not yet vetted). Vets in
      batches of 6 per Morpheus call. Marks deal_flags->'vet' so each listing
      is vetted once; also sets ai_processed=true / ai_processed_at.
    - The vet FLAGS, it does not re-tier: a FLAG lands in deal_flags and the
      run summary; deal_tier is never changed by this script (that stays a
      pipeline/Brian decision).
    - Quiet unless something is flagged: a run with zero flags only updates
      the state heartbeat. Summary bridge rows: sender='dealsdesk',
      target='spencer', urgency=routine.
    - Pricing-data policy: all output stays inside the ecosystem (DB flags +
      bridge rows). Nothing publishable is generated.
    - Honest limit: the vet sees title + price + claimed market_value +
      body_text. Dropdown scams whose variant table isn't in the text may
      slip through; title/description mismatches are its strength.
"""
import json, os, subprocess, urllib.request
from datetime import datetime

MORPHEUS_URL = "http://127.0.0.1:11437/v1/chat/completions"
PG = {"host": "localhost", "dbname": "ecosystem_central",
      "user": "successbrian", "password": "postgres"}
STATE_FILE = "/home/successbrian/.hermes/profiles/dealsdesk/state/listing_vet_state.json"
TIERS = ["STEAL", "EXCELLENT_DEAL", "SNATCH", "GREAT_DEAL"]
PER_RUN = 60
BATCH = 6


def _pg(query, args=()):
    """Read via psycopg2, fall back to psql (venv python lacks psycopg2)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            "host=%s dbname=%s user=%s password=%s connect_timeout=10" % (
                PG["host"], PG["dbname"], PG["user"], PG["password"]))
        cur = conn.cursor()
        cur.execute(query, args)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows, True
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    q = query
    for a in args:
        q = q.replace("%s", "'%s'" % str(a).replace("'", "''"), 1)
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-F", "\x1f", "-c", q],
                       capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:200])
    return [[c for c in ln.split("\x1f")] for ln in r.stdout.splitlines()
            if ln.strip()], False


def _pg_write(query, args=()):
    try:
        import psycopg2
        conn = psycopg2.connect(
            "host=%s dbname=%s user=%s password=%s connect_timeout=10" % (
                PG["host"], PG["dbname"], PG["user"], PG["password"]))
        cur = conn.cursor()
        cur.execute(query, args)
        conn.commit()
        n = cur.rowcount
        cur.close(); conn.close()
        return n
    except ImportError:
        pass
    env = dict(os.environ, PGPASSWORD=PG["password"])
    q = query
    for a in args:
        q = q.replace("%s", "'%s'" % str(a).replace("'", "''"), 1)
    r = subprocess.run(["psql", "-h", PG["host"], "-U", PG["user"],
                        "-d", PG["dbname"], "-t", "-A", "-c", q],
                       capture_output=True, text=True, env=env, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr[:200])
    return None


def fetch_candidates():
    rows, _ = _pg(
        """SELECT id, title, price, market_value, deal_tier,
                  left(COALESCE(body_text,''), 1500)
           FROM marketplace_listings
           WHERE status='active' AND deal_tier = ANY(%s)
             AND NOT (COALESCE(deal_flags,'{}'::jsonb) ? 'vet')
           ORDER BY array_position(%s::text[], deal_tier), id DESC
           LIMIT %s""", (TIERS, TIERS, PER_RUN))
    out = []
    for r in rows:
        out.append({"id": int(r[0]), "title": r[1], "price": r[2],
                    "market_value": r[3], "tier": r[4], "body": r[5] or ""})
    return out


def vet_batch(items):
    listing_text = ""
    for it in items:
        listing_text += (
            "\n--- id=%d | tier=%s | price=%s | market_value=%s\n"
            "TITLE: %s\nDESC: %s\n" % (
                it["id"], it["tier"], it["price"], it["market_value"],
                it["title"], it["body"][:1200]))
    prompt = (
        "You vet eBay/hardware listings a rules engine flagged as deals. "
        "For each listing reply with exactly one line:\n"
        "<id>: PASS | FLAG: <short reason>\n\n"
        "FLAG when:\n"
        "- TITLE/ITEM MISMATCH: the actual item is a part or accessory, not "
        "what the title claims. E.g. 'motherboard' that is only the I/O "
        "shield; 'hard drive' that is only the caddy/tray; 'server' that is "
        "a bare chassis. Sellers bury the truth in the description - read it.\n"
        "- DROPDOWN SCAM: the displayed price is for a cheaper variant in a "
        "dropdown; the pictured/described item costs more. Signs: price far "
        "below market for the described item, variant/option lists.\n"
        "- MARKET VALUE WRONG: the claimed market_value is wildly off for "
        "what the item actually is (2x or more) - obvious errors only.\n"
        "- OTHER DECEPTION: 'for parts' hidden in text, quantity tricks, "
        "counterfeit signs.\n\n"
        "Do NOT flag: honestly described used/refurbished items; 'for parts' "
        "clearly stated; bulk lots where the math roughly works. When unsure, "
        "PASS - your price knowledge may be stale, so market-value flags are "
        "for obvious errors only.\n"
        "Listings:\n" + listing_text)
    req = urllib.request.Request(
        MORPHEUS_URL,
        data=json.dumps({"model": "morpheus",
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 600, "stream": False,
                         "temperature": 0.2}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"]


def parse_verdicts(text):
    """Returns {id: (verdict, reason)}."""
    res = {}
    for ln in text.splitlines():
        s = ln.strip().lstrip("-* ").strip()
        if ":" not in s:
            continue
        head, rest = s.split(":", 1)
        try:
            lid = int("".join(c for c in head if c.isdigit()))
        except ValueError:
            continue
        rest = rest.strip()
        if rest.upper().startswith("FLAG"):
            reason = rest[4:].lstrip(": ").strip()[:200] or "flagged"
            res[lid] = ("FLAG", reason)
        elif rest.upper().startswith("PASS"):
            res[lid] = ("PASS", "")
    return res


def record(item, verdict, reason):
    vet = json.dumps({"verdict": verdict, "reason": reason,
                      "by": "morpheus", "at": datetime.now().isoformat()})
    _pg_write(
        """UPDATE marketplace_listings
           SET ai_processed=true, ai_processed_at=now(),
               deal_flags = COALESCE(deal_flags,'{}'::jsonb) || %s::jsonb
           WHERE id=%s""", (json.dumps({"vet": json.loads(vet)}), item["id"]))


def bridge_insert(subject, body):
    _pg_write(
        """INSERT INTO altair.knowledge_bridge
           (sender, target, subject, body, urgency)
           VALUES ('dealsdesk','spencer',%s,%s,'routine')""",
        (subject, body))


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump(state, open(STATE_FILE, "w"))
    except Exception:
        pass


def main():
    state = {}
    try:
        if os.path.exists(STATE_FILE):
            state = json.load(open(STATE_FILE))
    except Exception:
        pass
    cands = fetch_candidates()
    state["last_run"] = datetime.now().isoformat()
    state["candidates_seen"] = len(cands)
    if not cands:
        state["note"] = "no unvetted deal-tier listings"
        save_state(state)
        print("vet: nothing to vet")
        return
    flagged = []
    for i in range(0, len(cands), BATCH):
        batch = cands[i:i + BATCH]
        try:
            text = vet_batch(batch)
        except Exception as e:
            print("vet: morpheus call failed on batch %d: %s" %
                  (i // BATCH, str(e)[:120]))
            continue
        verdicts = parse_verdicts(text)
        for it in batch:
            v, reason = verdicts.get(it["id"], ("PASS", ""))
            try:
                record(it, v, reason)
            except Exception as e:
                print("vet: record failed for %d: %s" % (it["id"], str(e)[:100]))
            if v == "FLAG":
                flagged.append((it, reason))
    state["last_flags"] = len(flagged)
    save_state(state)
    print("vet: %d vetted, %d flagged" % (len(cands), len(flagged)))
    if flagged:
        lines = ["- [%s] %s ($%s, claimed MV $%s): %s" %
                 (it["tier"], it["title"][:90], it["price"],
                  it["market_value"], reason)
                 for it, reason in flagged[:15]]
        bridge_insert(
            "[vet] %d listings flagged by Morpheus" % len(flagged),
            "Morpheus listing vet (%s):\n\n%s\n\n"
            "Flags recorded in marketplace_listings.deal_flags->'vet'; "
            "deal_tier unchanged (review before re-tiering)." % (
                datetime.now().strftime("%Y-%m-%d %H:%M"), "\n".join(lines)))


if __name__ == "__main__":
    main()
