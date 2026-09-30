"""Turn a fleshed-out venture into a goal draft with milestones.

The draft stays 'draft' until Brian (or the entrepreneur) approves it;
Spencer then creates the real tracked goal from it.
"""


def draft_goal(title, pitch, profile, streams):
    steps = [s for s in (profile.get("first_steps") or []) if s]
    milestones = []
    # Milestone 1: validate the core assumption, cheaply.
    milestones.append({
        "title": "Validate: %s" % (profile.get("customer") or "target customer"),
        "detail": "Prove someone pays before spending big. Problem: %s" %
                  (profile.get("problem") or "—")})
    for i, step in enumerate(steps[:3], start=1):
        milestones.append({"title": "Step %d: %s" % (i, step), "detail": ""})
    milestones.append({
        "title": "First dollar in",
        "detail": "Revenue model: %s at %s" %
                  (profile.get("revenue_model") or "—",
                   profile.get("price_point") or "—")})
    milestones.append({
        "title": "30-day review: keep, fix, or shelve",
        "detail": "Risks to watch: %s" %
                  ("; ".join(profile.get("risks") or []) or "—")})
    description = (
        "%s\n\nOffer: %s\nCustomer: %s\nRevenue: %s at %s\n"
        "Startup cost: $%s | Weekly hours: %s\nStreams: %s" % (
            pitch,
            profile.get("offer") or "—",
            profile.get("customer") or "—",
            profile.get("revenue_model") or "—",
            profile.get("price_point") or "—",
            profile.get("startup_cost_usd") or "—",
            profile.get("weekly_hours") or "—",
            ", ".join(streams) or "—"))
    return {"title": "Venture: %s" % title,
            "description": description,
            "milestones": milestones}
