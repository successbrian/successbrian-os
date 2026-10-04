# Onboarding Vision — the interview before the scoring

Per Brian 2026-10-04. This is a directive for Altair, not a suggestion.

## The principle

The system must learn what game the person wants to play **before** it
scores any opportunity. Scoring a candidate against a user whose
preferences were never asked is scoring against a stranger.

## The boot interview (as early as possible)

At first boot, a conversational agent — ideally Altair — guides the new
user through setup as a conversation, not a form. It asks, at minimum:

1. **How do you feel about MLM / network marketing as a way to earn?**
   promoter (I build this) / open (fine if the product is good) / avoid (not for me)
2. **How do you feel about affiliate marketing?** Same three answers.
3. **What kinds of income streams do you want?**
   mlm, affiliate, own-product, services, content, investing — pick any.
4. **Recurring monthly income, fast cash per sale, or both?**

No ethical coaching. People who chose MLM want help finding high-value
MLMs for themselves and their followers — not a lecture on the choice
itself. (This is why the focus coach's perception axis is a pride test,
not a smell test.)

## Tier routing (per Brian 2026-10-04)

The conversational boot interview is a **DeepSeek V4 Pro cloud-tier** job —
it needs top-tier conversational quality, not the local workhorse. It is
**blocked on the cloud API**: the InstantlyClaw rental is currently dry
(balance -$0.01, is_available=false as of 2026-10-04; the hourly
`v4pro_balance.py` check will see when it refills).

Until then, the shipping path is the deterministic fallback:
`tools/setup/init.py` asks the same questions as a script. No user waits on
the cloud. When the rental refills, the conversational interviewer (Altair
on the V4 Pro tier) takes over the boot conversation; the user model format
it writes is identical, so nothing migrates.

## Where the answers live

`tools/focus/user_focus.json` → `"values"`. This file is the **user model**:
gitignored, private, never committed. The deterministic fallback interview
is `tools/setup/init.py` (same questions, script form, for users who
prefer to self-serve or where no agent is present).

## How the system uses it

`tools/focus/focus.py` reads the user model and surfaces values alignment
as **flags, never hidden score tweaks**:

- candidate's stream type ∈ preferred types → `values-aligned`
- candidate's stream type ∈ avoided stances → `values-mismatch`
- recurring-vs-fast-cash mismatch → `income-style-mismatch`

The score stays deterministic and explainable; the user's values stay
visible in the output, not buried in the math.

## Continuous adaptation

The boot interview is not a one-time event. The local successbrian-os
should keep matching the person's unique ecosystem for as long as they
use it:

- Altair keeps the user model current as the user evolves (new streams,
  changed stances, audiences they can actually reach).
- Personalization lives in the user model + the modules that read it —
  never in forked or hand-edited code. The same public codebase serves
  every user; the private config makes it theirs.
- When the user model changes, past evaluations can be re-run to show
  what the new preferences change. Nothing is silently re-decided; the
  user re-decides with better information.

Scores propose. The user decides. The system remembers who the user is.
