#!/usr/bin/env bash
# Usage: ./scripts/shell.sh [exp-id]
# Interactive shell on the remote:
#   - with an exp-id (or latest): attach to that experiment's tmux session
#   - with --free:                open a plain shell in the runs dir
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

if [ "${1:-}" = "--free" ] || [ "${1:-}" = "-f" ]; then
  exec ssh -t "${SSH_OPTS[@]}" "$SSH_TARGET" "cd '$REMOTE_RUNS_DIR' && exec \$SHELL -l"
fi

EXP_ID="$(resolve_exp_id "${1:-}")"
SESSION="train-$EXP_ID"
echo "[shell] attaching to tmux session: $SESSION  (Ctrl-b then d to detach)"
exec ssh -t "${SSH_OPTS[@]}" "$SSH_TARGET" "tmux attach -t '$SESSION'"
