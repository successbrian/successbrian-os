#!/usr/bin/env python3
"""refine_intake.py — dedupe + group raw intake into briefing items.

PURPOSE
    The refine pass between intake_items and briefing_items. Brian 2026-09-27:
    "refine it not reduce it. deduping is important, or grouping things
    similar." Raw drops land in public.intake_items; this worker merges
    near-duplicates and clusters similar items into single briefing_items
    rows so the Sunday briefing (and Altair) sees groups, not noise.

WHAT "REFINE" MEANS (not lossy reduction)
    1. DEDUPE: exact/near duplicates (same alert re-firing, same offer
       re-notified, same story from 2 phones) merge into ONE briefing item.
    2. GROUP: similar items cluster under one briefing item (4 eBay price
       drops -> one group). Members are listed, not summarized away.
    3. NOTHING LOST: intake rows are marked refined (refined_at), never
       deleted. Every briefing item traces back to its source intake ids
       via refined_briefing_item_id + a merged-ids note in the detail.

HOW
    - Deterministic pre-pass first: same dedup_key (phone notifications),
      or same (source, title, sender) -> merged without any model.
    - Ambiguous remainder -> Morpheus (Qwen 2.5 14B, :11437) for similarity
      judgments, structured JSON in/out ONLY. The 14B classifies and
      clusters; it never invents content (anti-confabulation rule).
    - Parse/validation failure -> everything falls through as orphans
      (individual briefing items). Fail-safe: nothing is dropped.

CALLED BY
    - Humans / driver agents: --run, --dry-run, --status
    - (future: the intake cadence cron Brian hasn't scheduled yet)

NOTES
    - Idempotent: WHERE refined_at IS NULL. Re-running skips processed ids.
    - This is NOT a relevance filter: orphans pass through as individual
      briefing items. Relevance scoring is intake_triage.py's job.
    - Adds 3 columns to intake_items on first run (additive migration):
      refined_at, refined_briefing_item_id, refined_note.
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

KSSH = Path.home() / "workspace" / "bin" / "kssh"
MORPHEUS_URL = "http://localhost:11437/v1/chat/completions"

CATEGORIES = ("operational", "blog_idea", "build_idea",
              "ecosystem_knowledge", "decision")
SOURCE_TAG = "intake-refine"


def pg_exec(sql: str, timeout: int = 60) -> str:
    b64 = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    out = subprocess.run(
        [str(KSSH), "psql -h localhost -U successbrian -d ecosystem_central "
                    f"-t -A -c \"$(echo {b64} | base64 -d)\""],
        capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def esc(s: str) -> str:
    return s.replace("'", "''")


def ensure_migration() -> None:
    pg_exec("ALTER TABLE public.intake_items "
            "ADD COLUMN IF NOT EXISTS refined_at timestamptz;")
    pg_exec("ALTER TABLE public.intake_items "
            "ADD COLUMN IF NOT EXISTS refined_briefing_item_id integer;")
    pg_exec("ALTER TABLE public.intake_items "
            "ADD COLUMN IF NOT EXISTS refined_note text;")


def fetch_unrefined(source: str | None = None) -> list[dict]:
    filt = f"AND source = '{esc(source)}' " if source else ""
    rows = pg_exec(
        "SELECT id, source, source_id, title, sender, url, "
        "coalesce(raw->>'dedup_key',''), "
        "to_char(received_at,'YYYY-MM-DD HH24:MI') "
        "FROM public.intake_items WHERE refined_at IS NULL "
        f"{filt}ORDER BY received_at ASC;")
    items = []
    for line in rows.splitlines():
        if not line.strip():
            continue
        p = line.split("|", 7)
        items.append({
            "id": int(p[0]), "source": p[1], "source_id": p[2] or None,
            "title": p[3] or "", "sender": p[4] or "", "url": p[5] or None,
            "dedup_key": p[6] or None, "received_at": p[7],
        })
    return items


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def deterministic_groups(items: list[dict]):
    """Exact-match pass. Returns (groups, remainder).

    groups: list of dicts {title, category, member_ids, rationale,
    deterministic: True}. Two items merge when they share a dedup_key
    (phone notification identity) or identical (source, title, sender).
    """
    buckets: dict[str, list[dict]] = {}
    for it in items:
        if it["dedup_key"]:
            key = "dk:" + it["dedup_key"]
        else:
            key = "tss:%s|%s|%s" % (norm(it["source"]), norm(it["title"]),
                                    norm(it["sender"]))
        buckets.setdefault(key, []).append(it)
    groups, remainder = [], []
    for key, members in buckets.items():
        if len(members) > 1:
            rep = members[0]
            groups.append({
                "title": rep["title"] or f"{rep['source']} alert",
                "category": "operational",
                "member_ids": [m["id"] for m in members],
                "rationale": ("exact duplicate "
                              f"({len(members)} identical drops)"),
                "deterministic": True,
            })
        else:
            remainder.append(members[0])
    return groups, remainder


SYSTEM_PROMPT = (
    "You are a clustering classifier for a notification intake queue. "
    "Output ONLY a JSON object, no prose, no markdown fences, no commentary. "
    "Schema: {\"groups\": [{\"title\": string, \"category\": string, "
    "\"member_ids\": [int], \"rationale\": string}], \"orphans\": [int]}. "
    "Category must be one of: operational, blog_idea, build_idea, "
    "ecosystem_knowledge, decision. "
    "Rules: use ONLY the item ids given below. Never invent ids, titles, "
    "senders, or content. Group items that describe the same underlying "
    "story, offer, or alert (e.g. several price-drop alerts -> one group; "
    "several affiliate offers in one niche -> one group). Each id appears "
    "in exactly one group or in orphans, never both. Items that fit no "
    "group go in orphans. Keep group titles short and factual, derived "
    "from the member titles. rationale is one short sentence."
)


def morpheus_cluster(items: list[dict]) -> dict:
    """Ask Morpheus to cluster. Returns {groups, orphans}; on any failure
    returns everything as orphans (fail-safe, nothing lost)."""
    if not items:
        return {"groups": [], "orphans": []}
    compact = [{"id": it["id"], "source": it["source"],
                "title": it["title"], "sender": it["sender"]}
               for it in items]
    payload = {
        "model": "morpheus",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content":
             "Cluster these intake items:\n" + json.dumps(compact)},
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    try:
        out = subprocess.run(
            [str(KSSH),
             f"echo {b64} | base64 -d | curl -s -m 300 "
             f"{MORPHEUS_URL} -H 'Content-Type: application/json' -d @-"],
            capture_output=True, text=True, timeout=330,
        )
        data = json.loads(out.stdout)
        text = data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"morpheus call failed ({e}); falling back to orphans",
              file=sys.stderr)
        return {"groups": [], "orphans": [it["id"] for it in items]}

    parsed = _extract_json(text)
    if parsed is None:
        # one retry with a nudge, then fail-safe
        try:
            payload["messages"].append(
                {"role": "user",
                 "content": "That was not valid JSON. Reply with ONLY the "
                            "JSON object, nothing else."})
            b64 = base64.b64encode(json.dumps(payload).encode()).decode()
            out = subprocess.run(
                [str(KSSH),
                 f"echo {b64} | base64 -d | curl -s -m 300 "
                 f"{MORPHEUS_URL} -H 'Content-Type: application/json' -d @-"],
                capture_output=True, text=True, timeout=330,
            )
            data = json.loads(out.stdout)
            text = data["choices"][0]["message"]["content"]
            parsed = _extract_json(text)
        except Exception as e:
            print(f"morpheus retry failed ({e}); falling back to orphans",
                  file=sys.stderr)
    if parsed is None:
        return {"groups": [], "orphans": [it["id"] for it in items]}
    return _validate(parsed, items)


def _extract_json(text: str):
    text = text.strip()
    # strip markdown fences if the model added them despite instructions
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _validate(parsed: dict, items: list[dict]) -> dict:
    """Force every input id to appear exactly once; drop anything the
    model invented. Returns {groups, orphans}."""
    valid_ids = {it["id"] for it in items}
    by_id = {it["id"]: it for it in items}
    seen: set[int] = set()
    groups = []
    for g in parsed.get("groups", []) or []:
        members = [i for i in (g.get("member_ids") or [])
                   if isinstance(i, int) and i in valid_ids and i not in seen]
        if len(members) < 2:
            continue  # singletons are orphans, not groups
        seen.update(members)
        cat = g.get("category") if g.get("category") in CATEGORIES \
            else "operational"
        title = str(g.get("title") or "")[:200] or "grouped items"
        groups.append({
            "title": title,
            "category": cat,
            "member_ids": members,
            "rationale": str(g.get("rationale") or "")[:300],
            "deterministic": False,
        })
    orphans = [i for i in (parsed.get("orphans") or [])
               if isinstance(i, int) and i in valid_ids and i not in seen]
    seen.update(orphans)
    # anything the model dropped entirely -> orphan (nothing lost)
    for i in valid_ids - seen:
        orphans.append(i)
    # keep orphan order stable by id
    orphans.sort(key=lambda i: by_id[i]["received_at"])
    return {"groups": groups, "orphans": orphans}


def build_detail(title: str, members: list[dict], rationale: str,
                 deterministic: bool) -> str:
    lines = [f"Refined from {len(members)} intake item(s).",
             f"Rationale: {rationale}" if rationale else None,
             ""]
    lines = [ln for ln in lines if ln is not None]
    for m in members:
        who = f" ({m['sender']})" if m["sender"] else ""
        lines.append(f"- [intake #{m['id']}] {m['title']}{who}")
    lines.append(f"Merged intake ids: {', '.join(str(m['id']) for m in members)}")
    if deterministic:
        lines.append("Merge method: exact deterministic match (no model).")
    return "\n".join(lines)


def write_results(plan: dict, by_id: dict, dry_run: bool) -> list[tuple]:
    """Insert briefing_items rows, mark intake rows refined. Returns
    list of (briefing_item_id_or_None, kind, title, member_ids)."""
    results = []
    jobs = []
    for g in plan["groups"]:
        jobs.append(("group", g["title"], g["category"], g["member_ids"],
                     g["rationale"], g.get("deterministic", False)))
    for oid in plan["orphans"]:
        it = by_id[oid]
        jobs.append(("orphan", it["title"] or f"{it['source']} item",
                     "operational", [oid], "no similar items", False))

    for kind, title, category, member_ids, rationale, det in jobs:
        members = [by_id[i] for i in member_ids]
        detail = build_detail(title, members, rationale, det)
        if dry_run:
            results.append((None, kind, title, member_ids))
            continue
        row = pg_exec(
            "INSERT INTO briefing_items (source, category, title, detail, "
            "priority) VALUES "
            f"('{SOURCE_TAG}', '{category}', '{esc(title[:200])}', "
            f"'{esc(detail)}', 'medium') RETURNING id;").splitlines()[0]
        bid = int(row)
        ids = ",".join(str(i) for i in member_ids)
        note = ("exact-duplicate merge" if det and kind == "group"
                else ("group: " + title[:120] if kind == "group"
                      else "orphan passthrough"))
        pg_exec(
            "UPDATE public.intake_items SET refined_at = now(), "
            f"refined_briefing_item_id = {bid}, "
            f"refined_note = '{esc(note)}' WHERE id IN ({ids});")
        results.append((bid, kind, title, member_ids))
    return results


def cmd_status() -> int:
    ensure_migration()
    rows = pg_exec(
        "SELECT count(*) FILTER (WHERE refined_at IS NULL), "
        "count(*) FILTER (WHERE refined_at IS NOT NULL), count(*) "
        "FROM public.intake_items;")
    unref, refd, total = rows.split("|")
    print(f"intake_items: total={total} refined={refd} unrefined={unref}")
    rows = pg_exec(
        "SELECT count(*) FROM briefing_items WHERE consumed_at IS NULL "
        f"AND source = '{SOURCE_TAG}';")
    print(f"briefing_items from intake-refine pending: {rows}")
    return 0


def run_refine(dry_run: bool, source: str | None = None) -> int:
    ensure_migration()
    items = fetch_unrefined(source)
    if not items:
        print("nothing unrefined — queue is clean")
        return 0
    by_id = {it["id"]: it for it in items}
    print(f"{len(items)} unrefined intake item(s)")

    det_groups, remainder = deterministic_groups(items)
    print(f"deterministic pass: {len(det_groups)} duplicate group(s), "
          f"{len(remainder)} item(s) to the 14B")
    for g in det_groups:
        print(f"  [exact] {g['title'][:70]} <- {g['member_ids']}")

    model_plan = morpheus_cluster(remainder)
    plan = {"groups": det_groups + model_plan["groups"],
            "orphans": model_plan["orphans"]}
    n_in = len(items)
    n_out = len(plan["groups"]) + len(plan["orphans"])
    print(f"14B pass: {len(model_plan['groups'])} group(s), "
          f"{len(model_plan['orphans'])} orphan(s)")
    for g in model_plan["groups"]:
        print(f"  [14B] {g['title'][:70]} <- {g['member_ids']} "
              f"({g['rationale'][:60]})")
    print(f"refine plan: {n_in} intake -> {n_out} briefing item(s)")

    if dry_run:
        print("DRY RUN — no writes")
        return 0
    results = write_results(plan, by_id, dry_run=False)
    for bid, kind, title, mids in results:
        print(f"  wrote briefing #{bid} [{kind}] {title[:70]} <- {mids}")
    # verify nothing lost
    left = pg_exec("SELECT count(*) FROM public.intake_items "
                   "WHERE refined_at IS NULL;")
    print(f"unrefined remaining: {left} (want 0 for this batch)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Refine pass: dedupe + group intake_items -> "
                    "briefing_items.")
    p.add_argument("--run", action="store_true",
                   help="refine all unprocessed intake items")
    p.add_argument("--dry-run", action="store_true",
                   help="show the refine plan without writing")
    p.add_argument("--status", action="store_true",
                   help="queue counts")
    p.add_argument("--source", default=None,
                   help="only refine intake rows from this source "
                        "(e.g. --source refine-test)")
    a = p.parse_args()
    if a.status:
        return cmd_status()
    if a.dry_run:
        return run_refine(dry_run=True, source=a.source)
    if a.run:
        return run_refine(dry_run=False, source=a.source)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
