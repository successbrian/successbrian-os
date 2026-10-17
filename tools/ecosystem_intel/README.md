# ecosystem_intel — stop re-deriving the world

Brian's law: no agent should spend precious time figuring out the same thing
over and over. Learn once, record here, serve cheaply forever.

## The three kinds

- **facts** — stable truths: IPs, API shapes, ports, credential locations.
- **howtos** — procedures that worked: deploy a bridge, push a repo, edit nginx.
- **gotchas** — traps that bit someone, with the fix.

## For agents (before discovery work)

```python
from intel import get_digest, find
digest = get_digest('brian')              # everything
digest = get_digest('brian', 'network')   # one category
hits = find('brian', 'nginx')             # keyword search
```

```bash
python3 intel.py --tenant brian --digest --category network
python3 intel.py --tenant brian --find "webhook"
```

## Recording (when you learn something hard-won)

```python
from intel import record_fact, record_howto, record_gotcha
record_fact('brian', 'x.api_auth', 'Bearer token', 'x', source='docs')
record_howto('brian', 'do the thing', 'summary', 'step 1\nstep 2')
record_gotcha('brian', 'the trap', 'why it bites', 'the fix')
```

Rule of thumb: if you spent >10 minutes discovering it and another agent
will need it, record it. Facts get `verified` confidence by default; mark
`unverified` when it's a guess.

## Multi-tenant

Same schema + code for every successbrian-os user; data isolated per
`tenant_id`. Sibling to `business_core` (which holds the BUSINESS); this
holds the ECOSYSTEM (how the machines and integrations work).
