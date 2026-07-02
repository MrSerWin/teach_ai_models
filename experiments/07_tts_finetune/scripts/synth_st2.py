#!/usr/bin/env python3
"""Synthesize probe sentences from a StyleTTS2 crh fine-tune checkpoint.

Port of Demo/Inference_LibriTTS.ipynb, but with the espeak-ng **crh** phonemizer
(so /q/ = uvular къ is an explicit IPA phoneme) and our fine-tuned checkpoint.

Style is taken from a reference wav (same speaker = Sevil). The diffusion sampler
predicts prosody/timbre; alpha/beta blend predicted vs reference style.

Run on the box inside `qrimtatar_tts` with espeak-ng (~/.local/bin) on PATH and
ESPEAK_DATA_PATH set, from ~/StyleTTS2:

  python synth_st2.py <checkpoint.pth> <ref.wav> <out_dir> [--probes probe.json]
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

torch.manual_seed(0)
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True
import random
random.seed(0)
np.random.seed(0)

# torch>=2.6 weights_only shim (checkpoints hold pickled configs)
_orig = torch.load
torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})

import subprocess
import yaml
import librosa
import torchaudio
from nltk.tokenize import word_tokenize

from models import build_model, load_ASR_models, load_F0_models
from utils import recursive_munch
from text_utils import TextCleaner
from Utils.PLBERT.util import load_plbert
from Modules.diffusion.sampler import DiffusionSampler, ADPM2Sampler, KarrasSchedule

DEFAULT = ["Qırım kene qırımtatarlarnen yaraştırılsın.",
           "Bugün ava pek güzel, küneş parlay.",
           "Çoq qadar yoq, aqşam oldı."]

ESPEAK_BIN = os.environ.get("ESPEAK_BIN", os.path.expanduser("~/.local/bin/espeak-ng"))

device = "cuda" if torch.cuda.is_available() else "cpu"
textcleaner = TextCleaner()


def phonemize_crh(text):
    """IPA via the espeak-ng crh binary (same voice/mode as training data)."""
    # text via stdin so leading '-'/punctuation isn't parsed as a flag
    out = subprocess.run([ESPEAK_BIN, "-v", "crh", "-q", "--ipa=3"],
                         input=text, capture_output=True, text=True, check=True).stdout
    # collapse lines, drop tie bars / ZWJ (TextCleaner skips them anyway)
    out = out.replace("\n", " ").replace("‍", "").replace("͡", "").replace("͜", "")
    return " ".join(out.split())
to_mel = torchaudio.transforms.MelSpectrogram(n_mels=80, n_fft=2048, win_length=1200, hop_length=300)
MEAN, STD = -4, 4


def length_to_mask(lengths):
    mask = torch.arange(lengths.max()).unsqueeze(0).expand(lengths.shape[0], -1).type_as(lengths)
    return torch.gt(mask + 1, lengths.unsqueeze(1))


def preprocess(wave):
    mel = to_mel(torch.from_numpy(wave).float())
    return (torch.log(1e-5 + mel.unsqueeze(0)) - MEAN) / STD


def compute_style(model, path):
    wave, sr = librosa.load(path, sr=24000)
    audio, _ = librosa.effects.trim(wave, top_db=30)
    mel = preprocess(audio).to(device)
    with torch.no_grad():
        ref_s = model.style_encoder(mel.unsqueeze(1))
        ref_p = model.predictor_encoder(mel.unsqueeze(1))
    return torch.cat([ref_s, ref_p], dim=1)


def build(config_path):
    config = yaml.safe_load(open(config_path))
    text_aligner = load_ASR_models(config["ASR_path"], config["ASR_config"])
    pitch_extractor = load_F0_models(config["F0_path"])
    plbert = load_plbert(config["PLBERT_dir"])
    model_params = recursive_munch(config["model_params"])
    model = build_model(model_params, text_aligner, pitch_extractor, plbert)
    for k in model:
        model[k].eval(); model[k].to(device)
    return model, model_params


def load_ckpt(model, ckpt):
    params = torch.load(ckpt, map_location="cpu")["net"]
    for key in model:
        if key in params:
            try:
                model[key].load_state_dict(params[key])
            except Exception:
                from collections import OrderedDict
                sd = OrderedDict((k[7:] if k.startswith("module.") else k, v) for k, v in params[key].items())
                model[key].load_state_dict(sd, strict=False)
        model[key].eval()


def make_sampler(model):
    return DiffusionSampler(model.diffusion.diffusion, sampler=ADPM2Sampler(),
                            sigma_schedule=KarrasSchedule(sigma_min=0.0001, sigma_max=3.0, rho=9.0),
                            clamp=False)


def inference(model, model_params, sampler, text, ref_s,
              alpha=0.3, beta=0.7, diffusion_steps=10, embedding_scale=1.0):
    ps = phonemize_crh(text.strip())
    ps = " ".join(word_tokenize(ps))
    tokens = textcleaner(ps)
    tokens.insert(0, 0)
    tokens = torch.LongTensor(tokens).to(device).unsqueeze(0)
    with torch.no_grad():
        lengths = torch.LongTensor([tokens.shape[-1]]).to(device)
        mask = length_to_mask(lengths).to(device)
        t_en = model.text_encoder(tokens, lengths, mask)
        bert_dur = model.bert(tokens, attention_mask=(~mask).int())
        d_en = model.bert_encoder(bert_dur).transpose(-1, -2)
        s_pred = sampler(noise=torch.randn((1, 256)).unsqueeze(1).to(device),
                         embedding=bert_dur, embedding_scale=embedding_scale,
                         features=ref_s, num_steps=diffusion_steps).squeeze(1)
        s, ref = s_pred[:, 128:], s_pred[:, :128]
        ref = alpha * ref + (1 - alpha) * ref_s[:, :128]
        s = beta * s + (1 - beta) * ref_s[:, 128:]
        d = model.predictor.text_encoder(d_en, s, lengths, mask)
        x, _ = model.predictor.lstm(d)
        duration = torch.sigmoid(model.predictor.duration_proj(x)).sum(axis=-1)
        pred_dur = torch.round(duration.squeeze()).clamp(min=1)
        if pred_dur.dim() == 0:
            pred_dur = pred_dur.unsqueeze(0)
        aln = torch.zeros(lengths, int(pred_dur.sum().data))
        c = 0
        for i in range(aln.size(0)):
            aln[i, c:c + int(pred_dur[i].data)] = 1
            c += int(pred_dur[i].data)
        en = d.transpose(-1, -2) @ aln.unsqueeze(0).to(device)
        if model_params.decoder.type == "hifigan":
            e = torch.zeros_like(en); e[:, :, 0] = en[:, :, 0]; e[:, :, 1:] = en[:, :, :-1]; en = e
        F0_pred, N_pred = model.predictor.F0Ntrain(en, s)
        asr = t_en @ aln.unsqueeze(0).to(device)
        if model_params.decoder.type == "hifigan":
            e = torch.zeros_like(asr); e[:, :, 0] = asr[:, :, 0]; e[:, :, 1:] = asr[:, :, :-1]; asr = e
        out = model.decoder(asr, F0_pred, N_pred, ref.squeeze().unsqueeze(0))
    return out.squeeze().cpu().numpy()[..., :-50]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt"); ap.add_argument("ref"); ap.add_argument("out_dir")
    ap.add_argument("--config", default="Configs/config_ft_crh.yml")
    ap.add_argument("--probes", default=None)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--escale", type=float, default=1.0)
    ap.add_argument("--alpha", type=float, default=0.3)
    ap.add_argument("--beta", type=float, default=0.7)
    a = ap.parse_args()
    probes = json.loads(Path(a.probes).read_text(encoding="utf-8")) if a.probes else DEFAULT
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    model, mp = build(a.config)
    load_ckpt(model, a.ckpt)
    sampler = make_sampler(model)
    ref_s = compute_style(model, a.ref)

    for i, s in enumerate(probes, 1):
        wav = inference(model, mp, sampler, s, ref_s, alpha=a.alpha, beta=a.beta,
                        diffusion_steps=a.steps, embedding_scale=a.escale)
        sf.write(str(out / f"{i:02d}.wav"), wav, 24000)
    print(f"[synth-st2] {len(probes)} wavs @ 24000 Hz -> {out}", flush=True)


if __name__ == "__main__":
    main()
