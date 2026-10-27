#!/bin/sh
# gitleaks pre-commit hook — secrets closure (2026-10-27).
# Blocks a commit when staged content contains a detected secret.
# Canonical source: successbrian-os/tools/guardrails/gitleaks-pre-commit.sh
# Installed as .git/hooks/pre-commit in successbrian-os + campaignsdesk.
GL="$HOME/.local/bin/gitleaks"
if [ ! -x "$GL" ]; then echo "gitleaks not found at $GL — commit blocked (fail closed)" >&2; exit 1; fi
exec "$GL" git --pre-commit --staged --redact --no-banner -v
