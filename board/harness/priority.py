"""
Priority: the order the board works the queue (Brian 2026-10-23).

WHY:
    Until now the agenda ran in Atlas pull order — gates first, then
    node_key order — which is an accident of storage, not a judgment.
    Brian 2026-10-23: "we need to start ordering the priorities so
    they work the most important decisions first... i'm not sure how
    we determine the priority, we may need to plan that, and i can
    give feedback over time to maybe help us figure out the best
    priority analysis."

    So v0 is deliberately simple, deterministic and EXPLAINABLE:
    every item gets a numeric score AND the reasons that produced it.
    The score and reasons print in the session log, land in the
    per-decision rulings ledger, and ride into the minutes — so
    Brian's morning feedback ("why was X above Y?") has something
    concrete to aim at, and the weights (config `priority.weights`,
    defaults below) get tuned instead of the system being rebuilt.
    The feedback loop is the product; v0's exact weights are a first
    guess, labeled as such.

SIGNALS (all from data the ecosystem already records):
    gate            a gate is a decision waiting on the board   +100
    stuck           timed out last session; re-presented          +80
    deadline        item carries a deadline: <=7d +40, <=30d +15
    standing_goal   filed against one of Brian's standing goals   +25
    age             starvation guard: +2/day waiting, capped +30
    theme           item has a routing theme (a real desk owns it) +5
"""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_WEIGHTS = {
    "gate": 100.0,
    "stuck": 80.0,
    "deadline_7d": 40.0,
    "deadline_30d": 15.0,
    "standing_goal": 25.0,
    "age_per_day": 2.0,
    "age_cap": 30.0,
    "theme": 5.0,
}


def _parse_date(value):
    if not value:
        return None
    try:
        txt = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def score_item(item, *, stuck_keys=(), weights=None, now=None):
    """Score one AgendaItem. Returns (score, reasons) and stamps both
    onto the item (priority_score / priority_reasons)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    now = now or datetime.now(timezone.utc)
    score, reasons = 0.0, []
    meta = getattr(item, "meta", {}) or {}
    details = meta.get("details") or {}

    if item.kind == "gate":
        score += w["gate"]
        reasons.append(f"gate (+{w['gate']:.0f})")

    if item.key in stuck_keys:
        score += w["stuck"]
        reasons.append(f"re-presented after timeout (+{w['stuck']:.0f})")

    deadline = _parse_date(
        details.get("deadline") or details.get("due") or details.get("due_date"))
    if deadline is not None:
        days = (deadline - now).days
        if days <= 7:
            score += w["deadline_7d"]
            reasons.append(f"deadline in {days}d (+{w['deadline_7d']:.0f})")
        elif days <= 30:
            score += w["deadline_30d"]
            reasons.append(f"deadline in {days}d (+{w['deadline_30d']:.0f})")

    source = str(details.get("source") or "")
    found_by = str(details.get("found_by") or "")
    if "standing-goal" in source or "standing-goal" in found_by:
        score += w["standing_goal"]
        reasons.append(f"standing goal (+{w['standing_goal']:.0f})")

    created = _parse_date(meta.get("created_at"))
    if created is not None:
        age_days = max(0, (now - created).days)
        pts = min(w["age_cap"], age_days * w["age_per_day"])
        if pts > 0:
            score += pts
            reasons.append(f"waiting {age_days}d (+{pts:.0f})")

    if getattr(item, "theme", ""):
        score += w["theme"]
        reasons.append(f"themed (+{w['theme']:.0f})")

    item.priority_score = score
    item.priority_reasons = reasons
    return score, reasons
