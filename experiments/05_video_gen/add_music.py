#!/usr/bin/env python
"""Generate a background music track (MusicGen) -> a .wav file.

Runs ON the GPU box in the `wan_video` env (transformers is already there).
Used as the quietest layer of the audio mix in produce.sh. Writes a 32 kHz mono
WAV with the stdlib `wave` module so no soundfile/scipy dependency is needed.
"""
import argparse
import sys
import wave
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="MusicGen background music")
    ap.add_argument("--prompt", required=True, help="music description, e.g. 'soft ambient, dreamy'")
    ap.add_argument("--out", required=True, help="output .wav path")
    ap.add_argument("--duration", type=float, default=8.0, help="seconds")
    ap.add_argument("--model", default="facebook/musicgen-small")
    args = ap.parse_args()

    import numpy as np
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[music] device={device} loading {args.model} ...", flush=True)
    processor = AutoProcessor.from_pretrained(args.model)
    model = MusicgenForConditionalGeneration.from_pretrained(args.model).to(device)

    sr = model.config.audio_encoder.sampling_rate  # 32000
    tokens = int(args.duration * 50)  # MusicGen ≈ 50 tokens/sec
    inputs = processor(text=[args.prompt], padding=True, return_tensors="pt").to(device)
    print(f"[music] generating ~{args.duration:.1f}s ({tokens} tokens) ...", flush=True)
    with torch.no_grad():
        audio = model.generate(**inputs, max_new_tokens=tokens, do_sample=True, guidance_scale=3.0)

    wav = audio[0, 0].cpu().float().numpy()
    wav = np.clip(wav, -1.0, 1.0)
    pcm = (wav * 32767.0).astype("<i2")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    size_kb = out.stat().st_size / 1024
    print(f"[music] wrote {out} ({size_kb:.0f} KB, {len(wav)/sr:.1f}s @ {sr}Hz)", flush=True)
    if size_kb < 5:
        print("WARN: music wav suspiciously small", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
