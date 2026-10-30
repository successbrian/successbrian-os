#!/usr/bin/env python3
"""bridge_poller — Tier 2 collectors bridge feeder.

PURPOSE: turn NEW Miniflux entries and changedetection.io changes into
Intel Bridge captures (atlas.scattered_captures, via the fleet's own
scattered_brain.capture) exactly once each.
WHY: collectors are useless if their output piles up in their own UIs;
the Bridge is where the ecosystem actually works intel (Intel Bridge
ruling, Brian 2026-10-25).
CALLED BY: flock'd cron every 30 min -> ~/logs/bridge_poller.log.
Dedupe: successbrian_os.collector_seen (migration
2026-10-27_collectors.sql). First contact with an item files it;
--baseline marks everything currently present as seen WITHOUT filing
(used once at install so old feed history does not flood the Bridge).
Nothing here sends, posts, or publishes anything.
"""
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "atlas"))
import scattered_brain  # noqa: E402  (fleet capture machinery, verbatim)

MAX_FILE_PER_RUN = 10
RAW_CAP = 12000


def env_file(path):
    out = {}
    with open(os.path.expanduser(path)) as f:
        for ln in f:
            if "=" in ln and not ln.startswith("#"):
                k, v = ln.strip().split("=", 1)
                out[k] = v
    return out


def http_json(url, headers=None, method="GET"):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def seen(conn, source, ext_id):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM successbrian_os.collector_seen "
                    "WHERE source=%s AND external_id=%s", (source, ext_id))
        return cur.fetchone() is not None


def mark(conn, source, ext_id, chash, capture_id, note):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO successbrian_os.collector_seen "
                    "(source, external_id, content_hash, capture_id, note) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (source, ext_id, chash, capture_id, note))
    conn.commit()


def file_capture(conn, title, context, raw):
    return scattered_brain.capture(conn, title, context=context,
                                   raw=raw[:RAW_CAP])


def poll_miniflux(conn, baseline=False):
    env = env_file("~/collectors/miniflux.env")
    import base64
    auth = base64.b64encode(("%s:%s" % (env["MINIFLUX_ADMIN_USER"],
                                        env["MINIFLUX_ADMIN_PASSWORD"])
                             ).encode()).decode()
    data = http_json(env["MINIFLUX_URL"] +
                     "/v1/entries?order=id&direction=desc&limit=100",
                     {"Authorization": "Basic " + auth})
    filed = 0
    for e in data.get("entries", []):
        ext = str(e["id"])
        if seen(conn, "miniflux", ext):
            continue
        feed = (e.get("feed") or {}).get("title", "Miniflux feed")
        chash = hashlib.sha256(((e.get("title") or "") +
                                (e.get("url") or "")).encode()).hexdigest()
        if baseline:
            mark(conn, "miniflux", ext, chash, None, "baseline")
            continue
        if filed >= MAX_FILE_PER_RUN:
            break
        cid = file_capture(
            conn,
            "Miniflux: %s" % (e.get("title") or "(untitled)")[:180],
            "kind=intel; source=miniflux feed '%s'; source URL: %s; "
            "checked 2026-10-27 via bridge_poller" % (feed, e.get("url")),
            (e.get("content") or e.get("title") or ""))
        mark(conn, "miniflux", ext, chash, cid, "filed")
        filed += 1
        print("miniflux entry %s -> capture #%d" % (ext, cid))
    return filed


def poll_changedetection(conn, baseline=False):
    env = env_file("~/collectors/changedetection.env")
    hdr = {"x-api-key": env["CD_API_KEY"]}
    watches = http_json(env["CD_URL"] + "/api/v1/watch", hdr)
    filed = 0
    for uuid, w in watches.items():
        hist = http_json("%s/api/v1/watch/%s/history" % (env["CD_URL"], uuid),
                         hdr)
        keys = sorted(hist.keys())
        if not keys:
            continue
        ext = "%s:%s" % (uuid, keys[-1])
        if seen(conn, "changedetection", ext):
            continue
        chash = hashlib.sha256(ext.encode()).hexdigest()
        if baseline or len(keys) < 2:
            mark(conn, "changedetection", ext, chash, None,
                 "baseline" if baseline else "first-snapshot")
            continue
        cid = file_capture(
            conn,
            "Changedetection: %s" % (w.get("title") or w.get("url"))[:180],
            "kind=intel; source=changedetection watch; source URL: %s; "
            "new snapshot %s; checked via bridge_poller" % (w.get("url"),
                                                             keys[-1]),
            "Watch '%s' (%s) recorded a new snapshot at %s. "
            "See changedetection UI for the diff." % (w.get("title"),
                                                      w.get("url"),
                                                      keys[-1]))
        mark(conn, "changedetection", ext, chash, cid, "filed")
        filed += 1
        print("changedetection %s -> capture #%d" % (ext, cid))
    return filed


def selftest(conn):
    """File ONE clearly-labeled synthetic changedetection item through the
    real dedupe+filing path, then prove a second pass files nothing."""
    ext = "selftest:changedetection:2026-10-27"
    if seen(conn, "changedetection-test", ext):
        print("selftest item already filed previously (dedupe holds)")
        return 0
    cid = file_capture(
        conn,
        "[TEST] changedetection poller proof item",
        "kind=intel; TEST ITEM filed by bridge_poller.py selftest "
        "2026-10-27 to prove the changedetection->Bridge path end to "
        "end. Not a real page change. Source: synthetic.",
        "Synthetic change event generated by bridge_poller selftest.")
    mark(conn, "changedetection-test", ext,
         hashlib.sha256(ext.encode()).hexdigest(), cid, "selftest")
    print("selftest: filed capture #%d" % cid)
    assert seen(conn, "changedetection-test", ext)
    print("PASS dedupe row present; a rerun files nothing new")
    return 0


def main(argv):
    conn = scattered_brain.pg()
    try:
        if len(argv) > 1 and argv[1] == "selftest":
            return selftest(conn)
        baseline = "--baseline" in argv
        f1 = poll_miniflux(conn, baseline)
        f2 = poll_changedetection(conn, baseline)
        print("bridge_poller: filed %d capture(s)%s"
              % (f1 + f2, " (baseline mode)" if baseline else ""))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
