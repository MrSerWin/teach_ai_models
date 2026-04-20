#!/usr/bin/env bash
# Usage: ./scripts/push-data.sh <local-dir> [remote-subdir]
# Uploads a dataset folder to $REMOTE_DATASETS_DIR/<remote-subdir> on the
# Windows training box. Idempotent — rsync only copies what changed.
# If <remote-subdir> is omitted, uses basename of <local-dir>.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

LOCAL_DIR="${1:?usage: push-data.sh <local-dir> [remote-subdir]}"
LOCAL_DIR="$(cd "$LOCAL_DIR" && pwd)"
REMOTE_SUB="${2:-$(basename "$LOCAL_DIR")}"
REMOTE_DIR="$REMOTE_DATASETS_DIR/$REMOTE_SUB"

echo "[push-data] $LOCAL_DIR  ->  $SSH_TARGET:$REMOTE_DIR"
rsh "mkdir -p '$REMOTE_DIR'"

rsync_push --progress --human-readable "$LOCAL_DIR/" "$SSH_TARGET:$REMOTE_DIR/"

echo "[push-data] done. In your config.yaml point to:"
echo "  $REMOTE_DIR"
