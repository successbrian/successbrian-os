"""Deterministic scoring rubric for fleshed-out venture ideas.

Transparent on purpose: every point is traceable to a profile field.
The score PROPOSES, Brian DECIDES. Bands, not verdicts.
"""

BANDS = [(70, "strong"), (45, "consider"), (0, "reshape-or-shelve")]


def _band(total):
    for floor, name in BANDS:
        if total >= floor:
            return name
    return "reshape-or-shelve"


def score_profile(profile, idea_streams, known_streams):
    """profile: dict from ideas.py flesh step. Returns {total, band, breakdown}."""
    bd = {}
    # 1. Clarity (0-20): how complete is the picture?
    core = ["problem", "customer", "offer", "revenue_model", "price_point",
            "startup_cost_usd", "weekly_hours"]
    filled = sum(1 for k in core if profile.get(k) not in (None, "", []))
    bd["clarity"] = round(20 * filled / len(core))
    # 2. Economics (0-25): cheap to start + a real price = strong.
    econ = 0
    try:
        cost = float(profile.get("startup_cost_usd") or 10 ** 9)
    except (TypeError, ValueError):
        cost = 10 ** 9
    if cost <= 500:
        econ = 20
    elif cost <= 2000:
        econ = 15
    elif cost <= 10000:
        econ = 10
    else:
        econ = 5
    if profile.get("price_point"):
        econ = min(25, econ + 5)
    bd["economics"] = econ
    # 3. Time fit (0-20): a side stream must fit beside the others.
    try:
        hrs = float(profile.get("weekly_hours") or 10 ** 9)
    except (TypeError, ValueError):
        hrs = 10 ** 9
    if hrs <= 5:
        bd["time_fit"] = 20
    elif hrs <= 10:
        bd["time_fit"] = 15
    elif hrs <= 20:
        bd["time_fit"] = 10
    else:
        bd["time_fit"] = 5
    # 4. Stream synergy (0-20): reuses what already exists.
    fit = [s for s in (profile.get("stream_fit") or []) if s]
    known = set(known_streams or []) | set(idea_streams or [])
    overlap = sum(1 for s in fit if s in known) + (1 if fit and not known else 0)
    bd["synergy"] = min(20, 10 * min(overlap, 2))
    # 5. Risk load (0-15): named risks are healthy; a pile of them is not.
    risks = profile.get("risks") or []
    bd["risk_load"] = max(3, 15 - 2 * len(risks))
    total = sum(bd.values())
    return {"total": total, "band": _band(total), "breakdown": bd}
