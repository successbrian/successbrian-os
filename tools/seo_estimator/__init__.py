#!/usr/bin/env python3
"""SEO traffic estimator for Brian's 100-blog network.

PURPOSE:
    Answer "will searches bring us visitors?" with computed numbers instead of
    gut feel: expand a topic into keywords, measure relative demand (Google
    Trends), score SERP beatability, and convert to estimated monthly visits
    via CTR curves. Writes est_monthly_visits back to
    successbrian_os.blog_idea_ranking.

WHY:
    Brian 2026-10-16: "how do we determine how well the SEO searches will
    bring us visitors." The blog_topics scores rate demand high/medium/low
    from research notes; this computes the actual visitor math so the 50K
    monthly-visits bar is tested, not assumed.

CALLED BY:
    CLI (`python3 cli.py estimate "<topic>" --seeds kw1,kw2`) run on k11.
    All data sources are free: Google Trends (direct HTTP, no pytrends),
    autocomplete + People-Also-Ask scraping, DuckDuckGo SERP scraping.
    No paid APIs, no model calls.

NOTES:
    - Volume is estimated as a RANGE (low/high), not false precision. Free
      data cannot give exact search volumes; the math is honest about that.
    - The 50K verdict reads the range: clears on low = strong yes, clears
      on high only = maybe, clears on neither = no.
    - anchors.json holds calibration anchors (known keyword volumes). Seed
      values are rough and labeled; replace with Search Console ground truth
      once Brian's blogs rank -- that is the real calibrator.
    - CTR curve: FirstPageSage 2024 organic CTR study. AI Overview erosion:
      0.6 multiplier on informational queries (conservative; tunable).
"""
