# F5Bot (Reddit keyword alerts) — SPEC ONLY, needs Brian

Status: **NOT INSTALLED / NOT SIGNED UP** (2026-10-27, Tier 2 collectors build).
Wall: F5Bot (f5bot.com) is a free hosted service, but it requires
creating an account with an email address. Per standing rules, no
external account sign-ups without Brian — this is a needs-Brian item.

## What it would do
F5Bot watches Reddit posts/comments for keywords and emails alerts.
Keywords proposed — ONLY names on record for Brian's businesses/shows
(from Atlas/MEMORY, not invented):
- SuccessBrian OS
- TrafficStreemz
- CryptoStreemz
- AegeanVedaFlow
- GotBackup
- Zilara
- Oliabo
- ContactFlowCRM
- Qwemstral

## Where results would land
F5Bot emails its alerts. Those emails would be picked up by the
existing mail/intel flow and filed at the front door — Intel Bridge
captures (atlas.scattered_captures, kind=intel) — via the same
bridge-feeding pattern as bridge_poller.py, so Brian sees them in the
normal brief, not in a separate inbox silo.

## What Brian needs to do (one step)
Create the F5Bot account himself (f5bot.com, his email), add the
keywords above (or trim the list), and say "done" — then the alert
emails can be wired into the Bridge feeder in under an hour.
Alternative if Brian prefers no new account: a self-hosted Reddit
keyword watcher is possible but Reddit API access ALSO requires an
account/app registration — same wall, more work. Recommendation:
F5Bot, Brian signs up.
