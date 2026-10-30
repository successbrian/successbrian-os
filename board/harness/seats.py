"""
Seat definitions: load C-level title spots from YAML.

WHY:
    The board's seats are EPHEMERAL TITLE SPOTS (hats directors wear for one
    meeting), not worker jobs and not hardcoded roles. YAML keeps the seat
    roster a config concern so a new entrepreneur bends the board without
    touching code — the generic-at-first half of the product.

CALLED BY:
    board.harness.session (BoardSession loads config at session start).

NOTES:
    Seat schema: {title, domain, mandate, wave, depends_on, brief_keys,
    constraints}. wave=1 seats run first; wave=2 seats receive wave-1 outputs
    (e.g. a CFO closer with depends_on listing every wave-1 title).
    Constraints are hard rules injected into the seat's system prompt
    (e.g. "strategy only, never trade signals").
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class Seat:
    title: str
    domain: str
    mandate: str
    wave: int = 1
    depends_on: list[str] = field(default_factory=list)
    brief_keys: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    profile: str = ""  # SBOS PATCH 2026-10-25: the seat's well-defined profile

    @classmethod
    def from_dict(cls, d: dict) -> "Seat":
        return cls(
            title=d["title"],
            domain=d.get("domain", ""),
            mandate=d.get("mandate", ""),
            wave=int(d.get("wave", 1)),
            depends_on=list(d.get("depends_on", []) or []),
            brief_keys=list(d.get("brief_keys", []) or []),
            constraints=list(d.get("constraints", []) or []),
            profile=str(d.get("profile", "") or ""),
        )

    def system_prompt(self, agenda_item: bool = False,
                    first_read: bool = False) -> str:  # flowv2
        lines = [
            f"You are the {self.title} on a board of directors.",
            f"Your domain: {self.domain}.",
            f"Your mandate: {self.mandate}.",
            "You are an EPHEMERAL title spot: you exist for this one meeting,",
            "make big-picture calls (direction, priorities, start/stop), then dissolve.",
            "You do NOT do the domain's work — you govern it with fresh eyes.",
        ]
        if self.profile:
            lines += ["", "YOUR PROFILE — who you are as this officer:", self.profile]
        if first_read:
            # SBOS PATCH 2026-10-25 (adopted flow): a first read asks.
            lines += [
                "This is a FIRST READ: on a first read the board does NOT "
                "rule, vote, or decide. Your only job is to read this "
                "packet and ASK — say what you need to know more about "
                "before it could be judged well.",
                "Return ONLY your questions, one per line, each starting "
                "'ASK: '. Ask about missing facts, data from your domain "
                "that is not here, unclear framing, prior decisions, and "
                "standing rules that might touch this. One to five "
                "questions. If the packet belongs squarely to another "
                "seat, ask that ('ASK: should this go to ...?').",
            ]
        elif agenda_item:
            # Agenda mode (Brian 2026-10-21): the board loops the agenda
            # queue; this seat rules on ONE queued item at a time.
            lines += [
                "You are ruling on ONE agenda item — the item in the user message.",
                "Return exactly ONE call on that item. The call: ONE sentence, then a ONE-line rationale.",
                "Format: 1. <call sentence> / Rationale: <one line>",
                "Rule on the item itself — approve it, reject it, send it back with "
                "conditions, or escalate it — do not drift into general advice.",
                # SBOS PATCH 2026-10-25: the send-back (Brian's ruling).
                "If you cannot make a good call on this packet — the facts "
                "you need are missing, your domain data is not in the brief, "
                "or the problem is not framed well enough to judge — do NOT "
                "guess. Return the packet instead, as your WHOLE answer: "
                "'RETURN: <what you need, in one or two lines>'. The clerk "
                "takes it from there. A returned packet is a good outcome; "
                "a confident bad call is not.",
            ]
        else:
            lines += [
                "Return your calls — one per decision in front of you. Each call: ONE sentence, then a ONE-line rationale.",
                "Format: numbered list, each item as: <call sentence> / Rationale: <one line>.",
            ]
        lines.append(
            "Be decisive. Vague filler ('increase marketing efforts') is a failure."
        )
        if self.constraints:
            lines.append("Hard constraints (violating one invalidates your output):")
            lines.extend(f"- {c}" for c in self.constraints)
        return "\n".join(lines)


def load_seats(path: str) -> list[Seat]:
    """Load seats from a YAML file. Top-level key: `seats` (list)."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return [Seat.from_dict(d) for d in data.get("seats", [])]


def load_config(path: str) -> dict:
    """Load the full board config (seats + model + gate + sink + deadlines)."""
    with open(path) as f:
        return yaml.safe_load(f) or {}
