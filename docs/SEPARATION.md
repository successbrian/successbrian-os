# Separation: Generic Core vs Personal Config

SuccessBrian OS works for **any** home-based entrepreneur. Your data is yours. This doc defines how the two stay separate.

## The principle

**The schema is generic. The data is personal.** Everything in this repo — table definitions, views, tools, docs — must work for a stranger who clones it tomorrow. Nothing in the core references a real person, business, or dollar amount.

## The three layers

```
┌─────────────────────────────────────────┐
│ 1. GENERIC CORE (this repo)             │
│    Schema, views, tools, docs.          │
│    No personal data. Ever.              │
│    Example: businesses table definition │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ 2. SEED DATA (marked, replaceable)      │
│    Example rows showing how to use it.  │
│    Clearly labeled SEED in notes.       │
│    Example: "Example Bakery (SEED)"     │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ 3. PERSONAL CONFIG (not in repo)        │
│    Your data, your .env, your configs.  │
│    Lives in ~/.config/ or env vars.     │
│    Example: your actual businesses      │
└─────────────────────────────────────────┘
```

## Rules

1. **No personal data in the repo.** No real names, emails, addresses, phone numbers, account IDs, or dollar amounts tied to a real person. The one exception is clearly-marked seed data (rule 2).
2. **Seed data is labeled.** Any example row has "(SEED)" in its name or "SEED DATA — replace with your own" in its notes field.
3. **Personal config lives outside.** API keys → environment variables. Personal settings → `~/.config/<tool>/` or a `config/` directory that's in `.gitignore`. The existing precedent: `board/config/brian.yaml` is documented as "the bent instance of the generic harness" — personal config bending generic code.
4. **Brian-specific code gets generalized or isolated.** If a tool hardcodes a personal value, either make it a config/env var (generalize) or move it to personal config (isolate). Never leave it hardcoded in the core.
5. **Docs speak to "you", not "Brian".** README, guides, and comments address any entrepreneur. Personal names appear only in seed data or personal config.

## Checklist for new code

Before committing, ask:
- [ ] Does this work if someone else clones it with empty tables?
- [ ] Are there hardcoded names, emails, paths, or credentials?
- [ ] Is example data labeled as seed?
- [ ] Are secrets in env vars, not in code?

## Migrating existing Brian-specific code

Found something personal in the core? Either:
- **Generalize:** Replace the hardcoded value with a config/env var. Update docs.
- **Isolate:** Move it to personal config outside the repo. Leave a pointer.
- **Label:** If it's genuinely useful as an example, label it SEED and keep it.

Never silently leave personal data in the generic core.
