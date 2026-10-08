#!/usr/bin/env bash
# fabric-health.sh
# PURPOSE: verify the fabric from a consumer: exporters reachable, namespaces
#          visible, multipath path counts healthy.
# WHY: single command to answer "is the fabric healthy?" after maintenance,
#      reboots, or before launching inference jobs.
# CALLED BY: operator, or cron for routine checks.
# NOTES: read-only. Exit 0 = healthy, 1 = degraded, 2 = down.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${1:-$SCRIPT_DIR/../fleet-fabric.conf}"
[ -f "$CONF" ] || CONF="/opt/fleet-fabric/fleet-fabric.conf"
# shellcheck source=/dev/null
source "$CONF"

: "${EXPORTERS:?EXPORTERS not set in $CONF}"
: "${SUBSYSTEMS:?SUBSYSTEMS not set in $CONF}"
NVMET_PORT="${NVMET_PORT:-4420}"

rc=0
echo "== exporter reachability =="
for exporter in $EXPORTERS; do
  if timeout 3 bash -c "echo > /dev/tcp/$exporter/$NVMET_PORT" 2>/dev/null; then
    echo "  UP    $exporter:$NVMET_PORT"
  else
    echo "  DOWN  $exporter:$NVMET_PORT"
    rc=1
  fi
done

echo "== namespaces (nvme list) =="
if ! nvme list 2>/dev/null | grep -iq tcp; then
  echo "  none visible over TCP"
  rc=2
else
  nvme list 2>/dev/null | grep -i tcp
fi

echo "== multipath paths per subsystem =="
for nqn in $SUBSYSTEMS; do
  # count live paths across all controllers for this subsystem
  paths=$(nvme list-subsys 2>/dev/null | grep -A20 "$nqn" | grep -c "nvme[0-9]" || true)
  echo "  $nqn : $paths path(s)"
  if [ "${paths:-0}" -lt 2 ]; then
    echo "  WARN: fewer than 2 paths — no failover redundancy"
    [ "$rc" -eq 0 ] && rc=1
  fi
done

echo "== link speeds (fabric interfaces) =="
for iface in $(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(eno|enp|eth|bond)'); do
  speed=$(ethtool "$iface" 2>/dev/null | grep -i "speed:" | awk '{print $2}' || true)
  [ -n "$speed" ] && echo "  $iface : $speed"
done

if [ "$rc" -eq 0 ]; then echo "HEALTHY"; elif [ "$rc" -eq 1 ]; then echo "DEGRADED"; else echo "DOWN"; fi
exit "$rc"
