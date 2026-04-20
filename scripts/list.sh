#!/usr/bin/env bash
# Usage: ./scripts/list.sh      (lists all remote experiments with state)
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

rsh bash -s <<REMOTE
cd "$REMOTE_RUNS_DIR" 2>/dev/null || { echo '(no runs dir yet)'; exit 0; }
printf '%-40s %-10s %s\n' EXP_ID STATE TMUX
for d in */; do
  exp="\${d%/}"
  state=\$([ -f "\$exp/status" ] && cat "\$exp/status" || echo '-')
  tmux has-session -t "train-\$exp" 2>/dev/null && tmux_s=alive || tmux_s=gone
  printf '%-40s %-10s %s\n' "\$exp" "\$state" "\$tmux_s"
done
REMOTE
