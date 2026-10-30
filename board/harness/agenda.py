"""
Agenda: the board's queue — what the session loops through, item by item.

WHY (Brian 2026-10-21):
    The board used to let each seat pick 2-3 big-picture calls from the
    brief and dissolve. Anything that did not make a seat's top 2-3 was
    never ruled on — the queue sat while the board "completed" (the Sep
    2026 post-mortem failure in a new costume). Brian switched the session:
    the board now LOOPS THROUGH THE ENTIRE AGENDA QUEUE. Every agenda item
    gets exactly one call from its owning seat, gated and recorded, until
    the queue is empty or the session deadline hits. Items the deadline
    leaves behind are NOT dropped and NOT marked processed — they stay in
    the queue and lead the next session. An item leaves the queue only
    when the board has actually made a call on it (binding -> sink;
    recommendation -> held for the human in the minutes). That is queue
    semantics: processed drains, unprocessed carries over, nothing is
    silently skipped.

AGENDA SOURCE (Brian 2026-10-21):
    Atlas open gates + tasks — atlas.nodes in ecosystem_central:
      gates: node_type='gate',       status='pending'
      tasks: node_type='atlas_task', status IN ('open','queued')
    Gates first (they are decisions waiting), then tasks oldest-first
    (node_key order). The puller NEVER mutates Atlas: the board proposes,
    Atlas remains the record of record until Brian or a worker acts.
    Processed items are tracked in the board's own ledger (JSONL, same
    pattern as the needs queue) and excluded from future agendas.

ROUTING:
    Each item is routed to ONE seat, deterministically, and the routing
    reason lands in the minutes so Brian can audit/correct it:
      1. Theme map (inbox-triage themes -> seat titles), when that seat
         sits in this session's roster.
      2. Keyword scoring: token overlap between the item text and each
         seat's title/domain/mandate/brief_keys.
      3. Fallback: the session's fallback seat (config agenda.fallback_seat,
         default Chief Ecosystem Build Officer — the ecosystem generalist;
         most Atlas items are ecosystem questions).
    Wave-2 closer seats still close after the loop; they may also own
    items (money-allocation -> CFO is the obvious one).

GENERIC vs BENT:
    AgendaItem + the ledger + routing are generic. AtlasAgenda is Brian's
    bent source (psql, direct or via kssh like the brief pullers).
    JsonlAgenda is the generic source: a JSONL file of
    {"key","kind","title","text","theme"} rows any entrepreneur can fill.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field

from .seats import Seat

# Inbox-triage themes (atlas task details->>'theme') -> preferred seat title.
THEME_SEAT = {
    "money-allocation": "Chief Financial Officer",
    "security-boundary": "Chief Compliance Officer",
    "privacy": "Chief Compliance Officer",
    "data-policy": "Chief Knowledge Officer",
    "architecture-direction": "Chief Ecosystem Build Officer",
    "scope": "Chief Ecosystem Build Officer",
}

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-']+")
_STOP = {
    "the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "by",
    "is", "are", "should", "may", "what", "which", "whether", "if", "it",
    "its", "be", "as", "at", "from", "with", "into", "this", "that",
    "chief", "officer", "board", "directors",
}


@dataclass
class AgendaItem:
    key: str            # Atlas node_key (or file-queue key)
    kind: str           # "gate" | "task"
    title: str
    text: str           # full question / item text the seat rules on
    theme: str = ""
    status: str = ""
    seat_title: str = ""        # filled by route()
    routing_reason: str = ""    # filled by route()
    meta: dict = field(default_factory=dict)  # filled by enrich (Atlas row data)
    priority_score: float = 0.0               # filled by priority.score_item
    priority_reasons: list = field(default_factory=list)


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def route(item: AgendaItem, seats: list[Seat], fallback_title: str) -> Seat:
    """Deterministically assign the item to one seat; record why."""
    by_title = {s.title: s for s in seats}
    preferred = THEME_SEAT.get(item.theme or "")
    if preferred and preferred in by_title:
        item.seat_title = preferred
        item.routing_reason = f"theme '{item.theme}' -> {preferred}"
        return by_title[preferred]
    item_words = _words(item.title + " " + item.text + " " + item.theme)
    best, best_score = None, 0
    for seat in seats:
        seat_words = _words(
            seat.title + " " + seat.domain + " " + seat.mandate + " "
            + " ".join(seat.brief_keys) + " " + " ".join(seat.constraints)
        )
        score = len(item_words & seat_words)
        if score > best_score:
            best, best_score = seat, score
    if best is not None:
        item.seat_title = best.title
        item.routing_reason = f"keyword score {best_score} -> {best.title}"
        if preferred:
            item.routing_reason += f" (theme seat '{preferred}' not in roster)"
        return best
    seat = by_title.get(fallback_title) or seats[0]
    item.seat_title = seat.title
    item.routing_reason = f"no theme/keyword match -> fallback {seat.title}"
    if preferred:
        item.routing_reason += f" (theme seat '{preferred}' not in roster)"
    return seat


# ---------------------------------------------------------------- ledger
class AgendaLedger:
    """Append-only JSONL of items the board has actually ruled on.

    An item is in the ledger iff a seat produced a usable call on it
    (binding or recommendation). Failed seats and deadline carry-overs
    are never written — the item stays on tomorrow's agenda.
    """

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def processed_keys(self) -> set[str]:
        keys = set()
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        keys.add(json.loads(line)["item_key"])
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, KeyError):
            # A corrupt ledger must not silently empty the queue; an
            # unreadable ledger means "trust nothing, re-serve the queue".
            return set()
        return keys

    def record(self, item: AgendaItem, seat_title: str, verdict: str,
               session_tag: str) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        row = {
            "item_key": item.key,
            "kind": item.kind,
            "seat": seat_title,
            "verdict": verdict,
            "session_tag": session_tag,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")


class RulingsLedger:
    """Per-decision durable record (Brian 2026-10-23, the beta lesson).

    The 2026-10-23 beta ruled 72 items and lost every one of them:
    rulings lived only in process memory until the end-of-session
    record step, and the session died first. This ledger is appended
    THE MOMENT each ruling is made (flush + fsync): whatever happens
    later in the session — a stall, a crash, a kill — every completed
    decision is already on disk, with its call, rationale, gate
    confidence and verdict, its seat and routing reason, and the
    priority score that ordered it. Stuck items are appended too,
    with their timeout analysis and the model's last raw output."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())


class StuckStore:
    """Parked items (Brian 2026-10-23): an item that blows its 3x time
    budget is parked here with its analysis; next session it is
    re-presented — boosted to the front of the priority order with
    the analysis attached to its text — instead of silently looping
    or silently vanishing. Events: 'stuck' (parked) and 'resolved'
    (later ruled); the latest event per key wins."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def park(self, event: dict) -> None:
        self._append({"event": "stuck", **event})

    def resolve(self, item_key: str, session_tag: str) -> None:
        self._append({"event": "resolved", "item_key": item_key,
                      "session_tag": session_tag})

    def open_stuck(self) -> dict:
        latest: dict = {}
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = row.get("item_key")
                    if not key:
                        continue
                    if row.get("event") == "stuck":
                        latest[key] = row
                    elif row.get("event") == "resolved":
                        latest.pop(key, None)
        except FileNotFoundError:
            pass
        return latest


# ---------------------------------------------------------------- sources
def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


ATLAS_AGENDA_SQL = (
    "SELECT node_key, node_type, name, status, coalesce(details::text, '{}') "
    "FROM atlas.nodes "
    "WHERE (node_type = 'gate' AND status = 'pending') "
    "OR (node_type = 'atlas_task' AND status IN ('open', 'queued')) "
    "ORDER BY (node_type = 'gate') DESC, node_key;"
)


def _parse_atlas_rows(out: str) -> list[AgendaItem]:
    items = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        key, ntype, name, status, details_txt = parts[:5]
        try:
            details = json.loads(details_txt) if details_txt else {}
        except json.JSONDecodeError:
            details = {}
        text = (details.get("question") or details.get("about")
                or name or "").strip()
        items.append(AgendaItem(
            key=key.strip(),
            kind="gate" if ntype == "gate" else "task",
            title=(name or key).strip(),
            text=text,
            theme=(details.get("theme") or "").strip(),
            status=status.strip(),
        ))
    return items


class AtlasAgenda:
    """Brian's bent agenda: Atlas open gates + tasks from ecosystem_central.

    Transport mirrors brief.py: `direct` runs psql here; `kssh` shells the
    psql through ~/workspace/bin/kssh (harness on the VM, DB on k11-alpha).
    """

    def __init__(self, via: str = "kssh"):
        self.via = via

    def fetch(self) -> list[AgendaItem]:
        if self.via == "kssh":
            kssh = os.path.expanduser("~/workspace/bin/kssh")
            inner = f"psql -d ecosystem_central -tAF '\t' -c {_q(ATLAS_AGENDA_SQL)}"
            proc = subprocess.run(f"{kssh} {_q(inner)}", shell=True,
                                  capture_output=True, timeout=60)
            out = proc.stdout.decode(errors="replace")
        else:
            proc = subprocess.run(
                ["psql", "-d", "ecosystem_central", "-tAF", "\t", "-c",
                 ATLAS_AGENDA_SQL],
                capture_output=True, timeout=60)
            out = proc.stdout.decode(errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                "agenda pull failed: "
                + proc.stderr.decode(errors="replace").strip()[:300])
        return _parse_atlas_rows(out)


class JsonlAgenda:
    """Generic agenda: a JSONL queue file of {key, kind, title, text, theme}."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def fetch(self) -> list[AgendaItem]:
        items = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                items.append(AgendaItem(
                    key=d["key"], kind=d.get("kind", "task"),
                    title=d.get("title", d["key"]),
                    text=d.get("text", d.get("title", "")),
                    theme=d.get("theme", ""), status=d.get("status", "")))
        # Gates first, then file order (the file is the queue).
        items.sort(key=lambda i: 0 if i.kind == "gate" else 1)
        return items


def load_agenda(cfg: dict, ledger: AgendaLedger) -> list[AgendaItem]:
    """Fetch the queue and drop items the board has already ruled on."""
    a = cfg.get("agenda", {})
    if a.get("source") == "jsonl":
        source = JsonlAgenda(a.get("path", "~/board-agenda.jsonl"))
    else:
        source = AtlasAgenda(via=a.get("via", "kssh"))
    done = ledger.processed_keys()
    return [i for i in source.fetch() if i.key not in done]


class SendbackStore:
    """Returned packets (Brian 2026-10-25): a seat that cannot make a good
    call on a packet sends it back to the clerk with a statement of what
    it needs. The store is the clerk's intake: an append-only jsonl in the
    minutes dir — the same place Altair's overnight routines already look
    (the evening needs-pass precedent). Events: 'returned' (seat, item,
    needs) and 'resent' (the clerk re-presented the packet with the need
    met); the latest event per key wins, so open_needs() is the clerk's
    live work list. A returned item is NOT ruled and NOT consumed: it
    stays on the agenda until it is ruled or Brian drops it."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def record_return(self, event: dict) -> None:
        self._append({"event": "returned", **event})

    def mark_resent(self, item_key: str, session_tag: str) -> None:
        self._append({"event": "resent", "item_key": item_key,
                      "session_tag": session_tag})

    def open_needs(self) -> dict:
        latest: dict = {}
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = row.get("item_key")
                    if not key:
                        continue
                    if row.get("event") == "returned":
                        latest[key] = row
                    elif row.get("event") == "resent":
                        latest.pop(key, None)
        except FileNotFoundError:
            pass
        return latest


class QuestionsStore:
    """First-read questions (Brian 2026-10-25, adopted flow): every
    reader seat's ASK lines for a packet, appended the moment they are
    asked. This file is the CLERK'S DEEPENING INTAKE: the clerk reads
    the questions, answers what the house holds, files requests for the
    rest, and the packet is processed again. Events carry the item key,
    the seat, and its questions; by_item() groups the latest session's
    questions per item for the clerk's pass."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def record(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({"event": "questions", **event}) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def by_item(self) -> dict:
        grouped: dict = {}
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = row.get("item_key")
                    if key and row.get("event") == "questions":
                        grouped.setdefault(key, []).append(row)
        except FileNotFoundError:
            pass
        return grouped
