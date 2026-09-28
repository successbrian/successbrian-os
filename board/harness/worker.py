"""
Model worker: one stateless inference call per seat against an
OpenAI-compatible chat completions endpoint.

WHY:
    Each chief is an EPHEMERAL FOCUSED worker: one prompt in, one judgment
    out, no conversation state. Stateless HTTP keeps that honest — there is
    nowhere for stale opinions to accumulate between meetings. Retry-once +
    fluff detection exists because the Sep 2026 failure mode was sessions that
    "completed" with empty summaries; a worker that returns nothing useful
    must be flagged, never silently accepted.

CALLED BY:
    board.harness.session (BoardSession runs wave-1 then wave-2 seats).

NOTES:
    Transport: `direct` POSTs to base_url over HTTP (use when the harness runs
    on the same host as the model). `kssh` shells the curl through
    ~/workspace/bin/kssh (use when the harness runs on the VM and the model
    lives on k11-alpha, e.g. Morpheus at 127.0.0.1:11437 — localhost-only on
    k11). iGPU inference serializes concurrent requests anyway, so the
    session runs seats sequentially; do not add threading to "parallelize".
    Measured 2026-09-27: ~17s/chief on a short brief, ~75s on a long one;
    allow 180s timeouts.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field

from .seats import Seat

CALL_RE = re.compile(
    r"^\s*(?:\d+[.)]\s*|[-*]\s*)(.+?)(?:\s*/\s*Rationale:\s*(.+))?$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class SeatResult:
    seat_title: str
    calls: list[tuple[str, str]]  # (call sentence, rationale)
    raw: str
    ok: bool
    latency_s: float
    attempts: int
    note: str = ""


@dataclass
class ModelWorker:
    base_url: str  # e.g. http://127.0.0.1:11437
    model: str  # e.g. morpheus
    timeout_s: int = 180
    max_tokens: int = 400
    temperature: float = 0.7
    via: str = "direct"  # "direct" | "kssh"
    kssh_bin: str = "~/workspace/bin/kssh"

    def _payload(self, system: str, user: str) -> bytes:
        return json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
        ).encode()

    def _post(self, payload: bytes) -> str:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        if self.via == "kssh":
            # Model is localhost-only on k11; tunnel the curl through ssh.
            inner = (
                "curl -s -m {to} {url} -H 'Content-Type: application/json' "
                "--data-binary @-"
            ).format(to=self.timeout_s, url=url)
            cmd = f"{self.kssh_bin} {shlex_quote(inner)}"
            proc = subprocess.run(
                cmd,
                shell=True,
                input=payload,
                capture_output=True,
                timeout=self.timeout_s + 30,
            )
            out = proc.stdout.decode(errors="replace")
        else:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                out = resp.read().decode(errors="replace")
        data = json.loads(out)
        return data["choices"][0]["message"]["content"]

    def run_seat(
        self, seat: Seat, brief_text: str, extra_context: str = ""
    ) -> SeatResult:
        """Run one seat. Retries once on failure/empty; never silently accepts fluff."""
        import time

        user = f"BRIEF:\n{brief_text}"
        if extra_context:
            user += f"\n\nPRIOR WAVE OUTPUT (other chiefs have spoken; build on it):\n{extra_context}"
        user += "\n\nYour 2-3 calls:"

        last_raw, last_note, attempts = "", "", 0
        start = time.time()
        for attempt in (1, 2):
            attempts = attempt
            try:
                raw = self._post(self._payload(seat.system_prompt(), user))
            except Exception as e:  # noqa: BLE001 - transport failure is a seat failure
                last_note = f"transport error: {e}"
                last_raw = ""
                continue
            calls = parse_calls(raw)
            if len(calls) >= 2:
                return SeatResult(
                    seat.title, calls, raw, True, time.time() - start, attempts
                )
            last_raw, last_note = raw, f"only {len(calls)} usable call(s) parsed"
        return SeatResult(
            seat.title,
            parse_calls(last_raw),
            last_raw,
            False,
            time.time() - start,
            attempts,
            note=f"FAILED after {attempts} attempts: {last_note}. "
            "Flagged as board-health failure; not silently accepted.",
        )


def parse_calls(raw: str) -> list[tuple[str, str]]:
    """Parse numbered 'call / Rationale:' lines. Returns [(call, rationale)]."""
    calls: list[tuple[str, str]] = []
    for m in CALL_RE.finditer(raw or ""):
        call = (m.group(1) or "").strip()
        rationale = (m.group(2) or "").strip()
        if len(call) < 12:  # not a real call, skip fragments
            continue
        calls.append((call, rationale or "(no rationale given)"))
    # Deduplicate while preserving order.
    seen, out = set(), []
    for c in calls:
        if c[0].lower() not in seen:
            seen.add(c[0].lower())
            out.append(c)
    return out


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"
