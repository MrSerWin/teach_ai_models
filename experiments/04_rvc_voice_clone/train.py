"""RVC v2 voice-clone training — orchestrates Applio's CLI.

Contract with submit.sh:
  python train.py --config <path> --output-dir <path>

What it does:
  1. Reads character config (dataset path, hyperparams, pretrain choice).
  2. Optionally downloads a custom pretrain (Ov2Super 48k by default).
  3. Calls Applio CLI: preprocess -> extract -> train -> index.
  4. Copies the best .pth + .index into <output-dir>/final_model/.
  5. Writes metrics.json (epochs run, final loss if parseable, paths).

Applio is expected to be installed on the Windows/WSL box at $APPLIO_DIR
(default /mnt/d/applio). Install instructions: README.md in this folder.

Auto-resume: Applio itself resumes from logs/<model_name>/ checkpoints if
the same model_name is reused. Submitting with --resume <exp-id> reuses the
output-dir, so we pass the same model_name and Applio picks up.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

def _resolve_applio_dir() -> Path:
    env = os.environ.get("APPLIO_DIR")
    if env:
        return Path(env)
    # Prefer ext4 home (~/applio) over NTFS /mnt/d/applio — git/chmod break on NTFS.
    for cand in [Path.home() / "applio", Path("/mnt/d/applio")]:
        if (cand / "core.py").exists():
            return cand
    return Path.home() / "applio"


APPLIO_DIR = _resolve_applio_dir()

# Ov2Super — community pretrain, strong default for small datasets (10-30 min).
# Source: https://huggingface.co/ORVC/Ov2Super
# NOTE: ORVC/Ov2Super only publishes 32k and 40k variants — no 48k.
# For 48k training, use pretrained="default" (Applio's bundled f0G/D48k.pth).
PRETRAINS = {
    "ov2super_40k": {
        "g": ("https://huggingface.co/ORVC/Ov2Super/resolve/main/f0Ov2Super40kG.pth", "f0Ov2Super40kG.pth"),
        "d": ("https://huggingface.co/ORVC/Ov2Super/resolve/main/f0Ov2Super40kD.pth", "f0Ov2Super40kD.pth"),
        "sr": 40000,
    },
    "ov2super_32k": {
        "g": ("https://huggingface.co/ORVC/Ov2Super/resolve/main/f0Ov2Super32kG.pth", "f0Ov2Super32kG.pth"),
        "d": ("https://huggingface.co/ORVC/Ov2Super/resolve/main/f0Ov2Super32kD.pth", "f0Ov2Super32kD.pth"),
        "sr": 32000,
    },
    # "default" -> let Applio use its bundled f0G/D{sr}k.pth (--custom_pretrained False).
    # This is the only viable option for 48k training.
    "default": None,
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[train] $ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_pretrain(name: str, dest_dir: Path) -> tuple[Path, Path] | None:
    if name not in PRETRAINS:
        sys.exit(
            f"[train] unknown pretrain '{name}'. Available: {sorted(PRETRAINS)}.\n"
            f"[train] For 48k sample_rate use pretrained=default (no 48k Ov2Super exists)."
        )
    spec = PRETRAINS[name]
    if spec is None:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key in ("g", "d"):
        url, filename = spec[key]
        out = dest_dir / filename
        if not out.exists():
            print(f"[train] downloading {filename}")
            urllib.request.urlretrieve(url, out)
        paths[key] = out
    return paths["g"], paths["d"]


def applio(args: list[str]) -> None:
    core = APPLIO_DIR / "core.py"
    if not core.exists():
        sys.exit(f"[train] Applio not found at {APPLIO_DIR}. Set APPLIO_DIR or install per README.")
    run([sys.executable, str(core), *args], cwd=APPLIO_DIR)


def _epoch_of(p: Path) -> int:
    # filename like  narrator_299e_11960s.pth  /  narrator_299e_11960s_best_epoch.pth
    for tok in p.stem.split("_"):
        if tok.endswith("e") and tok[:-1].isdigit():
            return int(tok[:-1])
    return -1


def pick_final_checkpoint(model_logs: Path, name: str) -> Path:
    """Applio writes inference-ready weights as <name>_<N>e_<M>s[_best_epoch].pth
    and heavy training checkpoints as G_*.pth. Prefer the inference weights:
    a *_best_epoch.pth if present, else the highest-epoch weight."""
    weights = list(model_logs.glob(f"{name}_*e_*s*.pth"))
    if weights:
        best = [w for w in weights if "best_epoch" in w.stem]
        pool = best or weights
        return max(pool, key=_epoch_of)
    # Fallback: heavy G_ checkpoint (works for inference but larger).
    gs = sorted(model_logs.glob("G_*.pth"), key=lambda p: int(p.stem.split("_")[1]))
    if not gs:
        sys.exit(f"[train] no .pth produced in {model_logs}")
    return gs[-1]


def pick_index(model_logs: Path) -> Path | None:
    # Applio writes added_<hash>_<model>.index after the `index` step.
    idxs = list(model_logs.glob("added_*.index"))
    if idxs:
        return idxs[0]
    idxs = list(model_logs.glob("*.index"))
    return idxs[0] if idxs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.output_dir).resolve()
    (out / "final_model").mkdir(parents=True, exist_ok=True)

    name = cfg["model_name"]
    sr = int(cfg["sample_rate"])
    dataset = cfg["dataset_path"]
    hp = cfg["train"]
    ext = cfg["extract"]

    if not Path(dataset).exists():
        sys.exit(f"[train] dataset not found: {dataset} (push it via scripts/push-data.sh)")

    # Pretrain
    pretrain_name = cfg.get("pretrained", "ov2super_48k")
    custom = ensure_pretrain(pretrain_name, APPLIO_DIR / "rvc" / "models" / "pretraineds" / "pretraineds_custom")
    if custom and PRETRAINS[pretrain_name]["sr"] != sr:
        sys.exit(f"[train] pretrain {pretrain_name} is {PRETRAINS[pretrain_name]['sr']}Hz but sample_rate={sr}")

    print(f"[train] model={name} sr={sr} pretrain={pretrain_name} dataset={dataset}")
    t0 = time.time()

    # 1. Preprocess. cut_preprocess: Skip|Simple|Automatic. We pre-sliced in
    # prep-rvc-dataset.sh, but Automatic re-validates and is robust, so keep it.
    applio([
        "preprocess",
        "--model_name", name,
        "--dataset_path", str(dataset),
        "--sample_rate", str(sr),
        "--cpu_cores", str(cfg.get("cpu_cores", 4)),
        "--cut_preprocess", cfg.get("cut_preprocess", "Automatic"),
        "--process_effects", str(cfg.get("process_effects", True)),
        "--noise_reduction", str(cfg.get("noise_reduction", False)),
    ])

    # 2. Extract pitch + content features.
    applio([
        "extract",
        "--model_name", name,
        "--sample_rate", str(sr),
        "--f0_method", ext.get("f0_method", "rmvpe"),
        "--cpu_cores", str(cfg.get("cpu_cores", 4)),
        "--gpu", str(cfg.get("gpu", 0)),
        "--embedder_model", ext.get("embedder", "contentvec"),
        "--include_mutes", str(ext.get("include_mutes", 2)),
    ])

    # 3. Train.
    train_args = [
        "train",
        "--model_name", name,
        "--sample_rate", str(sr),
        "--total_epoch", str(hp["epochs"]),
        "--batch_size", str(hp["batch_size"]),
        "--save_every_epoch", str(hp.get("save_every", 25)),
        "--save_only_latest", str(hp.get("save_only_latest", False)),
        "--save_every_weights", "True",
        "--cache_data_in_gpu", str(hp.get("cache_in_gpu", True)),
        "--gpu", str(cfg.get("gpu", 0)),
        "--pretrained", "True",
        "--overtraining_detector", str(hp.get("overtraining_detector", True)),
        "--overtraining_threshold", str(hp.get("overtraining_threshold", 50)),
    ]
    if custom:
        gp, dp = custom
        train_args += [
            "--custom_pretrained", "True",
            "--g_pretrained_path", str(gp),
            "--d_pretrained_path", str(dp),
        ]
    else:
        train_args += ["--custom_pretrained", "False"]
    applio(train_args)

    # 4. Build .index
    applio([
        "index",
        "--model_name", name,
    ])

    # 5. Copy artifacts to final_model/.
    # NOTE: shutil.copyfile (NOT copy2/copy) — the output dir is on NTFS (/mnt/d)
    # where copystat's utime() raises PermissionError. copyfile skips metadata.
    model_logs = APPLIO_DIR / "logs" / name
    pth = pick_final_checkpoint(model_logs, name)
    idx = pick_index(model_logs)
    final_pth = out / "final_model" / f"{name}.pth"
    shutil.copyfile(pth, final_pth)
    if idx:
        shutil.copyfile(idx, out / "final_model" / f"{name}.index")
    else:
        print("[train] WARNING: no .index file produced")

    # Per-epoch weights live in logs/<name>/<name>_<epoch>e_<step>s.pth — keep
    # a few snapshots so you can A/B test checkpoints (see ТЗ §5.4).
    snapshots = sorted(model_logs.glob(f"{name}_*e_*s*.pth"), key=_epoch_of)
    if snapshots:
        snap_dir = out / "final_model" / "checkpoints"
        snap_dir.mkdir(exist_ok=True)
        for s in snapshots[-5:]:  # last 5 saves
            shutil.copyfile(s, snap_dir / s.name)

    metrics = {
        "model_name": name,
        "sample_rate": sr,
        "pretrained": pretrain_name,
        "dataset_path": str(dataset),
        "epochs_requested": hp["epochs"],
        "batch_size": hp["batch_size"],
        "final_pth": str(final_pth.name),
        "final_index": (idx.name if idx else None),
        "duration_sec": round(time.time() - t0, 1),
        "applio_logs": str(model_logs),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"[train] done in {metrics['duration_sec']}s -> {final_pth}")


if __name__ == "__main__":
    main()
