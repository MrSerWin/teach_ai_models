# 05 · Video generation (Wan 2.2 TI2V-5B)

Free, local, scriptable video generator to replace the dead Gemini/Veo browser
path. Implements the MVP backend of [`TZ/TZ_video_generation.md`](../../TZ/TZ_video_generation.md):
a local OSS model on the GPU box that takes an English prompt and returns a
vertical `.mp4` — no login, no anti-bot, no watermark, fully scripted.

## Why this stack

| Decision | Choice | Reason |
|---|---|---|
| Model | **Wan 2.2 TI2V-5B** | TZ rec #1 for quality; the 5B variant fits 24 GB cleanly (A14B/Hunyuan need quant on 24 GB) |
| Runner | **diffusers** (not ComfyUI) | TZ allows both; diffusers is a plain Python CLI — reliably scriptable with no hand-built node graph or browser. ComfyUI API can be added later as a second backend |
| Base env | **clone of `applio`** | already ships `torch 2.7.1+cu128`, the one painful Blackwell/sm_120 dependency — cloning skips the hard part. Base stays clean |
| Output | **704×1280 native** | generated vertical 9:16 directly, so TrashCat's 16:9→9:16 conversion is skipped for this backend |

Target box: `WIN_HOST` from `.env` (RTX 5090 Laptop, 24 GB, WSL2). 24 GB is tight
for 5B + the umt5-xxl text encoder together, so `generate.py` enables
`enable_model_cpu_offload()` — modules move to GPU only while in use.

## Deploy (one time)

```bash
./experiments/05_video_gen/deploy.sh
```

Idempotent. Clones the env, installs the diffusers stack, downloads weights
(~30 GB, once) to `/mnt/d/models/Wan2.2-TI2V-5B`, syncs `generate.py`. Re-run
after any interruption — each stage skips itself if already done.

Overridable via env vars: `VIDEO_ENV`, `REMOTE_MODEL_DIR`, `REMOTE_APP_DIR`.

## Generate

```bash
./experiments/05_video_gen/generate.sh "a fluffy cat watching rain on a windowsill, cozy, cinematic, soft light"
```

Runs on the GPU box, pulls the clip to `out/<slug>_<ts>/video.mp4`.
Defaults: 704×1280, 121 frames @24 fps (≈5 s), 50 steps. Tune in `generate.py`.

## Longer clips (LTX-Video backend)

Wan is capped at ~5s (trained for 121 frames; pushing `--frames` past ~181
degrades). For longer, deploy the LTX backend — it reuses the same `wan_video`
env (LTX ships in diffusers), only downloads weights:

```bash
./experiments/05_video_gen/deploy_ltx.sh
./experiments/05_video_gen/generate.sh --backend ltx --frames 257 "<english prompt>"
```

161 frames ≈ 6.7s, 257 ≈ 10.7s on 24 GB. For true 30–60s, the native
Lightricks/LTX-Video repo is the next step; this diffusers path is the ~10s tier.

## One command: video + voice + SFX + music

`produce.sh` runs the whole pipeline in one shot — generate the clip, synthesize
each audio track whose text you pass, mix them (voice loud / SFX mid / music
quiet), mux onto the video, and pull `out/<slug>_<ts>/video_av.mp4` back:

```bash
./experiments/05_video_gen/produce.sh --backend ltx --frames 257 --slug ester_static \
  --video "<english video prompt>" \
  --voice "<english narration>" \
  --sfx   "<english sound description>" \
  --music "<english music description>" \
  [--ref myvoice.wav]   # optional: clone a specific voice
```

Each audio track runs only if its text is given; a track whose backend isn't
deployed is skipped with a warning (the command never hard-fails). Audio length
targets the clip length (`frames/fps`). First run downloads XTTS/MusicGen/MMAudio
weights (~6 GB total), so it's slow once, then cached.

Audio backends, each in its own conda env (none can break the others):
- **voice** — XTTS-v2 in `voice_assistant` (`deploy.sh` not needed; env pre-existed).
- **music** — MusicGen in `wan_video` (transformers).
- **SFX** — MMAudio in `mmaudio` (`deploy_audio.sh`; repo at `~/MMAudio`).

`add_audio.sh` remains as a voice-only helper for an already-generated clip.

## VRAM optimization (24 GB workstation)

`generate.sh` now defaults to the **optimized** runner (`generate_opt.py` / `generate_ltx_opt.py`) with the `aggressive` profile. The full ladder:

| Profile | What it stacks | Peak VRAM (LTX, 161f, 704×1280) |
|---|---|---|
| `baseline` | model_cpu_offload + VAE tiling/slicing | OOMs (kills WSL) on 161f |
| `safe` | + attention slicing + VAE tile=128 | ~18 GB |
| `aggressive` (default) | + **fp8 layerwise casting** (diffusers built-in) | **~15.5 GB** |
| `extreme` | + sequential offload + smaller VAE tile (no fp8 here) | ~12 GB, slow |

`fp8 layerwise casting` stores transformer weights as `float8_e4m3fn` and upcasts to bf16 on the fly during forward — ~50% transformer VRAM win, ~10% speed cost. Crucially **compatible with `enable_model_cpu_offload`** (unlike `optimum-quanto`'s marlin GEMM kernels, which assume contiguous layouts and break when offload shuffles tensors).

Override the profile or any individual knob:
```bash
./generate.sh --backend ltxd --profile safe "<prompt>"               # no fp8
./generate.sh --backend wan  --profile aggressive --no-attn-slicing "<prompt>"
./generate.sh --backend ltxd --vae-tile 96 --frames 257 "<prompt>"   # 10.7s clip
./generate.sh --backend wan  --legacy "<prompt>"                     # the old un-optimized scripts
```

### Measured benchmarks (RTX 5090 Laptop, 24 GB, aggressive profile)

| Backend | Length | Time | Peak VRAM | File |
|---|---|---|---|---|
| Wan 2.2 (50 steps, top quality) | 5.0 s (121f) | ~22 min | **11.6 GB** | 2.0 MB |
| LTX-distilled (8 steps, fast) | 6.7 s (161f) | ~3.8 min | 15.5 GB | 1.3 MB |
| LTX-distilled (8 steps, fast) | 10.7 s (257f) | ~5.4 min | 16.9 GB | 2.5 MB |

The previous OOM failures (`/mnt/d/video_gen/out/*_0-byte`) were the WSL VM itself getting killed because bf16 LTX-distilled (~22 GB on CPU) + T5 + activations exceeded WSL's default 31 GB RAM cap. fp8 layerwise halves both GPU and CPU memory pressure and made the pipeline survive without bumping `.wslconfig`.

## Files

- `deploy.sh` / `generate.py` — Wan 2.2 deploy + inference (legacy, unoptimized).
- `generate_opt.py` — Wan 2.2 with profile-based VRAM optimizations (default).
- `deploy_ltx.sh` / `generate_ltx.py` — LTX-Video deploy + inference (legacy).
- `generate_ltx_opt.py` — LTX-Video with profile-based VRAM optimizations (default).
- `deploy_audio.sh` — MMAudio SFX backend (own `mmaudio` env, repo on Linux fs).
- `generate.sh` — one generation over SSH, `--backend wan|ltx|ltxd`, `--profile`, pulls the clip.
- `produce.sh` — full pipeline in one command (video + voice + SFX + music + mix).
- `add_voice.py` / `add_music.py` / `add_sfx.py` — per-track audio generators (run on box).
- `add_audio.sh` — voice-only mux onto an existing clip.
- `requirements.txt` — extra pip deps layered on the cloned env.

## Not yet done (TZ roadmap, layers on top of this)

This is the **backend + smoke-test** only. Still to build for the full pipeline:
idea/prompt generation (local LLM), the 4-section `prompt.txt`, md5 dedup +
quality-gate registry, writing into the `to_load/<slug>_<ts>/` contract, cron
scheduling, and rsync delivery to the TrashCat box. `generate.sh` already emits
the `<slug>_<ts>/video.mp4` layout those steps expect.
