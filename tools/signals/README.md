# Ecosystem signals → screams

Brian 2026-10-17: the ecosystem's own strain and performance signals must be
detected and turned into needs ("screams") that DealsDesk reads and sources
against the budget.

## The loop

```
collect_*.py  →  ecosystem_signals  →  derive_needs.py  →  sbos_need_requests  →  DealsDesk need_reader.py
   (facts)         (latest per key)      (thresholds)         (the screams)         (budget-aware sourcing)
```

- **Signals** are facts with no judgment: `k11.cpu_temp_c = 93.2`.
- **Thresholds** are policy: temp > 90 → scream "inference thermal headroom".
- **Screams** stay generic (Brian's rule — never specific hardware). `need_class`
  and evidence ride in `specs` as structured text DealsDesk parses.

## Live collectors

- `collect_infra.py` (cron :05/:20/:35/:50) — k11 cpu temp, load, mem/swap,
  disk, longest DB query.

## Signal contracts (collectors not yet built — keys reserved)

When a feed comes online, the collector writes `ecosystem_signals` and the
threshold row already defines the scream. No code changes to the loop.

| signal_key | class | meaning |
|---|---|---|
| `blog.<slug>.hits_7d` | blog | weekly hits per blog |
| `blog.<slug>.hits_trend` | blog | +1 growing / -1 shrinking vs prior 7d |
| `email.<campaign>.open_rate` | email | open rate 0-1 |
| `email.<campaign>.click_rate` | email | click rate 0-1 |
| `email.<campaign>.bounce_rate` | email | bounce rate 0-1 |
| `funnel.<name>.step_conversion` | funnel | per-step conversion 0-1 |
| `audience.<channel>.followers` | audience | follower count |
| `audience.<channel>.growth_7d` | audience | 7d follower delta |
| `seo.site.visibility_trend` | seo | +1 improving / -1 declining |
| `pipeline.msv.lookups_1h` | pipeline | enrichment throughput |

Need classes these derive: `inference-hardware`, `blog-hosting`,
`scraper-capacity`, `storage`, `network`, `ops`, `general`.

## Cron

- `:05/:20/:35/:50` collect_infra.py
- `:10/:25/:40/:55` derive_needs.py (staggered 5 min after collection)
