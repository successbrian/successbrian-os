# Affiliate Monetization Strategy System

Turn one affiliate program into a portfolio of revenue lanes, playbooks,
and metrics.

**Pairing:** `tools/affiliate_program_check.py` answers *should I promote
this?* (the recurring-forever promote filter). This system answers
*how do I earn with it, and which lane is working?*

## Concepts

- **Program** — one affiliate program: terms, commission summary, cookie,
  payout minimum, status.
- **Lane** — one distinct way to earn with the program: review SEO,
  tutorials, video, email, bonus stacking, done-for-you services, agency
  referrals, coupons, community, paid traffic, lead magnets, webinars,
  case studies, social, partnerships. Each lane has effort, expected
  payoff, program-rule notes, status (idea → planned → active → paused),
  and actual earnings/referrals.
- **Playbook** — reusable content for a program or a lane: email
  sequences, review templates, video scripts, bonus frameworks.
- **Metrics** — monthly clicks, conversions, earnings per program or lane.
- **Notes** — strategy notes and research findings per program.

## Quick start

```bash
cd ~/successbrian-os/tools/affiliate_monetization
python3 affiliate_monetization.py init-db
python3 affiliate_monetization.py new-program kinsta --name "Kinsta" \
  --commission-summary "$50-$500 upfront + 10% lifetime recurring" \
  --cookie-days 60 --payout-minimum 50 --my-role "lead WP hosting lane"
python3 affiliate_monetization.py add-lane kinsta "Review SEO" \
  --lane-type review --effort medium --expected-payoff high \
  --why-it-works "high-intent buyers search best-hosting lists"
python3 affiliate_monetization.py report kinsta
```

The module runs against k11 Postgres (localhost psql from k11), same as
`tools/audience` and `tools/industry_map`. Seed data is Brian's; the
schema is generic.
