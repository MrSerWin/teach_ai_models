#!/usr/bin/env python3
"""Synthesize probe sentences from the phoneme-VITS crh checkpoint (Coqui).

Loads the Vits model directly (not the high-level Synthesizer, which trips over
the training phoneme_cache path). The run config carries phonemizer=espeak,
phoneme_language=crh, so inference phonemizes via the same espeak-ng crh voice.
Needs espeak-ng (~/.local/bin) on PATH.

Usage: synth_vits_ph.py <checkpoint.pth> <config.json> <out_dir> [--probes probe.json]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
_orig = torch.load
torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})

from TTS.config import load_config
from TTS.tts.models.vits import Vits
from TTS.tts.utils.synthesis import synthesis

DEFAULT = ["Qırım kene qırımtatarlarnen yaraştırılsın.", "Bugün ava pek güzel.", "Çoq qadar yoq."]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt"); ap.add_argument("config"); ap.add_argument("out_dir")
    ap.add_argument("--probes", default=None)
    a = ap.parse_args()
    probes = json.loads(Path(a.probes).read_text(encoding="utf-8")) if a.probes else DEFAULT
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    cuda = torch.cuda.is_available()

    config = load_config(a.config)
    config.phoneme_cache_path = None  # don't touch the training cache at inference
    model = Vits.init_from_config(config)
    model.load_checkpoint(config, a.ckpt, eval=True)
    if cuda:
        model.cuda()

    sr = config.audio.sample_rate
    for i, s in enumerate(probes, 1):
        o = synthesis(model, s, config, use_cuda=cuda, use_griffin_lim=False)
        wav = o["wav"]
        wav = np.asarray(wav, dtype=np.float32).squeeze()
        sf.write(str(out / f"{i:02d}.wav"), wav, sr)
    print(f"[synth-vits-ph] {len(probes)} wavs @ {sr} Hz -> {out}", flush=True)


if __name__ == "__main__":
    main()
