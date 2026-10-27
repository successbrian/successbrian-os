# Secrets Rotation Checklist — Brian, one sitting (~45–60 min)

**STATUS: ROTATION NOT DONE. Nothing was rotated, revoked, or modified by the scan.**
This checklist is executed BY BRIAN AT THE KEYBOARD. An agent prepared it; only Brian rotates.
Scan basis (2026-10-27): TruffleHog 3.99.7 in VERIFIED mode over all fleet git repos
(full history) + filesystem scan of crontabs / systemd units / shell scripts / Hermes
scheduled-job dirs. Inventory (credential TYPES and locations only — no values anywhere):
PostgreSQL `successbrian_os.secret_findings` (1,332 rows; 967 verified-live rows,
which dedupe to the 4 live credentials below — the row count is high because the same
tokens were echoed into hundreds of cron-output and backup files).

## Step 0 — Create your vault account FIRST (~5 min)
1. Open Vaultwarden (your new password vault, running on k11-alpha, NOT public):
   - From any Tailscale device: http://100.118.53.47:8222
   - On alpha itself: http://127.0.0.1:8222
2. "Create account" — use your email + a NEW master password you will remember.
   This master password is stored NOWHERE else. Do not type it into any chat or file.
3. Log in. You will store each new credential below as a vault item as you rotate it.
4. AFTER your account exists, tell Spencer/Altair "vault account done" — an agent will
   then set SIGNUPS_ALLOWED=false and restart the container so nobody else can register.

## Step 1 — Apify API token (VERIFIED LIVE — highest exposure count)
- What it unlocks: your Apify scraping account (actors, runs, billing).
- Evidence: 712 verified hits — ALL of them echoes inside DealsDesk Hermes cron OUTPUT
  files (`~/.hermes/profiles/dealsdesk/cron/output/…`, one recurring scraping job whose
  output prints its context). Treat the token as broadly copied.
- Rotate: https://console.apify.com → Settings → API & Integrations → regenerate the token.
- Store new value in Vaultwarden as: `Apify API token`.
- What breaks until updated: the DealsDesk scraping job(s) that use Apify will fail auth.
  Update the token where the dealsdesk Hermes profile job gets it (profile cron job
  definition / its config), then run the job once manually to confirm it works.
- Cleanup after rotation (old value is dead, but purge anyway):
  `rm -rf ~/.hermes/profiles/dealsdesk/cron/output/*` (outputs regenerate; they are logs).

## Step 2 — Scrapfly API key (VERIFIED LIVE)
- What it unlocks: your Scrapfly scraping account (api.scrapfly.io, billed per request).
- Evidence: 235 verified rows. Source copies in the DealsDesk repo working tree + git
  history (`lib/scrapfly_client.py` and ~14 scripts under `/home/dealsdesk/scripts/`,
  incl. `_archive/`), copies in the dealsdesk Hermes profile `scripts/`, 5 backup config
  files (`~/scripts/backups/llm_fixer_*/dealsdesk_config.yaml.bak`), and 2 cron
  `jobs.json.backup.*` files. Git-history copies stay readable until rotation — rotation
  is what kills them.
- Rotate: https://scrapfly.io/dashboard → API Key → reset/regenerate.
- Store new value in Vaultwarden as: `Scrapfly API key`.
- What breaks until updated: all Scrapfly-based DealsDesk scrapers. Update the ACTIVE
  scripts to read the key from an environment variable (ask an agent to do the code pass
  in the same sitting), and delete the `.bak` config files + old jobs.json backups.

## Step 3 — DeepSeek API key (VERIFIED LIVE)
- What it unlocks: your DeepSeek API account. (Fleet record says the balance is empty and
  the cloud path is dormant — the key still AUTHENTICATES, which is what "verified" means.)
- Evidence: 10 verified rows — 8 in AnythingLLM-cleanup quarantine archive JSONs
  (`~/bin/anythingllm-cleanup/state/archive-20260930-0600/…`) and 1 file in DealsDesk git
  history (`crewai-swarms/vibe-coding-crew/build_crew.py`).
- Rotate: https://platform.deepseek.com → API Keys → delete the old key, create a new one.
- Store new value in Vaultwarden as: `DeepSeek API key`.
- What breaks: nothing live (dormant path). If you revive the cloud path, use the vault copy.

## Step 4 — Telegram bot token (VERIFIED LIVE)
- What it unlocks: full control of the deals Telegram bot (send/read as the bot).
- Evidence: 10 verified rows — DealsDesk git `deals_alert.py`, `deals_analyzer.py`,
  `telegram_router.py`, `scraping-scripts/gary/telegram_bot.py` (each in 2 commits) +
  2 quarantine archive JSONs.
- Rotate: Telegram → @BotFather → /mybots → your bot → API Token → Revoke current token
  (this issues the new one).
- Store new value in Vaultwarden as: `Telegram deals bot token`.
- What breaks until updated: deal alert messages stop. Update the 4 scripts above
  (agent code pass: read from env), restart any running bot process.

## Step 5 — Confirm + close out (~10 min)
1. Tell an agent "rotation done" — it will re-run the verified scan
   (`tools/guardrails/secrets_scan.py`) and confirm the OLD credentials no longer verify.
   New findings total should drop to the unverified backlog only.
2. Agent marks the 4 credential types `rotated` in `successbrian_os.secret_findings`
   and closes Atlas task `task:secrets-rotation-brian`.

## Already clean — no action
- `tools/podcast_friday_kickoff.py` (the original "podcast kickoff password" incident):
  the literal was ALREADY removed on 2026-10-24 (file header documents it); it now reads
  the DB password from `~/.pgpass`, outside the repo. Both scanners confirm the current
  file and the full successbrian-os git history are clean.
- The user crontab itself: 0 findings. systemd user units: 0 findings.

## Unverified backlog — triage later, NOT urgent (365 rows, none confirmed live)
Largest groups: Scrapfly-pattern (98 files, unverified instances), URI-embedded
credentials (129), PhraseAccessToken (60), Postgres/JDBC connection strings (34).
182 rows are in `openclaw` — a cloned UPSTREAM third-party repo; treat as upstream
fixtures, not Brian's credentials, unless a file says otherwise.
Full list: `SELECT repo, file_path, credential_type FROM successbrian_os.secret_findings
WHERE NOT verified_live ORDER BY credential_type;`
