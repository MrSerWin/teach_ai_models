#!/usr/bin/env python3
"""Probe which XTTS *language token* best renders Crimean Tatar phonetics.

Same model, same reference wav, same crh text — vary only the language token.
This tells us which of XTTS's 17 languages carries a phonetic prior closest to
crh (crucially: which produces the uvular /q/ that Turkish collapses to /k/).
Runs on the base (un-fine-tuned) XTTS so the comparison reflects each language's
built-in phonetics, not our tr fine-tune.

Usage:
    lang_probe.py <base_dir> <checkpoint> <ref_wav> [--langs tr,ar,ru,de,hu,es]
                  [--out DIR] [--temp 0.7]
"""
import argparse
import html
from pathlib import Path

import torch
_orig = torch.load
torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})

import soundfile as sf
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

# crh words/phrases rich in the contrastive phonemes: q (къ), ğ (гъ), ö, ü, ı.
PROBES = [
    "Qırım",            # q + ı  (the name itself)
    "yoq",              # final q
    "çoq qadar",        # q, q
    "qartbabam",        # q
    "ağır dağ",         # ğ, ğ
    "yağmur yağa",      # ğ
    "közlerim östi",    # ö
    "üç kün küldi",     # ü, ü
    "qırmızı gül",      # q + ı, ü
    "aqşam oldı",       # q
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_dir"); ap.add_argument("checkpoint"); ap.add_argument("ref_wav")
    ap.add_argument("--langs", default="tr,ar,ru,de,hu,es")
    ap.add_argument("--out", default="lang_probe_out")
    ap.add_argument("--temp", type=float, default=0.7)
    a = ap.parse_args()
    langs = [x.strip() for x in a.langs.split(",") if x.strip()]
    base = Path(a.base_dir); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    cfg = XttsConfig(); cfg.load_json(str(base / "config.json"))
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_dir=str(Path(a.checkpoint).parent),
                          checkpoint_path=a.checkpoint,
                          vocab_path=str(base / "vocab.json"), use_deepspeed=False)
    model.to(device)
    gpt_cond, spk = model.get_conditioning_latents(audio_path=[a.ref_wav])

    grid = {}  # lang -> [wav rel paths]
    for lang in langs:
        d = out / lang; d.mkdir(exist_ok=True); wavs = []
        for i, s in enumerate(PROBES, 1):
            try:
                o = model.inference(s, lang, gpt_cond, spk, temperature=a.temp)
                sf.write(d / f"{i:02d}.wav", o["wav"], 24000)
                wavs.append(f"{lang}/{i:02d}.wav")
            except Exception as e:
                print(f"  {lang} {s!r} ERR {e}", flush=True)
                wavs.append(None)
        grid[lang] = wavs
        print(f"{lang}: {sum(w is not None for w in wavs)}/{len(PROBES)}", flush=True)

    cols = "".join(f"<th>{html.escape(l)}</th>" for l in langs)
    body = []
    for i, s in enumerate(PROBES):
        cells = ""
        for l in langs:
            w = grid[l][i]
            cells += f'<td><audio controls preload=none src="{w}"></audio></td>' if w else "<td>—</td>"
        body.append(f"<tr><td class=s>{html.escape(s)}</td>{cells}</tr>")
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>XTTS language-token probe (crh)</title>"
        "<style>body{font:14px system-ui;margin:20px}td,th{padding:6px;border:1px solid #ddd}"
        ".s{max-width:200px}audio{width:180px}</style>"
        f"<h2>XTTS language-token probe on Crimean Tatar (base model, shared ref)</h2>"
        f"<p>Same text/voice, different language token. Listen for the uvular /q/ in "
        f"Qırım, yoq, çoq, qadar; the /ğ/ in ağır, dağ, yağmur.</p>"
        f"<table><tr><th>crh text</th>{cols}</tr>{''.join(body)}</table>",
        encoding="utf-8")
    print(f"-> {out/'index.html'}")


if __name__ == "__main__":
    main()
