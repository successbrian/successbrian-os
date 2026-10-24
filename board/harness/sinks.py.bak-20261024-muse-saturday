"""
DecisionSink: where binding decisions land, plus the VERIFY step.

WHY:
    The Sep 2026 post-mortem's core finding: the old board's decision
    pipeline was DECORATIVE — schema existed but no engine executed any leg,
    so sessions "completed" while 440/441 tasks sat pending. A sink without
    verify() is that same trap. Every sink must be able to query back what it
    recorded so the session can COUNT decisions and declare failure when the
    count is zero. Record-then-verify is the execution engine.

CALLED BY:
    board.harness.session (record binding calls; verify counts afterwards).

NOTES:
    SecondBrainSink shells to tools/second_brain.py (Brian's bent sink) and
    verifies with a kssh psql count filtered by session tag + created_at.
    JsonlSink is the GENERIC fallback: any entrepreneur gets a working
    record+verify loop with zero infrastructure. Add new sinks by subclassing
    DecisionSink — never by branching inside session.py.
"""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Decision:
    call: str
    rationale: str
    seat_title: str
    confidence: float
    session_tag: str
    tags: list[str] = field(default_factory=list)


class DecisionSink(ABC):
    @abstractmethod
    def record(self, decision: Decision) -> str | None:
        """Persist one binding decision. Returns an id, or None on failure."""

    @abstractmethod
    def verify(self, session_tag: str) -> int:
        """Query back: how many decisions landed for this session tag?"""


def _run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


class SecondBrainSink(DecisionSink):
    """Brian's bent sink: PostgreSQL second_brain via tools/second_brain.py."""

    TOOL = os.path.expanduser("~/workspace/successbrian-os/tools/second_brain.py")
    KSSH = os.path.expanduser("~/workspace/bin/kssh")

    def record(self, decision: Decision) -> str | None:
        tags = ",".join(["board", decision.session_tag] + decision.tags)
        content = (
            f"[{decision.seat_title} | confidence {decision.confidence:.2f}] "
            f"{decision.call} Rationale: {decision.rationale}"
        )
        cmd = (
            f"python3 {_q(self.TOOL)} --topic {_q('Board decision: ' + decision.call[:120])} "
            f"--content {_q(content)} --category decision --confidence high "
            f"--source board-of-directors --tags {_q(tags)}"
        )
        proc = _run(cmd)
        if proc.returncode != 0:
            return None
        return proc.stdout.decode(errors="replace").strip() or "ok"

    def verify(self, session_tag: str) -> int:
        sql = (
            "SELECT count(*) FROM second_brain "
            f"WHERE '{session_tag}' = ANY(tags) AND category='decision';"
        )
        proc = _run(f"{self.KSSH} {_q(f'psql -d ecosystem_central -tAc {_q(sql)}')}")
        try:
            return int(proc.stdout.decode(errors="replace").strip())
        except (ValueError, TypeError):
            return -1  # verify itself failed; session must report, not assume


class JsonlSink(DecisionSink):
    """Generic fallback sink: append-only JSONL file. Works for anyone."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def record(self, decision: Decision) -> str | None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_tag": decision.session_tag,
            "seat": decision.seat_title,
            "confidence": decision.confidence,
            "call": decision.call,
            "rationale": decision.rationale,
            "tags": decision.tags,
        }
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(row) + "\n")
            return f"jsonl:{row['ts']}"
        except OSError:
            return None

    def verify(self, session_tag: str) -> int:
        try:
            with open(self.path) as f:
                return sum(
                    1
                    for line in f
                    if json.loads(line).get("session_tag") == session_tag
                )
        except (OSError, json.JSONDecodeError):
            return -1
