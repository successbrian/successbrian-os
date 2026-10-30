#!/usr/bin/env python3
"""intel_scrape — the SBOS scraping standard (Tier 2, 2026-10-27).

PURPOSE: URL in -> cleaned markdown out (crawl4ai, free OSS) -> filed
as an Intel Bridge intel capture with source URL + date, per the Intel
Bridge ruling (research results are filed, not left in chat).
WHY crawl4ai: Brian's standard scraper — one route for page->markdown
instead of every tool hand-rolling fetches.
CALLED BY: agents/humans on demand. Runs under the scrape venv
(~/collectors/venvs/scrape); re-execs itself there if needed.
Usage: intel_scrape.py <url> [--title T] [--no-file] | selftest
Nothing sends/posts/publishes.
"""
import asyncio
import datetime
import os
import sys

VENV_PY = os.path.expanduser("~/collectors/venvs/scrape/bin/python")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "atlas"))

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    if os.path.exists(VENV_PY) and os.path.abspath(sys.executable) != os.path.abspath(VENV_PY):
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])
    raise


async def scrape(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        if not result.success:
            raise RuntimeError("crawl failed: %s" % result.error_message)
        return result.markdown or ""


def file_intel(url, title, markdown):
    import scattered_brain
    conn = scattered_brain.pg()
    try:
        today = datetime.date.today().isoformat()
        cid = scattered_brain.capture(
            conn,
            "Scrape: %s" % (title or url)[:180],
            context="kind=intel; source=crawl4ai intel_scrape.py; "
                    "source URL: %s; checked %s" % (url, today),
            raw=markdown[:20000])
        return cid
    finally:
        conn.close()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "selftest":
        url = "https://timverdouw.com"  # on record: marketer_watchlist.yaml blog_url
        md = asyncio.run(scrape(url))
        assert len(md) > 200, "markdown suspiciously short"
        cid = file_intel(url, "Tim Verdouw blog (selftest)", md)
        print("PASS selftest: %d chars markdown from %s -> capture #%d"
              % (len(md), url, cid))
        print(md[:400].replace("\n", " ")[:400])
        return 0
    url = argv[1]
    title = None
    if "--title" in argv:
        title = argv[argv.index("--title") + 1]
    md = asyncio.run(scrape(url))
    print(md)
    if "--no-file" not in argv:
        cid = file_intel(url, title, md)
        print("\n[filed as intel capture #%d]" % cid, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
