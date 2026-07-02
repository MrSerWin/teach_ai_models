# 07 — TTS fine-tuning (Sevil / Crimean Tatar)

Fine-tunes TTS models on the dataset built by experiment 06, on the GPU box
(RTX 5090, WSL) over SSH. This experiment went through several model families in
pursuit of two goals at once: **correct crh phonetics** (especially the uvular
/q/ = къ, which Turkish/Arabic grapheme priors collapse to /k/–/g/) and a
**natural, full-bandwidth timbre**. See the narrative in
[`docs/crh_tts_journey.md`](../../docs/crh_tts_journey.md) and the status/results
tables in [§ Model comparison](#model-comparison) below.

> **Audio is never committed** (see repo `.gitignore`): all `*.wav` / model
> weights are large and regenerable. Only code, configs, text metadata
> (`metadata*.csv`, `segments.jsonl`) and the A/B **HTML** pages are tracked —
> the pages reference wavs that you re-render locally.

The first target was **`facebook/mms-tts-crh`** (VITS) — a base that is *already
Crimean Tatar*, so no foreign accent. Later targets: XTTS v2, SpeechT5, a
from-scratch phoneme-VITS, and finally **StyleTTS2** (current best direction).

## Why mms-tts-crh

- Native crh phonetics (vs Turkish/Azerbaijani/Russian which add accent).
- Cyrillic input (matches `metadata.cyr.csv`), 16 kHz, VITS.
- Fine-tuned via `ylacombe/finetune-hf-vits` (the standard MMS-TTS harness).

## Layout

```
scripts/build_vits_dataset.py   ds06 -> 16 kHz audiofolder (train/test)
scripts/synth_snapshots.py      render probe sentences from every epoch snapshot (A/B)
configs/mms_crh.json            full training config (100 epochs)
configs/mms_crh_smoke.json      2-epoch smoke config
box_repo/run_vits_finetuning.py PATCHED trainer (see below) — pushed to the box
deploy.sh                       set up box: repo, monotonic_align, discriminator, dataset
train.sh                        launch training on the box
```

## Trainer patch (box_repo/run_vits_finetuning.py)

Upstream saves the model **once at the end** and, due to an in-loop save block,
destructively removes weight-norm every epoch (corrupts training after epoch 1).
The patch replaces that with a **non-destructive snapshot every N epochs**
(`SNAPSHOT_EVERY_EPOCHS`, default 5): deep-copy the generator, strip weight-norm
on the copy, save an inference-ready checkpoint to `checkpoint-epoch<N>/`; the
final epoch writes to `output_dir`. Training continues untouched.

## Run (from the Mac)

```bash
# 1. build + push dataset, set up box (idempotent)
python experiments/07_tts_finetune/scripts/build_vits_dataset.py \
       experiments/06_tts_dataset experiments/07_tts_finetune/vits_data --variant cyr
bash experiments/07_tts_finetune/deploy.sh

# 2. train (snapshot every 5 epochs) — runs on the box
bash experiments/07_tts_finetune/train.sh configs/mms_crh.json

# 3. render A/B samples from every snapshot
ssh <box> "… synth_snapshots.py /mnt/d/runs/mms-crh-sevil"
#  -> /mnt/d/runs/mms-crh-sevil/samples/index.html
```

## Box

- Host from repo-root `.env` (`WIN_HOST`, helpers in `config.sh`).
- env `qrimtatar_tts` (torch 2.7.1+cu128, transformers 4.39, Coqui TTS 0.22).
- Repo at `~/finetune-hf-vits` (ext4 — `/mnt/d` NTFS can't chmod git locks).
- Discriminator-augmented base: `/mnt/d/runs/mms-tts-crh-disc`.
- Dataset: `/mnt/d/datasets/crh_sevil_vits/vits_data`, runs under `/mnt/d/runs`.
- Monitor: `tensorboard --logdir /mnt/d/runs/mms-crh-sevil` (logs eval audio too).

> **Disk (learned the hard way):** write runs to **`/mnt/c`** (C:, ~629 GB free),
> NOT `/mnt/d` (NTFS, ~99 % full) and NOT the WSL ext4 home `/` — its dynamic
> `.vhdx` physically lives on D:, so writing there grows the vhdx into a full D:,
> WSL I/O wedges and sshd resets at key-exchange. NTFS `/mnt/c` also can't
> `chmod`/`utime` (breaks `shutil.copy` copymode and plain `tar`; use
> `shutil.copyfile` and `tar xzmf --no-same-owner`).

## <a name="model-comparison"></a>Model comparison (chronological)

All fine-tuned on the ~3 h Sevil corpus from exp 06 (1371 clips after audit).

| Model | Input | SR | /q/ | Verdict |
|-------|-------|----|-----|---------|
| mms-tts-crh (VITS FT) | Cyrillic graphemes | 16 kHz | ✅ native | correct /q/ but metallic 16 kHz ceiling |
| XTTS v2 `tr` (new-only / merge) | Latin graphemes | 24 kHz | ❌ →/k/ | best timbre of the XTTS runs; `merge_e90` = best XTTS, but /q/ wrong — **dead end for /q/** |
| XTTS v2 `ar` | Latin graphemes | 24 kHz | ❌ →/g/ | Arabic prior wrong for /q/ and vowels |
| phoneme-VITS (from scratch) | espeak-crh IPA | 22 kHz | ✅ | /q/ ok but "очень плохо" timbre — 3 h too little from scratch |
| **StyleTTS2** (FT from LibriTTS) | espeak-crh IPA | 24 kHz | ✅ | **most realistic timbre**; e39/3h unstable (intonation, endings); the only path that fixes BOTH /q/ and naturalness |

**Key finding — the /q/ fix is at the phoneme level.** espeak-ng ≥1.52 has a
Crimean Tatar voice (`crh`, merged May 2025) that renders `qara`→/qɑɾɑ/ (uvular)
vs `kara`→/kɑɾɑ/, plus ğ→/ɣ/, ñ→/ŋ/, ı→/ɯ/. Any phoneme-input model (VITS,
StyleTTS2) therefore gets /q/ right; grapheme XTTS never will. Details:
[`docs/crh_q_phoneme`](../../docs/crh_tts_journey.md).

**Current direction — StyleTTS2 at true 24 kHz.** e39 (trained on 22.05 kHz audio
upsampled by the loader → empty spectrum >11 kHz) was rebuilt on a **true 24 kHz**
dataset re-cut from the 44.1 kHz book sources (`scripts/recut_24k.py`), retrained
longer. Sampler note: raising `embedding_scale`/`diffusion_steps` on an
undertrained diffusion makes it *worse* (screech/dropout) — keep `escale=1.0`,
`steps~10`; stability comes from training, not the sampler. Single-word inputs are
degenerate for the diffusion sampler — feed q-words in a **carrier phrase**.

## Scripts

```
scripts/build_vits_dataset.py   ds06 -> 16 kHz audiofolder (mms VITS)
scripts/build_merged_dataset.py merge exp06 + old HF ds (resample/dedup) for XTTS
scripts/recut_24k.py            (in exp 06) re-cut cleaned ds to TRUE 24 kHz for StyleTTS2
scripts/train_xtts.py           XTTS v2 fine-tune (GPTTrainer); train_xtts.sh launcher
scripts/train_vits_ph.py        from-scratch phoneme-VITS (Coqui, espeak crh)
scripts/synth_xtts.py           render probes from an XTTS checkpoint
scripts/synth_vits_ph.py        render probes from a phoneme-VITS checkpoint
scripts/synth_st2.py            render probes from a StyleTTS2 checkpoint (espeak-crh binary phonemizer)
scripts/synth_snapshots.py      render probes from every mms snapshot
scripts/compare_xtts.py         multi-model XTTS A/B page
scripts/lang_probe.py           probe the base XTTS across language tokens
probe20.lat.json / q_probe*.json / q_carrier.lat.json   probe sentences (Latin crh)
ab_pages/<name>/index.html      A/B comparison pages (wavs rendered locally, git-ignored)
```

### StyleTTS2 (on the box, `~/StyleTTS2`, env `qrimtatar_tts`)

```bash
# data lists = wav|IPA|0, IPA from `espeak-ng -v crh -q --ipa=3` (Data/crh_{train,val}.txt)
# config Configs/config_ft_crh.yml (22 kHz) or config_ft_crh_24k.yml (true 24 kHz)
# launch (nohup, log to /mnt/c): /tmp/st2_launch_24k.sh
# GOTCHAS: shutil.copy->copyfile (NTFS); prepend torch.load weights_only=False shim;
#          batch_size=2, max_len=250 (2nd stage is heavy); do NOT set expandable_segments.

# synth an A/B (from ~/StyleTTS2):
python synth_st2.py <ckpt.pth> <ref.wav> <out_dir> \
       --config Configs/config_ft_crh_24k.yml --probes q_carrier.lat.json --steps 10
```
