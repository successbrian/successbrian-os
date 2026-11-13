#!/usr/bin/env python3
"""standing_compile.py - Standing compile v1, piece 1 (BUILD_QUEUE B15-1).

Per money line (GotBackup 40/mo, TrafficStreemz $30, ContactFlowCRM $20,
the ~$1k/30-day stranger track) compile visits -> contacts -> revenue
from the live record into one REAP packet per line (the B2 feeder-packet
standard: <=500 max_tokens, facts whole, provenance fields), and file
each compile to successbrian_os.knowledge_index with kind='compile'
(the B6 residue contract - residue_inventory.py reads that kind, so a
filed compile lights up the decision stream automatically).

Honesty rules, enforced in code, not prose:
  - A leg with no live source is UNKNOWN / OWED, never zero and never
    invented. blog_scorecards rows with NULL metrics are UNMEASURED,
    not zero; money_flow sums of $0.00 are recorded $0, a different
    fact from unmeasured.
  - Contacts per line are a tag/name MATCH count against the dealsdesk
    pool, labelled as such - there is no per-line attribution column,
    so no per-line contact count is claimed.
  - Targets are STATED targets (Brian's rulings as recorded in the
    queue item), cited as stated, never as measured goal rows.
  - One row per line per Chicago date: canonical_id
    ki:compile-<line>-<YYYY-MM-DD>; re-runs the same day land nothing
    new (ON CONFLICT DO NOTHING).

REAP dispatch is B15-2, not here: this piece builds the packet and
files the compile. The packet prompt is stored in doc_text with its
probe_id + token estimate in pointer_note, so dispatch can rebuild
the identical packet from the filed row.

Usage: standing_compile.py [--compile [--dry-run] [--line KEY]]
         [--status] [--selftest]
Plan: builds/sbos-assembly/PLAN.md Phase 5.
"""
import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sbos_common import (  # noqa: E402
    build_reap_packet,
    estimate_tokens,
    pg_exec,
    pg_one,
    pg_rows,
)

SCHEMA = "successbrian_os"
KI = f"{SCHEMA}.knowledge_index"
KIND = "compile"
CHICAGO = ZoneInfo("America/Chicago")
PROMPT_TOKEN_BUDGET = 2000  # B12b: reap prompt budget; over it is a blocker

# Money lines. target: Brian's STATED target (queue B15 / alignment
# record), cited as stated. revenue_categories: public.money_flow
# categories that belong to the line (verified live 2026-11-13).
# scorecard_blog: campaignsdesk.blog_scorecards blog_slug serving the
# line, or None when no scorecard blog is mapped to it.
LINES = {
    "gotbackup": {
        "name": "GotBackup",
        "target": "40 sponsorships/month (stated target)",
        "revenue_categories": [
            "gotbackup_personal_sales",
            "gotbackup_team_override",
            "gotbackup_lead_system",
            "affiliate_gotbackup",
            "gotbackup_training_products",
        ],
        "scorecard_blog": None,
        "contact_match": "gotbackup",
    },
    "trafficstreemz": {
        "name": "TrafficStreemz",
        "target": "$30/month, first (stated target)",
        "revenue_categories": [
            "saas_trafficstreemz",
            "trafficstreemz_affiliate",
            "incubator_trafficstreemz",
        ],
        "scorecard_blog": "trafficstreemz-blog",
        "contact_match": "trafficstreemz",
    },
    "contactflowcrm": {
        "name": "ContactFlowCRM",
        "target": "$20/month, second (stated target)",
        "revenue_categories": [
            "saas_contactflowcrm",
            "incubator_contactflowcrm",
        ],
        "scorecard_blog": None,
        "contact_match": "contactflowcrm",
    },
    "stranger-1k": {
        "name": "Stranger $1k track",
        "target": "~$1,000 in 30 days from strangers, ~$300/sale "
                  "(stated target)",
        "revenue_categories": [],
        "scorecard_blog": None,
        "contact_match": None,
    },
}


def today_chicago() -> str:
    return datetime.now(CHICAGO).strftime("%Y-%m-%d")


def gather(key: str) -> dict:
    """Read-only gather for one line. Numbers are live; gaps are None."""
    line = LINES[key]
    cats = line["revenue_categories"]
    if cats:
        rev30 = pg_one(
            "select coalesce(sum(amount), 0) from public.money_flow "
            "where category = any(%s) and date >= current_date - 30",
            (cats,))
        rev_all = pg_one(
            "select coalesce(sum(amount), 0) from public.money_flow "
            "where category = any(%s)", (cats,))
        rev_rows = pg_one(
            "select count(*) from public.money_flow "
            "where category = any(%s)", (cats,))
    else:
        rev30 = rev_all = None
        rev_rows = 0
    scorecard = None
    if line["scorecard_blog"]:
        rows = pg_rows(
            "select period_start, period_end, unique_visits, "
            "contacts_captured, revenue_cents from "
            "campaignsdesk.blog_scorecards where blog_slug = %s "
            "order by period_end desc limit 1", (line["scorecard_blog"],))
        if rows:
            ps, pe, uv, cc, rc = rows[0]
            scorecard = {
                "period_start": str(ps), "period_end": str(pe),
                "unique_visits": uv, "contacts_captured": cc,
                "revenue_cents": rc,
            }
    contacts = None
    if line["contact_match"]:
        m = line["contact_match"]
        contacts = pg_one(
            "select count(*) from dealsdesk.contacts where "
            "tags::text ilike %s or company_name ilike %s "
            "or notes ilike %s or source ilike %s",
            (f"%{m}%", f"%{m}%", f"%{m}%", f"%{m}%"))
    pool = pg_one("select count(*) from dealsdesk.contacts")
    goals = pg_rows(
        "select count(*), count(*) filter (where status = 'active') "
        "from public.goals where title ilike %s", (f"%{line['name']}%",))
    g_total, g_active = goals[0] if goals else (0, 0)
    return {
        "key": key, "name": line["name"], "target": line["target"],
        "revenue_30d": (float(rev30) if rev30 is not None else None),
        "revenue_all": (float(rev_all) if rev_all is not None else None),
        "revenue_rows": int(rev_rows or 0),
        "revenue_categories": cats,
        "scorecard": scorecard,
        "scorecard_blog": line["scorecard_blog"],
        "contacts_matched": (int(contacts) if contacts is not None
                             else None),
        "contacts_pool": int(pool or 0),
        "goals_total": int(g_total or 0),
        "goals_active": int(g_active or 0),
    }


def _money(v):
    return f"${v:,.2f}" if v is not None else "UNKNOWN"


def build_brief(g: dict, day: str) -> tuple[str, str, list[str]]:
    """Compile one line into (brief, one-line verdict, owed legs).

    Pure function of the gather dict - the selftest exercises it with
    an all-UNKNOWN gather to prove nothing is invented.
    """
    owed = []
    parts = [f"STANDING COMPILE - {g['name']} - {day}",
             f"Target (stated): {g['target']}."]
    if g["revenue_30d"] is None:
        parts.append("Revenue: UNKNOWN - no money_flow category mapped "
                     "to this line.")
        owed.append("revenue (no money_flow category)")
    else:
        parts.append(
            f"Revenue: {_money(g['revenue_30d'])} last 30d / "
            f"{_money(g['revenue_all'])} all-time across "
            f"{g['revenue_rows']} money_flow rows "
            f"(categories: {', '.join(g['revenue_categories'])}).")
    sc = g["scorecard"]
    if g["scorecard_blog"] is None:
        parts.append("Visits: UNKNOWN - no scorecard blog mapped to "
                     "this line.")
        owed.append("visits (no scorecard blog)")
        parts.append("Contacts: UNKNOWN - no scorecard blog; see "
                     "tag-match below.")
        owed.append("contacts (no scorecard blog)")
    elif sc is None:
        parts.append(f"Visits: UNKNOWN - scorecard blog "
                     f"{g['scorecard_blog']} has no scorecard row.")
        owed.append(f"visits (no {g['scorecard_blog']} row)")
        parts.append("Contacts: UNKNOWN - no scorecard row.")
        owed.append("contacts (no scorecard row)")
    else:
        if sc["unique_visits"] is None:
            parts.append(
                f"Visits: UNKNOWN - {g['scorecard_blog']} scorecard "
                f"{sc['period_start']}..{sc['period_end']} has NULL "
                f"unique_visits (UNMEASURED, not zero).")
            owed.append("visits (scorecard NULL)")
        else:
            parts.append(
                f"Visits: {sc['unique_visits']} uniques "
                f"({sc['period_start']}..{sc['period_end']}, "
                f"{g['scorecard_blog']}).")
        if sc["contacts_captured"] is None:
            parts.append(
                f"Contacts: UNKNOWN - {g['scorecard_blog']} scorecard "
                f"has NULL contacts_captured (UNMEASURED, not zero).")
            owed.append("contacts (scorecard NULL)")
        else:
            parts.append(f"Contacts: {sc['contacts_captured']} captured "
                         f"({sc['period_start']}..{sc['period_end']}).")
        if sc["revenue_cents"] is None:
            parts.append("Blog revenue: UNKNOWN - scorecard "
                         "revenue_cents NULL (UNMEASURED).")
            owed.append("blog revenue (scorecard NULL)")
        else:
            parts.append(f"Blog revenue: "
                         f"${sc['revenue_cents'] / 100:,.2f}.")
    if g["contacts_matched"] is None:
        parts.append("Tag-match contacts: n/a for this line.")
    else:
        parts.append(
            f"Tag-match contacts: {g['contacts_matched']} of "
            f"{g['contacts_pool']} dealsdesk contacts match "
            f"'{LINES[g['key']]['contact_match']}' in tags/company/notes/"
            f"source (MATCH, not attribution - no per-line column "
            f"exists).")
    parts.append(f"Goals: {g['goals_total']} matching goal rows "
                 f"({g['goals_active']} active).")
    if owed:
        parts.append("OWED: " + "; ".join(owed) + ".")
    else:
        parts.append("OWED: none - every leg measured.")
    brief = "\n".join(parts)
    verdict = (f"{g['name']}: revenue "
               f"{_money(g['revenue_30d'])} 30d / "
               f"{_money(g['revenue_all'])} all-time vs target "
               f"{g['target']}; visits "
               f"{'UNKNOWN' if (sc is None or sc['unique_visits'] is None) else str(sc['unique_visits'])}; "
               f"contacts "
               f"{'UNKNOWN' if (sc is None or sc['contacts_captured'] is None) else str(sc['contacts_captured'])}"
               + (f"; OWED: {', '.join(owed)}" if owed else "; fully measured"))
    return brief, verdict, owed


def build_packet_for(g: dict, day: str, brief: str) -> dict:
    """One B2-standard REAP packet for the line's compile."""
    canonical = f"ki:compile-{g['key']}-{day}"
    return build_reap_packet(
        brief, source="standing-compile",
        probe_id=f"standing-compile-{g['key']}-{day}",
        section="compile", item_ref=canonical)


def file_compile(g: dict, day: str, brief: str, verdict: str,
                 owed: list[str], packet: dict) -> int:
    """File one compile row. Returns 1 landed, 0 already present."""
    canonical = f"ki:compile-{g['key']}-{day}"
    title = f"Standing compile: {g['name']} - {day}"
    note = (f"standing_compile.py B15-1 | probe "
            f"{packet['probe_id']} | prompt ~"
            f"{estimate_tokens(brief)} tok (budget {PROMPT_TOKEN_BUDGET}) "
            f"| max_tokens {packet['max_tokens']} | sources: "
            f"public.money_flow, campaignsdesk.blog_scorecards, "
            f"dealsdesk.contacts, public.goals"
            + (f" | OWED: {', '.join(owed)}" if owed else
               " | OWED: none"))
    return pg_exec(
        f"""insert into {KI} (canonical_id, subject, title, kind,
               status, version, distilled, doc_text, pointer_note)
             values (%s, %s, %s, %s, 'current', 1, %s, %s, %s)
             on conflict (canonical_id) do nothing""",
        (canonical, title, title, KIND, verdict, brief, note))


def compile_lines(keys, dry: bool = False) -> dict:
    day = today_chicago()
    out = {"day": day, "landed": 0, "already": 0, "would_land": 0,
           "lines": {}}
    for key in keys:
        g = gather(key)
        brief, verdict, owed = build_brief(g, day)
        packet = build_packet_for(g, day, brief)
        est = estimate_tokens(brief)
        if est > PROMPT_TOKEN_BUDGET:
            raise ValueError(
                f"{key}: compile prompt ~{est} tok exceeds the "
                f"{PROMPT_TOKEN_BUDGET} prompt budget - split the line")
        if dry:
            already = pg_one(
                f"select count(*) from {KI} where canonical_id = %s",
                (f"ki:compile-{key}-{day}",))
            out["would_land" if not int(already or 0) else "already"] += 1
            out["lines"][key] = {"verdict": verdict, "owed": owed,
                                 "prompt_tokens": est,
                                 "already": bool(int(already or 0))}
            print(f"{key}: would land "
                  f"ki:compile-{key}-{day} (~{est} tok)"
                  + (" (already filed)" if int(already or 0) else ""))
            continue
        n = file_compile(g, day, brief, verdict, owed, packet)
        out["landed" if n == 1 else "already"] += 1
        out["lines"][key] = {"verdict": verdict, "owed": owed,
                             "prompt_tokens": est,
                             "landed": n == 1}
        print(f"{key}: {'landed' if n == 1 else 'already present'} "
              f"ki:compile-{key}-{day} (~{est} tok)")
    return out


def status() -> dict:
    total = pg_one(f"select count(*) from {KI} where kind = %s", (KIND,))
    rows = pg_rows(
        f"""select canonical_id, distilled, created_at from {KI}
             where kind = %s order by created_at desc limit 8""",
        (KIND,))
    oldest = pg_one(
        f"""select coalesce(min(created_at)::text, 'none') from {KI}
             where kind = %s""", (KIND,))
    print(f"compile rows: {total} (oldest {oldest})")
    for cid, verdict, at in rows:
        print(f"  {cid} [{at}] {verdict[:160]}")
    return {"total": int(total or 0), "rows": rows}


def selftest() -> None:
    steps = []

    # 1. Four lines, each with a stated target and honest categories.
    assert len(LINES) == 4, "four money lines"
    for k, v in LINES.items():
        assert v["target"].startswith(("40 ", "$30", "$20", "~$1")), \
            f"{k}: stated target present"
        assert isinstance(v["revenue_categories"], list), \
            f"{k}: revenue categories are a list"
    steps.append("four money lines with stated targets")

    # 2. Packet ceiling enforced by the shared standard (B2).
    try:
        build_reap_packet("x", source="selftest", probe_id="t",
                          max_tokens=501)
        raise AssertionError("over-ceiling packet must raise")
    except ValueError:
        pass
    steps.append("packet ceiling enforced (501 raises)")

    # 3. All-UNKNOWN gather formats with OWED, invents nothing.
    fake = {"key": "stranger-1k", "name": "Stranger $1k track",
            "target": "~$1,000 in 30 days (stated target)",
            "revenue_30d": None, "revenue_all": None, "revenue_rows": 0,
            "revenue_categories": [], "scorecard": None,
            "scorecard_blog": None, "contacts_matched": None,
            "contacts_pool": 6854, "goals_total": 0, "goals_active": 0}
    brief, verdict, owed = build_brief(fake, "2026-11-13")
    assert "UNKNOWN" in brief and "OWED:" in brief, \
        "unknown legs named OWED"
    assert "$0" not in brief and " 0 " not in verdict, \
        "nothing invented as zero"
    assert len(owed) == 3, f"three owed legs (got {owed})"
    pkt = build_packet_for(fake, "2026-11-13", brief)
    assert pkt["max_tokens"] == 500 and \
        pkt["probe_id"] == "standing-compile-stranger-1k-2026-11-13", \
        "packet shape + probe_id"
    assert estimate_tokens(brief) <= PROMPT_TOKEN_BUDGET, \
        "brief inside prompt budget"
    steps.append("all-UNKNOWN brief names OWED, invents nothing")

    # 4. Live landing probe on a disposable row, then idempotency,
    #    then cleanup (knowledge_return selftest pattern).
    probe_day = "selftest-" + datetime.now(CHICAGO).strftime(
        "%Y%m%d%H%M%S")
    g = dict(fake, key="stranger-1k")
    brief2, verdict2, owed2 = build_brief(g, probe_day)
    pkt2 = build_packet_for(g, probe_day, brief2)
    canonical = f"ki:compile-stranger-1k-{probe_day}"
    try:
        n1 = file_compile(g, probe_day, brief2, verdict2, owed2, pkt2)
        assert n1 == 1, "probe row lands"
        row = pg_rows(
            f"select kind, status, distilled, doc_text from {KI} "
            "where canonical_id = %s", (canonical,))
        assert len(row) == 1, "exactly one probe row"
        assert row[0][0] == KIND and row[0][1] == "current", \
            "kind/status stamped"
        assert verdict2[:40] in (row[0][2] or ""), "distilled is verdict"
        assert "STANDING COMPILE" in (row[0][3] or ""), \
            "doc_text is the brief"
        steps.append("live landing probe (row + provenance verified)")
        n2 = file_compile(g, probe_day, brief2, verdict2, owed2, pkt2)
        assert n2 == 0, "second file lands nothing (idempotent)"
        steps.append("idempotency (re-file lands 0)")
        # Residue contract: the B6 leg reads kind='compile'.
        c = pg_one(f"select count(*) from {KI} where kind = %s",
                   (KIND,))
        assert int(c or 0) >= 1, "compile kind visible to residue leg"
        steps.append("residue contract (kind='compile' readable)")
    finally:
        pg_exec(f"delete from {KI} where canonical_id = %s",
                (canonical,))
        gone = pg_one(f"select count(*) from {KI} where canonical_id "
                      "= %s", (canonical,))
        assert int(gone or 0) == 0, "probe row cleaned up"
    steps.append("zero residue (probe row deleted)")

    # 5. Live gather runs read-only and returns all four lines.
    for key in LINES:
        gg = gather(key)
        assert gg["key"] == key and gg["contacts_pool"] > 0, \
            f"{key}: live gather returns a pool"
    steps.append("live gather runs on all four lines")

    print(f"SELFTEST PASS ({len(steps)} steps)")
    for s in steps:
        print(f"  - {s}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--line", choices=list(LINES))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if a.status:
        status()
        return 0
    if a.compile:
        keys = [a.line] if a.line else list(LINES)
        compile_lines(keys, dry=a.dry_run)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
