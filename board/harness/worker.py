"""
Model worker: one stateless inference call per seat against an
OpenAI-compatible chat completions endpoint.

WHY:
    Each chief is an EPHEMERAL FOCUSED worker: one prompt in, one judgment
    out, no conversation state. Stateless HTTP keeps that honest — there is
    nowhere for stale opinions to accumulate between meetings. Per 2026-10-08
    the worker WAITS on the model API: transport errors and thin outputs
    retry with exponential backoff (30s base, 300s cap), unbounded — a seat
    never fails just because the API was slow. Fluff is still never silently
    accepted: attempts are logged and the wait is visible in the minutes.
    Retry-once was the Sep 2026 behavior; the Oct 2026 failure mode was
    sessions "completing" with seats missing because the API was slow.

CALLED BY:
    board.harness.session (BoardSession: agenda items via run_agenda_item,
    wave-2 closer via run_seat).

AGENDA MODE (Brian 2026-10-21):
    The session no longer asks each seat for 2-3 self-chosen calls. It
    loops the agenda queue (harness.agenda) and calls run_agenda_item once
    per item: one item in, exactly one call out.

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
from dataclasses import dataclass

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
    last_raw: str = ""      # last model output seen, kept even on failure
    timed_out: bool = False  # True when the item budget (3x rule) stopped us
    returned: str = ""  # SBOS PATCH 2026-10-25: seat sent the packet back; this is its needs statement


@dataclass
class ModelWorker:
    base_url: str  # e.g. http://127.0.0.1:11437
    model: str  # e.g. morpheus
    timeout_s: int = 180
    max_tokens: int = 400
    temperature: float = 0.7
    via: str = "direct"  # "direct" | "kssh"
    kssh_bin: str = "~/workspace/bin/kssh"
    retry_base_s: float = 30.0  # first wait between attempts; doubles each retry
    retry_cap_s: float = 300.0  # max wait between attempts (5 min)

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
        """Run one seat for a synthesis/closer pass (e.g. the wave-2 CFO
        consolidation, or test_dryrun). BLOCKS until the seat completes:
        transport errors and thin/unparseable outputs are retried with
        exponential backoff, no attempt cap. Per Brian 2026-10-08: if we're
        waiting on the model API, we WAIT — a seat never fails just because
        the API was slow, and the next seat never starts until this one is
        done."""
        user = f"BRIEF:\n{brief_text}"
        if extra_context:
            user += f"\n\nPRIOR WAVE OUTPUT (other chiefs have spoken; build on it):\n{extra_context}"
        user += "\n\nYour calls:"
        return self._run_blocking(seat, seat.system_prompt(), user, min_calls=1)

    def run_agenda_item(
        self, seat: Seat, item, brief_text: str, deadline_s: float | None = None
    ) -> SeatResult:
        """Rule on ONE agenda item (Brian 2026-10-21 agenda-loop switch).

        The prompt carries the brief for context plus the item itself; the
        seat must return exactly one call on that item. Only the FIRST
        parsed call is kept — one item, one ruling — so a seat cannot pad
        an item into a list. Same blocking-retry discipline as run_seat.
        `item` is a harness.agenda.AgendaItem (duck-typed: key/kind/title/
        text/theme)."""
        user = (
            f"BRIEF:\n{brief_text}\n\n"
            f"AGENDA ITEM [{item.kind}: {item.key}]\n"
            f"Title: {item.title}\n"
            + (f"Theme: {item.theme}\n" if getattr(item, "theme", "") else "")
            + f"Item: {item.text}\n\n"
            "Your ONE call on this item:"
        )
        result = self._run_blocking(
            seat, seat.system_prompt(agenda_item=True), user, min_calls=1,
            deadline_s=deadline_s, allow_return=True,
        )
        if result.ok and len(result.calls) > 1:
            result.calls = result.calls[:1]
        return result

    def run_first_read(
        self, seat: Seat, item, brief_text: str,
        deadline_s: float | None = None,
    ) -> SeatResult:
        """First read (Brian 2026-10-25, adopted flow): the seat reads
        ONE agenda item and returns QUESTIONS ONLY — no ruling. The
        questions ride SeatResult.calls as (question, '') tuples."""
        user = (
            f"BRIEF:\n{brief_text}\n\n"
            f"AGENDA ITEM [{item.kind}: {item.key}]\n"
            f"Title: {item.title}\n"
            + (f"Theme: {item.theme}\n" if getattr(item, "theme", "") else "")
            + f"Item: {item.text}\n\n"
            "Your questions (ASK: lines only):"
        )
        return self._run_blocking(
            seat, seat.system_prompt(first_read=True), user, min_calls=1,
            deadline_s=deadline_s,
            parse=lambda raw: [(q, "") for q in parse_questions(raw)])

    def _run_blocking(
        self, seat: Seat, system: str, user: str, min_calls: int = 1,
        deadline_s: float | None = None, allow_return: bool = False,
        parse=None,  # flowv2
    ) -> SeatResult:
        """Blocking retry loop. With deadline_s=None this is the 2026-10-08
        discipline: wait forever, a seat never fails because the API was
        slow. With deadline_s set (agenda items, Brian 2026-10-23) the
        item has a budget — 3x the session's running average decision
        time: exceeding it STOPS the item (timed_out result, last output
        preserved) so the session can park it for analysis and move on,
        instead of one unparseable item eating the whole meeting like
        task:gb40:closing-kit did in the 2026-10-23 beta. The budget is
        soft by at most one in-flight call (timeout_s) plus one backoff
        slice."""
        import time

        attempt, backoff = 0, self.retry_base_s
        start = time.time()
        last_raw = ""
        while True:
            attempt += 1
            try:
                raw = self._post(self._payload(system, user))
                last_raw = raw or last_raw
            except Exception as e:  # noqa: BLE001 - transport failure -> wait, retry
                elapsed = time.time() - start
                if deadline_s is not None and elapsed > deadline_s:
                    return SeatResult(
                        seat.title, [], last_raw, False, elapsed, attempt,
                        note=(f"TIMEOUT: item budget {deadline_s:.0f}s "
                              f"exceeded during transport retries ({e}); "
                              "parked for analysis, re-presents next session"),
                        last_raw=last_raw, timed_out=True)
                print(f"[{seat.title}] attempt {attempt}: transport error "
                      f"({e}); waiting {backoff:.0f}s then retrying "
                      f"(elapsed {elapsed:.0f}s)", flush=True)
                wait = backoff
                if deadline_s is not None:
                    wait = min(wait, max(0.0, deadline_s - elapsed))
                time.sleep(wait)
                backoff = min(backoff * 2, self.retry_cap_s)
                continue
            if allow_return:
                needs = parse_return(raw)
                if needs:
                    return SeatResult(
                        seat.title, [], raw, True, time.time() - start,
                        attempt, note=f"RETURNED to clerk: {needs}",
                        returned=needs)
            calls = parse(raw) if parse else parse_calls(raw)
            if len(calls) >= min_calls:
                return SeatResult(
                    seat.title, calls, raw, True, time.time() - start, attempt
                )
            elapsed = time.time() - start
            if deadline_s is not None and elapsed > deadline_s:
                return SeatResult(
                    seat.title, [], last_raw, False, elapsed, attempt,
                    note=(f"TIMEOUT: item budget {deadline_s:.0f}s exceeded "
                          f"after {attempt} attempt(s) with 0 usable calls "
                          "parsed; last model output preserved in the "
                          "stuck record for analysis; item re-presents "
                          "next session"),
                    last_raw=last_raw, timed_out=True)
            print(f"[{seat.title}] attempt {attempt}: only {len(calls)} usable "
                  f"call(s) parsed; waiting {backoff:.0f}s then retrying "
                  f"(elapsed {elapsed:.0f}s)", flush=True)
            wait = backoff
            if deadline_s is not None:
                wait = min(wait, max(0.0, deadline_s - elapsed))
            time.sleep(wait)
            backoff = min(backoff * 2, self.retry_cap_s)


BARE_CALL_RE = re.compile(
    r"^(.{12,}?)\s*/\s*Rationale:\s*(.+)$", re.IGNORECASE | re.MULTILINE
)


RETURN_RE = re.compile(r"^\s*RETURN\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_return(raw: str) -> str | None:
    """SBOS PATCH 2026-10-25: a seat's send-back. The seat answers a
    packet it cannot judge well with 'RETURN: <what it needs>' and the
    packet goes back to the clerk instead of forcing a thin call."""
    m = RETURN_RE.search(raw or "")
    return m.group(1).strip() if m else None


ASK_RE = re.compile(
    r"^\s*(?:[-*]\s*|\d+[.)]\s*)?ASK\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE)


def parse_questions(raw: str) -> list[str]:
    """SBOS PATCH 2026-10-25 (flowv2): first-read 'ASK: ...' lines."""
    out, seen = [], set()
    for m in ASK_RE.finditer(raw or ""):
        q = m.group(1).strip()
        if len(q) >= 8 and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def parse_calls(raw: str) -> list[tuple[str, str]]:
    """Parse 'call / Rationale:' lines. Returns [(call, rationale)].

    Tier 1: the numbered/bulleted format the seat prompt asks for.
    Tier 2 (Brian 2026-10-23, the closing-kit lesson): if NO numbered
    call parses, accept the same shape WITHOUT the leading number —
    'Approve the thing / Rationale: why'. In the 2026-10-23 beta the
    CFO produced exactly that, a good ruling, and the strict parser
    discarded it ~25 times while the session stalled to death. A
    ruling must never die over a missing '1.'."""
    calls: list[tuple[str, str]] = []
    for m in CALL_RE.finditer(raw or ""):
        call = (m.group(1) or "").strip()
        rationale = (m.group(2) or "").strip()
        if len(call) < 12:  # not a real call, skip fragments
            continue
        calls.append((call, rationale or "(no rationale given)"))
    if not calls:
        for m in BARE_CALL_RE.finditer(raw or ""):
            call = (m.group(1) or "").strip()
            rationale = (m.group(2) or "").strip()
            if len(call) < 12 or call.lower().startswith(("rationale", "format")):
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
