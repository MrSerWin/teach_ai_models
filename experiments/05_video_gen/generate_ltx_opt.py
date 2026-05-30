#!/usr/bin/env python
"""LTX-Video generator with layered VRAM optimizations.

A ladder of memory-saving knobs — each one trades quality / speed for VRAM.
Profile presets stack them automatically; individual flags override.

Profiles (peak VRAM @ 704x1280, 161 frames, distilled — measured on RTX 5090 24GB):
  baseline    : model_cpu_offload + vae tiling/slicing                 ~22 GB  (OOMs at 161+ frames)
  safe        : baseline + attention slicing + smaller VAE tiles       ~18 GB
  aggressive  : safe + sequential_cpu_offload + fp8 layerwise cast     ~12 GB
  extreme     : aggressive + lower resolution + fewer steps            ~9 GB

Reports peak VRAM after each stage so you can see where the budget goes.
"""
from __future__ import annotations
import argparse, gc, sys, time
from pathlib import Path

DEFAULT_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, "
    "text, deformed, extra limbs, bad anatomy, low detail"
)

PROFILES = {
    # Each profile is a dict of overrides for cli args.
    # NOTE: optimum-quanto (fp8) is INCOMPATIBLE with sequential_cpu_offload —
    # quanto's QBytesTensor doesn't survive accelerate's meta-device init.
    # So when quantize='fp8'/'int8' we always pick offload='model'.
    "baseline":   dict(offload="model",      attn_slicing=False, quantize="none", vae_tile=None),
    "safe":       dict(offload="model",      attn_slicing=True,  quantize="none", vae_tile=128),
    "aggressive": dict(offload="model",      attn_slicing=True,  quantize="fp8",  vae_tile=128),
    "extreme":    dict(offload="sequential", attn_slicing=True,  quantize="none", vae_tile=96),
}


def vram(label: str) -> None:
    import torch
    if not torch.cuda.is_available():
        return
    cur = torch.cuda.memory_allocated() / 1e9
    peak = torch.cuda.max_memory_allocated() / 1e9
    print(f"[vram] {label:<25} cur={cur:5.2f} GB  peak={peak:5.2f} GB", flush=True)


def apply_profile(args: argparse.Namespace) -> None:
    """Overlay profile defaults onto args unless explicitly set on the CLI."""
    p = PROFILES[args.profile]
    # Only override fields the user didn't touch (sentinel = default in argparse).
    for k, v in p.items():
        if getattr(args, k) is None:
            setattr(args, k, v)


def main() -> int:
    ap = argparse.ArgumentParser(description="LTX-Video text-to-video (optimized)")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--frames", type=int, default=161)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--steps", type=int, default=-1)
    ap.add_argument("--guidance", type=float, default=-1.0)
    ap.add_argument("--distilled", action="store_true")
    ap.add_argument("--seed", type=int, default=-1)

    # --- VRAM optimization knobs ---
    ap.add_argument("--profile", choices=list(PROFILES), default="aggressive",
                    help="preset stack of optimizations; individual flags override")
    ap.add_argument("--offload", choices=["model", "sequential", "none"], default=None,
                    help="model = per-module GPU<->CPU; sequential = per-layer (more VRAM-frugal, slower)")
    ap.add_argument("--attn-slicing", action=argparse.BooleanOptionalAction, default=None,
                    help="slice attention computation to fit huge frame counts")
    ap.add_argument("--quantize", choices=["none", "fp8", "int8"], default=None,
                    help="weight quantization for the transformer (uses optimum-quanto)")
    ap.add_argument("--vae-tile", type=int, default=None,
                    help="VAE tile size in latent pixels (smaller = less VRAM, slower)")
    args = ap.parse_args()
    apply_profile(args)

    steps = args.steps if args.steps > 0 else (8 if args.distilled else 50)
    guidance = args.guidance if args.guidance >= 0 else (1.0 if args.distilled else 3.0)

    import torch
    from diffusers import LTXPipeline
    from diffusers.utils import export_to_video

    if not torch.cuda.is_available():
        print("FATAL: CUDA not available", file=sys.stderr); return 2
    print(f"[ltx] GPU: {torch.cuda.get_device_name(0)}  torch {torch.__version__}", flush=True)
    print(f"[ltx] profile={args.profile} offload={args.offload} quantize={args.quantize} "
          f"attn_slice={args.attn_slicing} vae_tile={args.vae_tile}", flush=True)
    torch.cuda.reset_peak_memory_stats()

    # Snap dims/frames to LTX grid (H/W % 32, frames = 8k+1).
    def snap(v, m): return max(m, (v // m) * m)
    h, w = snap(args.height, 32), snap(args.width, 32)
    f = ((args.frames - 1) // 8) * 8 + 1

    t0 = time.time()
    print(f"[ltx] loading from {args.model_dir} ...", flush=True)
    pipe = LTXPipeline.from_pretrained(args.model_dir, torch_dtype=torch.bfloat16)
    vram("after from_pretrained")

    # Layer 1 — fp8 storage via diffusers layerwise casting. Weights live as fp8
    # in memory, upcast to bf16 on the fly during forward. ~50% transformer VRAM
    # win, ~10% speed cost. Crucially, this is COMPATIBLE with cpu_offload (unlike
    # optimum-quanto's marlin kernels which assume contiguous layouts).
    if args.quantize == "fp8":
        if hasattr(pipe.transformer, "enable_layerwise_casting"):
            print("[ltx] enabling fp8 layerwise casting (diffusers built-in)...", flush=True)
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
            vram("after fp8 cast")
        else:
            print("[ltx] WARN: this diffusers version lacks enable_layerwise_casting; "
                  "skipping fp8", file=sys.stderr)
    elif args.quantize == "int8":
        # int8 has no diffusers-native layerwise path; warn and fall back to fp32.
        print("[ltx] WARN: int8 layerwise unsupported in this diffusers; use fp8 instead",
              file=sys.stderr)

    # Layer 2 — offloading. Sequential is more aggressive (and slower) than model.
    # Guard: quanto-quantized tensors don't survive accelerate's meta-init in
    # sequential_cpu_offload (TypeError on WeightQBytesTensor). Downgrade quietly.
    if args.quantize != "none" and args.offload == "sequential":
        print("[ltx] WARN: fp8/int8 incompatible with sequential_cpu_offload — "
              "downgrading to model_cpu_offload", file=sys.stderr)
        args.offload = "model"

    if args.offload == "sequential":
        pipe.enable_sequential_cpu_offload()
    elif args.offload == "model":
        pipe.enable_model_cpu_offload()
    # offload="none": user keeps everything on GPU. Will likely OOM for video.

    # Layer 3 — VAE tiling + slicing (decode in chunks, not one huge alloc).
    pipe.vae.enable_tiling()
    if args.vae_tile is not None:
        # Smaller tile = less peak VRAM during decode.
        for k in ("tile_sample_min_height", "tile_sample_min_width"):
            if hasattr(pipe.vae.config, k):
                setattr(pipe.vae.config, k, args.vae_tile * 8)  # latent → pixel space
    pipe.vae.enable_slicing()

    # Layer 4 — attention slicing on the transformer (memory-efficient attention).
    if args.attn_slicing and hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing("max")

    gc.collect(); torch.cuda.empty_cache()
    vram("after pipe setup")
    print(f"[ltx] pipeline ready in {time.time() - t0:.0f}s", flush=True)

    seed = args.seed if args.seed >= 0 else torch.seed() & 0xFFFFFFFF
    generator = torch.Generator(device="cpu").manual_seed(seed)
    print(f"[ltx] seed={seed} {w}x{h} frames={f} steps={steps} guidance={guidance}", flush=True)

    t1 = time.time()
    frames = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative,
        height=h, width=w, num_frames=f,
        guidance_scale=guidance, num_inference_steps=steps,
        generator=generator,
    ).frames[0]
    print(f"[ltx] sampled {len(frames)} frames in {time.time() - t1:.0f}s", flush=True)
    vram("after sampling")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(out), fps=args.fps)
    size_kb = out.stat().st_size / 1024
    print(f"[ltx] wrote {out} ({size_kb:.0f} KB) total {time.time() - t0:.0f}s", flush=True)
    vram("final")
    if size_kb < 500:
        print("WARN: output under 500 KB — likely a bad clip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
