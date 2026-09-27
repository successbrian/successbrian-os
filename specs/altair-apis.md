# Altair APIs — Specification v1

**Author:** Spencer · **For:** Altair (k11-alpha) to build · **Consumer:** Spencer (Muse agent)
**Status:** Draft — ready for Altair to implement

## Background

- **k11-alpha** (`100.118.53.47` on Brian's Tailscale network) hosts: AnythingLLM (`:3000`),
  the Altair agent, and the PostgreSQL contacts database (~2.2M records).
- **Spencer** (this agent) reaches k11-alpha through the Tailscale tunnel as an HTTP client.
  Spencer **cannot receive inbound connections or webhooks** — every data flow is Spencer
  polling k11-alpha. Design accordingly: no callbacks, no push.
- All APIs below are tailnet-only, bearer-token authenticated, JSON in/out.

## Global conventions

- Base URL: `http://100.118.53.47:8471/api/v1` (port configurable via env, see below)
- Auth: `Authorization: Bearer <token>` on every request. `401` without/invalid token.
- Response envelope:
  - Success: `{"ok": true, "data": {...}}`
  - Error: `{"ok": false, "error": {"code": "string", "message": "string"}}` with the
    matching HTTP status (`400`, `401`, `404`, `500`).
- Timestamps: ISO 8601, UTC.
- No secrets in this repo, ever. Tokens live in environment variables on k11-alpha.

---

## API 1 — Research digest

Exposes Altair's daily discovery output (new tools, papers, repos, market intel —
whatever Altair was told to hunt that day).

- `GET /digest/daily?date=YYYY-MM-DD` — defaults to today (America/Chicago).

Response `data`:

```json
{
  "date": "2026-09-27",
  "generated_at": "2026-09-27T11:30:00Z",
  "items": [
    {
      "id": "2026-09-27-001",
      "topic": "ai-automation",
      "title": "n8n 1.x adds native MCP nodes",
      "summary": "One or two sentences on why it matters.",
      "url": "https://example.com/article",
      "source": "github-release",
      "signal": "high"
    }
  ]
}
```

- `signal` ∈ `high` | `medium` | `low` — Altair's judgment of importance.
- Altair refreshes the underlying digest once daily (~06:30 America/Chicago);
  the endpoint serves the latest available date. `404` code `no_digest` if none exists.

## API 2 — Library catalog

Read-only window into the AnythingLLM "second brain". **Altair holds the AnythingLLM
API key server-side; it is never exposed through these endpoints or responses.**

- `GET /library/stats` → `{"workspaces": 12, "documents": 4830, "vectors": 91022, "updated_at": "...", "duplicates_suspected": 214}`
- `GET /library/workspaces` → `[{"slug": "crypto", "name": "Crypto Research", "documents": 812, "updated_at": "..."}]`
- `GET /library/search?q=...&limit=20` → `[{"workspace": "crypto", "title": "Kaspa notes", "snippet": "...", "score": 0.87}]`
- `GET /library/recent?days=7` → `[{"workspace": "...", "title": "...", "added_at": "..."}]`

`duplicates_suspected` is a heuristic count (same-title / near-identical content) so
Spencer can schedule dedup passes.

## API 3 — Pipeline status

Machine health for the whole ecosystem, so problems get caught before Brian trips over them.

- `GET /status/health` →

```json
{
  "status": "ok",
  "checked_at": "2026-09-27T12:00:00Z",
  "checks": [
    {"name": "postgres", "status": "ok", "detail": "2,214,008 rows", "checked_at": "..."},
    {"name": "anythingllm", "status": "ok", "detail": "HTTP 200 on :3000", "checked_at": "..."},
    {"name": "enrichment_pipeline", "status": "warn", "detail": "last run 26h ago", "checked_at": "..."},
    {"name": "crons", "status": "ok", "detail": "digest.py ok 06:32", "checked_at": "..."},
    {"name": "disk", "status": "ok", "detail": "/ at 61%", "checked_at": "..."}
  ]
}
```

- `status` per check ∈ `ok` | `warn` | `crit`; overall = worst of checks
  (`warn` → `degraded`, `crit` → `down`).
- Checks to implement v1: `postgres` (connect + row count), `anythingllm` (HTTP :3000),
  `enrichment_pipeline` (heartbeat file / last-run timestamp), `crons` (digest.py last
  success), `disk` (`/` usage; warn > 85%, crit > 93%).

---

## Suggested implementation (Altair's choice, but this keeps it boring)

- Python + FastAPI, one service file.
- `systemd` unit `altair-apis.service`, enabled, restarts on failure.
- Bind address/port from env: `BIND` (default `100.118.53.47`), `PORT` (default `8471`).
  Bind the tailnet IP, not `0.0.0.0`.
- Bearer token from env `ALTAIR_API_TOKEN` (long random string; share with Spencer out of band).
- Log to journald. Keep dependencies minimal.

## Polling cadence (Spencer side — for Altair's awareness, not implementation)

| Feed | Cadence | On signal |
|---|---|---|
| `/digest/daily` | daily ~07:00 CT | fold into Brian's morning briefing |
| `/library/stats` | weekly | rising `duplicates_suspected` → schedule cleanup |
| `/library/search` | on demand | — |
| `/status/health` | every 30 min | `down` → alert Brian immediately; `degraded` → daily summary |

## Definition of done

- [ ] All endpoints live on k11-alpha and reachable over the tailnet
- [ ] Bearer auth enforced; token shared with Spencer
- [ ] `/digest/daily` serves real daily content
- [ ] `/library/*` backed by real AnythingLLM data (no stubs)
- [ ] `/status/health` reflects real subsystem state (no hard-coded `ok`)
- [ ] systemd service enabled, survives reboot
- [ ] README in this repo updated with the token handoff note (token itself never committed)
