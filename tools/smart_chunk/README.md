# smart_chunk -- AnythingLLM staleness pipeline

Three-stage pipeline for judging AnythingLLM documents for staleness.
Deterministic code gathers the facts; Morpheus (127.0.0.1:11437) only judges.

1. `smart_chunk.py <doc.json> [-o out.jsonl]` -- splits a document on markdown
   headers (<=6000 chars/piece); Morpheus labels each chunk with topic,
   one-line summary, and dates. Emits JSONL with latest_date, age_days,
   and a stale flag (>180 days).
2. `chunk_facts.py <chunks.jsonl> [-o out.jsonl]` -- deterministic facts per
   chunk: corpus_refs (other docs mentioning the source title),
   duplicate_of, superseded_by (same topic, newer chunk), workspace.
3. `stale_review.py <chunks-with-facts.jsonl> [-o out.jsonl]` -- Morpheus
   judges stale + delete_safe with one-sentence reasons, given the facts.
   PROPOSES ONLY. Nothing is ever deleted by these scripts.

Pilot run (2026-10-19): sb-batch-unsorted-01.md -> 4 chunks, all flagged
stale/delete_safe by the judge on content grounds (transient status reports)
despite latest_date 2026-10-15 -- review before trusting delete verdicts.
