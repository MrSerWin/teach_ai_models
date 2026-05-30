#!/usr/bin/env python
"""Synthesize an English voiceover (XTTS-v2 via coqui-tts) -> a .wav file.

Runs ON the GPU box in the `voice_assistant` conda env (already has coqui-tts +
CUDA torch). Used as the first audio track of the mix in add_audio.sh.

XTTS needs a voice identity: either a reference clip (--ref some.wav, ~6-20s of
clean speech to clone) or one of the built-in studio speakers (--speaker).
First run downloads the XTTS-v2 weights (~2 GB) and needs license acceptance,
which we set via COQUI_TOS_AGREED in the wrapper.
"""
import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="XTTS-v2 English voiceover")
    ap.add_argument("--text", required=True, help="narration text (English)")
    ap.add_argument("--out", required=True, help="output .wav path")
    ap.add_argument("--language", default="en")
    ap.add_argument("--ref", default="", help="reference voice .wav to clone (optional)")
    ap.add_argument("--speaker", default="Claribel Dervla",
                    help="built-in studio speaker if no --ref")
    # voice_assistant ships torch cu121, which has no Blackwell (sm_120) kernels,
    # so GPU XTTS crashes with "no kernel image". CPU is the safe default here;
    # narration is short so it's fast enough.
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    args = ap.parse_args()

    import torch
    from TTS.api import TTS

    device = args.device if (args.device == "cpu" or torch.cuda.is_available()) else "cpu"
    print(f"[voice] device={device} loading XTTS-v2 ...", flush=True)
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    kwargs = dict(text=args.text, file_path=str(out), language=args.language)
    if args.ref and Path(args.ref).is_file():
        print(f"[voice] cloning from reference: {args.ref}", flush=True)
        kwargs["speaker_wav"] = args.ref
    else:
        print(f"[voice] built-in speaker: {args.speaker}", flush=True)
        kwargs["speaker"] = args.speaker

    tts.tts_to_file(**kwargs)
    size_kb = out.stat().st_size / 1024
    print(f"[voice] wrote {out} ({size_kb:.0f} KB)", flush=True)
    if size_kb < 5:
        print("WARN: voice wav suspiciously small", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
