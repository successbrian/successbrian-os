#!/usr/bin/env bash
# nvme-fabric-connect.sh
# PURPOSE: connect this host to all fabric exporters as an NVMe/TCP initiator
#          with multipath enabled for automatic path failover.
# WHY: consumers (DL380 Proxmox hosts) get remote NVMe/SSD as local /dev/nvme*
#      devices; if an exporter goes down, I/O retries on surviving paths.
# CALLED BY: operator, or initiator/nvme-fabric.service at boot.
# NOTES: idempotent — safe to re-run. Requires root and nvme-cli.
#        Enables nvme_core multipath persistently via /etc/modprobe.d.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${1:-$SCRIPT_DIR/../fleet-fabric.conf}"
[ -f "$CONF" ] || CONF="/opt/fleet-fabric/fleet-fabric.conf"
# shellcheck source=/dev/null
source "$CONF"

: "${EXPORTERS:?EXPORTERS not set in $CONF}"
: "${SUBSYSTEMS:?SUBSYSTEMS not set in $CONF}"
NVMET_PORT="${NVMET_PORT:-4420}"

command -v nvme >/dev/null || { echo "FATAL: nvme-cli not installed (apt install nvme-cli)"; exit 1; }

# --- multipath: must be set before nvme-tcp loads ---
if ! grep -q "nvme_core multipath=Y" /etc/modprobe.d/fleet-fabric.conf 2>/dev/null; then
  echo "options nvme_core multipath=Y" > /etc/modprobe.d/fleet-fabric.conf
  echo "enabled nvme_core multipath (takes effect on module load)"
fi
if ! lsmod | grep -q "^nvme_core"; then
  modprobe nvme_core multipath=Y
elif [ "$(cat /sys/module/nvme_core/parameters/multipath 2>/dev/null)" != "Y" ]; then
  echo "WARN: nvme_core already loaded without multipath=Y; reboot or reload modules to enable"
fi
modprobe nvme-tcp 2>/dev/null || { echo "FATAL: cannot load nvme-tcp"; exit 1; }
modprobe nvme-fabrics 2>/dev/null || true

# --- connect: every subsystem on every exporter ---
for exporter in $EXPORTERS; do
  # skip unreachable exporters quickly; multipath covers the rest
  if ! timeout 3 bash -c "echo > /dev/tcp/$exporter/$NVMET_PORT" 2>/dev/null; then
    echo "WARN: $exporter:$NVMET_PORT unreachable, skipping (multipath covers)"
    continue
  fi
  for nqn in $SUBSYSTEMS; do
    if nvme list-subsys 2>/dev/null | grep -q "$nqn"; then
      echo "already connected: $nqn via $exporter"
      continue
    fi
    if nvme connect -t tcp -n "$nqn" -a "$exporter" -s "$NVMET_PORT" 2>&1; then
      echo "connected: $nqn via $exporter"
    else
      echo "WARN: failed to connect $nqn via $exporter"
    fi
  done
done

echo "--- resulting devices ---"
nvme list 2>/dev/null | grep -i tcp || echo "(no TCP namespaces yet)"
echo "--- multipath status ---"
cat /sys/module/nvme_core/parameters/multipath 2>/dev/null || echo "unknown"
