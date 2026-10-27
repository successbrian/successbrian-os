# PROPOSAL — Agent Sandbox & Egress Design

**PROPOSAL — Brian has not approved this design. Nothing in this document is built.**
Project: `agent-sandbox-egress-design` (SBOS PM, registered 2026-10-27, requested by Brian)
Date: 2026-10-27

## Problem

SBOS agents (desks, workers, board seats) today run with the ambient
authority of the host: any tool a process can reach, any host it can
dial, any folder it can read. The 2026-10-27 gap-hunt research
(NemoClaw / OpenShell pattern) points the other way: an agent should
run in a sandbox whose *egress* — what it may connect to, and what
tools/files it may touch — is declared up front, and anything outside
the declaration surfaces for approval instead of silently working.

## Design

### 1. Per-desk isolation

Each desk (CampaignsDesk, DealsDesk, TradesDesk, the board, the
clerk, personal/life ops) runs in its own container or lightweight VM
with:

- Only its own tool set mounted (CampaignsDesk gets blog/content
  tools; it does not get DealsDesk scrapers or fleet SSH keys).
- Only its own folders writable; shared state goes through Postgres
  and AnythingLLM — the sanctioned homes (R32) — not shared files.
- Its own service identity/credentials, scoped to what the desk
  actually uses; no desk inherits Brian's or another desk's keys.
- No lateral network reachability between desk sandboxes by default;
  inter-desk communication goes through the existing PM / A2A /
  database channels, which are auditable.

### 2. Declarative egress allowlist (NemoClaw/OpenShell pattern)

Each sandbox carries a declarative policy file — the ONLY hosts,
ports, and tools it may use. Sketch:

```yaml
# egress policy — desk: campaignsdesk   (PROPOSAL sketch, not live config)
desk: campaignsdesk
filesystem:
  read:  [~/campaignsdesk, ~/successbrian-os/tools/marketing]
  write: [~/campaignsdesk]
tools:
  allow: [content_pm.py, blog_manager.py, allm_embed.py]
network:
  egress:
    - host: api.wix.com            # blog publish path
      ports: [443]
    - host: 127.0.0.1              # local Postgres / AnythingLLM
      ports: [5432, 3000]
    - host: graph.facebook.com     # only after Postiz/dev-app gates
      ports: [443]
  default: deny
approvals:
  new_host: surface_in_chat        # see section 4
  new_tool: surface_in_chat
```

Default-deny egress, per-desk files, version-controlled next to the
desk's code so a policy change is a reviewable diff.

### 3. Privacy router

Sensitive context stays local. A router in front of model calls
classifies outbound context:

- **Local-only**: personal/family material, credentials-adjacent
  context, private communications — routed only to local models
  (the fleet's Sonic/local tiers), never to a cloud model.
- **Redacted-to-cloud**: cloud models (e.g. V4 Pro) receive only the
  redacted/selected slice a task needs — names/identifiers stripped
  where the task doesn't need them — consistent with the existing
  model-tier discipline.
- The router logs (task, tier, what classes of context left the box)
  to Postgres state, so "what did we send where" is answerable.

### 4. Approval surfacing in chat

A sandbox hitting a non-allowlisted host or tool does not fail
silently and does not self-approve: it files a request that surfaces
in Brian's chat (the channel he actually reads) — what desk, what
host/tool, what task needs it — and waits. Brian's yes/no becomes a
policy diff (allow once / allow always for this desk / deny). This
matches the standing approval law: enthusiasm is not authorization;
each new reach gets its own explicit go.

### 5. Phased rollout (proposal)

1. **Inventory** (no enforcement): log what each existing desk
   actually connects to and touches for a week; draft policies from
   the logs.
2. **One pilot desk** in warn-only mode: violations logged and
   surfaced, nothing blocked. Tune the policy until warn-only is
   quiet.
3. **Enforce on the pilot**, then desk-by-desk, lowest-risk first.
   Board/clerk (highest ambient authority) last, with Brian present.
4. Privacy router ships with phase 2 (log-only) and enforces from
   phase 3.

## What needs Brian

- Approval of this design (or changes to it) — **proposal only so far**.
- Per-desk risk calls during rollout: which desks enforce first.
- Every *new-host / new-tool* request the system surfaces (by design,
  forever — that is the point).
- A decision on how strict local-only classification should be for
  cloud model context.

Nothing was built, installed, or enforced in this pass.
