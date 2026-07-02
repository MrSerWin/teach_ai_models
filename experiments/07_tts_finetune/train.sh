#!/usr/bin/env bash
# Launch (detached) an mms-tts-crh fine-tune on the GPU box. Run FROM the Mac.
#   experiments/07_tts_finetune/train.sh [config.json] [snapshot_every_epochs]
# Default config: configs/mms_crh.json, snapshot every 5 epochs.
set -euo pipefail
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXP_DIR/../.."
source config.sh

CFG_LOCAL="${1:-$EXP_DIR/configs/mms_crh.json}"
SNAP="${2:-5}"
CFG="$(basename "$CFG_LOCAL")"
rsync_push "$CFG_LOCAL" "$SSH_TARGET:finetune-hf-vits/crh_configs/$CFG"

rsh "bash -lc '
source ~/miniconda3/etc/profile.d/conda.sh; conda activate qrimtatar_tts
cd ~/finetune-hf-vits
export SNAPSHOT_EVERY_EPOCHS='"$SNAP"' HF_HUB_DISABLE_PROGRESS_BARS=1 TOKENIZERS_PARALLELISM=false
nohup accelerate launch --num_processes 1 --mixed_precision fp16 \
  run_vits_finetuning.py crh_configs/'"$CFG"' > /mnt/d/runs/train_'"$CFG"'.log 2>&1 &
echo started; sleep 2; pgrep -af run_vits_finetuning | head -1
'"
echo "==> training launched. Monitor:  ssh $SSH_TARGET 'tail -f /mnt/d/runs/train_$CFG.log'"
echo "==> A/B samples after:  ssh $SSH_TARGET '… synth_snapshots.py /mnt/d/runs/<output_dir>'"
