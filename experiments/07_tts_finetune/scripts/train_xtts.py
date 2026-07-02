#!/usr/bin/env python3
"""Fine-tune XTTS v2 (Coqui) on the Sevil crh dataset. Runs on the GPU box.

Standard Coqui GPT-XTTS fine-tune. Dataset is the LJSpeech layout from
experiment 06 (metadata.<variant>.csv + wavs/). Crimean Tatar isn't a native
XTTS language, so we borrow the closest in-set language token (default `tr`,
Turkic + Latin script — matches metadata.lat.csv). Use `ru` with the Cyrillic
metadata as an alternative.

Checkpoints: XTTS checkpoints are large (~1.9 GB GPT), so we snapshot every
SAVE_EVERY_EPOCHS and keep the last KEEP_N (disk-bounded — unlike the tiny VITS
snapshots). Env overrides: XTTS_LANG, XTTS_META, SAVE_EVERY_EPOCHS, KEEP_N,
XTTS_EPOCHS, XTTS_BATCH.

Usage:
    train_xtts.py <dataset_dir> <out_dir> <base_dir>
      dataset_dir : has metadata.*.csv and wavs/
      base_dir    : holds vocab.json, model.pth (XTTS v2), dvae.pth, mel_norms.pth
"""
import math
import os
import sys
from pathlib import Path

# Coqui TTS 0.22 + torch>=2.6: torch.load now defaults to weights_only=True and
# rejects XTTS's pickled config. The base/dvae checkpoints are trusted, so
# restore the old behaviour before TTS imports trigger any load.
import torch
_orig_torch_load = torch.load
def _torch_load(*a, **k):
    k.setdefault("weights_only", False)
    return _orig_torch_load(*a, **k)
torch.load = _torch_load

from trainer import Trainer, TrainerArgs
from TTS.config.shared_configs import BaseDatasetConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.layers.xtts.trainer.gpt_trainer import (
    GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig,
)

DATA, OUT, BASE = (Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
LANG = os.environ.get("XTTS_LANG", "tr")
META = os.environ.get("XTTS_META", "metadata.lat.csv")
EPOCHS = int(os.environ.get("XTTS_EPOCHS", "60"))
BATCH = int(os.environ.get("XTTS_BATCH", "3"))
GRAD_ACUM = int(os.environ.get("XTTS_GRAD_ACUM", "84"))   # ~252 effective
SAVE_EVERY_EPOCHS = int(os.environ.get("SAVE_EVERY_EPOCHS", "5"))
# XTTS checkpoints are ~2-5 GB each; keep only a rolling few (disk-bounded).
# A/B audio is rendered from these before they roll off.
KEEP_N = int(os.environ.get("KEEP_N", "3"))

dataset = BaseDatasetConfig(
    formatter="ljspeech", dataset_name="crh_sevil",
    path=str(DATA), meta_file_train=META, language=LANG,
)

model_args = GPTArgs(
    max_conditioning_length=132300,   # 6 s @ 22050
    min_conditioning_length=11025,
    max_wav_length=255995,            # ~11.6 s @ 22050
    max_text_length=200,
    mel_norm_file=str(BASE / "mel_norms.pth"),
    dvae_checkpoint=str(BASE / "dvae.pth"),
    xtts_checkpoint=str(BASE / "model.pth"),
    tokenizer_file=str(BASE / "vocab.json"),
    gpt_num_audio_tokens=1026,
    gpt_start_audio_token=1024,
    gpt_stop_audio_token=1025,
    gpt_use_masking_gt_prompt_approach=True,
    gpt_use_perceiver_resampler=True,
)
audio = XttsAudioConfig(sample_rate=22050, dvae_sample_rate=22050, output_sample_rate=24000)

train_samples, eval_samples = load_tts_samples(
    [dataset], eval_split=True, eval_split_size=0.02,
)
# Coqui increments GLOBAL_STEP per forward batch (not per optimizer update),
# so save_step is in raw batches.
steps_per_epoch = max(1, math.ceil(len(train_samples) / BATCH))
save_step = steps_per_epoch * SAVE_EVERY_EPOCHS

config = GPTTrainerConfig(
    run_name="xtts-crh-sevil",
    project_name="xtts_crh",
    output_path=str(OUT),
    epochs=EPOCHS,
    batch_size=BATCH,
    batch_group_size=48,
    eval_batch_size=BATCH,
    num_loader_workers=4,
    print_step=50,
    save_step=save_step,
    save_n_checkpoints=KEEP_N,
    save_checkpoints=True,
    plot_step=200,
    log_model_step=save_step,
    lr=5e-6,
    optimizer="AdamW",
    optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
    lr_scheduler="MultiStepLR",
    lr_scheduler_params={"milestones": [50000, 150000, 300000], "gamma": 0.5, "last_epoch": -1},
    model_args=model_args,
    audio=audio,
    mixed_precision=False,   # XTTS GPT NaNs in fp16; train fp32 (fits in 24 GB)
)

model = GPTTrainer.init_from_config(config)
trainer = Trainer(
    TrainerArgs(restore_path="", skip_train_epoch=False, grad_accum_steps=GRAD_ACUM),
    config, output_path=str(OUT), model=model,
    train_samples=train_samples, eval_samples=eval_samples,
)
print(f"[xtts] lang={LANG} meta={META} train={len(train_samples)} eval={len(eval_samples)} "
      f"save_step={save_step} (~{SAVE_EVERY_EPOCHS} epochs)", flush=True)
if os.environ.get("DRY_RUN"):
    print("[xtts] DRY_RUN ok — config/model/dataset initialized, skipping fit()", flush=True)
    sys.exit(0)
trainer.fit()
