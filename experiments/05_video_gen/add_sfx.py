#!/usr/bin/env python
"""Generate SFX/ambient audio synced to a video (MMAudio) -> a .wav file.

Runs ON the GPU box in the `mmaudio` conda env. Wraps MMAudio's demo.py (the
stable interface) rather than its internal API: runs it with --skip_video_composite
so it only emits the generated audio, then converts that to our sfx.wav. Used as
the mid-volume layer of the mix in produce.sh.

First run downloads MMAudio weights (a few GB) into the HF cache.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="MMAudio SFX/ambient for a video")
    ap.add_argument("--video", required=True, help="silent input video")
    ap.add_argument("--prompt", required=True, help="English sound description")
    ap.add_argument("--negative", default="music, speech, voice")
    ap.add_argument("--out", required=True, help="output .wav path")
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--variant", default="large_44k_v2")
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--repo", default=str(Path.home() / "MMAudio"))
    args = ap.parse_args()

    repo = Path(args.repo)
    demo = repo / "demo.py"
    if not demo.is_file():
        print(f"FATAL: MMAudio demo.py not found at {demo}", file=sys.stderr)
        return 2

    video = Path(args.video).resolve()
    out = Path(args.out).resolve()
    work = out.parent / "_mmaudio"
    work.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(demo),
        "--video", str(video),
        "--prompt", args.prompt,
        "--negative_prompt", args.negative,
        "--duration", str(args.duration),
        "--variant", args.variant,
        "--num_steps", str(args.steps),
        "--output", str(work),
        "--skip_video_composite",   # we only want the audio track
    ]
    print(f"[sfx] running MMAudio ({args.variant}, {args.duration:.1f}s) ...", flush=True)
    # cwd=repo so any relative config lookups inside demo.py resolve.
    subprocess.run(cmd, cwd=str(repo), check=True)

    # demo.py names output after the video stem; glob to stay version-agnostic.
    produced = sorted(
        [*work.rglob("*.flac"), *work.rglob("*.wav")],
        key=lambda p: p.stat().st_mtime,
    )
    if not produced:
        print(f"FATAL: no audio produced in {work}", file=sys.stderr)
        return 3
    src = produced[-1]
    print(f"[sfx] got {src.name}, converting -> {out.name}", flush=True)

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(out)],
        check=True,
    )
    size_kb = out.stat().st_size / 1024
    print(f"[sfx] wrote {out} ({size_kb:.0f} KB)", flush=True)
    if size_kb < 5:
        print("WARN: sfx wav suspiciously small", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
