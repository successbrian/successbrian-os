#!/usr/bin/env python3
"""
PURPOSE:
    Fan-out dispatcher for discovered people/deal data ("people intake").
    Takes one normalized discovery JSON and writes it to every sink that
    exists: people.people, dealsdesk.sightings, knowledge_bridge->dealsdesk,
    second_brain (optional), markdown people pages (optional, Hatch runs).

WHY:
    When a pipeline (scraper, contact watcher, Messenger scan) or a chat
    discovers a person plus context and deals, the connections used to be
    made by hand: a memory page here, a knowledge_bridge row to dealsdesk
    there. Miss one and the data goes stale in a silo. This makes the
    fan-out deterministic and idempotent so every discovery lands in all
    the right databases and tools.

CALLED BY:
    - pipelines on k11 (contact_watcher, scrapers, messenger scans) via cron
    - manual intake: python3 dispatch.py --file discovery.json [--learn] [--write-md DIR]

NOTES:
    - Idempotent: person upsert keyed on slug; sightings deduped on
      (person_id, item) while status='spotted'; knowledge_bridge rows are
      append-only by design (one row per dispatch with deals).
    - Sinks whose tables don't exist yet are SKIPPED with a report line,
      not an error — graceful degradation until the DDL lands.
    - knowledge_bridge rows go to dealsdesk ONLY when the discovery has deals.
    - Never deletes anything. Dry-run with --dry-run.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

DB = os.environ.get("SBOS_DB", "ecosystem_central")


def lit(s):
    """Quote a string as a Postgres dollar-quoted literal."""
    if s is None:
        return "NULL"
    s = str(s)
    assert "$$" not in s, "dollar-quote collision"
    return "$$" + s + "$$"


def jlit(obj):
    return lit(json.dumps(obj if obj is not None else [])) + "::jsonb"


def psql(sql):
    r = subprocess.run(
        ["psql", "-d", DB, "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + r.stderr.strip()[:500])
    return r.stdout.strip()


def table_exists(schema, table):
    out = psql(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=%s "
        "AND table_name=%s LIMIT 1;" % (lit(schema), lit(table)))
    return out == "1"


def slugify(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def upsert_person(d, slug):
    sql = (
        "INSERT INTO people.people "
        "(slug, display_name, first_name, last_name, summary, facts, history, "
        "relationship, in_common, open_threads, source, source_ref, rank, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
        "ON CONFLICT (slug) DO UPDATE SET "
        "display_name=EXCLUDED.display_name, summary=EXCLUDED.summary, "
        "facts=EXCLUDED.facts, history=people.people.history || EXCLUDED.history, "
        "relationship=EXCLUDED.relationship, in_common=EXCLUDED.in_common, "
        "open_threads=EXCLUDED.open_threads, source=EXCLUDED.source, "
        "source_ref=EXCLUDED.source_ref, updated_at=now() "
        "RETURNING id;" % (
            lit(slug), lit(d["name"]), lit(d.get("first_name")),
            lit(d.get("last_name")), lit(d.get("summary")),
            jlit(d.get("facts")), jlit(d.get("history")),
            lit(d.get("relationship")), jlit(d.get("in_common")),
            jlit(d.get("open_threads")), lit(d.get("source")),
            lit(d.get("source_ref")), d.get("rank") or "NULL"))
    return int(psql(sql))


def insert_sighting(person_id, deal, source):
    dup = psql(
        "SELECT id FROM dealsdesk.sightings WHERE person_id=%d "
        "AND item=%s AND status='spotted' LIMIT 1;" % (person_id, lit(deal["item"])))
    if dup:
        return int(dup), False
    new_id = psql(
        "INSERT INTO dealsdesk.sightings (person_id, item, detail, status, source) "
        "VALUES (%d,%s,%s,'spotted',%s) RETURNING id;" % (
            person_id, lit(deal["item"]), jlit(deal.get("detail")),
            lit(source)))
    return int(new_id), True


def kb_to_dealsdesk(message, urgency="routine"):
    return int(psql(
        "INSERT INTO public.knowledge_bridge "
        "(source_agent, target_agent, message, urgency) "
        "VALUES ('people_intake','dealsdesk',%s,%s) RETURNING id;"
        % (lit(message), lit(urgency))))


def learn(topic, content, tags):
    return int(psql(
        "INSERT INTO public.second_brain "
        "(topic, category, content, confidence, source, verification, tags) "
        "VALUES (%s,'intake',%s,'high','people_intake','dispatched discovery',%s) "
        "RETURNING id;" % (lit(topic), lit(content), lit("{%s}" % ",".join(tags)))))


def render_md(d, slug, outdir):
    lines = ["---",
             "display_name: %s" % d["name"],
             "first_name: %s" % (d.get("first_name") or ""),
             "last_name: %s" % (d.get("last_name") or ""),
             "summary: %s" % (d.get("summary") or ""),
             "rank: %s" % (d.get("rank") or 60),
             "updated: %s" % date.today().isoformat(),
             "---", "",
             "# %s" % d["name"], "",
             "## Facts"]
    lines += ["- %s" % f for f in (d.get("facts") or [])]
    lines += ["", "## History"]
    lines += ["- %s" % h for h in (d.get("history") or [])]
    lines += ["", "## The relationship", d.get("relationship") or "", "",
              "## In common"]
    lines += ["- %s" % c for c in (d.get("in_common") or [])]
    lines += ["", "## Open threads"]
    lines += ["- %s" % t for t in (d.get("open_threads") or [])]
    lines += ["", "## Strengthening", ""]
    path = os.path.join(outdir, slug + ".md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="discovery JSON file")
    ap.add_argument("--learn", action="store_true", help="also write second_brain")
    ap.add_argument("--write-md", metavar="DIR", help="also render md people page (Hatch runs)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.file) as f:
        d = json.load(f)
    slug = d.get("slug") or slugify(d["name"])
    deals = d.get("deals") or []
    report = {"slug": slug, "dry_run": args.dry_run, "sinks": {}}

    have_people = table_exists("people", "people")
    have_sightings = table_exists("dealsdesk", "sightings")
    report["sinks"]["people.people"] = "ok" if have_people else "skipped (no table)"
    report["sinks"]["dealsdesk.sightings"] = "ok" if have_sightings else "skipped (no table)"
    report["sinks"]["knowledge_bridge->dealsdesk"] = "ok" if deals else "skipped (no deals)"
    report["sinks"]["second_brain"] = "ok" if args.learn else "skipped (no --learn)"
    report["sinks"]["md_page"] = "ok" if args.write_md else "skipped (no --write-md)"

    if args.dry_run:
        report["would_write"] = {
            "person": d["name"],
            "deals": [x["item"] for x in deals],
        }
        print(json.dumps(report, indent=2))
        return

    person_id = None
    if have_people:
        person_id = upsert_person(d, slug)
        report["person_id"] = person_id
    if have_sightings and person_id:
        report["sighting_ids"] = []
        for deal in deals:
            sid, created = insert_sighting(person_id, deal, d.get("source"))
            if created:
                report["sighting_ids"].append(sid)
    if deals:
        lines = ["People-intake discovery %s: %s" % (date.today().isoformat(), d["name"]),
                 "Source: %s %s" % (d.get("source"), d.get("source_ref") or "")]
        for deal in deals:
            det = deal.get("detail") or {}
            lines.append("- %s | %s" % (deal["item"], json.dumps(det)))
        if d.get("open_threads"):
            lines.append("Open: " + "; ".join(d["open_threads"]))
        lines.append("Pricing research only — no contact without Brian's go-ahead.")
        report["kb_id"] = kb_to_dealsdesk("\n".join(lines))
    if args.learn:
        report["brain_id"] = learn(
            d.get("learn_topic") or ("intake: " + d["name"]),
            d.get("learn_content") or d.get("summary") or "",
            d.get("learn_tags") or ["intake"])
    if args.write_md:
        report["md_path"] = render_md(d, slug, args.write_md)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
