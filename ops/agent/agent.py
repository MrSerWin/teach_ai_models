#!/usr/bin/env python3
"""TTS box agent — runs on the GPU box (WSL), polls the NAS control plane.

It never listens on a port: it reaches out. So the box can sit behind any
network, reboot, or die in repair, and the queue on the NAS just waits.

Two independent workers:
  * GPU worker — one job at a time (the control plane enforces the lock).
  * CPU worker — probe renders. These run *while training holds the GPU*, which
    is the whole point: you get fresh samples to listen to without killing the run.

It also watches a training run's output dir and, every AUTO_SYNTH_EVERY epochs,
enqueues a CPU synth job for the fresh checkpoint. So by morning there are
samples for e40/e50/e60… waiting on the NAS — no stopping anything.

Config via env (see config.example.env).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import requests

CONTROL = os.environ["TTS_CONTROL"].rstrip("/")     # e.g. http://nas:8080
TOKEN = os.environ.get("TTS_TOKEN", "change-me")
HOST = os.environ.get("TTS_HOST", "win-train")
REPO = Path(os.environ.get("TTS_REPO", str(Path.home() / "teach_ai_models")))
ST2 = Path(os.environ.get("ST2_DIR", str(Path.home() / "StyleTTS2")))
CONDA_SH = os.environ.get("CONDA_SH", str(Path.home() / "miniconda3/etc/profile.d/conda.sh"))
CONDA_ENV = os.environ.get("CONDA_ENV", "qrimtatar_tts")
ESPEAK_DATA = os.environ.get("ESPEAK_DATA_PATH", str(Path.home() / ".local/share/espeak-ng-data"))
DISK_PATH = os.environ.get("DISK_PATH", "/mnt/c")
AUTO_SYNTH_EVERY = int(os.environ.get("AUTO_SYNTH_EVERY", "10"))   # epochs; 0 = off
AUTO_SYNTH_PROBES = os.environ.get("AUTO_SYNTH_PROBES", "q_carrier.lat.json")
NVIDIA_SMI = os.environ.get("NVIDIA_SMI", "/usr/lib/wsl/lib/nvidia-smi")
POLL_SEC = int(os.environ.get("POLL_SEC", "15"))

S = requests.Session()
S.headers["X-Token"] = TOKEN

_procs = {}          # job_id -> Popen
_cancel = set()      # job ids the control plane asked us to stop

# StyleTTS2 log line: "Epoch [46/80], Step [520/670], Loss: 0.33, ... F0 Loss: 1.75, ..."
EPOCH_RE = re.compile(r"Epoch \[(\d+)/(\d+)\].*?Step \[(\d+)/(\d+)\]")
LOSS_RE = re.compile(r"([A-Za-z0-9]+(?: [A-Za-z0-9]+)?) Loss: ([\d.]+)")


def api(method, path, **kw):
    try:
        r = S.request(method, f"{CONTROL}{path}", timeout=30, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[agent] api {method} {path} failed: {e}", flush=True)
        return None


def gpu_mem():
    try:
        out = subprocess.run(
            [NVIDIA_SMI, "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        used, free = (int(x) for x in out.split(","))
        return used, free
    except Exception:
        return None, None


def disk_free_gb(path=DISK_PATH):
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        return None


def bash(cmd):
    """Run a command inside the conda env, with espeak on PATH."""
    pre = (f'source "{CONDA_SH}" && conda activate {CONDA_ENV} && '
           f'export PATH="$HOME/.local/bin:$PATH" && '
           f'export ESPEAK_DATA_PATH="{ESPEAK_DATA}" && ')
    return ["bash", "-lc", pre + cmd]


# ---------------------------------------------------------------- job runners

def cmd_for(job):
    """Map a job to a shell command. Allowlist only — no arbitrary shell from the API."""
    t, p = job["type"], job["params"]

    if t == "train_st2":
        config = p.get("config", "Configs/config_ft_crh_24k.yml")
        return bash(f'cd "{ST2}" && python train_finetune.py -p "{config}"')

    if t == "synth_st2":
        ckpt = p["checkpoint"]
        ref = p.get("ref", "/mnt/c/wsl_datasets/crh_sevil_st2_24k/wavs/avdet_avasy_0001.wav")
        out = p["out_dir"]
        probes = p.get("probes", AUTO_SYNTH_PROBES)
        cfg = p.get("config", "Configs/config_ft_crh_24k.yml")
        steps = p.get("steps", 10)
        escale = p.get("escale", 1.0)
        # device=cpu jobs must not touch the GPU that training is holding
        hide = "CUDA_VISIBLE_DEVICES= " if job["device"] == "cpu" else ""
        return bash(
            f'cd "{ST2}" && {hide}python synth_st2.py "{ckpt}" "{ref}" "{out}" '
            f'--config "{cfg}" --probes "{probes}" --steps {steps} --escale {escale}')

    if t == "recut_24k":
        books = p["books_dir"]; ds = p["dataset_dir"]; out = p["out_dir"]
        return bash(f'cd "{REPO}" && python experiments/06_tts_dataset/scripts/recut_24k.py '
                    f'"{books}" "{ds}" "{out}"')

    if t == "audit":
        ds = p["dataset_dir"]
        return bash(f'cd "{REPO}" && python experiments/06_tts_dataset/scripts/audit_dataset.py "{ds}"')

    raise ValueError(f"unknown job type {t}")


def upload_samples(job, out_dir):
    wavs = sorted(Path(out_dir).glob("*.wav"))
    if not wavs:
        return
    p = job["params"]
    files = [("files", (w.name, w.read_bytes(), "audio/wav")) for w in wavs]
    data = {
        "run": p.get("run", "unknown"),
        "probe_set": Path(p.get("probes", AUTO_SYNTH_PROBES)).stem,
        "epoch": str(p.get("epoch", 0)),
        "job_id": str(job["id"]),
        "params": json.dumps({k: p.get(k) for k in ("steps", "escale", "alpha", "beta")}),
    }
    try:
        S.post(f"{CONTROL}/api/samples", data=data, files=files, timeout=300).raise_for_status()
        print(f"[agent] uploaded {len(wavs)} wavs for job {job['id']}", flush=True)
    except Exception as e:
        print(f"[agent] sample upload failed: {e}", flush=True)


def watch_checkpoints(job, out_dir, stop):
    """Register new checkpoints and auto-enqueue a CPU probe render every N epochs."""
    seen = set()
    run = job["params"].get("run", "st2_crh_24k")
    while not stop.is_set():
        try:
            for ck in sorted(Path(out_dir).glob("epoch_2nd_*.pth")):
                if ck in seen:
                    continue
                seen.add(ck)
                m = re.search(r"(\d+)\.pth$", ck.name)
                epoch = int(m.group(1)) if m else None
                size = ck.stat().st_size
                api("POST", "/api/checkpoints", json={
                    "run": run, "epoch": epoch, "path": str(ck), "size_bytes": size})
                if AUTO_SYNTH_EVERY and epoch and epoch % AUTO_SYNTH_EVERY == 0:
                    api("POST", "/api/jobs", json={
                        "type": "synth_st2", "device": "cpu", "priority": 5,
                        "params": {
                            "checkpoint": str(ck), "run": run, "epoch": epoch,
                            "out_dir": f"/tmp/tts_samples/{run}_e{epoch}",
                            "probes": AUTO_SYNTH_PROBES,
                            "config": job["params"].get("config", "Configs/config_ft_crh_24k.yml"),
                        }})
                    print(f"[agent] auto-queued CPU synth for e{epoch}", flush=True)
        except Exception as e:
            print(f"[agent] ckpt watch: {e}", flush=True)
        stop.wait(60)


def run_job(job):
    jid = job["id"]
    print(f"[agent] running job {jid} ({job['type']}, {job['device']})", flush=True)
    stop = threading.Event()
    watcher = None
    try:
        cmd = cmd_for(job)
    except Exception as e:
        api("POST", f"/api/jobs/{jid}/done", json={"status": "failed", "error": str(e)})
        return

    if job["type"] == "train_st2":
        out_dir = job["params"].get("log_dir", "/mnt/c/wsl_runs/st2_crh_24k")
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        watcher = threading.Thread(target=watch_checkpoints, args=(job, out_dir, stop), daemon=True)
        watcher.start()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, preexec_fn=os.setsid)
    _procs[jid] = proc
    buf, last_push, progress = [], 0.0, {}

    for line in proc.stdout or []:
        buf.append(line)
        m = EPOCH_RE.search(line)
        if m:
            progress = {
                "epoch": int(m.group(1)), "epochs": int(m.group(2)),
                "step": int(m.group(3)), "steps": int(m.group(4)),
                "losses": {k: float(v) for k, v in LOSS_RE.findall(line)},
            }
        now = time.time()
        if now - last_push > 10:
            api("POST", f"/api/jobs/{jid}/progress",
                json={"progress": progress, "log": "".join(buf)})
            buf, last_push = [], now
        if jid in _cancel:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            break

    proc.wait()
    stop.set()
    if buf:
        api("POST", f"/api/jobs/{jid}/progress", json={"progress": progress, "log": "".join(buf)})
    _procs.pop(jid, None)

    if jid in _cancel:
        _cancel.discard(jid)
        api("POST", f"/api/jobs/{jid}/done", json={"status": "canceled"})
        return
    if proc.returncode == 0:
        if job["type"] == "synth_st2":
            upload_samples(job, job["params"]["out_dir"])
        api("POST", f"/api/jobs/{jid}/done", json={"status": "done"})
    else:
        tail = "".join(buf[-20:]) or f"exit code {proc.returncode}"
        api("POST", f"/api/jobs/{jid}/done", json={"status": "failed", "error": tail})


# ---------------------------------------------------------------- workers

def worker(device, max_parallel):
    active = []
    while True:
        active = [t for t in active if t.is_alive()]
        if len(active) < max_parallel:
            r = api("GET", f"/api/jobs/next?device={device}")
            job = (r or {}).get("job")
            if job:
                t = threading.Thread(target=run_job, args=(job,), daemon=True)
                t.start()
                active.append(t)
                continue
        time.sleep(POLL_SEC)


def heartbeat_loop():
    while True:
        used, free = gpu_mem()
        r = api("POST", "/api/heartbeat", json={
            "host": HOST, "gpu_used_mb": used, "gpu_free_mb": free,
            "disk_free_gb": disk_free_gb(), "running_jobs": list(_procs.keys()),
            "meta": {"repo": str(REPO)},
        })
        for jid in (r or {}).get("cancel", []):
            _cancel.add(jid)
        time.sleep(30)


def main():
    print(f"[agent] {HOST} -> {CONTROL}", flush=True)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    threading.Thread(target=worker, args=("cpu", 2), daemon=True).start()
    worker("gpu", 1)   # blocks


if __name__ == "__main__":
    main()
