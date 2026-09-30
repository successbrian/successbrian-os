# Morpheus Listing Vet (DealsDesk)

Second pair of eyes on deal candidates. A rules engine flags listings as
STEAL / EXCELLENT_DEAL / SNATCH / GREAT_DEAL; rules are blind to
deception. Morpheus reads the listing text and flags what the scorer got
wrong - free, local, zero AI credits.

## Why

Brian 2026-09-30: "this isn't a motherboard, it's an I/O shield. this
isn't a hard drive, it's a hard drive caddy. this is a drop down scam,
not a hot deal. this one the market value is not right."

## What it catches

- TITLE/ITEM MISMATCH: actual item is a part/accessory, not what the
  title claims (I/O shield vs motherboard, caddy vs hard drive).
- DROPDOWN SCAM: displayed price is for a cheaper variant; the
  pictured/described item costs more.
- MARKET VALUE WRONG: claimed market_value wildly off (2x+) for what
  the item actually is. Obvious errors only - the model's price
  knowledge may be stale.
- OTHER DECEPTION: hidden "for parts", quantity tricks, counterfeits.

## Components

- Canonical: `tools/dealsdesk/listing_vet.py`
- Deployed: `/home/successbrian/.hermes/profiles/dealsdesk/scripts/listing_vet.py`
- Cron: `dealsdesk-listing-vet` on the dealsdesk profile, --no-agent,
  `17 */4 * * *` (every 4h, offset from the 4hr sweep).
- State: `/home/successbrian/.hermes/profiles/dealsdesk/state/listing_vet_state.json`

## Flow

1. Fetch up to 60 unvetted active listings in the top 4 tiers
   (STEAL first, newest first). Vetted = `deal_flags ? 'vet'`.
2. Vet in batches of 6 per Morpheus call (~10 min per run).
3. For each: set `ai_processed=true`, stamp `ai_processed_at`, merge
   `deal_flags->'vet' = {verdict, reason, by, at}`.
4. If any FLAGs: one bridge row sender='dealsdesk' target='spencer'
   (routine) listing them. Zero flags: quiet, heartbeat only.

## Boundaries

- The vet FLAGS, it never re-tiers: `deal_tier` is untouched. Re-tiering
  on a vet FLAG is a pipeline/Brian decision (open item).
- When unsure, PASS: no flag without confidence. Brian's attention is
  the scarce resource; false flags cost more than missed edge cases.
- Pricing-data policy: output stays inside the ecosystem (DB flags +
  bridge rows). Nothing publishable is generated.
- Honest limit: the vet sees title + price + market_value + body_text.
  Dropdown scams whose variant table isn't in the text may slip through;
  title/description mismatches are its strength.
