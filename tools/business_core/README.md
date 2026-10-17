# business_core — the business brain as a system

The business brain lives in the **database**, not in a doc. The markdown
`BUSINESS_CORE.md` is a *rendered view* (`core.py --render`) — never a
separate source of truth.

## Multi-tenant by design

The schema + this code ship with successbrian-os for every user. The DATA
is per-tenant: every table carries `tenant_id`. Brian's tenant is `brian`;
another user's install holds their own business. Same tools, unique data —
the same boundary the products themselves respect.

## For agents

```python
from core import get_brief
brief = get_brief('brian')   # everything, as a dict
```

Or in SQL:

```sql
SELECT * FROM business_core.products WHERE tenant_id = 'brian';
```

Or the rendered doc:

```bash
python3 core.py --tenant brian --render > BUSINESS_CORE.md
```

## Tables

| Table | What it holds |
|---|---|
| tenants | Each user's business identity |
| products | Products across layers (crm-core, skin-core, skin, os, channel) |
| product_links | How products fit: builds_on, integrates_with, competes_with |
| income_streams | Money sleeves |
| capital_flows | Directed flows between sleeves + the rule |
| rules | Inviolable rules (architecture, privacy, engineering, money, safety, product) |
| tool_stack | Tools, roles, cost basis |
| people | Key humans + agents |
| roadmap | Where the business is going (now / next / future) |

## Maintenance

When Brian makes a product, architecture, or money decision, it lands here
(via a `business-core`-tagged second_brain rollup or direct edit). Brian
corrects it; agents don't freelance on it. Re-render the doc after changes.

## New tenant onboarding

```sql
INSERT INTO business_core.tenants (id, display_name, tagline)
VALUES ('their-id', 'Their Name', 'Their tagline');
```

Then fill products, income_streams, rules, etc. — the setup flow (or Altair)
walks them through it. Empty tables = valid; the brief just renders sparse.
