#!/usr/bin/env bash
# Usage: ./scripts/clean.sh [-y] [exp-id]
# Removes remote conda env AND remote run dir (/mnt/d/runs/<exp-id>).
# Refuses if the tmux session is still alive — cancel.sh first.
# Local models/<exp-id> is NOT touched (you've fetched it — it's yours).
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

YES=0
if [ "${1:-}" = "-y" ]; then YES=1; shift; fi

EXP_ID="$(resolve_exp_id "${1:-}")"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
SESSION="train-$EXP_ID"

echo "[clean] exp       : $EXP_ID"
echo "[clean] remote dir: $SSH_TARGET:$REMOTE_DIR"
echo "[clean] conda env : $EXP_ID"

if rsh "tmux has-session -t '$SESSION' 2>/dev/null"; then
  echo "[clean] refused: tmux session '$SESSION' is still alive. Run ./scripts/cancel.sh first." >&2
  exit 1
fi

if [ "$YES" -ne 1 ]; then
  printf '[clean] proceed? [y/N] '
  read -r ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "[clean] aborted"; exit 0; }
fi

rsh bash -s <<REMOTE
set -u
CONDA_BASE="\$(conda info --base 2>/dev/null || echo \$HOME/miniconda3)"
source "\$CONDA_BASE/etc/profile.d/conda.sh"

if conda env list | awk '{print \$1}' | grep -qx "$EXP_ID"; then
  echo "[remote] removing conda env: $EXP_ID"
  conda env remove --yes --name "$EXP_ID" >/dev/null
else
  echo "[remote] conda env '$EXP_ID' not found (already gone)"
fi

if [ -d "$REMOTE_DIR" ]; then
  echo "[remote] removing run dir: $REMOTE_DIR"
  rm -rf "$REMOTE_DIR"
else
  echo "[remote] run dir '$REMOTE_DIR' not found (already gone)"
fi
REMOTE

# Drop the pointer if it pointed at this exp
LATEST="$(runs_state_dir)/latest"
if [ -f "$LATEST" ] && [ "$(cat "$LATEST")" = "$EXP_ID" ]; then
  rm "$LATEST"
fi

echo "[clean] done"
