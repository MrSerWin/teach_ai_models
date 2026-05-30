#!/usr/bin/env bash
# Add the MMAudio SFX/ambient backend on the GPU box (run FROM the Mac).
#
#   ./experiments/05_video_gen/deploy_audio.sh
#
# MMAudio generates audio synced to a (silent) video + text prompt. Its deps are
# picky, so it gets its OWN conda env (clone of applio for the working CUDA torch)
# — a torch bump inside it can't break wan_video. Weights auto-download on first
# inference. Idempotent.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

SFX_ENV="${SFX_ENV:-mmaudio}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
# Repo lives on the Linux fs (~), NOT /mnt/d — git can't chmod lock files on
# DrvFs ("could not set core.filemode"). Code is small; weights cache to ~ anyway.
MMAUDIO_DIR="\$HOME/MMAudio"

echo "==> MMAudio backend: env=$SFX_ENV repo=~/MMAudio (clone of $BASE_CONDA_ENV)"

rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"

if conda env list | awk '{print \$1}' | grep -qx "$SFX_ENV"; then
  echo "env '$SFX_ENV' exists — skip clone"
else
  echo "cloning $BASE_CONDA_ENV -> $SFX_ENV ..."
  conda create -y --name "$SFX_ENV" --clone "$BASE_CONDA_ENV"
fi
conda activate "$SFX_ENV"

if [ -d "$MMAUDIO_DIR/.git" ]; then
  echo "MMAudio repo present — pulling latest"
  git -C "$MMAUDIO_DIR" pull --ff-only || true
else
  git clone https://github.com/hkchengrex/MMAudio.git "$MMAUDIO_DIR"
fi

cd "$MMAUDIO_DIR"
# Install the package + its deps; torch already present from the clone. If pip
# tries to change torch, that's contained to this env only.
pip install -q -e .
python -c 'import mmaudio; print("mmaudio import ok")'
echo "MMAudio ready in env $SFX_ENV. Weights download on first run."
# Surface the real CLI surface so add_sfx.py can be matched to it.
echo "--- demo.py args ---"
python "$MMAUDIO_DIR/demo.py" --help 2>&1 | head -40 || echo "(demo.py --help not available)"
REMOTE_SCRIPT
