#!/usr/bin/env python3
"""Opportunistic inbox refresh — skips when the system is jammed.
Required daily run is a separate cron; this one only runs if load is low.
"""
import os, sys

# Skip if load average (1min) exceeds 1.5x CPU count, or jam flag exists
if os.path.exists('/tmp/ecosystem-jam'):
    print('SKIP: jam flag set')
    sys.exit(0)
try:
    load1 = os.getloadavg()[0]
    ncpu = os.cpu_count() or 4
    if load1 > ncpu * 1.5:
        print(f'SKIP: load {load1:.1f} > {ncpu*1.5:.1f}')
        sys.exit(0)
except Exception as e:
    print(f'load check failed ({e}), running anyway')

os.system('/usr/bin/python3 /home/successbrian/successbrian-os/tools/dashboard/build_unified_inbox.py')
os.system('/usr/bin/scp -o ConnectTimeout=10 /home/successbrian/dashboard-fragments/inbox-unified.html root@100.118.196.66:/var/www/fleet-builds/inbox-unified.html >> /tmp/unified-inbox.log 2>&1')
print('RAN: opportunistic refresh complete')
