#!/usr/bin/env bash
# Usage:
#   ./scripts/submit.sh [-d|--detach] <experiment-dir>
#   ./scripts/submit.sh [-d|--detach] --resume <exp-id>      # pick up where it left off
#
# Rsyncs experiment (code + config, NOT data/models) to Windows WSL, clones the
# BASE_CONDA_ENV into a per-experiment env, starts training in tmux, follows the
# log live. Use -d/--detach to return immediately. Use --resume to reuse an
# existing exp-id (and its conda env + checkpoints) instead of starting fresh.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

FOLLOW=1
RESUME_ID=""
GPU_IDS=""
QUEUE=0
CLONE_ENV=0
while [ $# -gt 0 ]; do
  case "$1" in
    -d|--detach) FOLLOW=0; shift ;;
    --resume)    RESUME_ID="${2:?--resume needs an exp-id}"; shift 2 ;;
    --gpu)       GPU_IDS="${2:?--gpu needs a device id or comma list}"; shift 2 ;;
    --queue)     QUEUE=1; shift ;;
    --clone)     CLONE_ENV=1; shift ;;
    --)          shift; break ;;
    -*)          echo "unknown flag: $1" >&2; exit 2 ;;
    *)           break ;;
  esac
done

if [ -n "$RESUME_ID" ]; then
  EXP_ID="$RESUME_ID"
  # Infer source dir from local state if possible; otherwise require explicit path.
  EXP_DIR="${1:-}"
  if [ -z "$EXP_DIR" ]; then
    EXP_NAME="${EXP_ID#*-*-}"          # strip leading YYYYMMDD-HHMMSS-
    for guess in "experiments/$EXP_NAME" "./$EXP_NAME"; do
      [ -d "$guess" ] && EXP_DIR="$guess" && break
    done
    [ -z "$EXP_DIR" ] && { echo "error: can't infer source dir for '$EXP_ID'; pass it explicitly" >&2; exit 2; }
  fi
else
  EXP_DIR="${1:?usage: submit.sh [-d|--detach] <experiment-dir>  OR  submit.sh --resume <exp-id> [source-dir]}"
fi

EXP_DIR="$(cd "$EXP_DIR" && pwd)"
EXP_NAME="$(basename "$EXP_DIR")"
if [ -z "$RESUME_ID" ]; then
  EXP_ID="$(date +%Y%m%d-%H%M%S)-${EXP_NAME}"
fi
REMOTE_DIR="$REMOTE_RUNS_DIR/$EXP_ID"
SESSION="train-$EXP_ID"
# Default: reuse BASE_CONDA_ENV directly (fast, minimal disk). --clone makes a
# per-experiment copy for full isolation.
if [ "$CLONE_ENV" -eq 1 ]; then
  CONDA_ENV="$EXP_ID"
else
  CONDA_ENV="$BASE_CONDA_ENV"
fi

if [ -n "$RESUME_ID" ]; then
  echo "[submit] resuming exp: $EXP_ID"
else
  echo "[submit] exp id : $EXP_ID"
fi
echo "[submit] remote : $SSH_TARGET:$REMOTE_DIR"
[ -n "$GPU_IDS" ] && echo "[submit] gpu    : CUDA_VISIBLE_DEVICES=$GPU_IDS"

# Refuse to overwrite a live run.
if rsh "tmux has-session -t '$SESSION' 2>/dev/null"; then
  echo "[submit] error: tmux session '$SESSION' is already running. Use ./scripts/cancel.sh first." >&2
  exit 1
fi

# Warn if the remote disk is getting full (default threshold: 5 GiB).
MIN_FREE_GIB="${MIN_FREE_GIB:-5}"
FREE_KB=$(rsh "df -Pk '$REMOTE_RUNS_DIR' 2>/dev/null | awk 'NR==2 {print \$4}'" || echo 0)
FREE_GIB=$(( ${FREE_KB:-0} / 1024 / 1024 ))
if [ "$FREE_GIB" -lt "$MIN_FREE_GIB" ]; then
  echo "[submit] WARNING: only ${FREE_GIB} GiB free on $REMOTE_RUNS_DIR (threshold: ${MIN_FREE_GIB} GiB)"
  echo "[submit]          consider running ./scripts/gc.sh or ./scripts/clean.sh on stale runs"
  printf '[submit] continue anyway? [y/N] '
  read -r ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "[submit] aborted"; exit 1; }
fi

rsh "mkdir -p '$REMOTE_DIR'"

# Record git provenance so months later you know WHICH code trained a model.
GIT_INFO_FILE="$(mktemp)"
trap 'rm -f "$GIT_INFO_FILE"' EXIT
if (cd "$EXP_DIR" && git rev-parse --is-inside-work-tree >/dev/null 2>&1); then
  cd "$EXP_DIR"
  G_COMMIT=$(git rev-parse HEAD)
  G_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  G_REMOTE=$(git config --get remote.origin.url 2>/dev/null || echo "")
  G_SUBJECT=$(git log -1 --format=%s | tr -d '"' | head -c 200)
  G_DIRTY=$(git status --porcelain | head -c 1 | wc -c | tr -d ' ')
  cd - >/dev/null
  cat >"$GIT_INFO_FILE" <<JSON
{
  "commit": "$G_COMMIT",
  "branch": "$G_BRANCH",
  "remote": "$G_REMOTE",
  "subject": "$G_SUBJECT",
  "dirty": $([ "$G_DIRTY" = "1" ] && echo true || echo false),
  "submitted_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
else
  cat >"$GIT_INFO_FILE" <<JSON
{ "commit": null, "submitted_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)" }
JSON
fi

rsync_push \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  --exclude 'data/' --exclude 'models/' --exclude 'runs/' \
  "$EXP_DIR/" "$SSH_TARGET:$REMOTE_DIR/"

rsync_push "$GIT_INFO_FILE" "$SSH_TARGET:$REMOTE_DIR/git_info.json"

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

if [ "$CLONE_ENV" = "1" ]; then
  if ! conda env list | awk '{print \$1}' | grep -qx "$CONDA_ENV"; then
    echo "[remote] cloning $BASE_CONDA_ENV -> $CONDA_ENV"
    conda create --yes --name "$CONDA_ENV" --clone "$BASE_CONDA_ENV" >/dev/null
  fi
  # Optional extras on top of the clone.
  if [ -s requirements.txt ] && grep -vE '^\s*(#|$)' requirements.txt >/dev/null; then
    echo "[remote] installing extras from requirements.txt"
    conda run -n "$CONDA_ENV" --no-capture-output pip install --quiet -r requirements.txt
  fi
else
  # Shared mode: reuse BASE_CONDA_ENV directly. Refuse to auto-install extras
  # here because that would pollute the shared env and affect future runs.
  if [ -s requirements.txt ] && grep -vE '^\s*(#|$)' requirements.txt >/dev/null; then
    echo "[remote] NOTE: requirements.txt has extras but shared env is in use (no --clone)."
    echo "[remote]       Install manually into $BASE_CONDA_ENV first, or re-submit with --clone."
  fi
  echo "[remote] using shared env: $BASE_CONDA_ENV (no clone)"
fi

# Write a small wrapper that tmux executes. Keeps the tmux invocation single-
# quoted (no nested-quote hell) and lets queue mode cleanly prefix with flock.
# Pipe through sed instead of 'sed -i' because /mnt/d is NTFS and rejects the
# permission-preserving rename sed does in-place.
# Pre-create train.log so the Mac-side 'tail -F' finds it immediately instead
# of racing the tmux bootstrap.
: > train.log

cat <<'WRAPPER' | sed "s|__CONDA_ENV__|$CONDA_ENV|g; s|__GPU_IDS__|$GPU_IDS|g" > _run.sh
#!/usr/bin/env bash
set -u
CONDA_BASE="\$(conda info --base 2>/dev/null || echo \$HOME/miniconda3)"
source "\$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "__CONDA_ENV__"
[ -n "__GPU_IDS__" ] && export CUDA_VISIBLE_DEVICES="__GPU_IDS__"
echo running > status
python -u train.py --config config.yaml --output-dir . 2>&1 | tee train.log
rc=\${PIPESTATUS[0]}
echo \$rc > status.exit
if [ \$rc -eq 0 ]; then echo done > status; else echo failed > status; fi
WRAPPER

if [ "$QUEUE" -eq 1 ]; then
  LOCK="$REMOTE_RUNS_DIR/.gpu-${GPU_IDS:-all}.lock"
  LOCK=\${LOCK//,/_}                  # commas are illegal in some fs
  echo queued > status
  tmux new-session -d -s "$SESSION" "cd $REMOTE_DIR && flock -x \$LOCK bash _run.sh"
else
  tmux new-session -d -s "$SESSION" "cd $REMOTE_DIR && bash _run.sh"
fi
REMOTE

printf '%s\n' "$EXP_ID" > "$(runs_state_dir)/latest"
echo "[submit] tmux session: $SESSION"

if [ "$FOLLOW" -eq 1 ]; then
  echo "[submit] following logs (auto-exit when training finishes; Ctrl-C to detach early)"
  echo "[submit] resume later: ./scripts/logs.sh $EXP_ID"
  # Remote watcher: tail the log AND poll status file — exit tail automatically
  # once the training process flips status to done/failed/cancelled.
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s "$REMOTE_DIR" <<'REMOTE_TAIL'
set -u
cd "$1"
tail -n +1 -F train.log &
TAIL_PID=$!
trap 'kill $TAIL_PID 2>/dev/null' EXIT INT TERM
state=running
while :; do
  state=$(cat status 2>/dev/null || echo running)
  case "$state" in
    done|failed|cancelled) break ;;
  esac
  sleep 2
done
sleep 1                            # let tail flush the last lines
kill $TAIL_PID 2>/dev/null || true
echo
echo "[remote] training finished — state: $state"
REMOTE_TAIL

  FINAL_STATE=$(rsh "cat '$REMOTE_DIR/status' 2>/dev/null || echo unknown" | tr -d '\r\n')
  case "$FINAL_STATE" in
    done)      PRIO=default ;;
    failed)    PRIO=high    ;;
    cancelled) PRIO=low     ;;
    *)         PRIO=default ;;
  esac
  "$(dirname "$0")/_notify.sh" "teach_ai_models: $FINAL_STATE" "$EXP_ID" "$PRIO"
else
  echo "[submit] logs   : ./scripts/logs.sh"
  echo "[submit] status : ./scripts/status.sh"
  echo "[submit] fetch  : ./scripts/fetch.sh   (when status=done)"
fi
