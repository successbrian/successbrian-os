#!/bin/bash
# P5 dumb pipe: Hatch media_library/captures -> k11 captures_intake.
# DELIBERATELY DUMB: no OCR, no extraction, no model calls, no tokens.
# Moves image files only; all intelligence lives on k11 (p5_ingest.py).
# Runs on the Hatch VM via its own scheduler, a few minutes BEFORE the k11
# ingestion slot (:45) so files land in time. Uses the same tailnet proxy
# transport as ~/workspace/bin/kssh (auth read fresh from $HTTPS_PROXY).
set -u

SRC="$HOME/workspace/user/media_library/captures/"
K11_USER="successbrian"
K11_HOST="100.118.53.47"
DST_DIR="/home/successbrian/captures_intake"

if [ ! -d "$SRC" ]; then
  echo "pipe: source dir $SRC missing; nothing to do"
  exit 0
fi

AUTH="${HTTPS_PROXY#*://}"
AUTH="${AUTH%@*}"
export RSYNC_RSH="ssh -i $HOME/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=25 \
-o StrictHostKeyChecking=accept-new \
-o ProxyCommand=\"socat - PROXY:hatch-egress-proxy:${K11_HOST}:22,proxyport=3130,proxyauth=$AUTH\""

# Make sure the intake dirs exist on k11 (kssh = same transport, dumb command).
"$HOME/workspace/bin/kssh" "mkdir -p $DST_DIR $DST_DIR/processed $DST_DIR/needs_review" \
  || { echo "pipe: k11 mkdir failed"; exit 1; }

# Move image files only. --remove-source-files keeps the Hatch side clean.
rsync -az --remove-source-files \
  --include='*/' \
  --include='*.png' --include='*.PNG' \
  --include='*.jpg' --include='*.JPG' \
  --include='*.jpeg' --include='*.JPEG' \
  --include='*.webp' --include='*.WEBP' \
  --exclude='*' \
  -e "$RSYNC_RSH" \
  "$SRC" "${K11_USER}@${K11_HOST}:${DST_DIR}/"

echo "pipe: moved $(date -u +%FT%TZ)"
