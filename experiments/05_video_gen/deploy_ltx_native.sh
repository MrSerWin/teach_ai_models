#!/usr/bin/env bash
# Deploy the NATIVE Lightricks/LTX-Video repo (official inference.py + YAML
# configs) — used as a third backend for длинное videos. The diffusers path
# couldn't match the 2B distilled transformer with the 0.9.0 base VAE; the
# native repo's configs pin matching components.
#
# Own env (clone of applio) so its deps can't break wan_video. Code on Linux fs
# (~) — same DrvFs git issue as MMAudio. Idempotent.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

LTXN_ENV="${LTXN_ENV:-ltx_native}"
LTXN_DIR="\$HOME/LTX-Video-native"

echo "==> Native LTX-Video backend: env=$LTXN_ENV repo=~/LTX-Video-native"

rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"

if conda env list | awk '{print \$1}' | grep -qx "$LTXN_ENV"; then
  echo "env '$LTXN_ENV' exists — skip clone"
else
  echo "cloning $BASE_CONDA_ENV -> $LTXN_ENV ..."
  conda create -y --name "$LTXN_ENV" --clone "$BASE_CONDA_ENV"
fi
conda activate "$LTXN_ENV"

if [ -d "$LTXN_DIR/.git" ]; then
  echo "LTX-Video repo present — pulling latest"
  git -C "$LTXN_DIR" pull --ff-only || true
else
  git clone https://github.com/Lightricks/LTX-Video.git "$LTXN_DIR"
fi

cd "$LTXN_DIR"
# Install with cu128 / no torch downgrade. -e so we can patch if needed.
pip install -q -e .
python -c 'import ltx_video; print("ltx_video import ok")' 2>/dev/null \
  || python -c 'from inference import main; print("inference module ok")' 2>/dev/null \
  || echo "(import probe failed — inference.py is the canonical entry)"

echo "--- configs available ---"
ls "$LTXN_DIR/configs/" 2>/dev/null | head
echo "--- inference.py args ---"
python "$LTXN_DIR/inference.py" --help 2>&1 | head -60 || echo "(--help failed)"
REMOTE_SCRIPT
