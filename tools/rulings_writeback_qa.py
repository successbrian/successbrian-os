#!/usr/bin/env python3
"""Rulings write-back gauge -- flow study 2026-11-27 (friction #68).

The Brian current's last handoff: a ruling Brian makes in chat is
filed as an Intel Bridge capture; the deterministic rulings_bridge
promotes captures carrying the ruling-audit format (CLAIM + BRIAN'S
QUOTED WORDS in raw_text) into altair.brian_decisions /
altair.brian_learnings every 30 min. On 2026-11-18 the format stopped
arriving: filers put the substance in `context` and left raw_text
empty or prose, so the bridge's pool froze at 186 captures while 911
new captures flowed past. brian_decisions has had no new row since
2026-11-18 10:21 -- nine days of rulings never wrote back, and
nothing measured the handoff.

This gauge fails while ruling-indicating captures exist that the
bridge cannot promote (starved) -- they wait on the model leg /
filing-format repair, and the count stays visible until they move.
It prints RULINGS_WRITEBACK_OK only when starved = 0.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402

STARVED_SQL = (
    "SELECT count(*) FROM atlas.scattered_captures c "
    "WHERE c.created_at > now() - interval '14 days' "
    "AND (c.title ILIKE 'RULING%' OR c.context ILIKE '%Brian ruled%') "
    "AND coalesce(c.raw_text, '') NOT LIKE '%BRIAN''S QUOTED WORDS:%' "
    "AND NOT EXISTS (SELECT 1 FROM altair.brian_decisions d "
    "WHERE d.context LIKE '%rulings_bridge:capture-' || c.id || '%')")

FRESH_SQL = (
    "SELECT ROUND(EXTRACT(EPOCH FROM (now()-MAX(answered_at)))/3600) "
    "FROM altair.brian_decisions")


def main():
    starved = int((sbos_common.pg_rows(STARVED_SQL) or [[0]])[0][0] or 0)
    age_h = (sbos_common.pg_rows(FRESH_SQL) or [[None]])[0][0]
    print(f"starved_unformatted={starved} "
          f"brian_decisions_age_h={age_h}")
    if starved == 0:
        print("RULINGS_WRITEBACK_OK")
        return 0
    print("RULINGS_WRITEBACK_STARVED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
