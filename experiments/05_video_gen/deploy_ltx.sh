#!/usr/bin/env bash
# Add the LTX-Video (long-clip) backend to the GPU box (run FROM the Mac).
#
#   ./experiments/05_video_gen/deploy_ltx.sh
#
# Lightweight: reuses the existing `wan_video` conda env (LTX ships inside the
# diffusers we already installed), so this only downloads LTX weights and syncs
# generate_ltx.py. Run deploy.sh first. Idempotent.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

VIDEO_ENV="${VIDEO_ENV:-wan_video}"
# Override both to fetch the distilled variant:
#   MODEL_REPO=Lightricks/LTX-Video-0.9.7-distilled \
#   REMOTE_MODEL_DIR=/mnt/d/models/LTX-Video-0.9.7-distilled ./deploy_ltx.sh
MODEL_REPO="${MODEL_REPO:-Lightricks/LTX-Video}"
REMOTE_MODEL_DIR="${REMOTE_MODEL_DIR:-/mnt/d/models/LTX-Video}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> LTX backend: $MODEL_REPO -> $REMOTE_MODEL_DIR  (env: $VIDEO_ENV)"

rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$VIDEO_ENV"
python -c 'from diffusers import LTXPipeline; print("diffusers LTX import ok")'

mkdir -p "$REMOTE_MODEL_DIR"
if [ -f "$REMOTE_MODEL_DIR/model_index.json" ] && [ -d "$REMOTE_MODEL_DIR/transformer" ]; then
  echo "LTX weights present — skip download (\$(du -sh "$REMOTE_MODEL_DIR" | cut -f1))"
else
  echo "downloading $MODEL_REPO (diffusers format only; ~15-20 GB) ..."
  # Pull only the diffusers subfolders + configs — skip the redundant top-level
  # single-file .safetensors checkpoints that would double the download.
  hf download "$MODEL_REPO" --local-dir "$REMOTE_MODEL_DIR" \
    --include "*.json" "transformer/*" "vae/*" \
              "text_encoder/*" "tokenizer/*" "scheduler/*"
fi
# Belt-and-suspenders: --include "*.json" can miss root-level files on some
# hf-cli versions. Diffusers won't load without model_index.json.
[ -f "$REMOTE_MODEL_DIR/model_index.json" ] || \
  hf download "$MODEL_REPO" model_index.json --local-dir "$REMOTE_MODEL_DIR"
echo "LTX ready: model=$REMOTE_MODEL_DIR"
REMOTE_SCRIPT

echo "==> syncing generate_ltx.py"
rsync_push "$EXP_DIR/generate_ltx.py" "$SSH_TARGET:$REMOTE_APP_DIR/generate_ltx.py"

echo "==> done. Generate a long clip with:"
echo "    ./experiments/05_video_gen/generate.sh --backend ltx --frames 257 \"<english prompt>\""
