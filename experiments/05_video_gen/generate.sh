#!/usr/bin/env bash
# Generate one clip from a prompt on the GPU box and pull it back (run FROM Mac).
#
#   ./experiments/05_video_gen/generate.sh "<english cinematic prompt>"
#   ./experiments/05_video_gen/generate.sh --slug rainy_cat "<prompt>"
#
# MVP backend driver: drives generate.py over SSH, then rsyncs the .mp4 into
# experiments/05_video_gen/out/<slug>_<ts>/video.mp4. The full TZ pipeline
# (idea gen, prompt.txt, dedup, to_load/, cron) layers on top of this.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

VIDEO_ENV="${VIDEO_ENV:-wan_video}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"

SLUG=""
BACKEND="wan"      # wan (5s, top quality) | ltx (long, up to ~10s here)
USE_OPT=1          # 1 = use generate_*_opt.py with --profile (default); 0 = legacy
PROFILE="aggressive"   # aggressive = fp8 layerwise + model offload + attn slice + vae tile=128
GEN_ARGS=()        # forwarded verbatim to the backend script
while [ $# -gt 0 ]; do
  case "$1" in
    --slug)    SLUG="${2:?--slug needs a value}"; shift 2 ;;
    --backend) BACKEND="${2:?--backend needs wan|ltx|ltxd}"; shift 2 ;;
    --profile) PROFILE="${2:?--profile needs baseline|safe|aggressive|extreme}"; shift 2 ;;
    --legacy)  USE_OPT=0; shift ;;   # use the un-optimized scripts
    # Numeric knobs forwarded straight through. Wan trained for 121 frames (4n+1);
    # LTX wants 8k+1 and H/W % 32. The opt scripts also accept --offload, --quantize,
    # --vae-tile, --no-attn-slicing — forward them via GEN_ARGS too.
    --frames|--steps|--height|--width|--seed|--fps|--guidance|--offload|--quantize|--vae-tile)
              GEN_ARGS+=("$1" "${2:?$1 needs a value}"); shift 2 ;;
    --attn-slicing|--no-attn-slicing)
              GEN_ARGS+=("$1"); shift ;;
    --) shift; break ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
PROMPT="${1:?usage: generate.sh [--backend wan|ltx|ltxd] [--profile aggressive|safe|extreme] [--slug name] [--frames N] \"<english prompt>\"}"

# Map backend -> inference script + default weights dir (override via REMOTE_MODEL_DIR).
if [ "$USE_OPT" -eq 1 ]; then
  case "$BACKEND" in
    wan)  SCRIPT="generate_opt.py";     DEF_MODEL="/mnt/d/models/Wan2.2-TI2V-5B" ;;
    ltx)  SCRIPT="generate_ltx_opt.py"; DEF_MODEL="/mnt/d/models/LTX-Video" ;;
    ltxd) SCRIPT="generate_ltx_opt.py"; DEF_MODEL="/mnt/d/models/LTX-Video-0.9.7-distilled"; GEN_ARGS+=("--distilled") ;;
    *)    echo "unknown backend: $BACKEND (want wan|ltx|ltxd)" >&2; exit 2 ;;
  esac
  GEN_ARGS=("--profile" "$PROFILE" "${GEN_ARGS[@]}")
else
  case "$BACKEND" in
    wan)  SCRIPT="generate.py";     DEF_MODEL="/mnt/d/models/Wan2.2-TI2V-5B" ;;
    ltx)  SCRIPT="generate_ltx.py"; DEF_MODEL="/mnt/d/models/LTX-Video" ;;
    ltxd) SCRIPT="generate_ltx.py"; DEF_MODEL="/mnt/d/models/ltxv-2b-0.9.6-distilled-04-25.safetensors"; GEN_ARGS+=("--distilled" "--base-dir" "/mnt/d/models/LTX-Video") ;;
    *)    echo "unknown backend: $BACKEND (want wan|ltx|ltxd)" >&2; exit 2 ;;
  esac
fi
REMOTE_MODEL_DIR="${REMOTE_MODEL_DIR:-$DEF_MODEL}"

# Derive a filesystem-safe slug from the prompt if none given (<=60 chars, TZ §5.2).
if [ -z "$SLUG" ]; then
  SLUG="$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]' \
    | tr -c 'a-z0-9' '_' | tr -s '_' | sed 's/^_//;s/_$//' | cut -c1-60)"
fi
TS="$(date +%s)"
NAME="${SLUG}_${TS}"
REMOTE_OUT="$REMOTE_APP_DIR/out/$NAME/video.mp4"

EXTRA="${GEN_ARGS[*]:-}"   # numeric knobs only — safe to flatten to a string
echo "==> generating '$NAME' [$BACKEND] on $SSH_TARGET ${EXTRA:+($EXTRA)}"
rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$VIDEO_ENV"
python "$REMOTE_APP_DIR/$SCRIPT" \
  --prompt "$PROMPT" \
  --model-dir "$REMOTE_MODEL_DIR" \
  --out "$REMOTE_OUT" \
  $EXTRA
REMOTE_SCRIPT

LOCAL_OUT="$EXP_DIR/out/$NAME"
mkdir -p "$LOCAL_OUT"
echo "==> pulling clip"
rsync_pull "$SSH_TARGET:$REMOTE_OUT" "$LOCAL_OUT/video.mp4"
echo "==> done: $LOCAL_OUT/video.mp4"
