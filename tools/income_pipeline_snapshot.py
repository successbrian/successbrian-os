#!/usr/bin/env python3
"""
income_pipeline_snapshot.py — daily snapshot of the valued income
map (Brian 2026-10-29: daily, weekly, and monthly pipeline value).

Writes one row per valued stream into income_pipeline_snapshots and
one portfolio row into income_pipeline_totals_daily, so the brief
and reports can show today's monthly pipeline value against 7 and
30 days ago. Rollup and channel rows are excluded from totals
(they would double count the umbrella's dollars).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common  # noqa: E402


def main():
    sbos_common.pg_exec(
        """INSERT INTO successbrian_os.income_pipeline_snapshots
             (snapshot_date, stream_id, monthly_value_usd,
              actual_monthly_usd)
           SELECT CURRENT_DATE, id, monthly_value_usd, actual_monthly_usd
             FROM successbrian_os.income_streams
            WHERE NOT COALESCE(is_rollup, false)
              AND COALESCE(value_confidence, '') NOT IN ('channel')
         ON CONFLICT (snapshot_date, stream_id) DO UPDATE SET
             monthly_value_usd = EXCLUDED.monthly_value_usd,
             actual_monthly_usd = EXCLUDED.actual_monthly_usd""")
    sbos_common.pg_exec(
        """INSERT INTO successbrian_os.income_pipeline_totals_daily
             (snapshot_date, total_monthly_value, total_actual,
              streams_valued, streams_total)
           SELECT CURRENT_DATE,
                  COALESCE(sum(monthly_value_usd), 0),
                  COALESCE(sum(actual_monthly_usd), 0),
                  count(monthly_value_usd),
                  count(*)
             FROM successbrian_os.income_streams
            WHERE NOT COALESCE(is_rollup, false)
              AND COALESCE(value_confidence, '') NOT IN ('channel')
         ON CONFLICT (snapshot_date) DO UPDATE SET
             total_monthly_value = EXCLUDED.total_monthly_value,
             total_actual = EXCLUDED.total_actual,
             streams_valued = EXCLUDED.streams_valued,
             streams_total = EXCLUDED.streams_total""")
    row = sbos_common.pg_rows(
        """SELECT total_monthly_value, total_actual, streams_valued,
                  streams_total
             FROM successbrian_os.income_pipeline_totals_daily
            WHERE snapshot_date = CURRENT_DATE""")
    print("pipeline snapshot: total $%s/mo scenario value, $%s actual, "
          "%s of %s streams valued" % (row[0][0], row[0][1], row[0][2],
                                       row[0][3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
