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
        )

    def system_prompt(self) -> str:
        lines = [
            f"You are the {self.title} on a board of directors.",
            f"Your domain: {self.domain}.",
            f"Your mandate: {self.mandate}.",
            "You are an EPHEMERAL title spot: you exist for this one meeting,",
            "make big-picture calls (direction, priorities, start/stop), then dissolve.",
            "You do NOT do the domain's work — you govern it with fresh eyes.",
            "Return exactly 2-3 calls. Each call: ONE sentence, then a ONE-line rationale.",
            "Format: numbered list, each item as: <call sentence> / Rationale: <one line>.",
            "Be decisive. Vague filler ('increase marketing efforts') is a failure.",
        ]
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
