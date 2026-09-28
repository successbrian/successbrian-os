"""
BriefBuilder: assemble the per-session brief from pluggable state pullers.

WHY:
    A board can only govern what it can see. The Sep 2026 post-mortem found
    "revenue silence" — the board claimed to track revenue while the revenue
    tables sat empty. So the brief has a hard rule: a puller that finds no
    state must say "NOT INSTRUMENTED" explicitly. Faking state (or quietly
    omitting a domain) is how boards deliberate on fiction.

CALLED BY:
    board.harness.session (BoardSession.build_brief).

NOTES:
    Pullers are registered by name in PULLERS. A seat's `brief_keys` selects
    which sections it receives; every seat also gets the shared context
    (night-shift report, recent decisions, pending items). Brian's real
    pullers shell to kssh/psql — they are the BENT half; the generic harness
    ships stub pullers that return NOT INSTRUMENTED so a new entrepreneur sees
    exactly what to wire up.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from dataclasses import dataclass, field

NOT_INSTRUMENTED = "NOT INSTRUMENTED — no data source wired for this domain yet."


def _kssh(cmd: str, timeout: int = 30) -> str:
    try:
        proc = subprocess.run(
            os.path.expanduser("~/workspace/bin/kssh") + " " + _q(cmd),
            shell=True,
            capture_output=True,
            timeout=timeout,
        )
        return proc.stdout.decode(errors="replace").strip()
    except Exception as e:  # noqa: BLE001
        return f"PULLER ERROR: {e}"


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------- Brian's pullers
def pull_night_shift_report() -> str:
    """Most recent night-shift report from the altair-brain inbox."""
    paths = sorted(
        glob.glob(
            os.path.expanduser(
                "~/workspace/altair-brain/inbox/*night-shift-report*.md"
            )
        )
    )
    if not paths:
        return "No night-shift report found in the inbox."
    try:
        with open(paths[-1]) as f:
            text = f.read()
        return f"({os.path.basename(paths[-1])}) {text[:1500]}"
    except OSError as e:
        return f"PULLER ERROR: {e}"


def pull_recent_decisions(hours: int = 24, limit: int = 12) -> str:
    """High/medium-confidence second-brain decisions from the last N hours."""
    sql = (
        "SELECT topic, confidence, created_at FROM second_brain "
        f"WHERE created_at > now() - interval '{hours} hours' "
        f"AND category='decision' ORDER BY created_at DESC LIMIT {limit};"
    )
    out = _kssh(f"psql -d ecosystem_central -tAc {_q(sql)}")
    if not out or out.startswith("PULLER ERROR"):
        return out or "No recent decisions recorded."
    lines = [l for l in out.splitlines() if l.strip()]
    return "\n".join(f"- {l}" for l in lines) or "No recent decisions recorded."


def pull_marketer_watch_offers() -> str:
    """Offers pushed by the affiliate marketers Brian watches (last 30 days).

    Brian 2026-09-28: watching top affiliate earners should reveal the best
    offers for HIM to promote — the signal is "what offers they're pushing,"
    aggregated so multi-marketer pushes rank highest. Sources the local
    marketer-watch seen db via tools/marketer_watch.py --offers (not psql);
    offers enter the db during enrichment (--enrich-summary --offer) or via
    backfill (--set-offer). Loud on failure, never silent.
    """
    script = os.path.expanduser(
        "~/workspace/successbrian-os/tools/marketer_watch.py")
    try:
        proc = subprocess.run(
            [sys.executable, script, "--offers"],
            capture_output=True, timeout=60,
        )
        out = proc.stdout.decode(errors="replace").strip()
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            return f"PULLER ERROR (marketer_watch --offers rc={proc.returncode}): {err}"
        return out or "No marketer-watch offer data returned."
    except Exception as e:  # noqa: BLE001 - a broken puller must not kill the session
        return f"PULLER ERROR (marketer_watch --offers): {e}"


def stub_puller(domain: str):
    """Generic fallback: marks the domain as not instrumented."""

    def _pull() -> str:
        return f"{NOT_INSTRUMENTED} (domain: {domain}) — wire a puller in brief.py."

    _pull.__name__ = f"stub_{domain}"
    return _pull


# Registry: brief_key -> puller callable.
PULLERS: dict[str, callable] = {
    "night_shift": pull_night_shift_report,
    "recent_decisions": pull_recent_decisions,
    # Brian's domain pullers: bent stubs for now — each returns NOT
    # INSTRUMENTED until a real data source is wired. The board flags these.
    "blog_pipeline": stub_puller("blog_pipeline"),
    "video_readiness": stub_puller("video_readiness"),
    "hiro_fm": stub_puller("hiro_fm"),
    "mlm": stub_puller("mlm"),
    "affiliate": stub_puller("affiliate"),
    "marketer_watch_offers": pull_marketer_watch_offers,
    "systemeio": stub_puller("systemeio"),
    "leads": stub_puller("leads"),
    "trading": stub_puller("trading"),
    "flipping": stub_puller("flipping"),
    "ecosystem_build": stub_puller("ecosystem_build"),
}


@dataclass
class Brief:
    shared: str  # every seat sees this
    sections: dict[str, str] = field(default_factory=dict)

    def for_seat(self, brief_keys: list[str]) -> str:
        parts = [self.shared]
        for key in brief_keys:
            if key in self.sections:
                parts.append(f"[{key}]\n{self.sections[key]}")
        return "\n\n".join(parts)


class BriefBuilder:
    """Assemble a Brief from registered pullers."""

    def __init__(self, pullers: dict[str, callable] | None = None):
        self.pullers = pullers or PULLERS

    def build(self, brief_keys: list[str]) -> Brief:
        shared = "\n\n".join(
            [
                "[night_shift]\n" + self._run("night_shift"),
                "[recent_decisions]\n" + self._run("recent_decisions"),
            ]
        )
        sections = {k: self._run(k) for k in brief_keys if k not in ("night_shift", "recent_decisions")}
        return Brief(shared=shared, sections=sections)

    def _run(self, key: str) -> str:
        puller = self.pullers.get(key)
        if puller is None:
            return f"{NOT_INSTRUMENTED} (no puller registered for '{key}')."
        try:
            return puller() or NOT_INSTRUMENTED
        except Exception as e:  # noqa: BLE001 - a broken puller must not kill the session
            return f"PULLER ERROR for '{key}': {e}"
