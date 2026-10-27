#!/usr/bin/env python3
"""SBOS portability export — Brian's Tier-2 gap build (2026-10-27).

Writes a dated, secret-scrubbed bundle of the core SBOS state so the
system is portable / restorable outside the live Postgres:

  sbos-bundle-YYYYMMDD-HHMM/
    atlas_nodes.json          atlas.nodes
    atlas_edges.json          atlas.edges
    calendar_events.json      life_calendar.events
    calendar_events_sbos.json successbrian_os.calendar_events
    life_calendar.json        successbrian_os.life_calendar
    publications.json         campaignsdesk.publications
    content_items.json        campaignsdesk.content_items
    renditions.json           campaignsdesk.renditions
    article_ideas.json        campaignsdesk.article_ideas
    pm_projects.json          successbrian_os.pm_projects
    pm_decisions.json         successbrian_os.pm_decisions
    MANIFEST.md               contents, row counts, source tables,
                              export time, redaction count

SECRET SCRUB (the point of the tool): every value is scrubbed before
writing, and every written file is re-scanned as a final pass.
Scrubbing a value = dropping the offending dict field / list item /
line and counting the redaction. Certain patterns (a private-key
block) are UNSCRUBBABLE by field-drop alone in free text: if such a
pattern survives scrubbing in any output file, the export FAILS with
a nonzero exit, naming the file and the pattern CLASS only — the
secret itself is never printed.

CLI:
  sbos_export.py export [--out DIR]
  sbos_export.py selftest
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

# ---------------------------------------------------------------------------
# Secret scrubbing — pure functions, unit-tested by selftest.
# ---------------------------------------------------------------------------

# Field names whose VALUES are always dropped.
SECRET_FIELD_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
    r"token|password|passwd|secret|credential|private[_-]?key)",
    re.I)

# Value patterns: (class_name, regex, scrubbable_by_redaction)
VALUE_PATTERNS = [
    ("private_key_block",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), False),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), True),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), True),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), True),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}"), True),
    ("assigned_secret",
     re.compile(r"(?i)\b(api[_-]?key|password|passwd|secret|token)\s*[:=]\s*"
                r"['\"]?[^\s'\"]{8,}"), True),
]

REDACTED = "[REDACTED]"


def scrub_text(text):
    """Scrub a string. Returns (new_text, redactions, unscrubbable_classes).

    Token-like substrings are replaced with [REDACTED]. A private-key
    BLOCK (header through footer) is removed whole when a footer is
    present; a lone header with no footer is unscrubbable — reported
    so the caller can fail the export.
    """
    redactions = 0
    unscrubbable = []
    # Private-key block: remove header..footer inclusive when paired.
    block_re = re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.S)
    text, n = block_re.subn(REDACTED, text)
    redactions += n
    for cls, rx, scrubbable in VALUE_PATTERNS:
        if cls == "private_key_block":
            if rx.search(text):
                unscrubbable.append(cls)
            continue
        text, n = rx.subn(REDACTED, text)
        redactions += n
    return text, redactions, unscrubbable


def scrub_obj(obj):
    """Recursively scrub a JSON-able object.

    Dict fields whose NAME matches a secret pattern are dropped.
    String values are scrubbed via scrub_text. Returns
    (new_obj, redactions, unscrubbable_classes).
    """
    redactions = 0
    unscrubbable = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and SECRET_FIELD_RE.search(k):
                redactions += 1
                continue
            nv, r, u = scrub_obj(v)
            redactions += r
            unscrubbable.extend(u)
            out[k] = nv
        return out, redactions, unscrubbable
    if isinstance(obj, list):
        out = []
        for v in obj:
            nv, r, u = scrub_obj(v)
            redactions += r
            unscrubbable.extend(u)
            out.append(nv)
        return out, redactions, unscrubbable
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj, 0, []


def scan_text(text):
    """Final-pass scan: return list of pattern classes present."""
    hits = []
    for cls, rx, _ in VALUE_PATTERNS:
        if rx.search(text):
            hits.append(cls)
    # assigned_secret uses the scrubbed form check too: a bare
    # 'api_key: [REDACTED]' must not trip the scanner.
    return [h for h in hits
            if not (h == "assigned_secret" and REDACTED in text
                    and not re.search(
                        r"(?i)\b(api[_-]?key|password|passwd|secret|token)"
                        r"\s*[:=]\s*(?!\[REDACTED\])[^\s'\"]{8,}", text))]


def scan_obj_text(text):
    return scan_text(text)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

TABLES = [
    ("atlas_nodes.json", "atlas.nodes"),
    ("atlas_edges.json", "atlas.edges"),
    ("calendar_events.json", "life_calendar.events"),
    ("calendar_events_sbos.json", "successbrian_os.calendar_events"),
    ("life_calendar.json", "successbrian_os.life_calendar"),
    ("publications.json", "campaignsdesk.publications"),
    ("content_items.json", "campaignsdesk.content_items"),
    ("renditions.json", "campaignsdesk.renditions"),
    ("article_ideas.json", "campaignsdesk.article_ideas"),
    ("pm_projects.json", "successbrian_os.pm_projects"),
    ("pm_decisions.json", "successbrian_os.pm_decisions"),
]


def _conn():
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(dbname="ecosystem_central", host="localhost",
                            cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_table(cur, table):
    cur.execute("SELECT * FROM %s" % table)
    return [dict(r) for r in cur.fetchall()]


def run_export(out_dir):
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    bundle = os.path.join(out_dir, "sbos-bundle-%s" % stamp)
    os.makedirs(bundle, exist_ok=True)
    total_redactions = 0
    manifest_rows = []
    conn = _conn()
    cur = conn.cursor()
    try:
        for fname, table in TABLES:
            try:
                rows = fetch_table(cur, table)
            except Exception as e:
                conn.rollback()
                rows = []
                manifest_rows.append((fname, table, 0,
                                      "ERROR: %s" % type(e).__name__))
                continue
            clean, r, unscrubbable = scrub_obj(
                json.loads(json.dumps(rows, default=str)))
            total_redactions += r
            if unscrubbable:
                print("EXPORT FAILED: %s contains unscrubbable pattern "
                      "class: %s" % (fname, sorted(set(unscrubbable))),
                      file=sys.stderr)
                conn.close()
                return 1, bundle
            path = os.path.join(bundle, fname)
            with open(path, "w") as f:
                json.dump(clean, f, indent=1, default=str)
            manifest_rows.append((fname, table, len(rows), "ok"))
    finally:
        try:
            conn.close()
        except Exception:
            pass
    # Manifest
    lines = ["# SBOS portability bundle", "",
             "Export time: %s" % datetime.now().isoformat(timespec="seconds"),
             "Bundle: %s" % os.path.basename(bundle), "",
             "| file | source table | rows | status |",
             "|---|---|---:|---|"]
    for fname, table, n, st in manifest_rows:
        lines.append("| %s | %s | %d | %s |" % (fname, table, n, st))
    lines += ["", "Secret redactions applied: %d" % total_redactions,
              "Secret policy: fields named like key/token/password/secret "
              "are dropped; token-shaped values are redacted; a surviving "
              "secret pattern fails the export.", ""]
    with open(os.path.join(bundle, "MANIFEST.md"), "w") as f:
        f.write("\n".join(lines))
    # Final pass: re-scan every written file.
    for fname in os.listdir(bundle):
        text = open(os.path.join(bundle, fname)).read()
        hits = scan_obj_text(text)
        if hits:
            print("EXPORT FAILED: final scan of %s found pattern class: %s"
                  % (fname, hits), file=sys.stderr)
            return 1, bundle
    print("export OK: %s (%d files, %d redactions)"
          % (bundle, len(manifest_rows) + 1, total_redactions))
    return 0, bundle


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def selftest():
    checks = 0
    fails = 0

    def check(cond, label):
        nonlocal checks, fails
        checks += 1
        if cond:
            print("PASS %s" % label)
        else:
            fails += 1
            print("FAIL %s" % label)

    fake_key_line = "api_key = 'FAKEKEY1234567890abcdef'"
    obj, r, u = scrub_obj({"note": fake_key_line, "name": "clean"})
    check(r >= 1 and "FAKEKEY1234567890" not in json.dumps(obj),
          "fake api_key line is redacted")
    check(obj.get("name") == "clean", "clean sibling field survives")

    obj2, r2, _ = scrub_obj({"api_key": "whatever-secret-value",
                             "title": "keep me"})
    check("api_key" not in obj2 and r2 == 1 and obj2["title"] == "keep me",
          "secret-named field is dropped")

    pk = ("-----BEGIN RSA PRIVATE KEY-----\nMIIFAKEFAKEFAKE\n"
          "-----END RSA PRIVATE KEY-----")
    obj3, r3, u3 = scrub_obj({"blob": "prefix " + pk + " suffix"})
    check(r3 >= 1 and "MIIFAKE" not in json.dumps(obj3),
          "paired private-key block is removed whole")

    lone = "-----BEGIN RSA PRIVATE KEY-----\nMIIFAKE-no-footer"
    _, _, u4 = scrub_obj({"blob": lone})
    check("private_key_block" in u4,
          "lone private-key header is unscrubbable -> export must fail")

    clean, r5, u5 = scrub_obj({"a": "ordinary text about calendars"})
    check(r5 == 0 and not u5 and clean["a"].startswith("ordinary"),
          "clean text passes untouched")

    gh = {"note": "token ghp_" + "A" * 24 + " here"}
    obj6, r6, _ = scrub_obj(gh)
    check(r6 >= 1 and "ghp_" not in json.dumps(obj6),
          "github-token-shaped value is redacted")

    # Real export smoke run to /tmp.
    tmp = tempfile.mkdtemp(prefix="sbos-export-selftest-")
    try:
        rc, bundle = run_export(tmp)
        check(rc == 0 and os.path.isdir(bundle), "smoke export exits 0")
        manifest = os.path.join(bundle, "MANIFEST.md")
        check(os.path.isfile(manifest), "smoke manifest exists")
        ok_json = True
        hits = 0
        for fname in os.listdir(bundle):
            p = os.path.join(bundle, fname)
            if fname.endswith(".json"):
                try:
                    json.load(open(p))
                except Exception:
                    ok_json = False
            hits += len(scan_obj_text(open(p).read()))
        check(ok_json, "smoke JSON files all parse")
        check(hits == 0, "smoke final scan: zero pattern hits")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("SELFTEST %s: %d/%d checks passed"
          % ("OK" if fails == 0 else "FAILED", checks - fails, checks))
    return 0 if fails == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="SBOS portability export")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--out", default=os.path.expanduser("~/exports"))
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    os.makedirs(args.out, exist_ok=True)
    rc, _ = run_export(args.out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
