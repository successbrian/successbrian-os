#!/usr/bin/env python3
"""weekly_scorecard.py — the SuccessBrian OS WEEKLY SCORECARD store.

Brian's order, 2026-11-15: build the weekly scorecard into the
product. Design: ~/workspace/builds/sbos-scorecard/
DESIGN-2026-11-15.md — "one card, two readers": the owner reads five
numbers for 25 minutes once a week to run their business; the OS
reads the same numbers as signals and works on them all week. This
module is the store behind that card, and it is what the agent
interface's scorecard door (tools/agent_interface.py, Phase 3) has
been waiting for: until this store existed, the door answered
honestly that there was nothing behind it.

In plain words for the owner: this is a once-a-week checkup for a
busy one-person business. Five numbers, once a week:

  1. In        — new leads: new contacts or inquiries this week
  2. Talks     — sales talks: real conversations with possible buyers
  3. Delivered — deliveries finished: promised work, finished and sent
  4. Shipped   — assets shipped: posts, pages, videos, systems —
                 made once, keeps working
  5. Cash      — cash in: money actually collected

The slots are ROLES: the owner names each number in their own words
and sets their own floor / target / stretch. Status follows the
Deiss rule — green on target, yellow behind with a plan, red behind
with no plan — and yellow/red three weeks in a row means the number
is stuck, no matter how good the plan sounds. Each review ends with
one fix and one promise; the next review opens with that promise.
On top sits the owner's "enough" number (what the business must
bring in monthly to be worth it); below the five sit the two system
checks — shoulder taps (how many times the business needed the owner
personally) and hours on the business against the owner's cap.

Rules this store never breaks (from the design):
  * The owner types the numbers. Desks may pre-collect counts from
    real records and store them as SUGGESTED values — a suggestion
    is shown as a suggestion and never becomes the owner's number
    silently, and nothing anywhere invents a number.
  * The owner's numbers are the owner's: every row is keyed by
    operator_key, and no read ever crosses owners.
  * A missed week carries forward: its row stays 'open', flagged
    carried_forward, never counted as handled (the calendar law).

DDL: tools/weekly_scorecard_migration_2026-11-15.sql (tables
successbrian_os.weekly_scorecard_settings / _metrics / _weeks /
_entries / _taps).

Usage (CLI):
  python3 weekly_scorecard.py setup --operator OP
      (create the owner's card: five default numbers + settings)
  python3 weekly_scorecard.py set-metric --operator OP --slot 1 \
      [--name "..."] [--counts "..."] [--floor N] [--target N] \
      [--stretch N] [--goal GOAL_SLUG]
  python3 weekly_scorecard.py settings --operator OP \
      [--enough N] [--hours-cap N]
  python3 weekly_scorecard.py suggest --operator OP --slot 1 \
      --value N [--week YYYY-MM-DD]     (desk pre-collection)
  python3 weekly_scorecard.py enter-week --operator OP \
      [--week YYYY-MM-DD] [--set 1=12] [--set 5=1500] \
      [--plan 2="..."] [--shoulder-taps N] [--hours N] \
      [--fix "..."] [--promise "..."] [--prev-promise-kept yes|no]
      (the owner's weekly review — the real write path)
  python3 weekly_scorecard.py tap --operator OP --kind "..." \
      [--note "..."] [--date YYYY-MM-DD]
  python3 weekly_scorecard.py show --operator OP [--weeks 13] [--json]
  python3 weekly_scorecard.py selftest
"""

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal

import sbos_common  # noqa: E402  (the one connection factory)
from sbos_common import pg_exec, pg_one, pg_rows  # noqa: E402

SLOTS = (1, 2, 3, 4, 5)
DEFAULT_METRICS = [
    (1, "in", "New leads",
     "New contacts or inquiries this week"),
    (2, "talks", "Sales talks",
     "Real conversations with possible buyers"),
    (3, "delivered", "Deliveries finished",
     "Work you promised, finished and sent"),
    (4, "shipped", "Things shipped",
     "Posts, pages, videos, or systems you made once that keep working"),
    (5, "cash", "Cash in",
     "Money actually collected this week"),
]
CASH_SLOT = 5
_UNSET = object()


# ---------------------------------------------------------------- helpers

def _num(v):
    """Decimal -> int/float for clean dicts; None stays None."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def monday_of(d):
    """The Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def _parse_date(s):
    if s is None:
        return date.today()
    return date.fromisoformat(s)


def _week_start(s):
    return monday_of(_parse_date(s))


def compute_status(value, target, plan):
    """The Deiss rule: green on target, yellow behind with a plan,
    red behind with no plan. No value or no target -> not judged
    (None): unknown stays unknown, never dressed up as a color."""
    if value is None or target is None:
        return None
    if value >= target:
        return "green"
    return "yellow" if (plan and str(plan).strip()) else "red"


# ---------------------------------------------------------------- setup

def ensure_setup(operator_key):
    """Create the owner's card if it does not exist yet: the settings
    row and the five default numbers. Idempotent — an owner's own
    names and targets are never overwritten by re-running setup."""
    pg_exec(
        "insert into successbrian_os.weekly_scorecard_settings "
        "(operator_key) values (%s) on conflict (operator_key) "
        "do nothing", (operator_key,))
    for slot, role, name, counts in DEFAULT_METRICS:
        pg_exec(
            """insert into successbrian_os.weekly_scorecard_metrics
                 (operator_key, slot, role, name, what_it_counts)
               values (%s,%s,%s,%s,%s)
               on conflict (operator_key, slot) do nothing""",
            (operator_key, slot, role, name, counts))
    return get_metrics(operator_key)


def get_metrics(operator_key):
    rows = pg_rows(
        """select id, slot, role, name, what_it_counts, floor_value,
                  target_value, stretch_value, goal_slug, active
             from successbrian_os.weekly_scorecard_metrics
            where operator_key=%s order by slot""", (operator_key,))
    keys = ("id", "slot", "role", "name", "what_it_counts", "floor",
            "target", "stretch", "goal_slug", "active")
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        for k in ("floor", "target", "stretch"):
            d[k] = _num(d[k])
        out.append(d)
    return out


def get_settings(operator_key):
    row = pg_one(
        """select enough_monthly, hours_cap
             from successbrian_os.weekly_scorecard_settings
            where operator_key=%s""", (operator_key,))
    if row is None:
        return {"enough_monthly": None, "hours_cap": None}
    return {"enough_monthly": _num(row[0]), "hours_cap": _num(row[1])}


def set_metric(operator_key, slot, name=_UNSET, what_it_counts=_UNSET,
               floor=_UNSET, target=_UNSET, stretch=_UNSET,
               goal_slug=_UNSET):
    """Owner-side: name a number in your own words, set its floor /
    target / stretch, link it to a goal. Only fields passed are
    changed; pass None explicitly to clear one."""
    if slot not in SLOTS:
        raise ValueError(f"slot must be one of {SLOTS}")
    ensure_setup(operator_key)
    sets, params = [], []
    for col, val in (("name", name), ("what_it_counts", what_it_counts),
                     ("floor_value", floor), ("target_value", target),
                     ("stretch_value", stretch), ("goal_slug", goal_slug)):
        if val is not _UNSET:
            sets.append(f"{col}=%s")
            params.append(val)
    if not sets:
        return get_metrics(operator_key)
    params.append(operator_key)
    params.append(slot)
    pg_exec(
        f"""update successbrian_os.weekly_scorecard_metrics
               set {', '.join(sets)}, updated_at=now()
             where operator_key=%s and slot=%s""", tuple(params))
    return get_metrics(operator_key)


def set_settings(operator_key, enough_monthly=_UNSET, hours_cap=_UNSET):
    """Owner-side: set the standing numbers — the monthly 'enough'
    number and the weekly hours cap."""
    pg_exec(
        "insert into successbrian_os.weekly_scorecard_settings "
        "(operator_key) values (%s) on conflict (operator_key) "
        "do nothing", (operator_key,))
    sets, params = [], []
    for col, val in (("enough_monthly", enough_monthly),
                     ("hours_cap", hours_cap)):
        if val is not _UNSET:
            sets.append(f"{col}=%s")
            params.append(val)
    if sets:
        params.append(operator_key)
        pg_exec(
            f"""update successbrian_os.weekly_scorecard_settings
                   set {', '.join(sets)}, updated_at=now()
                 where operator_key=%s""", tuple(params))
    return get_settings(operator_key)


# ---------------------------------------------------------------- weeks

def _open_week(operator_key, week_start):
    """Get the week's row, creating it 'open' if needed. An open row
    is a week waiting for its review — a missed week stays open and
    carries forward; it is never counted as handled."""
    row = pg_one(
        """select id from successbrian_os.weekly_scorecard_weeks
            where operator_key=%s and week_start=%s""",
        (operator_key, week_start))
    if row is not None:
        return row
    cap = get_settings(operator_key)["hours_cap"]
    return pg_one(
        """insert into successbrian_os.weekly_scorecard_weeks
             (operator_key, week_start, hours_cap)
           values (%s,%s,%s) returning id""",
        (operator_key, week_start, cap))


def _metric_by_slot(operator_key):
    return {m["slot"]: m for m in get_metrics(operator_key)}


def suggest(operator_key, week_start, slot, value):
    """Desk pre-collection: store a SUGGESTED value for one number.
    A suggestion is shown to the owner at review as a suggestion —
    it never becomes the owner's number and never overwrites one."""
    if slot not in SLOTS:
        raise ValueError(f"slot must be one of {SLOTS}")
    ensure_setup(operator_key)
    week_id = _open_week(operator_key, week_start)
    metric = _metric_by_slot(operator_key)[slot]
    pg_exec(
        """insert into successbrian_os.weekly_scorecard_entries
             (week_id, metric_id, suggested_value, floor_value,
              target_value, stretch_value)
           values (%s,%s,%s,%s,%s,%s)
           on conflict (week_id, metric_id) do update
             set suggested_value=excluded.suggested_value,
                 updated_at=now()""",
        (week_id, metric["id"], value, metric["floor"],
         metric["target"], metric["stretch"]))
    return {"week_start": week_start.isoformat(), "slot": slot,
            "suggested_value": _num(value)}


def enter_week(operator_key, week_start, entries,
               shoulder_taps=_UNSET, hours_on_business=_UNSET,
               one_fix=_UNSET, one_promise=_UNSET,
               prev_promise_kept=_UNSET):
    """THE owner's weekly review — the real write path. entries maps
    slot -> (value, plan); only the numbers the owner actually gives
    are written (re-running enter-week for the same week corrects
    it). Each entry snapshots the floor/target/stretch it is judged
    against and computes its status by the Deiss rule. The week is
    marked reviewed; nothing not passed is touched."""
    ensure_setup(operator_key)
    week_id = _open_week(operator_key, week_start)
    metrics = _metric_by_slot(operator_key)
    for slot, pair in entries.items():
        if slot not in SLOTS:
            raise ValueError(f"slot must be one of {SLOTS}")
        value, plan = pair
        metric = metrics[slot]
        if value is None or plan is None:
            # A correction that names only one field keeps the other
            # as stored — re-entering a week never erases a number
            # the owner already gave.
            existing = pg_one(
                """select value, plan
                     from successbrian_os.weekly_scorecard_entries
                    where week_id=%s and metric_id=%s""",
                (week_id, metric["id"])) or (None, None)
            if value is None:
                value = _num(existing[0])
            if plan is None:
                plan = existing[1]
        status = compute_status(
            None if value is None else Decimal(str(value)),
            None if metric["target"] is None
            else Decimal(str(metric["target"])), plan)
        pg_exec(
            """insert into successbrian_os.weekly_scorecard_entries
                 (week_id, metric_id, value, plan, status, floor_value,
                  target_value, stretch_value)
               values (%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (week_id, metric_id) do update
                 set value=excluded.value, plan=excluded.plan,
                     status=excluded.status,
                     floor_value=excluded.floor_value,
                     target_value=excluded.target_value,
                     stretch_value=excluded.stretch_value,
                     updated_at=now()""",
            (week_id, metric["id"], value, plan, status,
             metric["floor"], metric["target"], metric["stretch"]))
    sets, params = ["status='reviewed'", "reviewed_at=now()"], []
    for col, val in (("shoulder_taps", shoulder_taps),
                     ("hours_on_business", hours_on_business),
                     ("one_fix", one_fix), ("one_promise", one_promise),
                     ("prev_promise_kept", prev_promise_kept)):
        if val is not _UNSET:
            sets.append(f"{col}=%s")
            params.append(val)
    params.append(week_id)
    pg_exec(
        f"""update successbrian_os.weekly_scorecard_weeks
               set {', '.join(sets)}, updated_at=now()
             where id=%s""", tuple(params))
    card = get_card(operator_key)
    for w in card["weeks"]:
        if w["week_start"] == week_start.isoformat():
            return w
    return None


# ---------------------------------------------------------------- taps

def log_tap(operator_key, kind, note=None, tapped_on=None):
    """Log one shoulder tap by kind: the business needed the owner
    personally. A recurring kind is a system defect with a name."""
    tapped_on = tapped_on or date.today()
    tap_id = pg_one(
        """insert into successbrian_os.weekly_scorecard_taps
             (operator_key, tapped_on, kind, note)
           values (%s,%s,%s,%s) returning id""",
        (operator_key, tapped_on, kind, note))
    return {"id": tap_id, "tapped_on": tapped_on.isoformat(),
            "kind": kind}


def taps_for_week(operator_key, week_start):
    rows = pg_rows(
        """select kind, count(*) from successbrian_os.weekly_scorecard_taps
            where operator_key=%s and tapped_on >= %s and tapped_on < %s
            group by kind order by count(*) desc, kind""",
        (operator_key, week_start, week_start + timedelta(days=7)))
    return {"logged": sum(r[1] for r in rows),
            "by_kind": {r[0]: r[1] for r in rows}}


# ---------------------------------------------------------------- the card

def get_card(operator_key, weeks=13):
    """The read model — one card, both readers. The CLI prints it;
    the agent interface's scorecard door serves it. Only the owner's
    own rows, most recent week first, the last `weeks` weeks (the
    design keeps 13 visible and judges the last 4 together). Derived
    facts (behind streaks, cash pace, the habit count, the promise
    chain) are arithmetic on stored rows only — a week with no data
    reads as no data."""
    settings = get_settings(operator_key)
    metrics = get_metrics(operator_key)
    current_monday = monday_of(date.today())
    earliest = current_monday - timedelta(weeks=weeks - 1)
    rows = pg_rows(
        """select id, week_start, status, shoulder_taps,
                  hours_on_business, hours_cap, one_fix, one_promise,
                  prev_promise_kept, reviewed_at::text
             from successbrian_os.weekly_scorecard_weeks
            where operator_key=%s and week_start >= %s
            order by week_start desc""", (operator_key, earliest))
    week_ids = [r[0] for r in rows]
    entries = {}
    if week_ids:
        for (wid, slot, value, sugg, fl, tg, st, status, plan) in pg_rows(
                """select e.week_id, m.slot, e.value, e.suggested_value,
                          e.floor_value, e.target_value, e.stretch_value,
                          e.status, e.plan
                     from successbrian_os.weekly_scorecard_entries e
                     join successbrian_os.weekly_scorecard_metrics m
                       on m.id = e.metric_id
                    where e.week_id = any(%s)""", (week_ids,)):
            entries[(wid, slot)] = {
                "value": _num(value), "suggested_value": _num(sugg),
                "floor": _num(fl), "target": _num(tg),
                "stretch": _num(st), "status": status, "plan": plan}
    week_dicts = []
    for (wid, ws, status, taps, hours, cap, fix, promise, prev_kept,
         reviewed_at) in rows:
        numbers = []
        for m in metrics:
            e = entries.get((wid, m["slot"]))
            numbers.append({
                "slot": m["slot"], "role": m["role"], "name": m["name"],
                "value": e["value"] if e else None,
                "suggested_value": e["suggested_value"] if e else None,
                "floor": e["floor"] if e else m["floor"],
                "target": e["target"] if e else m["target"],
                "stretch": e["stretch"] if e else m["stretch"],
                "status": e["status"] if e else None,
                "plan": e["plan"] if e else None,
                "goal_slug": m["goal_slug"]})
        week_dicts.append({
            "week_start": ws.isoformat(), "status": status,
            "carried_forward": bool(
                status == "open" and ws < current_monday),
            "numbers": numbers,
            "shoulder_taps": taps,
            "taps_logged": taps_for_week(operator_key, ws),
            "hours_on_business": _num(hours), "hours_cap": _num(cap),
            "one_fix": fix, "one_promise": promise,
            "prev_promise_kept": prev_kept,
            "reviewed_at": reviewed_at})
    reviewed = [w for w in week_dicts if w["status"] == "reviewed"]
    # Behind streaks per number (EOS safety net: 3 in a row = stuck),
    # counted back from the most recent reviewed week that judged it.
    for m in metrics:
        streak = 0
        for w in reviewed:
            n = next(x for x in w["numbers"] if x["slot"] == m["slot"])
            if n["status"] in ("yellow", "red"):
                streak += 1
            elif n["status"] == "green":
                break
            else:
                break
        m["behind_streak"] = streak
        m["stuck"] = streak >= 3
    # Cash pace vs the enough number — the last 4 reviewed weeks that
    # actually carry a cash number, stated with its week count.
    cash_values = []
    for w in reviewed:
        n = next(x for x in w["numbers"] if x["slot"] == CASH_SLOT)
        if n["value"] is not None:
            cash_values.append(n["value"])
        if len(cash_values) >= 4:
            break
    cash_pace = None
    if cash_values:
        weekly_avg = sum(cash_values) / len(cash_values)
        monthly = weekly_avg * 52 / 12
        enough = settings["enough_monthly"]
        cash_pace = {
            "weeks_counted": len(cash_values),
            "weekly_average": round(weekly_avg, 2),
            "monthly_pace": round(monthly, 2),
            "enough_monthly": enough,
            "pct_of_enough": (round(monthly / enough * 100, 1)
                              if enough else None)}
    # The promise chain: the newest promise, and whether it was kept
    # (recorded at the next review after it was made).
    latest_promise = None
    asc = list(reversed(reviewed))
    for i, w in enumerate(asc):
        if w["one_promise"]:
            kept = None
            for later in asc[i + 1:]:
                if later["prev_promise_kept"] is not None:
                    kept = later["prev_promise_kept"]
                    break
            latest_promise = {"week_start": w["week_start"],
                              "promise": w["one_promise"], "kept": kept}
    return {
        "operator_key": operator_key,
        "setup_done": len(metrics) > 0,
        "enough_monthly": settings["enough_monthly"],
        "hours_cap": settings["hours_cap"],
        "metrics": metrics,
        "weeks": week_dicts,
        "reviewed_weeks": len(reviewed),
        "habit": {"reviewed": len(reviewed), "of": weeks},
        "cash_pace": cash_pace,
        "latest_promise": latest_promise}


_STATUS_WORDS = {"green": "on target", "yellow": "behind — has a plan",
                 "red": "behind — no plan"}


def render_text(card):
    """The owner's 25-minute view, in plain words."""
    lines = ["Your weekly scorecard — five numbers, once a week."]
    if card["enough_monthly"] is not None:
        lines.append(f"Your enough number: {card['enough_monthly']:,} "
                     "a month.")
    else:
        lines.append("Your enough number is not set yet.")
    pace = card["cash_pace"]
    if pace is not None:
        s = (f"Cash pace: over the last {pace['weeks_counted']} "
             f"reviewed week(s) you averaged "
             f"{pace['weekly_average']:,} a week — near "
             f"{pace['monthly_pace']:,} a month")
        if pace["pct_of_enough"] is not None:
            s += f", {pace['pct_of_enough']}% of your enough number."
        else:
            s += "."
        lines.append(s)
    lines.append(f"Weeks reviewed: {card['habit']['reviewed']} of "
                 f"the last {card['habit']['of']}.")
    lp = card["latest_promise"]
    if lp is not None:
        kept = {True: "kept", False: "not kept",
                None: "not checked yet"}[lp["kept"]]
        lines.append(f"Latest promise ({lp['week_start']}): "
                     f"\"{lp['promise']}\" — {kept}.")
    stuck = [m for m in card["metrics"] if m.get("stuck")]
    for m in stuck:
        lines.append(f"STUCK: {m['name']} has been behind three "
                     "weeks in a row.")
    if not card["weeks"]:
        lines.append("")
        lines.append("No weeks on the card yet. Your first review "
                     "starts it — five numbers, that's all.")
        return "\n".join(lines)
    for w in card["weeks"]:
        lines.append("")
        head = f"Week of {w['week_start']}"
        if w["status"] == "reviewed":
            head += " (reviewed)"
        elif w["carried_forward"]:
            head += " (still open — carried forward, not handled)"
        else:
            head += " (open — this week, not reviewed yet)"
        lines.append(head)
        for n in w["numbers"]:
            if n["value"] is None:
                v = "not entered"
                if n["suggested_value"] is not None:
                    v += f" (suggested: {n['suggested_value']:,})"
            else:
                v = f"{n['value']:,}"
            t = (f" of target {n['target']:,}"
                 if n["target"] is not None else "")
            word = _STATUS_WORDS.get(n["status"], "")
            lines.append(f"  {n['name']}: {v}{t}"
                         + (f" — {word}" if word else ""))
            if n["plan"]:
                lines.append(f"    plan: {n['plan']}")
        bits = []
        if w["shoulder_taps"] is not None:
            bits.append(f"shoulder taps: {w['shoulder_taps']}")
        elif w["taps_logged"]["logged"]:
            bits.append(f"shoulder taps logged: "
                        f"{w['taps_logged']['logged']}")
        if w["hours_on_business"] is not None:
            cap = (f" of {w['hours_cap']:,} cap"
                   if w["hours_cap"] is not None else "")
            bits.append(f"hours on the business: "
                        f"{w['hours_on_business']:,}{cap}")
        if bits:
            lines.append("  " + " · ".join(bits))
        if w["one_fix"]:
            lines.append(f"  One fix: {w['one_fix']}")
        if w["one_promise"]:
            lines.append(f"  One promise: {w['one_promise']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- selftest

TEST_OPERATOR = "weekly-scorecard-selftest-operator"


def delete_owner_rows(operator_key):
    """Remove ALL of one owner's scorecard rows (entries first —
    they hang off weeks). Exists for selftest cleanup of disposable
    operators; nothing in the product flow deletes an owner's card."""
    pg_exec(
        """delete from successbrian_os.weekly_scorecard_entries e
             using successbrian_os.weekly_scorecard_weeks w
             where e.week_id = w.id and w.operator_key=%s""",
        (operator_key,))
    for tbl in ("weekly_scorecard_taps", "weekly_scorecard_weeks",
                "weekly_scorecard_metrics",
                "weekly_scorecard_settings"):
        pg_exec(f"delete from successbrian_os.{tbl} "
                "where operator_key=%s", (operator_key,))


def _cleanup_test_rows():
    # Disposable selftest cleanup (the standing precedent):
    # production records are never deleted; selftest scaffolding
    # rows under the test operator are removed whole.
    delete_owner_rows(TEST_OPERATOR)


def selftest():
    """End-to-end proof on disposable rows: setup -> defaults ->
    a suggestion stays a suggestion -> the owner's review writes
    real numbers through the real write path -> statuses follow the
    Deiss rule -> three behind weeks read as stuck -> taps log by
    kind -> cash pace is honest arithmetic -> cleanup verified."""
    steps = []

    def check(label, cond):
        steps.append((label, bool(cond)))
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")
        if not cond:
            raise AssertionError(label)

    _cleanup_test_rows()
    print("weekly_scorecard selftest")
    today = date.today()
    w1 = monday_of(today - timedelta(days=21))
    w2 = monday_of(today - timedelta(days=14))
    w3 = monday_of(today - timedelta(days=7))
    # 1. setup creates the five default numbers, in the owner's words
    metrics = ensure_setup(TEST_OPERATOR)
    check("setup creates exactly five numbers",
          len(metrics) == 5 and [m["slot"] for m in metrics] == [1, 2, 3, 4, 5])
    check("defaults carry the design's plain names",
          metrics[0]["name"] == "New leads"
          and metrics[4]["role"] == "cash")
    again = ensure_setup(TEST_OPERATOR)
    check("setup is idempotent (no duplicates, no clobbering)",
          len(again) == 5)
    # 2. owner sets targets + standing numbers
    set_metric(TEST_OPERATOR, 1, target=10, floor=5, stretch=20)
    set_metric(TEST_OPERATOR, 2, target=5)
    set_metric(TEST_OPERATOR, 3, target=4)
    set_metric(TEST_OPERATOR, 5, target=1000)
    s = set_settings(TEST_OPERATOR, enough_monthly=4000, hours_cap=25)
    check("settings store the enough number and hours cap",
          s["enough_monthly"] == 4000 and s["hours_cap"] == 25)
    # 3. a desk suggestion stays a suggestion — never the value
    suggest(TEST_OPERATOR, w1, 1, 9)
    card = get_card(TEST_OPERATOR)
    wk = next(w for w in card["weeks"]
              if w["week_start"] == w1.isoformat())
    n1 = next(n for n in wk["numbers"] if n["slot"] == 1)
    check("suggestion lands as suggested_value only",
          n1["suggested_value"] == 9 and n1["value"] is None)
    check("a suggested week is open, not reviewed",
          wk["status"] == "open" and card["reviewed_weeks"] == 0)
    # 4. the owner's review writes real numbers (the real write path)
    enter_week(TEST_OPERATOR, w1,
               {1: (12, None), 2: (2, "Call the list twice"),
                3: (1, None), 5: (1500, None)},
               shoulder_taps=3, hours_on_business=22,
               one_fix="Fix the follow-up gap",
               one_promise="Send the quote")
    card = get_card(TEST_OPERATOR)
    wk = next(w for w in card["weeks"]
              if w["week_start"] == w1.isoformat())
    by_slot = {n["slot"]: n for n in wk["numbers"]}
    check("reviewed week serves the owner's exact numbers",
          by_slot[1]["value"] == 12 and by_slot[5]["value"] == 1500)
    check("the suggestion survives beside the owner's number",
          by_slot[1]["suggested_value"] == 9)
    check("statuses follow the Deiss rule (green/yellow/red)",
          by_slot[1]["status"] == "green"
          and by_slot[2]["status"] == "yellow"
          and by_slot[3]["status"] == "red")
    check("an unentered number stays unentered — never invented",
          by_slot[4]["value"] is None and by_slot[4]["status"] is None)
    check("the week's fix, promise, taps and hours are stored",
          wk["one_fix"] == "Fix the follow-up gap"
          and wk["one_promise"] == "Send the quote"
          and wk["shoulder_taps"] == 3
          and wk["hours_on_business"] == 22
          and wk["hours_cap"] == 25)
    # 5. two more behind weeks for slot 3 -> stuck (EOS safety net)
    enter_week(TEST_OPERATOR, w2, {3: (2, None)}, prev_promise_kept=True)
    enter_week(TEST_OPERATOR, w3, {3: (3, None)})
    card = get_card(TEST_OPERATOR)
    m3 = next(m for m in card["metrics"] if m["slot"] == 3)
    check("three behind weeks in a row read as stuck",
          m3["behind_streak"] == 3 and m3["stuck"] is True)
    check("habit counts the reviewed weeks",
          card["habit"]["reviewed"] == 3)
    check("the promise chain records kept",
          card["latest_promise"]["promise"] == "Send the quote"
          and card["latest_promise"]["kept"] is True)
    # 6. cash pace is honest arithmetic on stored numbers only
    pace = card["cash_pace"]
    check("cash pace: one cash week, monthly = weekly x 52/12",
          pace["weeks_counted"] == 1
          and pace["monthly_pace"] == 6500
          and pace["pct_of_enough"] == 162.5)
    # 7. shoulder taps log by kind
    log_tap(TEST_OPERATOR, "password reset", tapped_on=w3 + timedelta(days=1))
    log_tap(TEST_OPERATOR, "password reset", tapped_on=w3 + timedelta(days=2))
    log_tap(TEST_OPERATOR, "approve a post", tapped_on=w3)
    taps = taps_for_week(TEST_OPERATOR, w3)
    check("taps log counts by kind",
          taps["logged"] == 3
          and taps["by_kind"] == {"approve a post": 1, "password reset": 2})
    # 8. per-owner separation: another owner sees an empty card
    other = get_card("weekly-scorecard-selftest-other")
    check("another owner's card is empty (no cross-owner reads)",
          other["setup_done"] is False and other["weeks"] == [])
    _cleanup_test_rows()
    left = pg_one(
        "select (select count(*) from successbrian_os.weekly_scorecard_weeks where operator_key=%s) + "
        "(select count(*) from successbrian_os.weekly_scorecard_metrics where operator_key=%s) + "
        "(select count(*) from successbrian_os.weekly_scorecard_settings where operator_key=%s) + "
        "(select count(*) from successbrian_os.weekly_scorecard_taps where operator_key=%s)",
        (TEST_OPERATOR,) * 4)
    check("cleanup: no selftest rows remain", left == 0)
    print("SELFTEST PASS")
    return 0


# ---------------------------------------------------------------- CLI

def _parse_slot_pairs(pairs, numeric):
    out = {}
    for p in pairs or []:
        slot_s, _, rest = p.partition("=")
        slot = int(slot_s)
        out[slot] = float(rest) if numeric else rest
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SBOS Weekly Scorecard — a once-a-week checkup "
                    "for a busy one-person business: five numbers, "
                    "entered by the owner, read by the owner and "
                    "the OS alike")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("setup")
    p.add_argument("--operator", required=True)

    p = sub.add_parser("set-metric")
    p.add_argument("--operator", required=True)
    p.add_argument("--slot", required=True, type=int)
    p.add_argument("--name")
    p.add_argument("--counts")
    p.add_argument("--floor", type=float)
    p.add_argument("--target", type=float)
    p.add_argument("--stretch", type=float)
    p.add_argument("--goal")

    p = sub.add_parser("settings")
    p.add_argument("--operator", required=True)
    p.add_argument("--enough", type=float)
    p.add_argument("--hours-cap", type=float)

    p = sub.add_parser("suggest")
    p.add_argument("--operator", required=True)
    p.add_argument("--slot", required=True, type=int)
    p.add_argument("--value", required=True, type=float)
    p.add_argument("--week")

    p = sub.add_parser("enter-week")
    p.add_argument("--operator", required=True)
    p.add_argument("--week")
    p.add_argument("--set", action="append", default=[],
                   help="SLOT=VALUE, repeatable — the owner's numbers")
    p.add_argument("--plan", action="append", default=[],
                   help="SLOT=TEXT, repeatable — the owner's plan "
                        "beside a number")
    p.add_argument("--shoulder-taps", type=int)
    p.add_argument("--hours", type=float)
    p.add_argument("--fix")
    p.add_argument("--promise")
    p.add_argument("--prev-promise-kept", choices=("yes", "no"))

    p = sub.add_parser("tap")
    p.add_argument("--operator", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--note")
    p.add_argument("--date")

    p = sub.add_parser("show")
    p.add_argument("--operator", required=True)
    p.add_argument("--weeks", type=int, default=13)
    p.add_argument("--json", action="store_true")

    sub.add_parser("selftest")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "selftest":
            return selftest()
        if args.cmd == "setup":
            out = ensure_setup(args.operator)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "set-metric":
            kw = {}
            if args.name is not None:
                kw["name"] = args.name
            if args.counts is not None:
                kw["what_it_counts"] = args.counts
            if args.floor is not None:
                kw["floor"] = args.floor
            if args.target is not None:
                kw["target"] = args.target
            if args.stretch is not None:
                kw["stretch"] = args.stretch
            if args.goal is not None:
                kw["goal_slug"] = args.goal
            out = set_metric(args.operator, args.slot, **kw)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "settings":
            kw = {}
            if args.enough is not None:
                kw["enough_monthly"] = args.enough
            if args.hours_cap is not None:
                kw["hours_cap"] = args.hours_cap
            out = set_settings(args.operator, **kw)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "suggest":
            out = suggest(args.operator, _week_start(args.week),
                          args.slot, args.value)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "enter-week":
            values = _parse_slot_pairs(args.set, numeric=True)
            plans = _parse_slot_pairs(args.plan, numeric=False)
            entries = {s: (v, plans.get(s)) for s, v in values.items()}
            for s, t in plans.items():
                if s not in entries:
                    entries[s] = (None, t)
            kw = {}
            if args.shoulder_taps is not None:
                kw["shoulder_taps"] = args.shoulder_taps
            if args.hours is not None:
                kw["hours_on_business"] = args.hours
            if args.fix is not None:
                kw["one_fix"] = args.fix
            if args.promise is not None:
                kw["one_promise"] = args.promise
            if args.prev_promise_kept is not None:
                kw["prev_promise_kept"] = args.prev_promise_kept == "yes"
            out = enter_week(args.operator, _week_start(args.week),
                             entries, **kw)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "tap":
            out = log_tap(args.operator, args.kind, args.note,
                          _parse_date(args.date) if args.date else None)
            print(json.dumps(out, indent=2, default=str))
            return 0
        if args.cmd == "show":
            card = get_card(args.operator, weeks=args.weeks)
            if args.json:
                print(json.dumps(card, indent=2, default=str))
            else:
                print(render_text(card))
            return 0
    except AssertionError as e:
        print(f"SELFTEST FAIL: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # store / usage errors
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
