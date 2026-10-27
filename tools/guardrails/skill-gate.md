# Skill Gate — skill/MCP supply-chain gate

Brian's order, 2026-10-27. Code: `tools/guardrails/skill_gate.py`.
State: `successbrian_os.skill_registry` in `ecosystem_central`
(migration: `2026-10-27_skill_registry.sql`, beside the code).

## Why

The fleet adopts external skills and MCP servers (Hermes profiles carry
skill dirs; the OS has `tools/mcp`). Skill ecosystems now carry real
supply-chain risk — malicious skills, prompt injection — so adoption is
a gated flow, and drift after adoption must be detectable.

## The adoption flow: scan → pin → register → drift-scan

1. **Scan** — look at what is actually on disk. Nothing is registered
   that was not found on disk; unknowns stay unregistered.
2. **Pin** — hash the skill directory / MCP server file (sha256,
   deterministic) and store it as `pinned_ref`: the exact bytes adopted.
3. **Register** — one row in `skill_registry` (kind, name, location,
   hash, `adopted_at`, verdict `registered`).
4. **Drift-scan** — weekly cron (Sun 04:20) re-hashes every registered
   location: matches pin → `clean`, differs → `drift`, gone →
   `missing`. Drift is a report, not a crash.

One command runs steps 1–3 for a new adoption:

```bash
python3 tools/guardrails/skill_gate.py adopt <path> [--kind skill|mcp] [--source-url <url>]
```

## Honest scope

This gate does **hash-pinning and drift detection only**. "Scan" in this
system means drift-scan (re-hash and compare). It does **not** do
behavioural scanning — no prompt-injection pattern analysis, no sandbox
execution, no publisher signature checks. That is a documented TODO in
the module docstring, not a claim. A `clean` verdict means "bytes
unchanged since pinning", never "vetted" or "safe".

## Commands

```bash
python3 tools/guardrails/skill_gate.py register [--root <dir>]...
python3 tools/guardrails/skill_gate.py scan
python3 tools/guardrails/skill_gate.py list [--verdict v]
python3 tools/guardrails/skill_gate.py show <name>
python3 tools/guardrails/skill_gate.py adopt <path>
python3 tools/guardrails/skill_gate.py selftest
```

Default `register` enumerates every Hermes profile skills dir
(`~/.hermes/profiles/*/skills/`), any SKILL.md parents in the OS repo,
and MCP server files in `~/successbrian-os/tools/mcp/` and
`~/mcp-servers/`. A skill is a directory containing a SKILL.md (named by
its path relative to the root), plus non-hidden top-level entries with
no SKILL.md beneath them. Hidden/Hermes-bookkeeping entries
(`.curator_backups`, `.hub`, `.usage.json`, …) are not skills and are
skipped. Register is idempotent: a second run adds 0 rows.

MCP rows carry the server **name and file path only** — never config
values or credentials.

## Cron

Weekly drift scan, Sun 04:20, flock-guarded, log at
`~/logs/skill-gate-scan.log`:

```
20 4 * * 0 /usr/bin/flock -n /tmp/skill-gate-scan.lock /usr/bin/python3 /home/successbrian/successbrian-os/tools/guardrails/skill_gate.py scan >> /home/successbrian/logs/skill-gate-scan.log 2>&1
```
