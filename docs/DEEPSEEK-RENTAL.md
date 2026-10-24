# DeepSeek V4 Pro — rental model

## The one thing to know

Brian **rents** DeepSeek V4 Pro API access from **InstantlyClaw.com**.
The API key belongs to them, not to Brian. Topping up the balance is the
owner's job — never Brian's, and never something to ask him for.

(Standing order recorded in Altair's August 2026 session dumps;
re-confirmed by Brian 2026-09-27.)

## How availability is tracked

`tools/v4pro_balance.py` probes the rental key once an hour (via the
`v4pro_balance_check` automation rule):

- The HTTPS check runs **on k11-alpha**, where the rental key lives in
  `~/.hermes/.env` (`DEEPSEEK_API_KEY`). The key never leaves that machine
  and is never stored on any other VM, in files, or in notes — only the
  parsed balance result crosses back.
- Endpoint: `GET https://api.deepseek.com/user/balance` (DeepSeek's own
  documented endpoint; a free call that spends no quota).
- **Available** means `is_available=true` AND total USD > $1.00.
  Dust doesn't count as a usable rental.
- The result flips the `v4pro_credits` flag in `tools/model_tiers.py`
  state. When the rental refills, the `v4pro_routing` rule announces the
  transition to the inbox and hard tasks flow back to the cloud tier.

## Current state (verified 2026-09-27)

Rental key is live but **exhausted**: `is_available=false`, `-0.00 USD`.
Flag correctly reads exhausted, which is why Altair's profile currently
defaults to the local Morpheus model. Nothing for Brian to do — when
InstantlyClaw refills, the hourly check sees it and routing resumes
on its own.

## The owned path (added 2026-10-20)

The rental stays the burst top tier for hard tasks when funded. In
parallel, the fleet is building owned V4-class capacity: the DeepSeek V4
Flash REAP 150B build (85 GB, Colibri streaming) on k11-alpha today, with
DL380 slices and cheap DDR4 nodes as background lanes (see MODELS.md,
"Streaming tier", and docs/fleet-map.md, expansion idea 9). The 150B is
retired as a routing tier — the local nodes contribute inference capacity;
they don't take the rental's place in routing, and none of this changes
the key handling above.
