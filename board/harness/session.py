"""
BoardSession: orchestrate one morning board meeting, end to end.

WHY:
    This is the choreography Brian specified 2026-09-27: brief → wave-1 chiefs
    → wave-2 closer (CFO consolidates money after the others) → chair's 90%
    gate → record → VERIFY → minutes. The session is the product's heartbeat;
    every failure guard from the Sep 2026 post-mortem lives here: empty
    output is flagged (never silent), record is always followed by verify,
    and the hard deadline is enforced by the caller (cron), not by hope.

CALLED BY:
    - board/test_dryrun.py (manual verification)
    - The 3:30 AM board-of-directors-daily cron worker (production)
    - Any scheduler an entrepreneur wires to their own config.

NOTES:
    Seats run SEQUENTIALLY even across waves — iGPU inference serializes
    concurrent requests anyway, and sequential keeps latencies predictable
    (~75s/seat on Morpheus). Wave-2 seats receive the formatted wave-1
    outputs as extra context. A session with zero usable calls is a FAILED
    session and says so in the minutes; a verify count below the recorded
    count is a PIPELINE failure and says so too. Neither is silent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .brief import BriefBuilder
from .gate import GatedCall, apply_gate
from .seats import Seat, load_config, load_seats
from .sinks import Decision, DecisionSink, JsonlSink, SecondBrainSink
from .worker import ModelWorker, SeatResult


@dataclass
class SessionResult:
    session_tag: str
    seat_results: list[SeatResult] = field(default_factory=list)
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
    return ModelWorker(
        base_url=m.get("base_url", "http://127.0.0.1:11437"),
        model=m.get("name", "morpheus"),
        timeout_s=int(m.get("timeout_s", 180)),
        max_tokens=int(m.get("max_tokens", 400)),
        temperature=float(m.get("temperature", 0.7)),
        via=m.get("via", "direct"),
    )


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
        res = SessionResult(session_tag=self.tag)
        brief_keys = sorted({k for s in self.seats for k in s.brief_keys})
        brief = self.briefer.build(brief_keys)

        by_wave: dict[int, list[Seat]] = {}
        for s in self.seats:
            by_wave.setdefault(s.wave, []).append(s)

        wave_outputs: dict[str, SeatResult] = {}
        for wave in sorted(by_wave):
            for seat in by_wave[wave]:
                extra = ""
                if seat.depends_on:
                    extra = self._format_wave_outputs(wave_outputs, seat.depends_on)
                sr = self.worker.run_seat(seat, brief.for_seat(seat.brief_keys), extra)
                wave_outputs[seat.title] = sr
                res.seat_results.append(sr)
                if not sr.ok:
                    res.failed_seats.append(seat.title)
                    res.health_notes.append(f"{seat.title}: {sr.note}")

        # Chair's gate over every usable call.
        for sr in res.seat_results:
            brief_had_state = "NOT INSTRUMENTED" not in brief.for_seat([])
            for call, rationale in sr.calls:
                res.gated.append(
                    apply_gate(call, rationale, sr.seat_title, self.threshold, brief_had_state)
                )

        if not res.gated:
            res.health_notes.append(
                "FAILED SESSION: zero usable calls from all seats. "
                "This is a fire-and-forget chat, not a board meeting."
            )
        else:
            for g in res.binding:
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
            f"Seats run: {len(res.seat_results)} | failed: {len(res.failed_seats)}",
            f"Binding decisions recorded: {res.recorded} | verified: {res.verified}",
            f"Recommendations held for human: {len(res.recommendations)}",
            "",
        ]
        if res.health_notes:
            L += ["## Health", ""] + [f"- {n}" for n in res.health_notes] + [""]
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

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "board/config/brian.yaml"
    result = BoardSession(cfg_path).run()
    print(f"session={result.session_tag} seats={len(result.seat_results)} "
          f"failed={result.failed_seats} binding_recorded={result.recorded} "
          f"verified={result.verified} recommendations={len(result.recommendations)}")
    print(f"minutes: {result.minutes_path}")
    for note in result.health_notes:
        print(f"HEALTH: {note}")
    sys.exit(0 if result.gated else 1)
