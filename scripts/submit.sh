#!/usr/bin/env bash
# Usage: ./scripts/submit.sh <experiment-dir>
# Rsyncs experiment (code + config, NOT data/models) to Windows WSL,
# clones the BASE_CONDA_ENV into a per-experiment env, starts training in tmux.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

EXP_DIR="${1:?usage: submit.sh <experiment-dir>}"
EXP_DIR="$(cd "$EXP_DIR" && pwd)"
EXP_NAME="$(basename "$EXP_DIR")"
EXP_ID="$(date +%Y%m%d-%H%M%S)-${EXP_NAME}"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
SESSION="train-$EXP_ID"
CONDA_ENV="$EXP_ID"

echo "[submit] exp id : $EXP_ID"
echo "[submit] remote : $SSH_TARGET:$REMOTE_DIR"

rsh "mkdir -p '$REMOTE_DIR'"

rsync_push \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  --exclude 'data/' --exclude 'models/' --exclude 'runs/' \
  "$EXP_DIR/" "$SSH_TARGET:$REMOTE_DIR/"

# Remote bootstrap: clone the pre-configured BASE_CONDA_ENV into a fresh
# per-experiment env (pristine base + isolated per run). conda envs live
# under \$CONDA_PREFIX/envs (ext4) — /mnt/d only holds code and outputs.
rsh bash -s <<REMOTE
set -euo pipefail
# make conda usable in this non-interactive shell
CONDA_BASE="\$(conda info --base 2>/dev/null || echo \$HOME/miniconda3)"
source "\$CONDA_BASE/etc/profile.d/conda.sh"

cd "$REMOTE_DIR"

if ! conda env list | awk '{print \$1}' | grep -qx "$BASE_CONDA_ENV"; then
  echo "error: base conda env '$BASE_CONDA_ENV' not found on remote" >&2
  exit 1
fi

if ! conda env list | awk '{print \$1}' | grep -qx "$CONDA_ENV"; then
  echo "[remote] cloning $BASE_CONDA_ENV -> $CONDA_ENV"
  conda create --yes --name "$CONDA_ENV" --clone "$BASE_CONDA_ENV" >/dev/null
fi

# Optional extras on top of the clone (only if requirements.txt non-empty non-comment)
if [ -s requirements.txt ] && grep -vE '^\s*(#|$)' requirements.txt >/dev/null; then
  echo "[remote] installing extras from requirements.txt"
  conda run -n "$CONDA_ENV" --no-capture-output pip install --quiet -r requirements.txt
fi

echo running > status
tmux new-session -d -s "$SESSION" "bash -lc 'source \"\$CONDA_BASE/etc/profile.d/conda.sh\" && conda activate $CONDA_ENV && python -u train.py --config config.yaml --output-dir . 2>&1 | tee train.log; rc=\\\${PIPESTATUS[0]}; echo \\\$rc > status.exit; if [ \\\$rc -eq 0 ]; then echo done > status; else echo failed > status; fi'"
REMOTE

printf '%s\n' "$EXP_ID" > "$(runs_state_dir)/latest"
echo "[submit] tmux session: $SESSION"
echo "[submit] logs   : ./scripts/logs.sh"
echo "[submit] status : ./scripts/status.sh"
echo "[submit] fetch  : ./scripts/fetch.sh   (when status=done)"
