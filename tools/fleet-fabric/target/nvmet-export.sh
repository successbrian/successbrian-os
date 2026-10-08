#!/usr/bin/env bash
# nvmet-export.sh
# PURPOSE: configure this host as an NVMe-oF (NVMe/TCP) target exporting the
#          namespaces listed in fleet-fabric.conf.
# WHY: lets NVMe-less machines (DL380 Gen8s) consume this host's NVMe/SSD as a
#      local NVMe device for Colibri's storage tier.
# CALLED BY: operator, or target/nvmet-fabric.service at boot.
# NOTES: idempotent — safe to re-run. Requires root. Kernel 5.4+.
#        Read-only sharing is enforced initiator-side (ro mount) + checksums;
#        all initiators are fleet-owned.

set -euo pipefail

# --- config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${1:-$SCRIPT_DIR/../fleet-fabric.conf}"
[ -f "$CONF" ] || CONF="/opt/fleet-fabric/fleet-fabric.conf"
# shellcheck source=/dev/null
source "$CONF"

: "${FABRIC_IP:?FABRIC_IP not set in $CONF}"
: "${NQN_BASE:?NQN_BASE not set in $CONF}"
: "${EXPORT_NAMESPACES:?EXPORT_NAMESPACES not set in $CONF}"
NVMET_PORT="${NVMET_PORT:-4420}"

CFG=/sys/kernel/config/nvmet

# --- modules ---
modprobe nvmet 2>/dev/null || { echo "FATAL: cannot load nvmet module"; exit 1; }
modprobe nvmet-tcp 2>/dev/null || { echo "FATAL: cannot load nvmet-tcp module"; exit 1; }
[ -d "$CFG" ] || { echo "FATAL: configfs nvmet not present at $CFG"; exit 1; }

# --- port 1: single TCP port shared by all subsystems on this host ---
if [ ! -d "$CFG/ports/1" ]; then
  mkdir "$CFG/ports/1"
  echo "tcp"              > "$CFG/ports/1/addr_trtype"
  echo "ipv4"             > "$CFG/ports/1/addr_adrfam"
  echo "$FABRIC_IP"       > "$CFG/ports/1/addr_traddr"
  echo "$NVMET_PORT"      > "$CFG/ports/1/addr_trsvcid"
  echo "created port 1 -> $FABRIC_IP:$NVMET_PORT"
else
  echo "port 1 already exists"
fi

# --- subsystems + namespaces ---
ns_idx=0
for pair in $EXPORT_NAMESPACES; do
  name="${pair%%:*}"
  dev="${pair##*:}"
  ns_idx=$((ns_idx + 1))
  nqn="${NQN_BASE}:${name}"

  [ -b "$dev" ] || { echo "WARN: $dev is not a block device, skipping $name"; continue; }

  if [ ! -d "$CFG/subsystems/$nqn" ]; then
    mkdir "$CFG/subsystems/$nqn"
    echo 1 > "$CFG/subsystems/$nqn/attr_allow_any_host"
    # stable serial per namespace so initiators see consistent IDs
    echo "fleet-${name}" > "$CFG/subsystems/$nqn/attr_serial" 2>/dev/null || true
    echo "created subsystem $nqn"
  fi

  nsdir="$CFG/subsystems/$nqn/namespaces/$ns_idx"
  if [ ! -d "$nsdir" ]; then
    mkdir "$nsdir"
    echo -n "$dev" > "$nsdir/device_path"
    echo 1 > "$nsdir/enable"
    echo "exported $dev as $nqn nsid $ns_idx"
  else
    echo "namespace $nqn/$ns_idx already exists"
  fi

  link="$CFG/ports/1/subsystems/$nqn"
  if [ ! -e "$link" ]; then
    ln -s "$CFG/subsystems/$nqn" "$link"
    echo "linked $nqn to port 1"
  fi
done

echo "OK: $(echo "$EXPORT_NAMESPACES" | wc -w) namespace(s) configured on $FABRIC_IP:$NVMET_PORT"
echo "Verify from a consumer: nvme discover -t tcp -a $FABRIC_IP -s $NVMET_PORT"
