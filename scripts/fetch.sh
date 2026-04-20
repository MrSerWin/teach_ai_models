#!/usr/bin/env bash
# Usage: ./scripts/fetch.sh [exp-id]
# Pulls ONLY the final artifacts (final_model/, metrics.json, config.yaml, train.log).
# Intermediate checkpoints, optimizer states, tensorboard logs stay on Windows.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

EXP_ID="$(resolve_exp_id "${1:-}")"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
LOCAL_DIR="$LOCAL_MODELS_DIR/$EXP_ID"

STATE="$(rsh "cat '$REMOTE_DIR/status' 2>/dev/null || echo missing" | tr -d '\r\n')"
if [ "$STATE" != "done" ]; then
  echo "[fetch] remote state is '$STATE' (expected 'done'). Aborting." >&2
  echo "[fetch] use: ./scripts/fetch.sh --force $EXP_ID  to override" >&2
  [ "${1:-}" = "--force" ] || exit 1
fi

mkdir -p "$LOCAL_DIR"
echo "[fetch] $SSH_TARGET:$REMOTE_DIR  ->  $LOCAL_DIR"

# Only the final artifacts. Add patterns here as needed.
rsync_pull \
  --include 'final_model/***' \
  --include 'metrics.json' \
  --include 'config.yaml' \
  --include 'train.log' \
  --include 'status' \
  --exclude '*' \
  "$SSH_TARGET:$REMOTE_DIR/" "$LOCAL_DIR/"

echo "[fetch] done -> $LOCAL_DIR"
