#!/usr/bin/env bash
# Set up the mms-tts-crh fine-tune on the GPU box (run FROM the Mac). Idempotent.
#   experiments/07_tts_finetune/deploy.sh
# Does, on the box:
#   1. clone ylacombe/finetune-hf-vits into ~ (ext4; /mnt/d NTFS breaks git chmod)
#   2. build monotonic_align
#   3. push the PATCHED trainer (periodic snapshots + plain-dict collator)
#      and synth_snapshots.py + configs
#   4. rsync the 16 kHz dataset to /mnt/d/datasets
#   5. convert facebook/mms-tts-crh -> discriminator-augmented base
set -euo pipefail
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EXP_DIR/../.."
source config.sh

echo "==> target: $SSH_TARGET"
REPO="~/finetune-hf-vits"

# 1-2. repo + monotonic_align
rsh "bash -lc '
set -e
source ~/miniconda3/etc/profile.d/conda.sh; conda activate '"$BASE_CONDA_ENV"' 2>/dev/null || conda activate qrimtatar_tts
if [ ! -d ~/finetune-hf-vits ]; then git clone -q https://github.com/ylacombe/finetune-hf-vits.git ~/finetune-hf-vits; fi
cd ~/finetune-hf-vits/monotonic_align && mkdir -p monotonic_align && python setup.py build_ext --inplace -q
python -c \"import monotonic_align\" && echo monotonic_align OK
'"

# 3. patched trainer + scripts + configs
rsync_push "$EXP_DIR/box_repo/run_vits_finetuning.py" "$SSH_TARGET:finetune-hf-vits/run_vits_finetuning.py"
rsync_push "$EXP_DIR/scripts/synth_snapshots.py"      "$SSH_TARGET:finetune-hf-vits/synth_snapshots.py"
rsh "mkdir -p finetune-hf-vits/crh_configs"
rsync_push "$EXP_DIR/configs/" "$SSH_TARGET:finetune-hf-vits/crh_configs/"

# 4. dataset (built locally by build_vits_dataset.py)
rsh "mkdir -p $REMOTE_DATASETS_DIR/crh_sevil_vits"
rsync_push "$EXP_DIR/vits_data" "$SSH_TARGET:$REMOTE_DATASETS_DIR/crh_sevil_vits/"

# 5. discriminator-augmented base checkpoint
rsh "bash -lc '
set -e
source ~/miniconda3/etc/profile.d/conda.sh; conda activate qrimtatar_tts
cd ~/finetune-hf-vits
if [ ! -f /mnt/d/runs/mms-tts-crh-disc/model.safetensors ]; then
  python convert_original_discriminator_checkpoint.py --language_code crh \
    --pytorch_dump_folder_path /mnt/d/runs/mms-tts-crh-disc
else echo discriminator base exists; fi
'"
echo "==> deploy done. Launch with: experiments/07_tts_finetune/train.sh"
