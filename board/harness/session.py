"""
BoardSession: orchestrate one morning board meeting, end to end.

WHY:
    Choreography (2026-09-27, agenda switch 2026-10-21): brief → AGENDA
    LOOP → wave-2 closer → chair's 90% gate → record → VERIFY → minutes.
    Brian 2026-10-21 switched the board off the old shape — each seat
    picking 2-3 self-chosen calls, everything else silently unruled — to
    LOOPING THROUGH THE ENTIRE AGENDA QUEUE (harness.agenda; Brian's
    source: Atlas open gates + tasks). Every queued item gets exactly one
    call from its routed seat. The loop runs until the queue is empty or
    the agenda deadline (config agenda.deadline_s, default 3600s) hits;
    items left behind are NOT processed, NOT dropped — they stay queued
    and lead the next session, and the minutes say exactly how many
    carried over. The wave-2 closer (CFO) then consolidates over ALL the
    loop's calls, not a sample. The session is the product's heartbeat;
    every failure guard from the Sep 2026 post-mortem lives here: empty
    output is flagged (never silent), record is always followed by verify,
    and the hard deadline is enforced by the caller (cron), not by hope.

CALLED BY:
    - board/test_dryrun.py (manual verification)
    - The 3:30 AM board-of-directors-daily cron worker (production)
    - Any scheduler an entrepreneur wires to their own config.

NOTES:
    Items run SEQUENTIALLY — iGPU inference serializes concurrent requests
    anyway, and sequential keeps latencies predictable (~75s/item on
    Morpheus). Per 2026-10-08: each item FULLY completes (blocking retries
    with backoff, unbounded) before the next starts, and if the model API
    is slow the session WAITS rather than failing the item — the agenda
    deadline is therefore checked BETWEEN items, never mid-item. An
    overlap guard (lockfile) prevents a new session piling onto a
    still-running one. A session with zero usable calls is a FAILED
    session and says so in the minutes; a verify count below the recorded
    count is a PIPELINE failure and says so too. Neither is silent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .agenda import (
    AgendaItem, AgendaLedger, RulingsLedger, StuckStore, load_agenda, route,
)
from .brief import BriefBuilder
from .enrich import enrich_items
from .priority import score_item
from .gate import GatedCall, apply_gate
from .seats import Seat, load_config
from .sinks import Decision, DecisionSink, JsonlSink, SecondBrainSink
from .worker import ModelWorker, SeatResult


@dataclass
class AgendaResult:
    item: AgendaItem
    seat_result: SeatResult
    gated: GatedCall | None = None


@dataclass
class SessionResult:
    session_tag: str
    seat_results: list[SeatResult] = field(default_factory=list)
    agenda_results: list[AgendaResult] = field(default_factory=list)
    agenda_total: int = 0
    carried_over: list[AgendaItem] = field(default_factory=list)
    gated: list[GatedCall] = field(default_factory=list)
    recorded: int = 0
    verified: int = -1
    failed_seats: list[str] = field(default_factory=list)
    health_notes: list[str] = field(default_factory=list)
    minutes_path: str = ""

    @property
    def binding(self) -> list[GatedCall]:
        return [g for g in self.gated if g.verdict == "binding"]

    @property
    def recommendations(self) -> list[GatedCall]:
        return [g for g in self.gated if g.verdict == "recommendation"]


def make_sink(cfg: dict) -> DecisionSink:
    sink_cfg = cfg.get("sink", {"type": "jsonl", "path": "~/board-decisions.jsonl"})
    if sink_cfg.get("type") == "second_brain":
        return SecondBrainSink()
    return JsonlSink(sink_cfg.get("path", "~/board-decisions.jsonl"))


def make_worker(cfg: dict) -> ModelWorker:
    m = cfg.get("model", {})
    r = cfg.get("retry", {})
    return ModelWorker(
        base_url=m.get("base_url", "http://127.0.0.1:11437"),
        model=m.get("name", "morpheus"),
        timeout_s=int(m.get("timeout_s", 180)),
        max_tokens=int(m.get("max_tokens", 400)),
        temperature=float(m.get("temperature", 0.7)),
        via=m.get("via", "direct"),
        retry_base_s=float(r.get("base_s", 30)),
        retry_cap_s=float(r.get("cap_s", 300)),
    )


def acquire_session_lock() -> bool:
    """Overlap guard: if yesterday's session is still running (waiting on the
    API), the new cron invocation exits instead of piling on. Returns True if
    this process holds the lock."""
    import fcntl
    lock_path = os.path.expanduser("~/.board-session.lock")
    f = open(lock_path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another board session is still running; exiting (no pileup).")
        return False
    # Keep the file object alive for the process lifetime via a global.
    global _session_lock_fh  # noqa: PLW0603
    _session_lock_fh = f
    f.write(str(os.getpid()))
    f.flush()
    return True


class BoardSession:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.seats = [Seat.from_dict(s) for s in self.cfg.get("seats", [])]
        self.worker = make_worker(self.cfg)
        self.sink = make_sink(self.cfg)
        self.briefer = BriefBuilder()
        self.threshold = float(self.cfg.get("gate", {}).get("threshold", 0.90))
        self.tag = "board-" + datetime.now().strftime("%Y%m%d")

    # -- run -----------------------------------------------------------
    def run(self) -> SessionResult:
        import time

        res = SessionResult(session_tag=self.tag)
        started = time.monotonic()
        brief_keys = sorted({k for s in self.seats for k in s.brief_keys})
        brief = self.briefer.build(brief_keys)

        agenda_cfg = self.cfg.get("agenda", {})
        deadline_s = float(agenda_cfg.get("deadline_s", 3600))
        fallback_seat = agenda_cfg.get(
            "fallback_seat", "Chief Ecosystem Build Officer")
        minutes_dir = os.path.expanduser(
            self.cfg.get("minutes_dir", "~/workspace/altair-brain/inbox"))
        ledger = AgendaLedger(
            agenda_cfg.get("ledger_path")
            or os.path.join(minutes_dir, "board-agenda-ledger.jsonl"))

        # -- the agenda queue -------------------------------------------
        try:
            queue = load_agenda(self.cfg, ledger)
        except Exception as e:  # noqa: BLE001 - a broken queue must be loud
            queue = []
            res.health_notes.append(
                f"AGENDA PULL FAILED: {e} — the board cannot rule on a queue "
                "it cannot read; session continues to minutes only.")
        res.agenda_total = len(queue)
        if not queue and not res.health_notes:
            res.health_notes.append(
                "AGENDA QUEUE EMPTY: no open gates or tasks for the board "
                "to rule on. The board does not invent free-form calls.")

        # -- prep (Brian 2026-10-23): enrich, prioritize, persist -------
        # Enrichment writes the detail into each item before a seat
        # rules on it; priority orders the queue so the most important
        # decisions go first (scores + reasons are printed and
        # ledgered so Brian's feedback can tune the weights); the
        # rulings ledger + stuck store make every decision durable
        # the moment it exists.
        stuck_store = StuckStore(
            os.path.join(minutes_dir, "board-stuck-items.jsonl"))
        stuck_open = stuck_store.open_stuck() if queue else {}
        if queue:
            n_enriched = enrich_items(queue, via=agenda_cfg.get("via", "direct"))
            print(f"[prep] enriched {n_enriched}/{len(queue)} item(s) "
                  "with Atlas detail", flush=True)
            weights = (self.cfg.get("priority") or {}).get("weights")
            for item in queue:
                score_item(item, stuck_keys=set(stuck_open), weights=weights)
                note = stuck_open.get(item.key)
                if note:
                    item.text += (
                        "\n\nRE-PRESENTED AFTER A TIMEOUT "
                        f"({note.get('session_tag', 'earlier session')}): "
                        f"{note.get('analysis', '')}")
            queue.sort(key=lambda i: -i.priority_score)
            for item in queue[:10]:
                print(f"[priority] {item.priority_score:6.1f}  {item.key}  "
                      f"({'; '.join(item.priority_reasons) or 'no signals'})",
                      flush=True)
        rulings = RulingsLedger(
            os.path.join(minutes_dir, f"board-rulings-{self.tag}.jsonl"))
        res.health_notes.append(
            f"RULINGS LEDGER: {rulings.path} — every decision written "
            "the moment it is made (Brian 2026-10-23).")
        timeout_cfg = agenda_cfg.get("item_timeout") or {}
        timeout_multiple = float(timeout_cfg.get("multiple", 3.0))
        timeout_floor_s = float(timeout_cfg.get("floor_s", 240))
        timeout_min_samples = int(timeout_cfg.get("min_samples", 3))
        latencies: list[float] = []
        loop_gated_count = 0

        def item_budget() -> float:
            if len(latencies) >= timeout_min_samples:
                avg = sum(latencies) / len(latencies)
                return max(timeout_floor_s, timeout_multiple * avg)
            return timeout_floor_s

        # -- the loop: every item, one call, until empty or deadline -----
        closers = [s for s in self.seats if s.wave >= 2 and s.depends_on]
        processed: list[AgendaResult] = []
        for idx, item in enumerate(queue):
            if time.monotonic() - started > deadline_s:
                res.carried_over = queue[idx:]
                res.health_notes.append(
                    f"AGENDA CAP (2h, by design): {len(res.carried_over)} "
                    "item(s) not reached; the board ends on time and chips "
                    "at the queue next session. They stay queued and lead "
                    "it (not dropped, not marked processed).")
                break
            seat = route(item, self.seats, fallback_seat)
            budget = item_budget()
            print(f"[agenda {idx + 1}/{len(queue)}] {item.key} -> "
                  f"{seat.title} ({item.routing_reason}) "
                  f"[budget {budget:.0f}s]", flush=True)
            # BARRIER: this item fully completes (blocking retries inside,
            # bounded by the 3x item budget) before the next item starts.
            sr = self.worker.run_agenda_item(
                seat, item, brief.for_seat(seat.brief_keys),
                deadline_s=budget)
            res.seat_results.append(sr)
            if getattr(sr, "timed_out", False):
                # Brian 2026-10-23: stop it, analyze it, re-present it
                # tomorrow. The analysis rides the stuck record; the
                # priority pass next session boosts it to the front
                # with the analysis attached.
                if sr.last_raw:
                    analysis = (
                        f"Model answered {sr.attempts} time(s) but no "
                        "usable call was ever parsed. Last output began: "
                        f"{sr.last_raw[:280]!r}")
                else:
                    analysis = (
                        f"No usable model output in {sr.attempts} "
                        "attempt(s) (transport/empty); see session log.")
                stuck_event = {
                    "item_key": item.key, "kind": item.kind,
                    "title": item.title, "seat": seat.title,
                    "session_tag": self.tag, "attempts": sr.attempts,
                    "elapsed_s": round(sr.latency_s, 1),
                    "budget_s": round(budget, 1),
                    "analysis": analysis,
                    "last_raw": sr.last_raw[:1000],
                }
                rulings.append({"event": "stuck", **stuck_event})
                stuck_store.park(stuck_event)
                res.failed_seats.append(seat.title)
                res.health_notes.append(
                    f"STUCK (3x timeout): {item.key}: {seat.title}: "
                    f"{analysis} — parked; re-presents next session "
                    "with this analysis attached.")
                print(f"[agenda {idx + 1}/{len(queue)}] STUCK: "
                      f"{item.key} parked after {sr.latency_s:.0f}s",
                      flush=True)
                continue
            print(f"[agenda {idx + 1}/{len(queue)}] ruled: {seat.title} "
                  f"({sr.latency_s:.0f}s, {sr.attempts} attempt(s))", flush=True)
            if not sr.ok or not sr.calls:
                res.failed_seats.append(seat.title)
                res.health_notes.append(
                    f"{item.key}: {seat.title}: {sr.note or 'no usable call'} "
                    "— item NOT ledgered; it stays on the agenda.")
                continue
            latencies.append(sr.latency_s)
            call, rationale = sr.calls[0]
            seat_brief = brief.for_seat(seat.brief_keys)
            gated = apply_gate(
                call, rationale, seat.title, self.threshold,
                brief_had_state="NOT INSTRUMENTED" not in seat_brief)
            res.gated.append(gated)
            loop_gated_count += 1
            # PERSIST NOW (Brian 2026-10-23): the ruling hits the
            # durable ledger — and a binding call hits the sink — the
            # moment it exists, not at the end of the session.
            rulings.append({
                "event": "ruled", "session_tag": self.tag,
                "item_key": item.key, "kind": item.kind,
                "title": item.title, "seat": seat.title,
                "routing_reason": item.routing_reason,
                "priority_score": item.priority_score,
                "priority_reasons": item.priority_reasons,
                "call": call, "rationale": rationale,
                "confidence": gated.confidence, "verdict": gated.verdict,
                "latency_s": round(sr.latency_s, 1),
                "attempts": sr.attempts,
            })
            if gated.verdict == "binding":
                d = Decision(gated.call, gated.rationale, gated.seat_title,
                             gated.confidence, self.tag)
                if self.sink.record(d) is None:
                    res.health_notes.append(
                        f"RECORD FAILED: {gated.seat_title}: {gated.call[:80]}")
                else:
                    res.recorded += 1
            if item.key in stuck_open:
                stuck_store.resolve(item.key, self.tag)
            ar = AgendaResult(item=item, seat_result=sr, gated=gated)
            processed.append(ar)
            res.agenda_results.append(ar)
        else:
            if queue:
                print(f"[agenda] queue drained: {len(processed)} item(s) "
                      "ruled, queue empty.", flush=True)

        # -- wave-2 closer: consolidates over ALL loop calls -------------
        agenda_outputs: dict[str, SeatResult] = {}
        for ar in processed:
            prev = agenda_outputs.get(ar.seat_result.seat_title)
            if prev is None:
                agenda_outputs[ar.seat_result.seat_title] = SeatResult(
                    ar.seat_result.seat_title, list(ar.seat_result.calls),
                    "", True, 0.0, 1)
            else:
                prev.calls.extend(ar.seat_result.calls)
        for seat in closers:
            if not processed:
                break
            if time.monotonic() - started > deadline_s:
                res.health_notes.append(
                    f"CLOSER SKIPPED: {seat.title} — agenda deadline reached "
                    "during the loop; consolidation carries to next session.")
                break
            extra = self._format_wave_outputs(agenda_outputs, seat.depends_on)
            print(f"[closer] starting seat: {seat.title}", flush=True)
            sr = self.worker.run_seat(seat, brief.for_seat(seat.brief_keys), extra)
            res.seat_results.append(sr)
            print(f"[closer] seat complete: {seat.title} "
                  f"({sr.latency_s:.0f}s, {sr.attempts} attempt(s))", flush=True)
            if not sr.ok:
                res.failed_seats.append(seat.title)
                res.health_notes.append(f"{seat.title}: {sr.note}")
                continue
            seat_brief = brief.for_seat(seat.brief_keys)
            for call, rationale in sr.calls:
                res.gated.append(apply_gate(
                    call, rationale, seat.title, self.threshold,
                    brief_had_state="NOT INSTRUMENTED" not in seat_brief))

        # -- gate already applied per call; record + verify --------------
        if not res.gated:
            res.health_notes.append(
                "FAILED SESSION: zero usable calls from all seats. "
                "This is a fire-and-forget chat, not a board meeting."
            )
        else:
            # Agenda-loop binding calls were already recorded per item
            # (the moment they were made). Only the wave-2 closer's
            # calls remain to record here.
            for g in res.gated[loop_gated_count:]:
                if g.verdict != "binding":
                    continue
                d = Decision(g.call, g.rationale, g.seat_title, g.confidence, self.tag)
                if self.sink.record(d) is None:
                    res.health_notes.append(f"RECORD FAILED: {g.seat_title}: {g.call[:80]}")
                else:
                    res.recorded += 1
            res.verified = self.sink.verify(self.tag)
            if res.verified == -1:
                res.health_notes.append("VERIFY FAILED: could not query the sink back.")
            elif res.verified < res.recorded:
                res.health_notes.append(
                    f"PIPELINE FAILURE: recorded {res.recorded}, verified {res.verified}. "
                    "The decision pipeline is decorative until this is fixed."
                )

        # -- ledger: only items the board actually ruled on leave the queue
        for ar in processed:
            if ar.gated is not None:
                ledger.record(ar.item, ar.seat_result.seat_title,
                              ar.gated.verdict, self.tag)

        res.minutes_path = self._write_minutes(res)
        return res

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _format_wave_outputs(
        outputs: dict[str, SeatResult], depends_on: list[str]
    ) -> str:
        parts = []
        for title, sr in outputs.items():
            if depends_on and title not in depends_on:
                continue
            if not sr.ok:
                parts.append(f"{title}: (no output — seat failed)")
                continue
            calls = "\n".join(f"- {c} (why: {r})" for c, r in sr.calls)
            parts.append(f"{title}:\n{calls}")
        return "\n\n".join(parts)

    def _write_minutes(self, res: SessionResult) -> str:
        minutes_dir = os.path.expanduser(
            self.cfg.get("minutes_dir", "~/workspace/altair-brain/inbox")
        )
        os.makedirs(minutes_dir, exist_ok=True)
        path = os.path.join(minutes_dir, f"board-minutes-{self.tag}.md")
        L: list[str] = [
            f"# Board minutes — {self.tag}",
            "",
            f"Agenda queue: {res.agenda_total} item(s) at start | "
            f"ruled: {len(res.agenda_results)} | "
            f"carried over: {len(res.carried_over)}",
            f"Seat runs: {len(res.seat_results)} | failed: {len(res.failed_seats)}",
            f"Binding decisions recorded: {res.recorded} | verified: {res.verified}",
            f"Recommendations held for human: {len(res.recommendations)}",
            "",
        ]
        if res.health_notes:
            L += ["## Health", ""] + [f"- {n}" for n in res.health_notes] + [""]
        L += ["## Agenda rulings", ""]
        for ar in res.agenda_results:
            g = ar.gated
            verdict = (f"{g.verdict} @ {g.confidence:.2f}" if g else "ungated")
            call = ar.seat_result.calls[0][0] if ar.seat_result.calls else "(none)"
            L += [
                f"- [{ar.item.kind}: {ar.item.key}] -> {ar.seat_result.seat_title} "
                f"({ar.item.routing_reason}) — {verdict}: {call}",
            ]
        if res.carried_over:
            L += ["", "## Carried over (still queued, lead next session)", ""]
            for item in res.carried_over:
                L += [f"- [{item.kind}: {item.key}] {item.title}"]
        L += [""]
        L += ["## Binding decisions", ""]
        for g in res.binding:
            L += [f"- [{g.seat_title} @ {g.confidence:.2f}] {g.call}", f"  _{g.rationale}_"]
        L += ["", "## Recommendations (held by gate)", ""]
        for g in res.recommendations:
            L += [f"- [{g.seat_title}] {g.call} — {g.reason}"]
        L += ["", "## Seat outputs", ""]
        for sr in res.seat_results:
            status = "ok" if sr.ok else "FAILED"
            L += [f"### {sr.seat_title} ({status}, {sr.latency_s:.0f}s)"]
            for c, r in sr.calls:
                L += [f"- {c}", f"  _{r}_"]
            L += [""]
        with open(path, "w") as f:
            f.write("\n".join(L))
        return path


if __name__ == "__main__":
    import sys

    if not acquire_session_lock():
        sys.exit(2)
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "board/config/brian.yaml"
    result = BoardSession(cfg_path).run()
    print(f"session={result.session_tag} agenda_total={result.agenda_total} "
          f"agenda_ruled={len(result.agenda_results)} "
          f"carried_over={len(result.carried_over)} "
          f"seat_runs={len(result.seat_results)} "
          f"failed={result.failed_seats} binding_recorded={result.recorded} "
          f"verified={result.verified} recommendations={len(result.recommendations)}")
    print(f"minutes: {result.minutes_path}")
    for note in result.health_notes:
        print(f"HEALTH: {note}")
    sys.exit(0 if result.gated else 1)
