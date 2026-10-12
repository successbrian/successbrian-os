"""Ingest engine package: read the founder's content, propose what to build.

PURPOSE
    Package init for the ingest engine. Importing tools.ingest.* gives the
    pipeline: read second brain / AnythingLLM / markdown / agent chats ->
    propose income streams, audiences, campaigns, and ideas as reviewable
    candidates. Contents: ingest.py (the engine), extract.py (the LLM
    adapter), prompts/ (extraction prompts), schema.sql (the candidates
    tables).

WHY
    A founder's notes already contain their next five businesses; they just
    cannot see them for the volume. The engine exists so the accumulated
    content gets mined systematically on the founder's own hardware instead
    of sitting unread. If this package were removed, the MCP tool
    ingest_candidates would serve an empty table and the whole "propose"
    half of the ecosystem intake would go silent.

CALLED BY
    - Anything importing tools.ingest.ingest (the engine) or
      tools.ingest.extract (the LLM reading adapter).
    - tools/mcp/ecosystem_data.py reads this engine's output tables
      (ingest_candidates) -- see its NOTES on the accept flow.

NOTES
    - Nothing here writes to ventures/audiences/campaigns until `accept`.
      The pipeline proposes; the entrepreneur decides.
    - See the module docstrings for the deterministic-vs-LLM split:
      deterministic code owns ingest/chunk/dedupe/store/review, the model
      only does the reading-and-proposing step.
"""
