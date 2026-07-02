#!/usr/bin/env bash
# Launch (detached) an XTTS v2 fine-tune on the GPU box. Run FROM the Mac.
#
#   experiments/07_tts_finetune/train_xtts.sh <dataset_dir> <out_dir> [meta] [epochs] [lang] [save_every]
#
# Defaults reproduce the "new-only" baseline:
#   dataset_dir = /mnt/d/datasets/crh_sevil_xtts   (exp-06, 22.05 kHz, lat+cyr; read-only)
#   out_dir     = /mnt/c/wsl_runs/xtts-crh-sevil   (C: has 629 GB free)
#   meta        = metadata.lat.csv  (Latin, tr token)
#   epochs      = 100
#
# IMPORTANT — where checkpoints land:
#   * NOT /mnt/d: that NTFS data drive sits at ~99 % (a few GB free on 1.1 TB).
#   * NOT the WSL ext4 home (~/runs): its backing .vhdx physically lives on D:,
#     so its "free GB" is fiction — writing there grows the vhdx into a full D:
#     and wedges WSL I/O (sshd resets, training dies). Learned the hard way.
#   * USE /mnt/c (the C: drive, 629 GB free, independent of D:). Each XTTS
#     checkpoint is ~5.6 GB and best_model is re-saved every epoch on eval-improve.
# Reads (dataset, base) stay on /mnt/d — read-only, no vhdx growth.
# Keep the SAME recipe (epochs/lr/batch/grad-accum) across runs so the
# dataset-vs-dataset A/B is honest.
set -euo pipefail
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXP_DIR/../.."
source config.sh

DATA="${1:-/mnt/d/datasets/crh_sevil_xtts}"
OUT="${2:-/mnt/c/wsl_runs/xtts-crh-sevil}"
META="${3:-metadata.lat.csv}"
EPOCHS="${4:-100}"
LANG="${5:-tr}"          # XTTS language token; ar = Arabic (has qāf /q/ = crh къ)
SAVE_EVERY="${6:-10}"
BASE="/mnt/d/models/xtts_base"

# push the (possibly patched) trainer + A/B scripts to the box
rsync_push "$EXP_DIR/scripts/train_xtts.py" "$SSH_TARGET:finetune-hf-vits/train_xtts.py"
rsync_push "$EXP_DIR/scripts/synth_xtts.py" "$SSH_TARGET:finetune-hf-vits/synth_xtts.py"
rsync_push "$EXP_DIR/probe20.json"          "$SSH_TARGET:finetune-hf-vits/probe20.json"

rsh "bash -lc '
source ~/miniconda3/etc/profile.d/conda.sh; conda activate qrimtatar_tts
cd ~/finetune-hf-vits
mkdir -p '"$(dirname "$OUT")"'
export XTTS_LANG='"$LANG"' XTTS_META='"$META"' XTTS_EPOCHS='"$EPOCHS"' \
       XTTS_BATCH=3 XTTS_GRAD_ACUM=42 SAVE_EVERY_EPOCHS='"$SAVE_EVERY"' KEEP_N=5 \
       HF_HUB_DISABLE_PROGRESS_BARS=1 TOKENIZERS_PARALLELISM=false
nohup python train_xtts.py '"$DATA"' '"$OUT"' '"$BASE"' \
      > '"$(dirname "$OUT")"'/xtts_train.log 2>&1 &
echo started pid=\$!; sleep 3; pgrep -af train_xtts.py | grep -v pgrep | head -1
'"
echo "==> XTTS launched. Monitor:  ssh $SSH_TARGET 'tail -f $(dirname "$OUT")/xtts_train.log'"
