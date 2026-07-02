#!/usr/bin/env python3
"""Render the same probe sentences across SEVERAL XTTS models into one A/B page.

Unlike synth_xtts.py (which sweeps the checkpoints of a single run), this takes a
spec of distinct models — e.g. v1 (old dataset), new-only, merge — and renders
them side by side. For a fair comparison every model is conditioned on the SAME
reference wav (pass --ref), so audible differences reflect the model/dataset, not
the speaker prompt.

spec.json: [{"label": "v1", "checkpoint": "...model.pth", "base": "<dir with
config.json+vocab.json>", "ref": "...wav"}, ...]   (ref optional if --ref given)

Usage:
    compare_xtts.py <spec.json> <out_dir> [--probes probe20.json] [--lang tr] [--ref shared.wav]
"""
import argparse
import html
import json
import sys
from pathlib import Path

import torch
_orig = torch.load
torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})

import soundfile as sf
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("out_dir")
    ap.add_argument("--probes", default=None)
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--ref", default=None, help="shared reference wav for all models")
    a = ap.parse_args()

    models = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    probes = json.loads(Path(a.probes).read_text(encoding="utf-8")) if a.probes else \
        ["Бабамнынъ козьлерине бакътым.", "Бугунь ава пек гузель."]
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    rows = []  # (label, [wav rel paths])
    for m in models:
        label = m["label"]
        base = Path(m["base"])
        ref = a.ref or m["ref"]
        lang = m.get("lang", a.lang)   # per-model language token (ar vs tr, etc.)
        cfg = XttsConfig(); cfg.load_json(str(base / "config.json"))
        model = Xtts.init_from_config(cfg)
        # pass checkpoint_dir too: load_checkpoint joins it with "speakers_xtts.pth"
        # and crashes if it's None (single-speaker → no speakers file, just skipped).
        model.load_checkpoint(cfg, checkpoint_dir=str(Path(m["checkpoint"]).parent),
                              checkpoint_path=m["checkpoint"],
                              vocab_path=str(base / "vocab.json"), use_deepspeed=False)
        model.to(device)
        gpt_cond, spk = model.get_conditioning_latents(audio_path=[ref])
        d = out / label; d.mkdir(exist_ok=True); wavs = []
        for i, s in enumerate(probes, 1):
            o = model.inference(s, lang, gpt_cond, spk, temperature=0.7)
            sf.write(d / f"{i:02d}.wav", o["wav"], 24000)
            wavs.append(f"{label}/{i:02d}.wav")
        rows.append((label, wavs)); print(f"{label}: {len(wavs)} samples", flush=True)
        del model; torch.cuda.empty_cache()

    cols = "".join(f"<th>{html.escape(t)}</th>" for t, _ in rows)
    body = []
    for i, s in enumerate(probes):
        cells = "".join(f'<td><audio controls preload=none src="{w[i]}"></audio></td>' for _, w in rows)
        body.append(f"<tr><td class=s>{html.escape(s)}</td>{cells}</tr>")
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>XTTS model A/B</title>"
        "<style>body{font:14px system-ui;margin:20px}td,th{padding:6px;border:1px solid #ddd}"
        ".s{max-width:260px}audio{width:210px}</style>"
        f"<h2>XTTS-crh-Sevil — model comparison (24 kHz, shared ref)</h2>"
        f"<table><tr><th>sentence</th>{cols}</tr>{''.join(body)}</table>",
        encoding="utf-8")
    print(f"-> {out/'index.html'}")


if __name__ == "__main__":
    main()
