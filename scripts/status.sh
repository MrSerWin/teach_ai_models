#!/usr/bin/env bash
# Usage: ./scripts/status.sh [exp-id]    (defaults to latest)
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

EXP_ID="$(resolve_exp_id "${1:-}")"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"

echo "[status] exp: $EXP_ID"
rsh bash -s <<REMOTE
cd "$REMOTE_DIR" 2>/dev/null || { echo missing; exit 0; }
printf 'state   : '; [ -f status ] && cat status || echo unknown
printf 'exit    : '; [ -f status.exit ] && cat status.exit || echo -
printf 'tmux    : '; tmux has-session -t "train-$EXP_ID" 2>/dev/null && echo alive || echo gone
echo '--- last 20 log lines ---'
tail -n 20 train.log 2>/dev/null || echo '(no log yet)'
REMOTE
