#!/usr/bin/env bash
# Usage: ./scripts/logs.sh [exp-id]     (follows remote train.log; Ctrl-C to stop)
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

EXP_ID="$(resolve_exp_id "${1:-}")"
echo "[logs] tailing $EXP_ID (Ctrl-C to stop)"
rsh "tail -n 200 -F '$REMOTE_RUNS_DIR/$EXP_ID/train.log'"
