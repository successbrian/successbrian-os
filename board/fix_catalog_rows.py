#!/usr/bin/env python3
"""Remove catalog rows whose registered filename does not
resolve to a real document via kindex.allm_doc.

These are the 2026-11-09 backfill's own malformed rows: the
first base-filename rule missed AnythingLLM's 16-hex suffix
shape ('name-md-<16hex>.json'), so the row's filename kept the
hash tail and allm_doc cannot match it. The documents
themselves are untouched; the corrected backfill re-registers
them under their true base names immediately after. Open
missing_doc tickets raised against the malformed rows go with
them (they describe the malformed row, not the document).
"""

import os
import sys

sys.path.insert(0, os.path.expanduser("~/successbrian-os/board"))
import kindex  # noqa: E402


def main():
    c = kindex.conn()
    cur = c.cursor()
    cur.execute(
        "SELECT canonical_id, allm_workspace, allm_filename "
        "FROM successbrian_os.knowledge_index WHERE "
        "kind = 'embedded-doc'")
    rows = cur.fetchall()
    bad = []
    for cid, ws, fn in rows:
        reg, present, _t = kindex.allm_doc(ws, fn)
        if not (reg and present):
            bad.append(cid)
    print("catalog rows checked: %d; non-resolving: %d"
          % (len(rows), len(bad)))
    if "--apply" not in sys.argv:
        for cid in bad[:10]:
            print("  WOULD REMOVE", cid)
        print("DRY RUN — pass --apply.")
        return 0
    for cid in bad:
        cur.execute(
            "DELETE FROM successbrian_os.knowledge_tickets "
            "WHERE canonical_id = %s AND status = 'open' "
            "AND kind = 'missing_doc'", (cid,))
        cur.execute(
            "DELETE FROM successbrian_os.knowledge_index "
            "WHERE canonical_id = %s AND kind = 'embedded-doc'",
            (cid,))
    c.commit()
    print("REMOVED %d malformed catalog rows (+ their open "
          "missing_doc tickets)" % len(bad))
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
