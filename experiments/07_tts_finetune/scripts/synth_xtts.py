#!/usr/bin/env python3
"""Synthesize probe sentences from fine-tuned XTTS checkpoints for A/B. On box.

For each checkpoint (best_model.pth + checkpoint_*.pth) under the run dir, loads
XTTS (base config + vocab + the fine-tuned weights), clones from a reference wav,
and renders the probe sentences -> samples_xtts/<ckpt>/<idx>.wav + index.html.

Usage:
    synth_xtts.py <run_dir> <base_dir> <ref_wav> [--probes probe20.json] [--lang tr]
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

import torch
_orig = torch.load
torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})

import soundfile as sf
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

DEFAULT = ["Бабамнынъ козьлерине бакътым.", "Бугунь ава пек гузель."]


def find_ckpts(run):
    run = Path(run)
    sub = next((d for d in run.iterdir() if d.is_dir() and list(d.glob("*.pth"))), run)
    cks = sorted(sub.glob("checkpoint_*.pth"), key=lambda p: int(re.search(r"(\d+)", p.name).group(1)))
    best = sub / "best_model.pth"
    if best.exists():
        cks.append(best)
    return sub, cks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("base_dir"); ap.add_argument("ref_wav")
    ap.add_argument("--probes", default=None); ap.add_argument("--lang", default="tr")
    a = ap.parse_args()
    probes = json.loads(Path(a.probes).read_text(encoding="utf-8")) if a.probes else DEFAULT
    base = Path(a.base_dir)
    sub, ckpts = find_ckpts(a.run_dir)
    if not ckpts:
        sys.exit(f"no checkpoints under {a.run_dir}")
    out = sub / "samples_xtts"; out.mkdir(exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    rows = []
    for ck in ckpts:
        tag = ck.stem.replace("checkpoint_", "step")
        cfg = XttsConfig(); cfg.load_json(str(base / "config.json"))
        model = Xtts.init_from_config(cfg)
        model.load_checkpoint(cfg, checkpoint_path=str(ck), vocab_path=str(base / "vocab.json"),
                              use_deepspeed=False)
        model.to(device)
        gpt_cond, spk = model.get_conditioning_latents(audio_path=[a.ref_wav])
        d = out / tag; d.mkdir(exist_ok=True); wavs = []
        for i, s in enumerate(probes, 1):
            o = model.inference(s, a.lang, gpt_cond, spk, temperature=0.7)
            sf.write(d / f"{i:02d}.wav", o["wav"], 24000)
            wavs.append(f"{tag}/{i:02d}.wav")
        rows.append((tag, wavs)); print(f"{tag}: {len(wavs)} samples", flush=True)
        del model
        torch.cuda.empty_cache()

    cols = "".join(f"<th>{html.escape(t)}</th>" for t, _ in rows)
    body = []
    for i, s in enumerate(probes):
        cells = "".join(f'<td><audio controls preload=none src="{w[i]}"></audio></td>' for _, w in rows)
        body.append(f"<tr><td class=s>{html.escape(s)}</td>{cells}</tr>")
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>XTTS A/B</title>"
        "<style>body{font:14px system-ui;margin:20px}td,th{padding:6px;border:1px solid #ddd}"
        ".s{max-width:240px}audio{width:200px}</style>"
        f"<h2>XTTS-crh-Sevil A/B (24 kHz)</h2><table><tr><th>sentence</th>{cols}</tr>{''.join(body)}</table>",
        encoding="utf-8")
    print(f"-> {out/'index.html'}")


if __name__ == "__main__":
    main()
