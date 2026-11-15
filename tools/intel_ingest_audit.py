#!/usr/bin/env python3
"""Intel ingestion audit — detects the WF3 failure classes.

# @docmap successbrian_os.ingest_leg

Built 2026-11-15 after captures #1834/#1836 exposed three
silent ingestion defects that nothing in the system measured:

  1. MISROUTE — a capture with a substantial result body was
     classified kind=price and swallowed by the price branch;
     its document was never filed. (The clerk's mixed rule,
     board/scatter_clerk.py SUBSTANCE_MIN_CHARS, fixes the
     cause; this audit catches any that still slip through,
     including ones filed before the fix.)
  2. SCALE — a price_intel row whose amount lost its title's
     magnitude suffix ($250k recorded as 250.0).
  3. NULL-AMOUNT — a price_intel row with no amount although
     the capture title states a parseable $ amount.

Also REPORTED (warning, never a failure — producers dump
freely per Brian's 2026-11-14 doctrine, so a missing link is
surfaced, not blocked): intel captures carrying no source URL
anywhere in context or body. Brian's filing form (2026-10-25)
asks intel to carry its source URL + checked date; this makes
the count visible instead of discoverable only by asking.

Prints INTEL_AUDIT_OK / INTEL_AUDIT_FAIL with counts and ids.
Registered as a daily PM QA check on project sbos-ingest-leg.
"""
import re
import sys

sys.path.insert(0, "/home/successbrian/successbrian-os/tools")
sys.path.insert(0, "/home/successbrian/successbrian-os/board")
import sbos_common  # noqa: E402

SUBSTANCE_MIN_CHARS = 1200  # mirrors scatter_clerk.py

_SUFFIX = {"k": 1000.0, "K": 1000.0, "m": 1000000.0, "M": 1000000.0}
_AMT_RE = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)([kKmM])?")


def _title_amounts(title):
    out = []
    for amt, suf in _AMT_RE.findall(title or ""):
        try:
            v = float(amt.replace(",", ""))
        except ValueError:
            continue
        out.append(v * _SUFFIX.get(suf, 1.0))
    return out


def main(argv):
    days = 30
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    misroute, scale, nullamt, no_url = [], [], [], []

    rows = sbos_common.pg_rows(
        "SELECT c.id, c.title, char_length(coalesce(c.raw_text,'')) "
        "AS raw_len, f.kind AS filing_kind "
        "FROM atlas.scattered_captures c "
        "LEFT JOIN successbrian_os.wf3_filings f "
        "ON f.capture_id = c.id "
        "WHERE c.created_at > now() - (%s || ' days')::interval "
        "AND c.context LIKE '%%INTEL dump%%' "
        "ORDER BY c.id", (str(days),))
    for cid, title, raw_len, filing_kind in rows:
        if filing_kind == "price" and (raw_len or 0) \
                >= SUBSTANCE_MIN_CHARS:
            misroute.append(cid)

    prows = sbos_common.pg_rows(
        "SELECT p.capture_id, p.amount, c.title "
        "FROM successbrian_os.price_intel p "
        "JOIN atlas.scattered_captures c ON c.id = p.capture_id "
        "WHERE p.checked_on > current_date - %s "
        "ORDER BY p.capture_id", (days,))
    for cid, amount, title in prows:
        amounts = _title_amounts(title)
        if amount is None:
            if amounts:
                nullamt.append(cid)
        elif amounts and not any(
                abs(float(amount) - a) < 0.01 for a in amounts):
            # The row's amount matches NO title amount — the
            # classic case is a dropped magnitude suffix.
            if any(abs(float(amount) * 1000.0 - a) < 0.01
                   or abs(float(amount) * 1000000.0 - a) < 0.01
                   for a in amounts):
                scale.append(cid)

    urows = sbos_common.pg_rows(
        "SELECT c.id FROM atlas.scattered_captures c "
        "WHERE c.created_at > now() - (%s || ' days')::interval "
        "AND c.context LIKE '%%INTEL dump%%' "
        "AND coalesce(c.context,'') !~ 'https?://' "
        "AND coalesce(c.raw_text,'') !~ 'https?://' "
        "ORDER BY c.id", (str(days),))
    no_url = [r[0] for r in urows]

    defects = len(misroute) + len(scale) + len(nullamt)
    warn = (f"warn_no_url={len(no_url)} {no_url[:20]}"
            if no_url else "warn_no_url=0")
    if defects:
        print(f"INTEL_AUDIT_FAIL defects={defects} "
              f"misroute={misroute} scale={scale} "
              f"null_amount={nullamt} {warn}")
        return 1
    print(f"INTEL_AUDIT_OK defects=0 {warn}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
