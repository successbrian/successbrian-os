#!/usr/bin/env python3
"""queue_view.py - ONE place to see what is queued and what is stuck.

SuccessBrian OS project: queue-stuck-visibility (Brian, 2026-10-27: "we do
need to see what's queued, what's stuck"; build started 2026-10-28 on his
pick of queue visibility as the first systems improvement).

Deterministic: no model calls. Reads every queue table in ecosystem_central
and renders one markdown page:
  1. STUCK FIRST - queues with old open items or no recent movement, worst first.
  2. MAIN QUEUES in detail (the working queues of the OS).
  3. CENSUS of every other queue-named table (legacy piles included).

"Stuck" rules (stated, not scored): a main-queue open item older than 7 days
is stuck; a census queue whose oldest open item is older than 14 days is a
dead-candidate; a main queue with open items and zero completions in 24h is
not draining. Terminal status sets are explicit per table below - a status
not listed counts as OPEN, so new statuses surface instead of hiding.

Usage: queue_view.py [--write]   (prints to stdout; --write also saves the
stable copy at tools/state/queue-view.md)
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbos_common as sc

TERMINAL_MAIN = {
    'successbrian_os.qwen_task_queue': {'done', 'completed', 'cancelled'},
    'successbrian_os.v4pro_handoffs': {'done', 'cancelled', 'failed'},
    'successbrian_os.work_queue': {'done', 'cancelled'},
    'successbrian_os.pending_questions': {'answered', 'dropped'},
    'public.ai_task_queue': {'completed', 'duplicated', 'cancelled'},
    'atlas.scattered_captures': {'triaged', 'discarded'},
}
LABEL_MAIN = {
    'successbrian_os.qwen_task_queue': ('title', 'created_at', 'finished_at'),
    'successbrian_os.v4pro_handoffs': ('task_summary', 'created_at', 'completed_at'),
    'successbrian_os.work_queue': ('title', 'created_at', 'updated_at'),
    'successbrian_os.pending_questions': ('question', 'created_at', 'updated_at'),
    'public.ai_task_queue': ('action', 'created_at', 'completed_at'),
    'atlas.scattered_captures': ('title', 'created_at', 'triaged_at'),
}
GENERIC_TERMINAL = {'done', 'completed', 'complete', 'cancelled', 'canceled',
                    'failed', 'error', 'resolved', 'closed', 'archived',
                    'sent', 'published', 'processed', 'skipped', 'rejected',
                    'dead', 'answered', 'dropped', 'triaged', 'discarded',
                    'duplicated', 'approved', 'applied', 'ingested', 'graded'}
STUCK_MAIN_DAYS = 7
STUCK_CENSUS_DAYS = 14

def q1(sql):
    lines = sc.pg_lines(sql)
    return lines[0] if lines else ''

def age_days(ts):
    if not ts or ts in ('', None):
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace(' ', 'T').split('+')[0].split('.')[0])
        return (datetime.datetime.now() - dt).days
    except Exception:
        return None

def main_queue_detail(full):
    schema, table = full.split('.')
    term = TERMINAL_MAIN[full]
    label_col, created_col, finish_col = LABEL_MAIN[full]
    term_sql = ",".join("'" + t + "'" for t in sorted(term))
    total_open = q1(f"SELECT count(*) FROM {full} WHERE status NOT IN ({term_sql})")
    by_status = [f"{a}={b}" for a, b in
                 (line.split('|') for line in sc.pg_lines(
                     f"SELECT status, count(*) FROM {full} WHERE status NOT IN ({term_sql}) GROUP BY 1 ORDER BY 2 DESC"))]
    oldest = q1(f"SELECT {created_col} FROM {full} WHERE status NOT IN ({term_sql}) ORDER BY {created_col} ASC LIMIT 1")
    oldest_label = q1(f"SELECT left({label_col}, 70) FROM {full} WHERE status NOT IN ({term_sql}) ORDER BY {created_col} ASC LIMIT 1")
    flow = q1(f"SELECT count(*) FROM {full} WHERE status IN ({term_sql}) AND {finish_col} > now() - interval '24 hours'")
    return {'open': int(total_open or 0), 'by_status': by_status,
            'oldest': oldest, 'oldest_age': age_days(oldest),
            'oldest_label': oldest_label, 'flow24': int(flow or 0)}

def census():
    tables = sc.pg_lines(
        "SELECT table_schema||'.'||table_name FROM information_schema.tables "
        "WHERE table_type='BASE TABLE' AND (table_name ILIKE '%queue%' "
        "OR table_name ILIKE '%handoff%' OR table_name ILIKE '%pending%') "
        "AND table_name NOT LIKE '%_bak_%' ORDER BY 1")
    out = []
    for full in tables:
        if full in TERMINAL_MAIN:
            continue
        schema, table = full.split('.')
        cols = sc.pg_lines(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema='{schema}' AND table_name='{table}'")
        scol = 'status' if 'status' in cols else ('state' if 'state' in cols else None)
        tcol = next((c for c in ['created_at', 'enqueued_at', 'queued_at', 'inserted_at', 'created', 'ts'] if c in cols), None)
        try:
            if scol:
                term_sql = ",".join("'" + t + "'" for t in sorted(GENERIC_TERMINAL))
                open_n = int(q1(f"SELECT count(*) FROM {full} WHERE {scol} NOT IN ({term_sql})") or 0)
                oldest = q1(f"SELECT {tcol} FROM {full} WHERE {scol} NOT IN ({term_sql}) ORDER BY {tcol} ASC LIMIT 1") if (tcol and open_n) else ''
            else:
                open_n = int(q1(f"SELECT count(*) FROM {full}") or 0)
                oldest = q1(f"SELECT {tcol} FROM {full} ORDER BY {tcol} ASC LIMIT 1") if (tcol and open_n) else ''
            top = ''
            if scol and open_n > 100:
                top = ', '.join(f"{a}={b}" for a, b in
                                (line.split('|') for line in sc.pg_lines(
                                    f"SELECT {scol}, count(*) FROM {full} WHERE {scol} NOT IN ({term_sql}) GROUP BY 1 ORDER BY 2 DESC LIMIT 3")))
            out.append({'table': full, 'open': open_n, 'oldest_age': age_days(oldest), 'top': top})
        except Exception as e:
            out.append({'table': full, 'open': -1, 'oldest_age': None, 'err': str(e)[:60]})
    return out

def main():
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    mains, stuck = {}, []
    for full in TERMINAL_MAIN:
        try:
            d = main_queue_detail(full)
        except Exception as e:
            d = {'open': -1, 'by_status': [], 'oldest': '', 'oldest_age': None,
                 'oldest_label': '', 'flow24': 0, 'err': str(e)[:60]}
        mains[full] = d
        if d['open'] > 0 and d['oldest_age'] is not None and d['oldest_age'] > STUCK_MAIN_DAYS:
            stuck.append((d['oldest_age'], f"{full}: {d['open']} open, oldest {d['oldest_age']}d - \"{d['oldest_label']}\""))
        if d['open'] > 0 and d['flow24'] == 0 and LABEL_MAIN[full][2] in ('finished_at', 'completed_at', 'triaged_at'):
            stuck.append((d['oldest_age'] or 0, f"{full}: NOT DRAINING - {d['open']} open, 0 completions in 24h"))
    cen = census()
    for c in cen:
        if c['open'] > 0 and c['oldest_age'] is not None and c['oldest_age'] > STUCK_CENSUS_DAYS:
            stuck.append((c['oldest_age'], f"{c['table']}: DEAD-CANDIDATE - {c['open']} open, oldest {c['oldest_age']}d"))
    stuck.sort(key=lambda x: -x[0])

    L = [f"# Queue view - {now}", '',
         'One place for what is queued and what is stuck across SuccessBrian OS.',
         'Process, not status tiles: counts, ages, and whether each queue moved in the last 24 hours.', '',
         '## Stuck first']
    if stuck:
        for _, s in stuck:
            L.append(f"- {s}")
    else:
        L.append('- Nothing over the stuck thresholds right now.')
    L += ['', '## Main queues']
    for full, d in mains.items():
        if d['open'] < 0:
            L.append(f"- **{full}** - UNREADABLE ({d.get('err','')})")
            continue
        bs = ', '.join(d['by_status']) if d['by_status'] else 'none open'
        age = f"oldest {d['oldest_age']}d" if d['oldest_age'] is not None else 'no open items'
        L.append(f"- **{full}** - {d['open']} open ({bs}); {age}; {d['flow24']} finished in last 24h")
        if d['open'] and d['oldest_label']:
            L.append(f"  - oldest open: \"{d['oldest_label']}\"")
    # Asking curve (autonomy study proposal D - measure our own asking rate)
    try:
        arr = int(q1("SELECT count(*) FROM successbrian_os.pending_questions WHERE created_at > now() - interval '7 days'") or 0)
        ans = int(q1("SELECT count(*) FROM successbrian_os.pending_questions WHERE status='answered' AND updated_at > now() - interval '7 days'") or 0)
        drp = int(q1("SELECT count(*) FROM successbrian_os.pending_questions WHERE status='dropped' AND updated_at > now() - interval '7 days'") or 0)
        ans_quiet = int(q1("SELECT count(*) FROM successbrian_os.pending_questions WHERE status='answered' AND updated_at > now() - interval '7 days' AND surfaced_at IS NULL") or 0)
        L += ['', '## Asking curve - last 7 days',
              f"- Questions arrived: {arr}; answered: {ans} (of those, {ans_quiet} answered without ever being surfaced to Brian - refinement did it); dropped as stale: {drp}; still open now: {mains['successbrian_os.pending_questions']['open']}",
              '- The asking rate is a number, not a feeling: if arrivals keep beating answers + drops, the pile grows and refinement is losing.']
    except Exception as e:
        L += ['', '## Asking curve - last 7 days', f'- UNREADABLE ({str(e)[:60]})']

    L += ['', '## Census - every other queue table']
    live = [c for c in cen if c['open'] > 0]
    empty = [c for c in cen if c['open'] == 0]
    unread = [c for c in cen if c['open'] < 0]
    for c in sorted(live, key=lambda x: -(x['oldest_age'] or 0)):
        age = f"oldest {c['oldest_age']}d" if c['oldest_age'] is not None else 'age unknown'
        extra = f" ({c['top']})" if c.get('top') else ''
        L.append(f"- {c['table']} - {c['open']} open; {age}{extra}")
    if empty:
        L.append(f"- (empty, nothing open: {len(empty)} tables)")
    for c in unread:
        L.append(f"- {c['table']} - UNREADABLE ({c.get('err','')})")
    L += ['', f"Rules: main-queue item open > {STUCK_MAIN_DAYS}d = stuck; census oldest open > {STUCK_CENSUS_DAYS}d = dead-candidate; "
              'open items + 0 completions in 24h = not draining. A status not in a table\'s terminal list counts as open, so new statuses surface instead of hiding.',
          'Project: queue-stuck-visibility. Tool: tools/queue_view.py (deterministic, no model calls).']
    text = '\n'.join(L) + '\n'
    print(text)
    if '--write' in sys.argv:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state', 'queue-view.md')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            f.write(text)
        print(f'[written: {out}]', file=sys.stderr)

if __name__ == '__main__':
    main()
