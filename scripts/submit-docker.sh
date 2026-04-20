#!/usr/bin/env bash
# Usage: ./scripts/submit-docker.sh [-d|--detach] [--image <name>] <experiment-dir>
# Docker-based alternative to submit.sh:
#   - rsyncs experiment + docker/Dockerfile to the remote
#   - builds the image (if missing) — nvidia-container-toolkit must be set up
#   - runs training in a container with /mnt/d/runs/<exp-id> mounted at /workspace
#
# Prereqs on the WSL box:
#   - docker engine (or Docker Desktop with WSL integration)
#   - nvidia-container-toolkit (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
#   - 'docker run --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi' must work
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

FOLLOW=1
IMAGE="${DOCKER_IMAGE:-teach-ai-models:latest}"
while [ $# -gt 0 ]; do
  case "$1" in
    -d|--detach) FOLLOW=0; shift ;;
    --image)     IMAGE="${2:?--image needs a tag}"; shift 2 ;;
    --)          shift; break ;;
    -*)          echo "unknown flag: $1" >&2; exit 2 ;;
    *)           break ;;
  esac
done

EXP_DIR="${1:?usage: submit-docker.sh [-d] [--image <name>] <experiment-dir>}"
EXP_DIR="$(cd "$EXP_DIR" && pwd)"
EXP_ID="$(date +%Y%m%d-%H%M%S)-$(basename "$EXP_DIR")"
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
SESSION="train-$EXP_ID"
DOCKERFILE_LOCAL="$(cd "$(dirname "$0")/.." && pwd)/docker/Dockerfile"

echo "[submit-docker] exp id: $EXP_ID"
echo "[submit-docker] image : $IMAGE"

rsh "mkdir -p '$REMOTE_DIR'"
rsync_push \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  --exclude 'data/' --exclude 'models/' --exclude 'runs/' \
  "$EXP_DIR/" "$SSH_TARGET:$REMOTE_DIR/"

# Ship the Dockerfile unless the experiment brings its own.
if [ ! -f "$EXP_DIR/Dockerfile" ]; then
  rsync_push "$DOCKERFILE_LOCAL" "$SSH_TARGET:$REMOTE_DIR/Dockerfile"
fi

rsh bash -s <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

if ! command -v docker >/dev/null; then
  echo "error: docker not installed on remote. See docker/Dockerfile header." >&2
  exit 1
fi

# Build image if not already present (docker's layer cache handles reruns).
if [ -z "\$(docker images -q '$IMAGE')" ]; then
  echo "[remote] building docker image: $IMAGE"
  docker build -t '$IMAGE' .
fi

echo running > status
: > train.log
# Mount datasets at the SAME path inside the container so config.yaml files
# (which reference e.g. /mnt/d/datasets/mnist) work transparently under both
# conda and docker flows.
tmux new-session -d -s "$SESSION" "docker run --rm --gpus all --name '$SESSION' \
  -v '$REMOTE_DIR':/workspace \
  -v '$REMOTE_DATASETS_DIR':'$REMOTE_DATASETS_DIR' \
  -w /workspace \
  '$IMAGE' \
  bash -c 'python -u train.py --config config.yaml --output-dir . 2>&1 | tee train.log; rc=\\\${PIPESTATUS[0]}; echo \\\$rc > status.exit; if [ \\\$rc -eq 0 ]; then echo done > status; else echo failed > status; fi'"
REMOTE

printf '%s\n' "$EXP_ID" > "$(runs_state_dir)/latest"
echo "[submit-docker] tmux session: $SESSION"

if [ "$FOLLOW" -eq 1 ]; then
  echo "[submit-docker] following logs (Ctrl-C to detach)"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s "$REMOTE_DIR" <<'REMOTE_TAIL'
set -u
cd "$1"
tail -n +1 -F train.log &
TAIL_PID=$!
trap 'kill $TAIL_PID 2>/dev/null' EXIT INT TERM
while :; do
  state=$(cat status 2>/dev/null || echo running)
  case "$state" in done|failed|cancelled) break ;; esac
  sleep 2
done
sleep 1
kill $TAIL_PID 2>/dev/null || true
echo
echo "[remote] training finished — state: $state"
REMOTE_TAIL
fi
