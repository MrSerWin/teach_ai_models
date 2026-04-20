#!/usr/bin/env bash
# Usage: ./scripts/tensorboard.sh [exp-id] [-p|--port <port>]
# Starts TensorBoard on the remote for <exp-id>'s output dir and forwards
# the port to localhost. Open http://localhost:<port> on Mac.
# Ctrl-C stops both TensorBoard and the SSH tunnel.
#
# Requires tensorboard to be installed in the experiment's cloned conda env
# (or in BASE_CONDA_ENV). If your train.py writes event files elsewhere,
# override LOGDIR_REL (default '.').
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

PORT=6006
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    -p|--port) PORT="${2:?--port needs a value}"; shift 2 ;;
    *)         POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]-}"

EXP_ID="$(resolve_exp_id "${1:-}")"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
CONDA_ENV="$EXP_ID"
LOGDIR_REL="${LOGDIR_REL:-.}"

echo "[tb] exp : $EXP_ID"
echo "[tb] url : http://localhost:$PORT"
echo "[tb] Ctrl-C stops TensorBoard."

exec ssh -t -L "${PORT}:localhost:${PORT}" "${SSH_OPTS[@]}" "$SSH_TARGET" bash -lc "
source \"\$(conda info --base 2>/dev/null || echo \$HOME/miniconda3)/etc/profile.d/conda.sh\"
if conda env list | awk '{print \$1}' | grep -qx '$CONDA_ENV'; then
  conda activate '$CONDA_ENV'
else
  conda activate '$BASE_CONDA_ENV'
fi
cd '$REMOTE_DIR'
if ! command -v tensorboard >/dev/null; then
  echo 'tensorboard not installed in this env. Install it:'
  echo '  conda run -n $CONDA_ENV pip install tensorboard'
  exit 1
fi
tensorboard --logdir '$LOGDIR_REL' --port $PORT --host 0.0.0.0
"
