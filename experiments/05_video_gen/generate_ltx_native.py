#!/usr/bin/env python
"""Generate a video via the NATIVE Lightricks/LTX-Video repo (`inference.py`).

Runs ON the GPU box in the `ltx_native` conda env. Wraps inference.py as a
subprocess — its YAML pipeline_config pins matching transformer + VAE +
text_encoder, sidestepping the diffusers VAE-mismatch failure we hit with the
single-file 2B distilled. Same CLI surface as generate.py / generate_ltx.py so
produce.sh just maps the new backend to this script.

First run downloads the model weights via the repo's hub fetcher into
~/.cache/huggingface.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, "
    "text, deformed, extra limbs, bad anatomy, low detail"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="LTX-Video native (inference.py wrapper)")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True, help="output .mp4 path")
    ap.add_argument("--config", required=True,
                    help="repo-relative pipeline config (e.g. configs/ltxv-2b-0.9.8-distilled.yaml)")
    # LTX-Video native constraints: H/W multiples of 32, num_frames = 8k+1.
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--frames", type=int, default=161)   # ~6.7s @24fps
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=-1)
    # Accepted but ignored — sampler steps/guidance live inside the YAML config.
    ap.add_argument("--steps", type=int, default=-1)
    ap.add_argument("--guidance", type=float, default=-1.0)
    ap.add_argument("--distilled", action="store_true")
    # Also unused (--model-dir kept for produce.sh symmetry, points at the repo).
    ap.add_argument("--model-dir", default=str(Path.home() / "LTX-Video-native"),
                    help="path to the LTX-Video-native repo root (has inference.py + configs/)")
    ap.add_argument("--base-dir", default="")  # unused, accepted for symmetry
    ap.add_argument("--offload-to-cpu", action="store_true")
    args = ap.parse_args()

    repo = Path(args.model_dir)
    inference = repo / "inference.py"
    cfg = repo / args.config if not Path(args.config).is_absolute() else Path(args.config)
    if not inference.is_file():
        print(f"FATAL: inference.py not found at {inference}", file=sys.stderr); return 2
    if not cfg.is_file():
        print(f"FATAL: pipeline config not found: {cfg}", file=sys.stderr); return 2

    # Snap to LTX grid (same constraints as diffusers path).
    def snap(v, m): return max(m, (v // m) * m)
    h, w = snap(args.height, 32), snap(args.width, 32)
    f = ((args.frames - 1) // 8) * 8 + 1

    out = Path(args.out).resolve()
    work = out.parent / "_ltxn"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(inference),
        "--prompt", args.prompt,
        "--negative_prompt", args.negative,
        "--pipeline_config", str(cfg),
        "--output_path", str(work),
        "--height", str(h),
        "--width", str(w),
        "--num_frames", str(f),
        "--frame_rate", str(args.fps),
    ]
    if args.seed >= 0:
        cmd += ["--seed", str(args.seed)]
    if args.offload_to_cpu:
        cmd += ["--offload_to_cpu"]
    print(f"[ltxn] running inference.py  cfg={cfg.name}  {w}x{h}  frames={f}", flush=True)
    subprocess.run(cmd, cwd=str(repo), check=True)

    # inference.py writes <output_path>/<something>.mp4 — pick the newest mp4.
    produced = sorted(work.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not produced:
        print(f"FATAL: no mp4 produced in {work}", file=sys.stderr); return 3
    src = produced[-1]
    shutil.move(str(src), str(out))
    size_kb = out.stat().st_size / 1024
    print(f"[ltxn] wrote {out} ({size_kb:.0f} KB)", flush=True)
    if size_kb < 500:
        print("WARN: output under 500 KB — likely a bad clip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
