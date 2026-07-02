# mms-tts-crh fine-tune — quality notes & improvement options

Observations (Sevil, 100 epochs, 20-probe A/B):
1. **Per-phrase inconsistency** — some phrases sound perfect, others quite bad.
2. **Metallic/robotic timbre** across almost all epochs.

These have *different* root causes; treat separately.

## 1. Why some phrases are great and others bad

Most likely, in order of probability:

- **Stochastic duration predictor (biggest factor).** MMS/VITS uses a
  *stochastic* duration predictor + flow sampling. Inference is non-deterministic:
  `noise_scale=0.667`, `noise_scale_duration=0.8` by default. The same model can
  render one phrase cleanly and mangle the next purely from sampling variance —
  bad alignment → smeared/garbled words. This explains "some perfect, some awful"
  better than anything else.
  - Mitigation (inference-only, no retrain): lower `noise_scale` (~0.3–0.5),
    lower/zero `noise_scale_duration`, fix a seed, sweep `length_scale` (rate).
- **Tokenizer drops punctuation & lowercases** (`normalize=true`, vocab = 44
  Cyrillic chars + space/dash). Phrases whose prosody depends on commas/dashes
  lose their pause cues → rushed/garbled. Dialogue dashes, quotes, `…` vanish.
- **crh digraphs as char pairs.** къ/гъ/нъ/дж tokenized as к+ъ, г+ъ, … The base
  mms-crh learned them weakly; phrases dense in these can degrade.
- **OOV / digits / latin.** Anything outside the 44-char vocab → dropped/garbled.
- **Length / domain mismatch.** Very short (2-word) or long phrases stray from
  the 8 s-avg training distribution.

Diagnostic worth doing later: correlate per-phrase badness with (length, #digraphs,
had-punctuation, OOV chars) to confirm which dominates.

## 2. Why it sounds metallic

- **16 kHz ceiling (primary).** mms-tts-crh is 16 kHz. Band-limited audio sounds
  inherently "tinny" vs 22.05/24 kHz. This alone explains much of the metallic
  character and **cannot** be fixed by more training at 16 kHz.
- **HiFi-GAN decoder artifacts.** VITS' GAN vocoder produces buzzy/metallic output
  when under-trained or when the discriminator/mel balance is off. 100 epochs on a
  base that was already weak for crh leaves vocoder artifacts.
- **fp16 GAN training.** Mixed-precision can add high-freq artifacts in the
  adversarial decoder; **bf16** (well supported on the 5090) or fp32 is often cleaner.
- **Lossy source (MINOR — corrected 2026-07-01).** Only **3 of 18 books** are
  mp3 (avdet avasy 192k, Koyniñ birincisi 256k, Nadzhie 192k); the other **15 are
  44.1 kHz float wav**. So mp3 is a *minor* contributor, not a main cause — the
  metallic timbre is overwhelmingly the 16 kHz ceiling. (Those 3 mp3 books do show
  up among the higher-misalignment ones in the audit, so mp3 may hurt CTC
  alignment slightly, but it is not why the output is metallic.)
- **Peak normalization.** We peak-normalized per clip; **LUFS/loudness** norm gives
  more consistent level and can reduce pumping/harshness.

## Improvement options, ranked by impact / effort

**A. Cheap, no retrain (try first):**
- Inference knobs: `noise_scale≈0.4`, `noise_scale_duration≈0`, fixed seed,
  `length_scale` sweep. Fixes most of the inconsistency (#1).
- Post-process: light de-esser / low-pass at ~7.5 kHz to mask 16 kHz harshness.

**B. Bigger wins (retrain / different base):**
- **Move off 16 kHz** → the real fix for metallic. XTTS v2 (24 kHz, your prior
  best) and even SpeechT5 pipelines with a 22–24 kHz vocoder will sound far less
  metallic. This is why trying XTTS/SpeechT5 next is the right call.
- Retrain mms-crh with **bf16**, longer schedule, tuned losses (`weight_mel`↑,
  warmup↑, lower lr for vocoder stability), larger segment size.
- **Cleaner data subset**: drop mp3-sourced books, keep wav-only; LUFS-normalize;
  drop low-`score` clips harder (tighten experiment-06 QC).
- **Punctuation/phonemes**: keep sentence punctuation or add a phonemizer so the
  duration predictor gets better cues (reduces per-phrase blowups).

**C. Inherent ceiling.** mms-tts-crh is a small 16 kHz model the user already found
weak for crh. Even tuned, it likely trails XTTS. Use it as a baseline, not the goal.

## Decision
Keep this run as the mms baseline. Next: XTTS v2 (24 kHz) and SpeechT5 on the same
3 h dataset, then A/B all three. Best realism most likely from XTTS.
