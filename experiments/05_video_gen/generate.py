#!/usr/bin/env python
"""Generate one short video from a text prompt with Wan 2.2 TI2V-5B (diffusers).

Runs ON the GPU box, inside the cloned conda env (see deploy.sh). Writes a single
.mp4 to --out. Designed for a 24 GB card (RTX 5090 Laptop): model CPU-offload is
on by default so the 5B transformer + umt5-xxl text encoder never sit on the GPU
at the same time.

Defaults produce a vertical 9:16 clip natively (704x1280, 121 frames @24fps ≈ 5s),
so the TrashCat 16:9→9:16 conversion step can be skipped for this backend.
"""
import argparse
import sys
import time
from pathlib import Path

# Wan's canonical negative prompt (quality/artifact guard), kept in English.
DEFAULT_NEGATIVE = (
    "low quality, worst quality, blurry, jpeg artifacts, watermark, text, "
    "static, still image, deformed, extra limbs, bad anatomy, oversaturated"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Wan 2.2 TI2V-5B text-to-video")
    ap.add_argument("--prompt", required=True, help="English, cinematic, <=8s of action")
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True, help="output .mp4 path")
    ap.add_argument("--model-dir", required=True, help="local Wan2.2-TI2V-5B-Diffusers dir")
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--frames", type=int, default=121)   # 121/24fps ≈ 5.0s
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=-1, help="-1 = random")
    args = ap.parse_args()

    import torch
    from diffusers import AutoencoderKLWan, WanPipeline
    from diffusers.utils import export_to_video

    if not torch.cuda.is_available():
        print("FATAL: CUDA not available in this env", file=sys.stderr)
        return 2
    print(f"[gen] GPU: {torch.cuda.get_device_name(0)}  torch {torch.__version__}", flush=True)

    model_dir = args.model_dir
    t0 = time.time()
    print(f"[gen] loading pipeline from {model_dir} ...", flush=True)
    # VAE wants fp32; the rest runs bf16. cpu-offload keeps peak VRAM ~24 GB safe.
    vae = AutoencoderKLWan.from_pretrained(model_dir, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanPipeline.from_pretrained(model_dir, vae=vae, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    # 24 GB can't VAE-decode 121 frames at once — without this it OOMs and WDDM
    # silently pages GPU mem to RAM (looks like a hang at 100% util). Tiling +
    # slicing decode the video in chunks, keeping peak VRAM in range.
    pipe.vae.enable_tiling()
    pipe.vae.enable_slicing()
    print(f"[gen] pipeline ready in {time.time() - t0:.0f}s", flush=True)

    seed = args.seed if args.seed >= 0 else torch.seed() & 0xFFFFFFFF
    generator = torch.Generator(device="cpu").manual_seed(seed)
    print(f"[gen] seed={seed} {args.width}x{args.height} frames={args.frames} steps={args.steps}", flush=True)

    t1 = time.time()
    result = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative,
        height=args.height,
        width=args.width,
        num_frames=args.frames,
        guidance_scale=args.guidance,
        num_inference_steps=args.steps,
        generator=generator,
    )
    frames = result.frames[0]
    print(f"[gen] sampled {len(frames)} frames in {time.time() - t1:.0f}s", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(out), fps=args.fps)
    size_kb = out.stat().st_size / 1024
    print(f"[gen] wrote {out} ({size_kb:.0f} KB) total {time.time() - t0:.0f}s", flush=True)

    # quality-gate hint for the caller (TZ §7): >=500KB, >=5s, vertical.
    if size_kb < 500:
        print("WARN: output under 500 KB — likely a bad clip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
