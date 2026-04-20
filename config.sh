#!/usr/bin/env bash
# Sourced by all scripts in scripts/*.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "error: $ROOT_DIR/.env not found. Copy .env.example and fill it in." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT_DIR/.env"
set +a

: "${WIN_HOST:?WIN_HOST not set in .env}"
: "${WIN_USER:?WIN_USER not set in .env}"
: "${WIN_SSH_PORT:=22}"
: "${REMOTE_RUNS_DIR:?REMOTE_RUNS_DIR not set in .env}"
: "${LOCAL_MODELS_DIR:=$ROOT_DIR/models}"

SSH_TARGET="$WIN_USER@$WIN_HOST"
SSH_OPTS=(-p "$WIN_SSH_PORT" -o ServerAliveInterval=30 -o ServerAliveCountMax=4)

rsh() { ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"; }
# Push to Windows DrvFs (/mnt/d) — skip owner/group/perms/times (ACL-incompatible).
rsync_push() { rsync -rlDvz --partial --no-perms --no-owner --no-group --omit-dir-times -e "ssh ${SSH_OPTS[*]}" "$@"; }
rsync_pull() { rsync -avz --partial --append-verify -e "ssh ${SSH_OPTS[*]}" "$@"; }

runs_state_dir() { mkdir -p "$ROOT_DIR/.runs"; echo "$ROOT_DIR/.runs"; }

resolve_exp_id() {
  local arg="${1:-}"
  if [ -n "$arg" ]; then echo "$arg"; return; fi
  local f; f="$(runs_state_dir)/latest"
  if [ -f "$f" ]; then cat "$f"; return; fi
  echo "error: no exp id given and no .runs/latest" >&2
  exit 1
}
