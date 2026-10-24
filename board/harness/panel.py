#!/usr/bin/env python3
"""Four-seat wave-1 panel (Brian, 2026-10-24 02:23 CDT).

RULED CORE: wave 1 judges each item from FOUR DIFFERENT SEAT PROFILES —
the four best seats for that item, each judging independently. NOT four
draws of one seat.

SELECTION (interim, from tonight's panel simulation): theme seat first
if it is a wave-1 seat in the roster, then highest keyword fit among
wave-1 seats (same _words scoring as agenda.route), ties broken by
roster order for determinism. CFO and all wave-2 seats are excluded —
the CFO is the wave-2 closer, not a wave-1 judge. Later replacement,
not yet built: chair assignment by seat record + domain fit (clerk-box
spec), which supersedes keyword fit when it exists.

NOT WIRED INTO session.py YET. Tonight's 02:30 session still runs one
seat per item (agenda.route). Integration, with Brian's go, is: the
session loop replaces route() + a single run_agenda_item() with
judge_panel(), records all four rulings, and flags splits to the
CFO/Brian instead of forcing a single verdict.

AGREEMENT (v2): each call is read as approve / reject / escalate /
other from its opening verb family (allow, proceed, prepare and keep
count as approve; do not approve counts as reject). A panel is
unanimous only when all four direction families match; anything else
is a SPLIT and is flagged, never averaged away. Separately, an OVERREACH flag fires when a call
approves a purchase on an item whose text says it is a spec / not an
approved purchase — the clerk-box case, where all four seats can
"approve" and still disagree on what they approved. Gate confidence
still applies per ruling, as in the single-seat loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .agenda import THEME_SEAT, _words
from .gate import apply_gate

PANEL_SIZE = 4


def rank_seats(item, wave1_seats):
    """Return [(seat, score, reason)] best-first, distinct seats only."""
    wave1 = [s for s in wave1_seats if s.wave == 1]
    by_title = {s.title: s for s in wave1}
    ranked = []
    preferred = THEME_SEAT.get(item.theme or "")
    if preferred and preferred in by_title:
        ranked.append((by_title[preferred], 999, f"theme '{item.theme}'"))
    item_words = _words(item.title + " " + item.text + " " + item.theme)
    scored = []
    for seat in wave1:
        if any(seat.title == s.title for s, _, _ in ranked):
            continue
        seat_words = _words(
            seat.title + " " + seat.domain + " " + seat.mandate + " "
            + " ".join(seat.brief_keys) + " " + " ".join(seat.constraints)
        )
        scored.append((seat, len(item_words & seat_words)))
    scored.sort(key=lambda t: (-t[1], wave1.index(t[0])))
    for seat, score in scored:
        ranked.append((seat, score, f"keyword score {score}"))
    return ranked


def best_four(item, wave1_seats):
    """The four best distinct wave-1 seats for this item."""
    return rank_seats(item, wave1_seats)[:PANEL_SIZE]


_REJECT_STARTS = ("reject", "do not approve", "don't approve", "decline",
                  "deny", "refuse", "not approve")
_ESCALATE_STARTS = ("escalate", "send back", "request clarification",
                    "defer", "park")
_APPROVE_STARTS = ("approve", "allow", "proceed", "prepare", "keep",
                   "continue", "accept", "endorse", "confirm", "use ",
                   "treat", "define", "proceed with")


def direction(call: str) -> str:
    """Direction family of a call, from its opening words (v2).

    v1 only knew approve/reject, so 'Allow', 'Prepare', 'Keep' and
    'Escalate' all fell into 'other' and a unanimous panel whose seats
    worded the same decision differently was flagged as a split
    (live evidence 2026-10-24: inbox-552 and inbox-554, all four seats
    agreed, split=True). v2 maps opening verbs to three families:
    approve (incl. allow/proceed/prepare/keep), reject (incl. do-not-
    approve), escalate. Anything else is 'other' and still counts as
    its own family for split purposes — unclassifiable is uncertainty,
    not agreement.
    """
    text = (call or "").strip().lower()
    head = text[:48]
    if any(head.startswith(s) for s in _REJECT_STARTS) or " reject " in f" {head} ":
        return "reject"
    if any(head.startswith(s) for s in _ESCALATE_STARTS):
        return "escalate"
    if any(head.startswith(s) for s in _APPROVE_STARTS) or " approve " in f" {head} ":
        return "approve"
    if "reject" in head:
        return "reject"
    if "approve" in head:
        return "approve"
    return "other"


@dataclass
class PanelRuling:
    seat_title: str
    call: str
    rationale: str
    confidence: float
    verdict: str
    latency_s: float = 0.0
    attempts: int = 1


@dataclass
class PanelResult:
    item_key: str
    seats: list
    rulings: list = field(default_factory=list)
    split: bool = False
    overreach: bool = False
    directions: dict = field(default_factory=dict)
    item_title: str = ""
    item_text: str = ""

    def finalize(self):
        dirs = {}
        for r in self.rulings:
            dirs[direction(r.call)] = dirs.get(direction(r.call), 0) + 1
        self.directions = dirs
        self.split = len(dirs) > 1
        spec_item = ("spec" in self.item_title.lower()
                     or "not an approved purchase" in self.item_text.lower())
        self.overreach = bool(spec_item and any(
            "purchase" in r.call.lower() for r in self.rulings))
        return self


def judge_panel(worker, item, seats, brief_for_seat, deadline_s=300, threshold=0.90):
    """Judge one item with the best four seats, sequentially.

    worker: an object with run_agenda_item(seat, item, brief_text,
    deadline_s=...) returning an object with .calls, .latency_s,
    .attempts, .ok — the harness ModelWorker, or a stub with the same
    shape for testing. Each seat judges independently: no seat sees
    another seat's call.
    """
    four = best_four(item, seats)
    result = PanelResult(item_key=item.key, seats=[s.title for s, _, _ in four],
                         item_title=item.title, item_text=item.text)
    for seat, score, reason in four:
        sr = worker.run_agenda_item(seat, item, brief_for_seat(seat), deadline_s=deadline_s)
        if not getattr(sr, "ok", False) or not getattr(sr, "calls", None):
            continue
        call, rationale = sr.calls[0]
        gated = apply_gate(call, rationale, seat.title, threshold,
                           brief_had_state=True)
        result.rulings.append(PanelRuling(
            seat_title=seat.title, call=call, rationale=rationale,
            confidence=gated.confidence, verdict=gated.verdict,
            latency_s=getattr(sr, "latency_s", 0.0),
            attempts=getattr(sr, "attempts", 1)))
    return result.finalize()
