#!/usr/bin/env python3
"""SuccessBrian OS: income-stream catalog + per-user stream configuration.

PURPOSE: The product ships a catalog of income streams (tools/ventures/
    streams.json). Each user of successbrian-os decides for themselves which
    streams are active and which are PERMANENT in their own ecosystem, via
    a gitignored user_streams.json (see user_streams.example.json).
WHY: Brian 2026-10-03 - "employment is a permanent stream in my ecosystem.
    each user of successbrian-os can decide if they need it permanent or not."
    Streams are personal: the product must not hardcode one user's choices.
CALLED BY: tools/ventures/ideas.py (`streams` command); importable by any
    module that needs the effective stream list.
NOTES:
    - Catalog (streams.json) is product data, committed. User config
      (user_streams.json) is personal, gitignored, never committed.
    - Effective rule: user config wins per stream; anything not mentioned
      falls back to catalog defaults (enabled, not permanent).
    - "permanent" is the user's declaration that a stream is a lasting part
      of their ecosystem (surfaces everywhere, never auto-disabled).
      "enabled" controls whether it shows up at all.
    - Single-user self-hosted installs use the JSON file. A hosted
      multi-user deployment would move this to a successbrian_os.user_streams
      table keyed by user id; the merge rule stays the same.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_FILE = os.path.join(HERE, "streams.json")
USER_FILE = os.path.join(HERE, "user_streams.json")
EXAMPLE_FILE = os.path.join(HERE, "user_streams.example.json")


def catalog():
    """Product-level stream names, in catalog order."""
    with open(CATALOG_FILE) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("streams", [])
    return list(data)


def user_config():
    """This user's per-stream overrides. {} when no user_streams.json exists."""
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def effective():
    """Merged view: [{name, enabled, permanent, source}]. Catalog order."""
    cfg = user_config()
    out = []
    for name in catalog():
        override = cfg.get(name, {})
        out.append({
            "name": name,
            "enabled": bool(override.get("enabled", True)),
            "permanent": bool(override.get("permanent", False)),
            "source": "user" if name in cfg else "catalog-default",
        })
    # User-declared streams not in the catalog are kept (custom streams).
    for name, override in cfg.items():
        if name not in catalog():
            out.append({
                "name": name,
                "enabled": bool(override.get("enabled", True)),
                "permanent": bool(override.get("permanent", False)),
                "source": "user-custom",
            })
    return out


def enabled_names(permanent_only=False):
    """Stream names the user has enabled (optionally only permanent ones)."""
    return [s["name"] for s in effective()
            if s["enabled"] and (not permanent_only or s["permanent"])]


if __name__ == "__main__":
    for s in effective():
        flag = "PERMANENT" if s["permanent"] else ("on" if s["enabled"] else "off")
        print("%-15s %-9s (%s)" % (s["name"], flag, s["source"]))
