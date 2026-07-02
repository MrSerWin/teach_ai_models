#!/usr/bin/env python3
"""Train a phoneme-input VITS (Coqui) on the crh Sevil dataset, 22.05 kHz.

The whole point: phonemes come from **espeak-ng `crh`** (Crimean Tatar, merged
2025), which renders къ/q as the uvular /q/ and гъ/ğ as /ɣ/ — the phonetic
distinctions the Turkish/Arabic XTTS grapheme priors collapse. So /q/ is fixed at
the input level, and 22.05 kHz (vs mms's 16 kHz) removes the metallic ceiling.

Needs the freshly-built espeak-ng (~/.local/bin) on PATH so Coqui's espeak
backend uses the crh voice.

Usage: train_vits_ph.py <dataset_dir> <out_dir>
  dataset_dir: metadata.csv (LJSpeech id|text|text, Latin crh) + wavs/ (22.05 kHz)
"""
import os
import sys

from trainer import Trainer, TrainerArgs
from TTS.tts.configs.shared_configs import BaseDatasetConfig, CharactersConfig
from TTS.tts.configs.vits_config import VitsConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.models.vits import Vits, VitsAudioConfig
from TTS.tts.utils.text.tokenizer import TTSTokenizer
from TTS.utils.audio import AudioProcessor

DATA, OUT = sys.argv[1], sys.argv[2]
EPOCHS = int(os.environ.get("VITS_EPOCHS", "1000"))
BATCH = int(os.environ.get("VITS_BATCH", "16"))

# exact espeak-ng crh IPA inventory over the dataset (48 syms; q, ɣ, ŋ, ɕ, ɟ, ɯ, ø ...)
PHONEMES = "abcdefghijklmnopqrstuvwxyzøŋɑɒɔɕɛɟɣɪɫɯɾʃʑʒʲˈˌː"

dataset = BaseDatasetConfig(formatter="ljspeech", meta_file_train="metadata.csv", path=DATA)
audio = VitsAudioConfig(sample_rate=22050, win_length=1024, hop_length=256,
                        num_mels=80, mel_fmin=0, mel_fmax=None, fft_size=1024)
chars = CharactersConfig(
    characters_class="TTS.tts.models.vits.VitsCharacters",
    pad="<PAD>", eos="<EOS>", bos="<BOS>", blank="<BLNK>",
    phonemes=PHONEMES, characters="",
    punctuations="!'(),-.:;? «»—…\"–",
)
config = VitsConfig(
    audio=audio, run_name="vits-crh-sevil-ph", project_name="vits_crh",
    batch_size=BATCH, eval_batch_size=8, batch_group_size=5,
    num_loader_workers=4, num_eval_loader_workers=2,
    epochs=EPOCHS, text_cleaner="phoneme_cleaners",
    use_phonemes=True, phoneme_language="crh", phonemizer="espeak",
    phoneme_cache_path=os.path.join(OUT, "phoneme_cache"),
    compute_input_seq_cache=True,
    print_step=50, print_eval=False, save_step=1000, save_n_checkpoints=3,
    save_best_after=2000, mixed_precision=False,   # fp32: cleaner GAN decoder
    output_path=OUT, datasets=[dataset], characters=chars, cudnn_benchmark=True,
    test_sentences=[
        "Qırım kene qırımtatarlarnen yaraştırılsın.",
        "Bugün ava pek güzel, küneş parlay.",
        "Çoq qadar yoq, aqşam oldı.",
    ],
)

ap = AudioProcessor.init_from_config(config)
tokenizer, config = TTSTokenizer.init_from_config(config)
train_samples, eval_samples = load_tts_samples([dataset], eval_split=True, eval_split_size=0.02)
print(f"[vits-ph] train={len(train_samples)} eval={len(eval_samples)} phonemes={len(PHONEMES)}", flush=True)
if os.environ.get("DRY_RUN"):
    # smoke: phonemize a q-word through the tokenizer and show the ids
    ids = tokenizer.text_to_ids("Qırım yoq çoq qadar")
    print(f"[vits-ph] DRY: 'Qırım yoq çoq qadar' -> {len(ids)} phoneme ids ok", flush=True)
    sys.exit(0)

model = Vits(config, ap, tokenizer, speaker_manager=None)
trainer = Trainer(TrainerArgs(), config, OUT, model=model,
                  train_samples=train_samples, eval_samples=eval_samples)
trainer.fit()
