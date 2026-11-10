# Earnings-mention dataset — first look (2026-11-08, v1 build day)
Built from Kalshi's own settled history: 982 settled mention markets, 504 company+word base-rate keys, 64 live markets across 12 tech names. NOT trades — paper-call candidates for Nvidia's Nov 18, 2026 call (markets close Dec 2).

## NVDA live words vs their base rates (same word + threshold, past calls)
- **Self Driving** — ask 35¢ vs base rate 0.75 (3 of 4 past calls) → YES side paper candidate
- **Gaming** — ask 51¢ vs base 0.80 (4 of 5) → YES side paper candidate
- **Taiwan** — ask 49¢ vs base 0.20 (1 of 5) → NO side paper candidate
- **Domestic** — ask 26¢ vs base 0.00 (0 of 4) → NO side paper candidate
- **Trump** — ask 9¢ vs base 0.00 (0 of 5) → NO side, thin edge after price
- **Tariff** — ask 9¢ vs base 0.00 (0 of 4) for NVDA — but AMZN "tariff" is 5 of 5 YES. Same word, opposite company base rate: the dataset must stay per-company, never pooled.
- **Hyperscaler** — ask 93¢ vs base 1.00 (4 of 4) → consistent favorite, tiny edge, tiny fee
- New words with no base rate (Rubin 3+, Isaac, DSX, Rent/Renting): no call from history — transcript layer would be needed; Rubin at 95¢ is priced as near-certain by the crowd.

## Strongest repeat patterns in the full table (offered ≥5x)
- Always-yes so far: MSFT "openai" 6/6, AAPL "china" 5/5, AAPL "siri" 5/5, AAPL "manufacturing" 5/5, AMZN "alexa+" 5/5, AMZN "tariff" 5/5
- Never-yes so far: AAPL "m3" 0/5 (stale chip name — a word that stays offered after the world moved on), GOOGL "privacy" 0/6, AAPL "liquid glass" 0/3

## Honest limits
- n is small (most words offered 1–6 times). A 0.75 base rate on n=4 is a lean, not a probability.
- Kalshi chooses which words to offer — selection bias is built in; words are often chosen because the outcome is uncertain.
- Regimes change: a new product cycle can flip a word overnight (the "m3" pattern is exactly that).
- Every candidate above is a PAPER call for the Nov 18 NVDA call, to be scored after Dec 2 settlement — one full season of paper calls is the gate before any live stage (per the evaluation).
