#!/usr/bin/env python
"""Generate a LONGER video from a text prompt with LTX-Video (diffusers).

Runs ON the GPU box, same `wan_video` conda env as generate.py (LTX ships inside
diffusers — no extra env). LTX is built for long clips: here we default to 161
frames (~6.7s @24fps) and it scales to ~257 (~10.7s) on a 24 GB card. Quality is
a notch below Wan 2.2 (TZ: "хорошее, ниже флагманов") but it's fast and long.

For true 30–60s, the native Lightricks/LTX-Video repo with its distilled config
is the next step; this diffusers path is the reliable ~10s tier.

Same CLI surface as generate.py so generate.sh --backend ltx just works.
"""
import argparse
import sys
import time
from pathlib import Path

# LTX likes long, descriptive prompts; this negative guards common artifacts.
DEFAULT_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, "
    "text, deformed, extra limbs, bad anatomy, low detail"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="LTX-Video text-to-video (long)")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", required=True, help="local LTX-Video diffusers dir")
    # LTX constraints: H/W multiples of 32, num_frames = 8k+1.
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--frames", type=int, default=161)   # ~6.7s; up to 257 (~10.7s)
    ap.add_argument("--fps", type=int, default=24)
    # Defaults resolve by model type below: distilled wants ~8 steps + guidance 1.0,
    # the base model wants ~50 steps + guidance 3.0. -1 = "use the type default".
    ap.add_argument("--steps", type=int, default=-1)
    ap.add_argument("--guidance", type=float, default=-1.0)
    ap.add_argument("--distilled", action="store_true",
                    help="model is an LTX *-distilled checkpoint (few-step, guidance 1.0)")
    ap.add_argument("--base-dir", default="",
                    help="when --model-dir is a single .safetensors transformer, "
                         "load text_encoder/tokenizer/vae/scheduler from this diffusers repo dir")
    ap.add_argument("--seed", type=int, default=-1)
    args = ap.parse_args()

    steps = args.steps if args.steps > 0 else (8 if args.distilled else 50)
    guidance = args.guidance if args.guidance >= 0 else (1.0 if args.distilled else 3.0)

    import torch
    from diffusers import LTXPipeline, LTXVideoTransformer3DModel
    from diffusers.utils import export_to_video

    if not torch.cuda.is_available():
        print("FATAL: CUDA not available in this env", file=sys.stderr)
        return 2
    print(f"[ltx] GPU: {torch.cuda.get_device_name(0)}  torch {torch.__version__}", flush=True)

    # LTX wants frames = 8k+1 and dims % 32; snap to the nearest valid values.
    def snap(v, m):
        return max(m, (v // m) * m)
    h, w = snap(args.height, 32), snap(args.width, 32)
    f = ((args.frames - 1) // 8) * 8 + 1
    if (h, w, f) != (args.height, args.width, args.frames):
        print(f"[ltx] snapped to LTX grid: {w}x{h} frames={f}", flush=True)

    t0 = time.time()
    if args.model_dir.endswith(".safetensors"):
        # Single-file transformer (e.g. the 2B distilled): load it standalone, then
        # build the rest of the pipeline from the base diffusers repo we already have.
        if not args.base_dir:
            print("FATAL: --model-dir is a single file; --base-dir is required", file=sys.stderr)
            return 2
        print(f"[ltx] loading transformer from single file {args.model_dir}", flush=True)
        print(f"[ltx] loading other components from {args.base_dir}", flush=True)
        transformer = LTXVideoTransformer3DModel.from_single_file(
            args.model_dir, torch_dtype=torch.bfloat16
        )
        pipe = LTXPipeline.from_pretrained(
            args.base_dir, transformer=transformer, torch_dtype=torch.bfloat16
        )
    else:
        print(f"[ltx] loading pipeline from {args.model_dir} ...", flush=True)
        pipe = LTXPipeline.from_pretrained(args.model_dir, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()   # long clip VAE decode won't fit 24 GB otherwise
    print(f"[ltx] pipeline ready in {time.time() - t0:.0f}s", flush=True)

    seed = args.seed if args.seed >= 0 else torch.seed() & 0xFFFFFFFF
    generator = torch.Generator(device="cpu").manual_seed(seed)
    print(f"[ltx] seed={seed} {w}x{h} frames={f} steps={steps} guidance={guidance} distilled={args.distilled}", flush=True)

    t1 = time.time()
    frames = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative,
        height=h,
        width=w,
        num_frames=f,
        guidance_scale=guidance,
        num_inference_steps=steps,
        generator=generator,
    ).frames[0]
    print(f"[ltx] sampled {len(frames)} frames in {time.time() - t1:.0f}s", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(out), fps=args.fps)
    size_kb = out.stat().st_size / 1024
    print(f"[ltx] wrote {out} ({size_kb:.0f} KB) total {time.time() - t0:.0f}s", flush=True)
    if size_kb < 500:
        print("WARN: output under 500 KB — likely a bad clip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
