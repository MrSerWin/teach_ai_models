#!/usr/bin/env python3
"""Synthesize the same test sentences from every epoch snapshot for A/B.

Runs on the GPU box. For each checkpoint-epoch* dir (and the final model) under
the run dir, loads the VITS model + tokenizer and renders a fixed set of crh
sentences, so you can listen across epochs and pick the most realistic one.

    samples/epoch<NN>/<idx>.wav  +  samples/index.html

Usage:
    synth_snapshots.py <run_dir> [--out <dir>] [--device cuda]
"""
import argparse
import html
import re
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel

# Fixed crh (Cyrillic) probe sentences — varied length / punctuation.
SENTENCES = [
    "Бабамнынъ козьлерине бакътым.",
    "Субетимиз агъыр эди, эм меним, эм онынъ ичюн.",
    "Къырым кене къырымтатарларнен яраштырылсын.",
    "Бугунь ава пек гузель, кунеш парлай.",
    "Балалар мектепке кеттилер ве дерслерини башладылар.",
]


def epoch_key(p: Path):
    m = re.search(r"epoch(\d+)", p.name)
    return int(m.group(1)) if m else 10**9  # final model (output_dir) sorts last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--probes", default=None, help="JSON file with a list of probe sentences")
    a = ap.parse_args()

    global SENTENCES
    if a.probes:
        import json
        SENTENCES = json.loads(Path(a.probes).read_text(encoding="utf-8"))

    run = Path(a.run_dir)
    out = Path(a.out or run / "samples")
    out.mkdir(parents=True, exist_ok=True)

    ckpts = sorted(run.glob("checkpoint-epoch*"), key=epoch_key)
    if (run / "model.safetensors").exists() or (run / "pytorch_model.bin").exists():
        ckpts.append(run)  # final model lives in run dir itself
    if not ckpts:
        raise SystemExit(f"no checkpoints under {run}")

    device = a.device if torch.cuda.is_available() else "cpu"
    rows = []
    for ck in ckpts:
        name = ck.name if ck != run else f"epoch{ '_final' }"
        tag = re.sub(r"checkpoint-", "", name)
        model = VitsModel.from_pretrained(ck).to(device).eval()
        tok = AutoTokenizer.from_pretrained(ck)
        sr = model.config.sampling_rate
        d = out / tag
        d.mkdir(exist_ok=True)
        wavs = []
        for i, s in enumerate(SENTENCES, 1):
            inp = tok(s, return_tensors="pt").to(device)
            with torch.no_grad():
                wav = model(**inp).waveform[0].cpu().numpy()
            fn = d / f"{i:02d}.wav"
            sf.write(fn, wav, sr)
            wavs.append(f"{tag}/{i:02d}.wav")
        rows.append((tag, wavs))
        print(f"{tag}: {len(wavs)} samples @ {sr} Hz", flush=True)
        del model

    # comparison page: rows = sentences, columns = epochs
    cols = "".join(f"<th>{html.escape(t)}</th>" for t, _ in rows)
    body = []
    for i, s in enumerate(SENTENCES):
        cells = "".join(
            f'<td><audio controls preload="none" src="{w[i]}"></audio></td>'
            for _, w in rows
        )
        body.append(f"<tr><td class=s>{html.escape(s)}</td>{cells}</tr>")
    doc = (f"<!doctype html><meta charset=utf-8><title>snapshot A/B</title>"
           f"<style>body{{font:14px system-ui;margin:20px}}td,th{{padding:6px;border:1px solid #ddd}}"
           f".s{{max-width:240px}}audio{{width:200px}}</style>"
           f"<h2>MMS-crh-Sevil — snapshot comparison</h2>"
           f"<table><tr><th>sentence</th>{cols}</tr>{''.join(body)}</table>")
    (out / "index.html").write_text(doc, encoding="utf-8")
    print(f"-> {out/'index.html'}")


if __name__ == "__main__":
    main()
