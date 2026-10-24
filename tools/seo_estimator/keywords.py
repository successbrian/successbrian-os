#!/usr/bin/env python3
"""Free keyword expansion: Google autocomplete + question variants.

PURPOSE: Turn 2-3 seed keywords into a working cluster (10-25 keywords).
WHY: A topic's traffic comes from the cluster, not one head term. Autocomplete
    reflects real searches people type; question forms catch informational
    intent (which is what AI Overviews erode -- we track it, not ignore it).
CALLED BY: estimate.py
"""

import json
import time
import urllib.parse

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_AC = "https://suggestqueries.google.com/complete/search"

_QUESTION_TEMPLATES = ["what is {s}", "how to use {s}", "best {s}",
                       "{s} benefits", "{s} side effects", "{s} vs",
                       "{s} dosage", "{s} reviews"]


def autocomplete(seed, retries=2):
    """Return suggestion strings for a seed keyword."""
    params = {"client": "firefox", "q": seed}
    last_err = None
    for _ in range(retries + 1):
        try:
            r = requests.get(_AC, params=params,
                             headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            data = r.json()
            return [s for s in data[1] if isinstance(s, str)]
        except Exception as e:  # noqa: BLE001 - transient
            last_err = e
            time.sleep(2)
    raise RuntimeError("autocomplete failed for %r: %s" % (seed, last_err))


def expand(seeds, max_per_seed=8):
    """Return deduped keyword list: seeds + autocomplete + question forms."""
    if isinstance(seeds, str):
        seeds = [seeds]
    out, seen = [], set()
    for seed in seeds:
        seed = seed.strip().lower()
        if seed and seed not in seen:
            seen.add(seed)
            out.append(seed)
        try:
            for sug in autocomplete(seed)[:max_per_seed]:
                s = sug.strip().lower()
                if s and s not in seen and len(s.split()) <= 8:
                    seen.add(s)
                    out.append(s)
        except RuntimeError:
            pass  # keep going on the other seeds
        for tmpl in _QUESTION_TEMPLATES:
            cand = tmpl.format(s=seed)
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
        time.sleep(1)  # be polite to the suggestion endpoint
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(expand(sys.argv[1:]), indent=1))
