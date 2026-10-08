#!/usr/bin/env bash
# model-sync.sh
# PURPOSE: rsync model weight directories from the source host to all replicas,
#          then verify with sha256 manifests.
# WHY: model weights live in multiple places (k11-alpha source, X79 NVMe replicas,
#      local copies). When weights change, every replica must converge.
# CALLED BY: operator on the source host after a model update.
# NOTES: idempotent. Uses ssh; replicas need the receiving user trusted.
#        Run from the MODEL_SOURCE_HOST.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${1:-$SCRIPT_DIR/../fleet-fabric.conf}"
[ -f "$CONF" ] || CONF="/opt/fleet-fabric/fleet-fabric.conf"
# shellcheck source=/dev/null
source "$CONF"

: "${MODEL_DIRS:?MODEL_DIRS not set in $CONF}"
: "${REPLICA_HOSTS:?REPLICA_HOSTS not set in $CONF}"

MANIFEST_DIR="/tmp/fleet-model-manifests"
mkdir -p "$MANIFEST_DIR"

for pair in $MODEL_DIRS; do
  src="${pair%%:*}"
  subdir="${pair##*:}"
  [ -d "$src" ] || { echo "WARN: source dir $src missing, skipping"; continue; }

  echo "building manifest for $src ..."
  ( cd "$src" && find . -type f -exec sha256sum {} + | sort > "$MANIFEST_DIR/$subdir.sha256" )

  for replica in $REPLICA_HOSTS; do
    dest="/srv/fleet-models/$subdir"
    echo "syncing $src -> $replica:$dest"
    ssh "$replica" "mkdir -p '$dest'"
    rsync -aH --delete --info=stats1 "$src/" "$replica:$dest/"
    echo "verifying $replica:$dest ..."
    ssh "$replica" "cd '$dest' && sha256sum -c --quiet" < "$MANIFEST_DIR/$subdir.sha256" \
      && echo "OK: $replica:$dest verified" \
      || { echo "FATAL: checksum mismatch on $replica:$dest"; exit 1; }
  done
done

echo "OK: all replicas in sync and verified"
