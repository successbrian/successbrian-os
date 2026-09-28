"""
The 90% gate: BOARD PROPOSES, CHAIR DISPOSES.

WHY:
    The board is breadth — narrow domain lenses, fast, some junk. The chair
    is depth — full cross-domain context, standing rules, known pitfalls. The
    gate forces every chief's call through the chair's deeper knowledge before
    it becomes a decision the ecosystem acts on. Without the gate the board
    is an advice firehose; with it, it's governance. Below threshold the call
    is HELD as a recommendation (for the human), never silently dropped and
    never auto-executed.

CALLED BY:
    board.harness.session (BoardSession.apply_gate over every seat call).

NOTES:
    Scoring is a deterministic heuristic, not a truth meter — the numbers are
    documented so a future agent can retune them deliberately. Hard holds
    (external actions, unverified data, irreversible moves) ALWAYS fall below
    threshold per the Sep 2026 doctrine, no matter how confident the seat.
    The gate never invents calls; it only classifies the board's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTERNAL_ACTION_RE = re.compile(
    # Bare nouns like "email sequence" must NOT trigger; only real outbound acts.
    r"\b(post|publish|launch|deploy|outreach|broadcast|dm\b)\b|\bsend\b",
    re.IGNORECASE,
)
UNVERIFIED_RE = re.compile(
    r"\b(data shows|metrics show|revenue is|report says|according to)\b", re.IGNORECASE
)
IRREVERSIBLE_RE = re.compile(
    r"\b(delete|shut down|shutdown|cancel .*contract|terminate|wipe|migrate .*production)\b",
    re.IGNORECASE,
)
VAGUE_RE = re.compile(
    r"\b(improve|increase|optimize|enhance|boost).{0,20}(efforts|marketing|things|stuff|overall)\b",
    re.IGNORECASE,
)


@dataclass
class GatedCall:
    call: str
    rationale: str
    seat_title: str
    confidence: float
    verdict: str  # "binding" | "recommendation"
    reason: str


def score_call(call: str, rationale: str, brief_had_state: bool) -> tuple[float, list[str]]:
    """Heuristic confidence in [0,1] plus human-readable penalty reasons."""
    score, reasons = 0.95, []
    text = f"{call} {rationale}"
    if EXTERNAL_ACTION_RE.search(text):
        score -= 0.30
        reasons.append("external action (post/publish/outreach) always needs the human")
    if IRREVERSIBLE_RE.search(text):
        score -= 0.40
        reasons.append("irreversible move cannot auto-execute")
    if UNVERIFIED_RE.search(text) and not brief_had_state:
        score -= 0.25
        reasons.append("cites data the brief did not provide")
    if VAGUE_RE.search(text) or len(call.split()) < 5:
        score -= 0.15
        reasons.append("vague or too thin to act on")
    if len(rationale.split()) < 5:
        score -= 0.10
        reasons.append("rationale missing or one word")
    return max(0.0, round(score, 2)), reasons


def apply_gate(
    call: str,
    rationale: str,
    seat_title: str,
    threshold: float = 0.90,
    brief_had_state: bool = True,
) -> GatedCall:
    confidence, reasons = score_call(call, rationale, brief_had_state)
    if confidence >= threshold:
        verdict, reason = "binding", f"passed at {confidence:.2f} ≥ {threshold:.2f}"
    else:
        verdict = "recommendation"
        why = "; ".join(reasons) if reasons else "below threshold"
        reason = f"HELD at {confidence:.2f} < {threshold:.2f}: {why}"
    return GatedCall(call, rationale, seat_title, confidence, verdict, reason)
