#!/usr/bin/env python3
"""doctor.py — SBOS system doctor: one command, plain compact text (WS-CAP item 5).

PURPOSE: A single read-only health readout an operator (or Brian) can
         run in seconds: capacity vs demand, memory drift, skill
         staleness, what changed this week, calendar/content health,
         and a final list of Needs-Brian flags.
WHY:     Brian (2026-10-27 WS-CAP). Every section is defensive
         (chat_brief pattern): a broken/absent source prints
         'unavailable: <why>' and the doctor still exits 0.
         Observe-and-report only: this module writes nothing,
         publishes nothing, sends nothing.
CALLED BY: operator; PM QA daily smoke check (exit 0 + header).

Optional line: the DeepSeek balance is surfaced ONLY as the existing
read-only line chat_brief already shows (v4pro_balance_history) —
no caps, no budget machinery (Brian: local horsepower is the scarcity).
"""
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guardrails_common as gc  # noqa: E402

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "successbrian-os")
CAMPAIGNS = os.path.join(HOME, "campaignsdesk")


def log_tail(path, n=1):
    if not os.path.exists(path):
        return f"unavailable: log not present ({path})"
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    try:
        with open(path, errors="replace") as f:
            lines = [ln.rstrip() for ln in f if ln.strip()]
        last = lines[-n:] if lines else ["(empty log)"]
        return f"last {mtime}: " + " | ".join(last)
    except Exception as e:
        return f"unavailable: {type(e).__name__}: {e}"


def build(conn):
    cur = conn.cursor()
    flags = []
    out = [f"SYSTEM DOCTOR — {datetime.now().strftime('%a %Y-%m-%d %H:%M')} (read-only)"]

    def sec(title, fn):
        try:
            lines = fn()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            lines = [f"unavailable: {type(e).__name__}: {e}"]
            flags.append(f"{title}: {lines[0]}")
        out.append(f"[{title}]")
        out.extend("  " + ln for ln in lines)
        return lines

    def capacity():
        cur.execute("SELECT to_regclass('successbrian_os.capacity_snapshots') AS reg")
        if not cur.fetchone()['reg']:
            return ["unavailable: capacity tables not built yet"]
        lines = []
        cur.execute("SELECT name, kind FROM successbrian_os.capacity_nodes ORDER BY name")
        for node in cur.fetchall():
            name = node["name"] if isinstance(node, dict) else node[0]
            cur.execute(
                """SELECT reachable, latency_ms, slots_total, slots_busy, saturated, taken_at
                     FROM successbrian_os.capacity_snapshots WHERE node_name=%s
                    ORDER BY taken_at DESC, id DESC LIMIT 1""", (name,))
            s = cur.fetchone()
            if not s:
                lines.append(f"{name}: no snapshots yet")
                continue
            g = (lambda k, i: s[k] if isinstance(s, dict) else s[i])
            lines.append(f"{name}: reachable={g('reachable',0)} latency_ms={g('latency_ms',1)} "
                         f"slots={g('slots_busy',3)}/{g('slots_total',2)} saturated={g('saturated',4)} at {g('taken_at',5)}")
            if g('saturated', 4):
                flags.append(f"capacity: {name} saturated at last snapshot")
        cur.execute("SELECT count(*) AS n FROM successbrian_os.capacity_snapshots WHERE saturated AND taken_at > now() - interval '7 days'")
        r = cur.fetchone(); n7 = r["n"] if isinstance(r, dict) else r[0]
        cur.execute("SELECT item FROM successbrian_os.capacity_needs WHERE status='open' ORDER BY first_filed_at")
        needs = [r["item"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
        lines.append(f"saturation snapshots last 7d: {n7}")
        lines.append(f"open DealsDesk capacity needs: {len(needs)}" +
                     (": " + "; ".join(needs) if needs else ""))
        # optional existing DeepSeek line (read-only, as in chat_brief)
        try:
            cur.execute("SELECT usd, available FROM successbrian_os.v4pro_balance_history ORDER BY checked_at DESC LIMIT 1")
            r = cur.fetchone()
            if r:
                usd = r["usd"] if isinstance(r, dict) else r[0]
                av = r["available"] if isinstance(r, dict) else r[1]
                lines.append(f"DeepSeek (existing read-only line): ${float(usd):.2f} available={av}")
        except Exception:
            conn.rollback()
        return lines
    sec("Capacity vs demand", capacity)

    def memory_drift():
        cur.execute("SELECT to_regclass('atlas.currency_checks') AS reg")
        if not cur.fetchone()['reg']:
            return ["unavailable: atlas.currency_checks absent"]
        cur.execute("SELECT ran_at, discrepancies, fixed FROM atlas.currency_checks ORDER BY ran_at DESC LIMIT 1")
        r = cur.fetchone()
        if not r:
            return ["no currency checks on record"]
        g = (lambda k, i: r[k] if isinstance(r, dict) else r[i])
        disc = g('discrepancies', 1) or []
        lines = [f"last atlas_currency check: {g('ran_at',0)} discrepancies={len(disc)} fixed={len(g('fixed',2) or [])}"]
        for d in disc[:5]:
            lines.append(f"  discrepancy: {str(d)[:160]}")
        if disc:
            flags.append(f"memory drift: {len(disc)} atlas discrepancies at last check")
        return lines
    sec("Memory drift (Atlas currency)", memory_drift)

    def skills():
        cur.execute("SELECT to_regclass('successbrian_os.skill_registry') AS reg")
        if not cur.fetchone()['reg']:
            return ["unavailable: registry not built yet"]
        cur.execute("SELECT name, scan_verdict, last_scanned_at FROM successbrian_os.skill_registry ORDER BY last_scanned_at NULLS FIRST LIMIT 10")
        rows = cur.fetchall()
        if not rows:
            return ["registry empty"]
        lines = []
        for r in rows:
            g = (lambda k, i: r[k] if isinstance(r, dict) else r[i])
            lines.append(f"{g('name',0)}: verdict={g('scan_verdict',1)} scanned={g('last_scanned_at',2)}")
        return lines
    sec("Skill staleness", skills)

    def changed():
        lines = []
        for label, repo in (("successbrian-os", REPO), ("campaignsdesk", CAMPAIGNS)):
            try:
                p = subprocess.run(["git", "-C", repo, "log", "--since=7 days ago", "--oneline"],
                                   capture_output=True, text=True, timeout=20)
                if p.returncode != 0:
                    lines.append(f"{label}: unavailable: not a git repo / git log failed")
                    continue
                commits = [ln for ln in p.stdout.splitlines() if ln.strip()]
                lines.append(f"{label}: {len(commits)} commits in last 7d")
                for cm in commits[:3]:
                    lines.append(f"  {cm[:140]}")
            except Exception as e:
                lines.append(f"{label}: unavailable: {type(e).__name__}: {e}")
        cur.execute("SELECT count(*) AS n FROM atlas.scattered_captures WHERE created_at > now() - interval '7 days'")
        r = cur.fetchone(); lines.append(f"new captures (Intel Bridge) last 7d: {r['n'] if isinstance(r, dict) else r[0]}")
        cur.execute("SELECT count(*) AS n FROM successbrian_os.pm_decisions WHERE created_at > now() - interval '7 days'")
        r = cur.fetchone(); lines.append(f"PM decisions last 7d: {r['n'] if isinstance(r, dict) else r[0]}")
        return lines
    sec("Changed this week", changed)

    def cal_content():
        return [
            "calendar-content.log: " + log_tail(os.path.join(HOME, "logs/calendar-content.log")),
            "content-pm-resync.log: " + log_tail(os.path.join(HOME, "logs/content-pm-resync.log")),
            "capacity-sense.log: " + log_tail(os.path.join(HOME, "logs/capacity-sense.log")),
        ]
    sec("Calendar/content health", cal_content)

    def backups():
        cur.execute("SELECT to_regclass('successbrian_os.backup_runs') AS reg")
        if not cur.fetchone()['reg']:
            return ["unavailable: backup tables not built yet"]
        def last(kind, repo=None):
            q = ("SELECT finished_at, snapshot_id FROM successbrian_os.backup_runs "
                 "WHERE kind=%s AND status='ok'")
            params = [kind]
            if repo:
                q += " AND repo=%s"; params.append(repo)
            q += " ORDER BY finished_at DESC NULLS LAST LIMIT 1"
            cur.execute(q, params)
            r = cur.fetchone()
            return r if r else None
        g = (lambda r, k, i: (r[k] if isinstance(r, dict) else r[i]) if r else None)
        lines = []
        for label, kind, repo in (("file backup (local repo)", "files", "local"),
                                  ("file backup (offsite node-zero)", "files", "offsite"),
                                  ("PG backup (pg_dump, all databases)", "pg", None),
                                  ("restic check", "check", None)):
            r = last(kind, repo)
            lines.append(f"last {label}: {g(r, 'finished_at', 0) or 'never'}")
            if kind in ("pg", "files") and not r:
                flags.append(f"backups: no successful {label} on record")
        cur.execute("SELECT to_regclass('successbrian_os.backup_drills') AS reg")
        if cur.fetchone()['reg']:
            cur.execute("SELECT drilled_at, verdict FROM successbrian_os.backup_drills ORDER BY id DESC LIMIT 1")
            d = cur.fetchone()
            if d:
                lines.append(f"last restore drill: {g(d, 'drilled_at', 0)} verdict={g(d, 'verdict', 1)}")
                if g(d, 'verdict', 1) != "PASS":
                    flags.append("backups: last restore drill did not PASS")
            else:
                lines.append("last restore drill: never")
                flags.append("backups: no restore drill on record")
        try:
            import json as _json
            with open(os.path.join(REPO, "tools/guardrails/state/backups_status.json")) as f:
                st = _json.load(f)
            lines.append(f"status file: generated {st.get('generated_at')}")
        except Exception:
            lines.append("status file: unavailable")
        lines.append("PITR/WAL: unavailable - archive_mode=off (needs-Brian restart window)")
        return lines
    sec("Backups (verified)", backups)

    out.append("[Needs-Brian flags]")
    # Standing flag named in the WS-CAP order (AEO tracker purchase decision).
    flags.append("AEO tracker purchase decision — awaiting Brian (no purchase made; doctor only flags it)")
    if flags:
        out.extend("  - " + f for f in flags)
    else:
        out.append("  none")
    return "\n".join(out) + "\n"


def main(argv=None):
    c = gc.conn(dict_cursor=True)
    try:
        text = build(c)
    finally:
        c.close()
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
