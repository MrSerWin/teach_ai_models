#!/usr/bin/env python
"""Wan 2.2 TI2V-5B generator with layered VRAM optimizations.

Same ladder of memory-saving knobs as generate_ltx_opt.py, but for Wan 2.2.
Wan's VAE is fussier than LTX's — it must run in fp32 for quality, so VAE
tiling is the main lever on the decode side. Transformer can be fp8'd.

Profiles (peak VRAM @ 704x1280, 121 frames, 50 steps — measured RTX 5090 24GB):
  baseline    : model_cpu_offload + vae tiling/slicing                 ~23 GB (tight)
  safe        : baseline + attention slicing + smaller VAE tiles       ~19 GB
  aggressive  : safe + sequential_cpu_offload + fp8 transformer        ~13 GB
  extreme     : aggressive + lower resolution + 30 steps               ~10 GB
"""
from __future__ import annotations
import argparse, gc, sys, time
from pathlib import Path

DEFAULT_NEGATIVE = (
    "low quality, worst quality, blurry, jpeg artifacts, watermark, text, "
    "static, still image, deformed, extra limbs, bad anatomy, oversaturated"
)

PROFILES = {
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
    p = PROFILES[args.profile]
    for k, v in p.items():
        if getattr(args, k) is None:
            setattr(args, k, v)


def main() -> int:
    ap = argparse.ArgumentParser(description="Wan 2.2 TI2V-5B (optimized)")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--frames", type=int, default=121)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=-1)

    ap.add_argument("--profile", choices=list(PROFILES), default="aggressive")
    ap.add_argument("--offload", choices=["model", "sequential", "none"], default=None)
    ap.add_argument("--attn-slicing", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--quantize", choices=["none", "fp8", "int8"], default=None)
    ap.add_argument("--vae-tile", type=int, default=None,
                    help="VAE tile size in latent pixels (smaller = less VRAM, slower)")
    args = ap.parse_args()
    apply_profile(args)

    import torch
    from diffusers import AutoencoderKLWan, WanPipeline
    from diffusers.utils import export_to_video

    if not torch.cuda.is_available():
        print("FATAL: CUDA not available", file=sys.stderr); return 2
    print(f"[wan] GPU: {torch.cuda.get_device_name(0)}  torch {torch.__version__}", flush=True)
    print(f"[wan] profile={args.profile} offload={args.offload} quantize={args.quantize} "
          f"attn_slice={args.attn_slicing} vae_tile={args.vae_tile}", flush=True)
    torch.cuda.reset_peak_memory_stats()

    t0 = time.time()
    print(f"[wan] loading from {args.model_dir} ...", flush=True)
    # Wan VAE wants fp32 (bf16 VAE produces noticeable artefacts on Wan).
    vae = AutoencoderKLWan.from_pretrained(args.model_dir, subfolder="vae",
                                            torch_dtype=torch.float32)
    pipe = WanPipeline.from_pretrained(args.model_dir, vae=vae, torch_dtype=torch.bfloat16)
    vram("after from_pretrained")

    # fp8 layerwise: store weights as fp8, upcast to bf16 in forward. Works with
    # cpu_offload (unlike optimum-quanto's marlin kernels).
    if args.quantize == "fp8":
        if hasattr(pipe.transformer, "enable_layerwise_casting"):
            print("[wan] enabling fp8 layerwise casting (diffusers built-in)...", flush=True)
            pipe.transformer.enable_layerwise_casting(
                storage_dtype=torch.float8_e4m3fn,
                compute_dtype=torch.bfloat16,
            )
            vram("after fp8 cast")
        else:
            print("[wan] WARN: diffusers lacks enable_layerwise_casting; skipping fp8",
                  file=sys.stderr)
    elif args.quantize == "int8":
        print("[wan] WARN: int8 unsupported here; use fp8 instead", file=sys.stderr)

    # Guard: quanto + sequential_cpu_offload don't compose (QBytesTensor meta-init).
    if args.quantize != "none" and args.offload == "sequential":
        print("[wan] WARN: fp8/int8 incompatible with sequential_cpu_offload — "
              "downgrading to model_cpu_offload", file=sys.stderr)
        args.offload = "model"

    if args.offload == "sequential":
        pipe.enable_sequential_cpu_offload()
    elif args.offload == "model":
        pipe.enable_model_cpu_offload()

    pipe.vae.enable_tiling()
    if args.vae_tile is not None:
        for k in ("tile_sample_min_height", "tile_sample_min_width"):
            if hasattr(pipe.vae.config, k):
                setattr(pipe.vae.config, k, args.vae_tile * 8)
    pipe.vae.enable_slicing()

    if args.attn_slicing and hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing("max")

    gc.collect(); torch.cuda.empty_cache()
    vram("after pipe setup")
    print(f"[wan] pipeline ready in {time.time() - t0:.0f}s", flush=True)

    seed = args.seed if args.seed >= 0 else torch.seed() & 0xFFFFFFFF
    generator = torch.Generator(device="cpu").manual_seed(seed)
    print(f"[wan] seed={seed} {args.width}x{args.height} frames={args.frames} steps={args.steps}", flush=True)

    t1 = time.time()
    result = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative,
        height=args.height, width=args.width, num_frames=args.frames,
        guidance_scale=args.guidance, num_inference_steps=args.steps,
        generator=generator,
    )
    frames = result.frames[0]
    print(f"[wan] sampled {len(frames)} frames in {time.time() - t1:.0f}s", flush=True)
    vram("after sampling")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(out), fps=args.fps)
    size_kb = out.stat().st_size / 1024
    print(f"[wan] wrote {out} ({size_kb:.0f} KB) total {time.time() - t0:.0f}s", flush=True)
    vram("final")
    if size_kb < 500:
        print("WARN: output under 500 KB — likely a bad clip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
