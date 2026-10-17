# orient — the one call every agent makes

```python
from orient import orient, check_rules

ctx = orient('brian', task_hint='deploy a webhook')
# ctx['context'] — business packet (products, money, links)
# ctx['intel']   — facts/howtos/gotchas filtered to the task
# ctx['rules']   — hard rules, ALWAYS included
# ctx['roadmap'] — open roadmap items
```

```python
hits = check_rules('brian', 'I will delete the old leads table')
# [{'category': 'safety', 'rule': 'Nothing destructive...',
#   'matched': ['delete']}]
```

## What it is

The front door to the system's memory. `business_core` holds the business,
`ecosystem_intel` holds the world — `orient` composes both into one answer
so agents never assemble context by hand.

## check_rules honesty

It's a checklist generator, not a judge. Keyword triggers surface the hard
rules a proposal *might* violate so the agent reviews them before acting.
Empty result = no obvious conflict, not a clean bill of health. The agent
still decides — but it can't claim ignorance.

## CLI

```bash
python3 orient.py --tenant brian --task "deploy a webhook"
python3 orient.py --tenant brian --check "buy a $99/mo SaaS for this"
```
