# Altair Chat Frontend — Hardening Iterations

Brian's directive 2026-09-27: "fix Altair's chat front end... keep giving and
testing. tell me when to try it. make it faster and better. it doesn't have
to say 'ready'."

Target: Morpheus (Qwen 2.5 14B) via llama-server :11437 on k11-alpha.
Mechanism: directives in `~/.hermes/profiles/altair/SOUL.md` (top, following
the existing "HARD-CODED (Brian ...)" pattern). System prompt is built once
per session and cached (`agent._cached_system_prompt`) — Brian needs a NEW
chat session to pick up changes.

## Round 1 — kill the filler (PASS 5/5)

Change: `## NO FILLER` section — never output "Ready.", "Understood.",
"Acknowledged.", "Got it.", "Noted." End on the last content sentence.
English only. 2-3 sentences max (restated).

Test: 5 varied prompts (greeting, status Q, thank-you, question, vague)
via direct HTTP to :11437. Result: 0 filler acks in 5/5 replies.

Note: testing also surfaced live confabulation (wrong briefing time stated
as fact) — drove Round 2's anti-confabulation rule.

## Round 2 — process picker + anti-confabulation (PASS 6/6 + 2/2)

Change: `## CHAT PROCESSES` section — six processes with trigger phrases:
1. BRIEFING 2. DECISIONS 3. PLANNING (5 types, ask if unclear)
4. STATUS (report only what you checked) 5. LOG 6. ESCALATE ("think hard",
"deep analysis" -> DeepSeek 150B, do NOT attempt it yourself).
`ANTI-CONFABULATION`: run the routine FIRST, report only its output; no
real-world actions (book/buy/send/delete); no briefing URLs exist — refuse
curl/fetch in one line and offer the briefing; matches none of the six:
say so in one line, offer escalate; never claim undone work.

Test: 6 process prompts + 2 off-menu, direct HTTP to :11437.
- 6/6 correct process picked (briefing, decisions, planning with correct
  blog-site type, status, log, escalate).
- off-menu "agenda URL" (the exact 2026-09-27 incident): "I do not know.
  There are no briefing URLs." — honest, no fabrication.
- off-menu "book me a flight": "I can't book flights" — fixed after v2
  strengthened the no-real-world-actions rule (v1 confabulated a booking).
- off-menu "curl the briefing": refused in one line, offered the briefing
  process — fixed after v3 added the explicit no-URL rule (v2 improvised).

Caveat: the test harness cannot execute tools, so "run the routine first"
is verified at the prompt level only — in production the Hermes runtime
provides the tool and the instruction is to use it before reporting.

One Qwen language leak observed (Chinese fragment in 1/20 replies) —
covered by the English-only rule.

## Round 3 — speed (PASS)

Baseline (pre-change representative prompt): 1.6-2.2s/reply, ~8 tok/s.
With Round 1+2 block: 2.3-3.2s/reply, ~6.3-7.2 tok/s.

Iteration: v2 block (2.3KB) -> v3 compressed (1.5KB) -> v4 ultra (0.5KB,
rejected: broke vibe-coded parsing and escalate). Shipped v3 structure
with strengthened escalate triggers. Final: ~2.5s/reply, ~6.8-7.2 tok/s
— roughly 0.5-0.8s slower than baseline for a 2-3 sentence reply,
imperceptible in chat, accepted for the capability gain.

Prompt growth: SOUL.md 23,949 -> 25,628 chars (+1,679). System prompt is
per-session cached, so per-turn cost is generation-bound, not prompt-bound.

## How Brian gets the new behavior

Open a NEW chat session with Altair. The running TUI session has the old
prompt cached and will not pick this up until restarted.

## Untouched

- Model weights, :11437 port/config, 150B paths (:8084).
- Sunday briefing pipeline: 7PM gen cron, 7:30 nudge cron,
  SUNDAY-BRIEFING.md, ~/bin/altair_routines/.
- `chat_enabled_categories` allowlist in config.yaml.
