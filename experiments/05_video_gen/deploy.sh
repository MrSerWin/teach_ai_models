#!/usr/bin/env bash
# Deploy the video-generation instance on the GPU box (run FROM the Mac).
#
#   ./experiments/05_video_gen/deploy.sh
#
# Idempotent. Each stage skips itself if already done, so re-running after a
# dropped SSH / failed download just resumes. What it does on the remote:
#   1. Clone BASE_CONDA_ENV (applio — already has torch cu128 for Blackwell)
#      into a dedicated VIDEO_ENV, keeping the base clean.
#   2. pip-install the diffusers video stack into that env.
#   3. Download Wan 2.2 TI2V-5B (diffusers) weights to a models dir on /mnt/d.
#   4. rsync generate.py over.
#   5. Smoke-test imports + CUDA.
#
# After this, generate.sh produces clips. See README.md.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

VIDEO_ENV="${VIDEO_ENV:-wan_video}"
MODEL_REPO="Wan-AI/Wan2.2-TI2V-5B-Diffusers"
REMOTE_MODEL_DIR="${REMOTE_MODEL_DIR:-/mnt/d/models/Wan2.2-TI2V-5B}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> target: $SSH_TARGET   base env: $BASE_CONDA_ENV -> $VIDEO_ENV"
echo "==> model:  $MODEL_REPO -> $REMOTE_MODEL_DIR"

# All remote work runs through a login-ish wrapper so conda is on PATH.
# (conda/nvidia-smi aren't in the non-interactive PATH on this WSL box.)
remote() { rsh "bash -s"; }

remote <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"

echo "--- [1/4] conda env ---"
if conda env list | awk '{print \$1}' | grep -qx "$VIDEO_ENV"; then
  echo "env '$VIDEO_ENV' exists — skip clone"
else
  echo "cloning $BASE_CONDA_ENV -> $VIDEO_ENV (a few minutes) ..."
  conda create -y --name "$VIDEO_ENV" --clone "$BASE_CONDA_ENV"
fi
conda activate "$VIDEO_ENV"
python -c 'import torch; assert torch.cuda.is_available(), "no CUDA in cloned env"; print("torch", torch.__version__, "cuda ok:", torch.cuda.get_device_name(0))'

echo "--- [2/4] video deps ---"
# diffusers stack only; torch/cuda come from the cloned env untouched.
pip install -q --upgrade \
  "diffusers>=0.36.0" "transformers>=4.49.0" accelerate ftfy \
  imageio imageio-ffmpeg huggingface_hub \
  sentencepiece tiktoken   # T5 tokenizer (LTX) needs these
python -c 'from diffusers import WanPipeline, AutoencoderKLWan; print("diffusers Wan import ok")'

echo "--- [3/4] model weights ---"
mkdir -p "$REMOTE_MODEL_DIR"
# model_index.json is the last-written sentinel of a complete diffusers repo.
if [ -f "$REMOTE_MODEL_DIR/model_index.json" ] && [ -d "$REMOTE_MODEL_DIR/transformer" ]; then
  echo "weights present — skip download (\$(du -sh "$REMOTE_MODEL_DIR" | cut -f1))"
else
  echo "downloading $MODEL_REPO (~30 GB, one time) ..."
  hf download "$MODEL_REPO" --local-dir "$REMOTE_MODEL_DIR"
fi

echo "--- [4/4] app dir ---"
mkdir -p "$REMOTE_APP_DIR/out"
echo "ready: env=$VIDEO_ENV model=$REMOTE_MODEL_DIR app=$REMOTE_APP_DIR"
REMOTE_SCRIPT

echo "==> syncing generate.py"
rsync_push "$EXP_DIR/generate.py" "$SSH_TARGET:$REMOTE_APP_DIR/generate.py"

echo "==> done. Smoke-test with:"
echo "    ./experiments/05_video_gen/generate.sh \"a fluffy cat watching rain on a windowsill, cozy, cinematic\""
