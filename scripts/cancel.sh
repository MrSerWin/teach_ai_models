#!/usr/bin/env bash
# Usage: ./scripts/cancel.sh [exp-id]    (kills the tmux session)
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

EXP_ID="$(resolve_exp_id "${1:-}")"
SESSION="train-$EXP_ID"
echo "[cancel] killing tmux session: $SESSION"
rsh "tmux kill-session -t '$SESSION' 2>/dev/null && echo killed || echo 'no such session'"
rsh "echo cancelled > '$REMOTE_RUNS_DIR/$EXP_ID/status' 2>/dev/null || true"
