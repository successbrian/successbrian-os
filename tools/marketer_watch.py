#!/usr/bin/env python3
"""
YouTube watcher for affiliate marketers Brian follows.

WHY:
    Brian follows marketers (Tim Verdouw, Todd Gross, ...) to track affiliate
    launches and tactics, but their email/newsletter volume clutters his inbox
    and notifications. Per his 2026-09-27 directive, incoming volume never
    implies importance: this watcher polls their public YouTube channels behind
    the scenes and distills each new video into a neutral second-brain
    observation (title + date + URL + title-based summary — no hype, no
    recommendations). Brian reads the digest instead of the firehose. If this
    is removed, marketer intel either stops or has to be gathered by hand.

CALLED BY:
    Humans (`--check`, `--list`, `--add`, `--baseline`), future cron (cadence
    TBD by Brian as of 2026-09-28). Reads tools/marketer_watchlist.yaml.

NOTES:
    - YouTube's public RSS feeds (feeds/videos.xml) returned 404 for valid
      channel IDs from multiple egresses as of 2026-09-27 — treated as
      deprecated. Polling parses the channel /videos page HTML
      (lockupViewModel structure) instead. If YouTube changes the markup, the
      parser in fetch_channel_videos() must be updated. Fetch failures are
      loud (stderr + nonzero exit), never silent.
    - Per-video descriptions are NOT retrievable: watch pages bot-check
      automated fetches (captcha), oEmbed returns title/author only. Summaries
      are title-based and say so explicitly. Never invent detail.
    - Dedupe: a video_id is logged to second brain exactly once (seen db).
      First-ever --check baselines silently (marks seen, logs nothing) so old
      videos don't flood the log; use --baseline to re-seed deliberately.
    - Publish times from the channel page are relative ("12h ago", "3mo ago")
      and recorded as-hinted, not as exact dates.
    - ENRICHMENT (per Brian 2026-09-28): reuses the EXISTING youtube-content
      skill on k11-alpha (~/.hermes/skills/media/youtube-content/scripts/
      fetch_transcript.py) — never reimplement transcript fetching. New videos
      whose titles match enrich_keywords in the YAML get their transcript
      pulled to tools/marketer_watch_transcripts/ and an ENRICH_CANDIDATE line
      is printed. The driver (cron worker) reads the transcript, writes a
      neutral summary, and records it via --enrich-summary VIDEO_ID
      --summary-file PATH (tagged 'enriched'). Selective by design:
      transcribing everything is wasteful. Do NOT touch the lead-gen scripts
      (crypto_youtube_discovery.py, find_youtube_prospects.py,
      youtube_scrape.py) — different job.
    - OFFER TRACKING (per Brian 2026-09-28): the signal isn't just "what they
      published" — it's "what offers they're pushing." Watching top affiliate
      earners reveals which offers Brian himself might promote. When the
      driver writes an enrichment summary it also identifies the promoted
      offer (--enrich-summary ... --offer "Product ($price, launch date)");
      the offer is stored in the seen db (offer/offer_slug columns) and the
      second-brain record carries it as a `Promoted offer:` line plus an
      `offer:<slug>` tag. --offers aggregates across the watchlist: which
      offers are pushed by MULTIPLE marketers in the last 30 days — the
      strongest promotion signal. --set-offer backfills an offer onto an
      already-seen video without re-logging to second brain (the new
      second-brain record from a re-run would duplicate).
    - BRIEF WIRING (2026-09-28): board/harness/brief.py has a real
      pull_marketer_watch_offers() puller (registered as
      "marketer_watch_offers") that shells out to this script's --offers;
      board/config/brian.yaml gives the Chief Affiliate Marketing Officer
      brief_keys [affiliate, marketer_watch_offers]. Generic harness
      untouched — this is Brian's bent puller, the designed extension point.
    - HOW THE DRIVER IDENTIFIES AN OFFER: read the transcript's call to
      action, "link in description" mentions, launch-price announcements,
      and bonus-stack language. The display string should be the product
      name plus launch facts, e.g. "UnfoldVideo ($27 launch, Sep 5 2026)".
      If the video reviews a tool without a clear offer, or promotes
      nothing (strategy talk, interviews), pass no --offer — the record
      says "Promoted offer: none identifiable." Never guess a price or
      date that isn't in the transcript/title.
"""

import argparse
import html as htmlmod
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(HERE, "marketer_watchlist.yaml")
DB_PATH = os.path.join(HERE, "marketer_watch.db")
SECOND_BRAIN = os.path.join(HERE, "second_brain.py")
TRANSCRIPT_DIR = os.path.join(HERE, "marketer_watch_transcripts")
KSSH = os.path.join(os.path.expanduser("~"), "workspace", "bin", "kssh")
# Reused existing skill on k11-alpha per Brian 2026-09-28 — do NOT reimplement.
YT_SKILL_SCRIPT = "~/.hermes/skills/media/youtube-content/scripts/fetch_transcript.py"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# ---------------------------------------------------------------- watchlist

def load_config(path=WATCHLIST):
    """Parse the YAML watchlist without a yaml dependency (simple schema).

    Returns (watchers, enrich_keywords).
    """
    with open(path) as f:
        text = f.read()
    watchers, enrich_keywords = [], []
    cur, in_kw = None, False
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s == "enrich_keywords:":
            in_kw, cur = True, None
            continue
        if in_kw:
            if s.startswith("- name:") or s == "watchers:":
                in_kw = False  # fall through to normal handling below
            elif s.startswith("- "):
                enrich_keywords.append(s[2:].strip().lower())
                continue
            else:
                continue
        if s.startswith("- name:"):
            in_kw = False
            cur = {"name": s.split(":", 1)[1].strip()}
            watchers.append(cur)
        elif cur is not None and ":" in s:
            k, v = s.split(":", 1)
            v = v.strip()
            cur[k.strip()] = None if v in ("null", "~", "") else v
    return ([w for w in watchers if w.get("youtube_channel_id")],
            enrich_keywords)


def load_watchlist(path=WATCHLIST):
    watchers, _ = load_config(path)
    return watchers


# ---------------------------------------------------------------- fetching

def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {url}")
        return r.read().decode("utf-8", errors="replace")


def _unescape(s):
    return htmlmod.unescape(s.encode().decode("unicode_escape", errors="replace"))


def fetch_channel_videos(channel_id, timeout=30):
    """Return [{video_id, title, published_hint, views_hint, url}] newest first.

    Parses the channel /videos page HTML. Raises on fetch/parse failure.
    """
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    page = fetch_url(url, timeout=timeout)
    items = page.split('"richItemRenderer":{"content":{"lockupViewModel":')[1:]
    if not items:
        raise RuntimeError(f"no video items parsed for channel {channel_id} "
                           "(YouTube markup may have changed)")
    videos, seen = [], set()
    for it in items:
        m = re.search(r"i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/", it)
        if not m:
            continue
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        t = re.search(r'lockupMetadataViewModel":\{"title":\{"content":"(.*?)"\}', it)
        title = _unescape(t.group(1)) if t else "(untitled)"
        meta = re.search(r'"metadataRows":\[\{"metadataParts":\[(.*?)\]\}', it)
        parts = []
        if meta:
            parts = [_unescape(p) for p in
                     re.findall(r'"text":\{"content":"(.*?)"\}', meta.group(1))]
        videos.append({
            "video_id": vid,
            "title": title,
            "published_hint": next((p for p in parts if "ago" in p), ""),
            "views_hint": parts[0] if parts and "ago" not in parts[0] else "",
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return videos


# ---------------------------------------------------------------- seen db

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS seen_videos (
        video_id TEXT PRIMARY KEY,
        slug TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        title TEXT,
        published_hint TEXT,
        first_seen_at TEXT NOT NULL,
        logged INTEGER NOT NULL DEFAULT 0
    )""")
    _ensure_offer_cols(con)
    return con


def _ensure_offer_cols(con):
    """Add offer/offer_slug columns to pre-existing seen db (2026-09-28)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(seen_videos)")}
    if "offer" not in cols:
        con.execute("ALTER TABLE seen_videos ADD COLUMN offer TEXT")
    if "offer_slug" not in cols:
        con.execute("ALTER TABLE seen_videos ADD COLUMN offer_slug TEXT")
    con.commit()


def offer_slug(offer_display):
    """Product key from a display string: 'UnfoldVideo ($27 launch, Sep 5 2026)'
    -> 'unfoldvideo'. Parenthetical launch facts stay in the display string."""
    base = re.sub(r"\s*\(.*?\)", "", offer_display or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "", base)
    return slug or None


def seen_ids(con, slug):
    return {r[0] for r in
            con.execute("SELECT video_id FROM seen_videos WHERE slug=?", (slug,))}


def mark_seen(con, slug, channel_id, videos, logged):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for v in videos:
        con.execute(
            """INSERT OR IGNORE INTO seen_videos
               (video_id, slug, channel_id, title, published_hint, first_seen_at, logged)
               VALUES (?,?,?,?,?,?,?)""",
            (v["video_id"], slug, channel_id, v["title"][:200],
             v["published_hint"], now, 1 if logged else 0))
    con.commit()


# ---------------------------------------------------------------- logging

def build_entry(marketer_name, slug, video):
    topic = f"{marketer_name} published: {video['title'][:120]}"
    lines = [
        video["url"],
        f"Published: {video['published_hint'] or 'date unknown'} "
        f"(as seen {datetime.now(timezone.utc).date().isoformat()}).",
    ]
    if video["views_hint"]:
        lines.append(f"Views at check: {video['views_hint']}.")
    lines.append(
        f"Summary: {_title_summary(marketer_name, video['title'])} "
        "Video description not retrievable (YouTube blocks automated "
        "fetches); summary is title-based only, no detail invented."
    )
    return topic, "\n".join(lines)


def _title_summary(marketer_name, title):
    # Neutral, title-derived, one sentence. Never hype, never recommend.
    t = title.strip().rstrip(".")
    return (f"{marketer_name} posted a video titled \"{t}\" — per the title, "
            f"it covers {t.lower()}.")


def log_to_second_brain(topic, content, slug, dry_run=False):
    cmd = [sys.executable, SECOND_BRAIN,
           "--topic", topic,
           "--content", content,
           "--category", "observation",
           "--confidence", "medium",
           "--source", "marketer-watch",
           "--tags", f"marketer-watch,{slug}"]
    if dry_run:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"second_brain.py failed: {r.stderr.strip()}")
    return r.stdout.strip()


# ---------------------------------------------------------------- enrichment
# Reuses the existing youtube-content skill on k11-alpha (transcript fetcher).
# Selective by design: only keyword-matching videos get transcribed. The agent
# driver (cron worker) reads the transcript, summarizes, and calls
# --enrich-summary to record the deep dive.

def is_enrich_candidate(title, keywords):
    t = title.lower()
    return [k for k in keywords if k in t]


def fetch_transcript(video_id, timeout=90):
    """Pull transcript via the k11 youtube-content skill. Returns path or None."""
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    out_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")
    url = f"https://www.youtube.com/watch?v={video_id}"
    r = subprocess.run(
        [KSSH, f"timeout 80 python3 {YT_SKILL_SCRIPT} {url} --text-only"],
        capture_output=True, text=True, timeout=timeout)
    text = r.stdout.strip()
    if r.returncode != 0 or len(text) < 50:
        print(f"transcript unavailable for {video_id} "
              f"(rc={r.returncode}, {len(text)} chars)", file=sys.stderr)
        return None
    with open(out_path, "w") as f:
        f.write(text)
    return out_path


def cmd_enrich_summary(video_id, summary_file, offer=None):
    """Record an agent-written deep-dive summary for an enriched video.

    offer: optional display string like "UnfoldVideo ($27 launch, Sep 5
    2026)" identified by the driver from the transcript/title/description.
    Stored in the seen db and recorded on the second-brain record as a
    `Promoted offer:` line plus an `offer:<slug>` tag. None (default) means
    no identifiable offer — recorded explicitly as such, never guessed.
    """
    con = db()
    row = con.execute(
        "SELECT slug, title FROM seen_videos WHERE video_id=?",
        (video_id,)).fetchone()
    if not row:
        con.close()
        print(f"error: unknown video_id {video_id} (not in seen db)",
              file=sys.stderr)
        return 2
    slug, title = row
    oslug = offer_slug(offer) if offer else None
    watchers = {w["slug"]: w for w in load_watchlist()}
    name = watchers.get(slug, {}).get("name", slug)
    with open(summary_file) as f:
        summary = f.read().strip()
    if not summary:
        con.close()
        print("error: summary file is empty", file=sys.stderr)
        return 2
    topic = f"{name}: {title[:100]} — deep dive"
    offer_line = (f"Promoted offer: {offer}" if offer
                  else "Promoted offer: none identifiable from "
                       "transcript/title/description.")
    content = (f"https://www.youtube.com/watch?v={video_id}\n"
               f"{offer_line}\n"
               f"Transcript-based summary (transcript pulled via the "
               f"youtube-content skill on k11-alpha):\n{summary}")
    tags = f"marketer-watch,{slug},enriched"
    if oslug:
        tags += f",offer:{oslug}"
        con.execute("UPDATE seen_videos SET offer=?, offer_slug=? "
                    "WHERE video_id=?", (offer, oslug, video_id))
        con.commit()
    con.close()
    cmd = [sys.executable, SECOND_BRAIN,
           "--topic", topic, "--content", content,
           "--category", "observation", "--confidence", "medium",
           "--source", "marketer-watch",
           "--tags", tags]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"LOG FAILED: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(r.stdout.strip())
    if oslug:
        print(f"offer tracked: {offer} (tag offer:{oslug})")
    return 0


def cmd_set_offer(video_id, offer):
    """Backfill/attach an offer to an already-seen video (no second-brain
    re-log — the enriched record already exists; this feeds --offers only)."""
    con = db()
    row = con.execute(
        "SELECT slug, title, offer FROM seen_videos WHERE video_id=?",
        (video_id,)).fetchone()
    if not row:
        con.close()
        print(f"error: unknown video_id {video_id} (not in seen db)",
              file=sys.stderr)
        return 2
    oslug = offer_slug(offer)
    if not oslug:
        con.close()
        print("error: could not derive an offer slug from that string",
              file=sys.stderr)
        return 2
    con.execute("UPDATE seen_videos SET offer=?, offer_slug=? WHERE video_id=?",
                (offer, oslug, video_id))
    con.commit()
    con.close()
    print(f"offer set on {video_id}: {offer} (tag offer:{oslug})")
    return 0


def cmd_offers(days=30):
    """Aggregate promoted offers across the watchlist over the last N days.

    The "what the top earners are pushing" signal: offers promoted by
    MULTIPLE watched marketers rank highest. Reads the local seen db
    (populated by --enrich-summary/--set-offer). Plain-text table on stdout;
    exit 0 with a "no offers" line when empty (never a silent empty run).
    """
    con = db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds")
    rows = con.execute(
        """SELECT offer, offer_slug, slug, title, video_id, first_seen_at
           FROM seen_videos
           WHERE offer_slug IS NOT NULL AND first_seen_at >= ?
           ORDER BY first_seen_at""", (cutoff,)).fetchall()
    con.close()
    watchers = {w["slug"]: w.get("name", w["slug"]) for w in load_watchlist()}

    agg = {}
    for offer, oslug, mslug, title, vid, seen in rows:
        e = agg.setdefault(oslug, {"name": offer, "marketers": set(),
                                   "first": seen, "last": seen, "n": 0})
        e["marketers"].add(mslug)
        e["n"] += 1
        e["first"] = min(e["first"], seen)
        e["last"] = max(e["last"], seen)

    print(f"Promoted offers tracked by marketer-watch (last {days} days)")
    print("=" * 72)
    if not agg:
        print("No offers tracked yet. Offers are captured during enrichment "
              "(--enrich-summary --offer) or backfilled (--set-offer).")
        return 0

    ranked = sorted(agg.items(),
                    key=lambda kv: (len(kv[1]["marketers"]), kv[1]["n"]),
                    reverse=True)
    print(f"{'OFFER':30} {'MARKETERS':9} {'VIDEOS':6} "
          f"{'FIRST SEEN':10}  {'LAST SEEN':10}")
    print("-" * 72)
    for oslug, e in ranked:
        ms = ",".join(sorted(e["marketers"]))
        print(f"{e['name'][:30]:30} {len(e['marketers']):<9} {e['n']:<6} "
              f"{e['first'][:10]:10}  {e['last'][:10]:10}")
    print("-" * 72)
    multi = [(oslug, e) for oslug, e in ranked if len(e["marketers"]) > 1]
    if multi:
        print("Pushed by MULTIPLE marketers (strongest signal):")
        for oslug, e in multi:
            names = ", ".join(watchers.get(m, m)
                              for m in sorted(e["marketers"]))
            print(f"  - {e['name']} [{oslug}]: {names} "
                  f"({e['n']} videos)")
    else:
        print("No offer is currently pushed by more than one watched "
              "marketer.")
    return 0


# ---------------------------------------------------------------- commands

def cmd_list():
    for w in load_watchlist():
        print(f"{w['slug']:15} {w['name']:20} {w['youtube_channel_id']}")


def cmd_check(dry_run=False, baseline=False, enrich_keywords=None):
    watchers, _ = load_config()
    con = db()
    failures, logged_total = [], 0
    for w in watchers:
        slug, name, cid = w["slug"], w["name"], w["youtube_channel_id"]
        try:
            videos = fetch_channel_videos(cid)
        except Exception as e:  # loud, continue with others
            print(f"[{slug}] FETCH FAILED: {e}", file=sys.stderr)
            failures.append(slug)
            continue
        known = seen_ids(con, slug)
        new = [v for v in videos if v["video_id"] not in known]
        if baseline or not known:
            if dry_run:
                print(f"[{slug}] would baseline {len(videos)} videos "
                      f"({len(new)} new) — nothing logged")
            else:
                mark_seen(con, slug, cid, videos, logged=False)
                print(f"[{slug}] baseline: marked {len(videos)} videos seen "
                      f"({len(new)} new) — nothing logged")
            continue
        if dry_run:
            print(f"[{slug}] would log {len(new)} new video(s):")
            for v in new:
                print(f"    - {v['published_hint'] or '?':>10} | {v['title'][:70]}")
            continue
        for v in new:
            topic, content = build_entry(name, slug, v)
            try:
                log_to_second_brain(topic, content, slug)
            except Exception as e:
                print(f"[{slug}] LOG FAILED for {v['video_id']}: {e}",
                      file=sys.stderr)
                failures.append(slug)
                break
            else:
                mark_seen(con, slug, cid, [v], logged=True)
                logged_total += 1
                print(f"[{slug}] logged: {v['title'][:70]}")
                hits = is_enrich_candidate(v["title"], enrich_keywords or [])
                if hits:
                    tpath = fetch_transcript(v["video_id"])
                    if tpath:
                        print(f"ENRICH_CANDIDATE {v['video_id']} "
                              f"keywords={','.join(hits)} transcript={tpath}")
        if not new:
            print(f"[{slug}] no new videos")
    con.close()
    if failures:
        print(f"failures: {', '.join(failures)}", file=sys.stderr)
        return 1
    if not dry_run and not baseline:
        print(f"done: {logged_total} new video(s) logged")
    return 0


def cmd_add(args):
    import re as _re
    if not _re.fullmatch(r"UC[A-Za-z0-9_-]{22}", args.channel_id or ""):
        print("error: --channel-id must be a valid YouTube channel ID "
              "(UC + 22 chars)", file=sys.stderr)
        return 2
    print("Add to tools/marketer_watchlist.yaml under watchers:")
    print(f"""  - name: {args.name}
    slug: {"-".join(args.name.lower().split())}
    note: <what they do and why Brian follows them>
    youtube_channel_id: {args.channel_id}
    youtube_channel_url: https://www.youtube.com/channel/{args.channel_id}
    youtube_rss_url: null
    added: {datetime.now(timezone.utc).date().isoformat()}""")
    print("Then verify: python3 tools/marketer_watch.py --check --dry-run")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Watch marketers' YouTube channels")
    ap.add_argument("--check", action="store_true", help="poll all, log new videos")
    ap.add_argument("--dry-run", action="store_true", help="show what would be logged")
    ap.add_argument("--baseline", action="store_true",
                    help="mark all current videos seen without logging")
    ap.add_argument("--list", action="store_true", help="list watched marketers")
    ap.add_argument("--add", metavar="NAME", help="print YAML stanza for a new marketer")
    ap.add_argument("--channel-id", help="YouTube channel ID for --add")
    ap.add_argument("--enrich-summary", metavar="VIDEO_ID",
                    help="record an agent-written deep-dive summary for a video "
                         "(needs --summary-file; optional --offer to track "
                         "the promoted offer)")
    ap.add_argument("--summary-file", metavar="PATH",
                    help="path to the summary text for --enrich-summary")
    ap.add_argument("--offer", metavar="OFFER",
                    help="promoted offer display string for --enrich-summary "
                         'or --set-offer, e.g. "UnfoldVideo ($27 launch, '
                         'Sep 5 2026)". Identified by the driver from '
                         "transcript/title/description — never guessed.")
    ap.add_argument("--set-offer", metavar="VIDEO_ID",
                    help="backfill/attach an offer to an already-seen video "
                         "(needs --offer; feeds --offers, no re-logging)")
    ap.add_argument("--offers", action="store_true",
                    help="aggregate promoted offers across the watchlist "
                         "(multi-marketer pushes rank highest)")
    ap.add_argument("--days", type=int, default=30,
                    help="lookback window for --offers (default 30)")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.add:
        return cmd_add(args)
    elif args.enrich_summary:
        if not args.summary_file:
            print("error: --enrich-summary needs --summary-file", file=sys.stderr)
            return 2
        return cmd_enrich_summary(args.enrich_summary, args.summary_file,
                                  offer=args.offer)
    elif args.set_offer:
        if not args.offer:
            print("error: --set-offer needs --offer", file=sys.stderr)
            return 2
        return cmd_set_offer(args.set_offer, args.offer)
    elif args.offers:
        return cmd_offers(days=args.days)
    elif args.check or args.baseline:
        _, keywords = load_config()
        return cmd_check(dry_run=args.dry_run, baseline=args.baseline,
                         enrich_keywords=keywords)
    else:
        ap.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
