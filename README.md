# teach_ai_models

Pipeline: prepare experiment on Mac, run training on Windows (192.168.1.100) via SSH+rsync+tmux, pull **only the final model** back.

```
Mac (control)                            Windows (compute, 192.168.1.100)
─────────────                            ──────────────────────────────
experiments/<name>/     ─── rsync ──▶    D:\runs\<exp-id>\  (via WSL2: /mnt/d/runs/<exp-id>)
  train.py                               conda clone ml_base → <exp-id>
  config.yaml                            python train.py ... (inside tmux)
                                         checkpoints/, train.log  ← stay here
                                         final_model/, metrics.json
models/<exp-id>/        ◀── rsync ───    final_model/ + metrics.json only
```

## One-time setup

### On Windows 192.168.1.100

1. **OpenSSH Server** (PowerShell as admin):
   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
   New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
   ```

2. **WSL2 + Ubuntu + CUDA + Miniconda + base env `ml_base`**:
   ```powershell
   wsl --install -d Ubuntu
   # inside Ubuntu:
   sudo apt update && sudo apt install -y tmux rsync openssh-server
   # install Miniconda if not present; create your base training env:
   conda create -n ml_base python=3.11 pytorch torchvision pyyaml -c pytorch -c nvidia
   # install NVIDIA CUDA toolkit for WSL:
   # https://docs.nvidia.com/cuda/wsl-user-guide/index.html
   ```

3. **Expose WSL's sshd on the LAN** (so Mac's `ssh 192.168.1.100` lands in WSL, giving uniform `/mnt/d/...` paths).

   Inside WSL:
   ```bash
   sudo sed -i 's/^#Port 22/Port 2222/' /etc/ssh/sshd_config
   sudo service ssh start
   ```
   In Windows PowerShell (admin), get WSL IP and forward:
   ```powershell
   $wslIp = (wsl hostname -I).Trim().Split()[0]
   netsh interface portproxy add v4tov4 listenport=22 listenaddress=0.0.0.0 connectport=2222 connectaddress=$wslIp
   New-NetFirewallRule -DisplayName "WSL SSH" -Direction Inbound -LocalPort 22 -Protocol TCP -Action Allow
   # stop native Windows sshd so port 22 is free for the proxy:
   Stop-Service sshd -ErrorAction SilentlyContinue
   Set-Service -Name sshd -StartupType Manual -ErrorAction SilentlyContinue
   ```
   Note: WSL IP changes on every Windows reboot — re-run the `netsh portproxy` command with the new IP, or automate via Task Scheduler.

4. **Keep WSL alive** (by default WSL shuts down when idle and sshd dies with it):
   ```powershell
   # in Windows PowerShell, write %USERPROFILE%\.wslconfig:
   "`n[wsl2]`nvmIdleTimeout=-1" | Out-File -Append -Encoding ASCII $env:USERPROFILE\.wslconfig
   wsl --shutdown  # apply
   ```

5. **Create the runs folder** (inside WSL):
   ```bash
   mkdir -p /mnt/d/runs
   ```

### On Mac

1. **SSH key to Windows**:
   ```bash
   ssh-keygen -t ed25519 -C "teach_ai_models"    # if you don't have one
   ssh-copy-id trainer@192.168.1.100
   ssh trainer@192.168.1.100 "echo ok"               # should print 'ok' without prompting
   ```
   If `ssh-copy-id` installed a non-default key (e.g. `id_nas`), add a host entry in `~/.ssh/config`:
   ```
   Host 192.168.1.100
       User trainer
       IdentityFile ~/.ssh/id_nas
       IdentitiesOnly yes
   ```

2. **Configure this project**:
   ```bash
   cd path/to/teach_ai_models
   cp .env.example .env
   # edit .env — see Configuration below
   chmod +x scripts/*.sh
   ```

## Configuration (`.env`)

| Variable           | Default          | Meaning                                                         |
|--------------------|------------------|-----------------------------------------------------------------|
| `WIN_HOST`         | `192.168.1.100`     | IP/hostname of the Windows machine on the LAN                   |
| `WIN_USER`         | —                | Linux username inside WSL (not the Windows user)                |
| `WIN_SSH_PORT`     | `22`             | Port exposed via Windows `portproxy`                            |
| `REMOTE_RUNS_DIR`  | `/mnt/d/runs`    | Where experiment artifacts live on Windows (D: drive via WSL)   |
| `BASE_CONDA_ENV`   | `ml_base`  | Pre-configured conda env that every experiment clones           |
| `LOCAL_MODELS_DIR` | `./models`       | Where fetched final models land on Mac                          |

## Scripts

All scripts live in [scripts/](scripts/) and source [config.sh](config.sh) which reads `.env`.

Every script that targets a specific run accepts `[exp-id]` as an argument; if omitted, it uses `.runs/latest` (written by `submit.sh`). Pass `<exp-id>` explicitly to act on older runs.

### [`submit.sh`](scripts/submit.sh) — start a training run

```bash
./scripts/submit.sh <experiment-dir>            # submit and follow logs live
./scripts/submit.sh -d <experiment-dir>         # submit and return immediately
./scripts/submit.sh --detach <experiment-dir>   # same
```

1. Generates `exp-id = <timestamp>-<experiment-dir-name>`.
2. `rsync` pushes the experiment folder to `$REMOTE_RUNS_DIR/<exp-id>/`. Excludes `__pycache__`, `*.pyc`, `.venv`, `data/`, `models/`, `runs/`. Uses `--no-perms --no-owner --no-group --omit-dir-times` because `/mnt/d` is Windows NTFS and rejects Unix metadata.
3. Remote bootstrap (over SSH): sources conda, verifies `$BASE_CONDA_ENV` exists, clones it into `<exp-id>` (≈30–60s vs. 5–10min for a fresh venv). If `requirements.txt` has uncommented entries, installs them on top via pip.
4. Starts `python -u train.py --config config.yaml --output-dir .` inside a detached `tmux` session named `train-<exp-id>`. Writes `status` file: `running`, then `done`/`failed`/`cancelled`.
5. Writes `.runs/latest = <exp-id>` on Mac, then by default attaches `tail -F` to the remote log. `Ctrl-C` detaches — training keeps running in tmux. Pass `-d`/`--detach` to skip the tail and return right away (useful for scripting).

**Training-script contract:** `train.py` must accept `--config <path> --output-dir <path>`. Write the final model to `<output-dir>/final_model/` and summary to `<output-dir>/metrics.json` (other names won't be fetched back).

### [`status.sh`](scripts/status.sh) — snapshot of a run

```bash
./scripts/status.sh [exp-id]
```

Shows current `status` file (`running`/`done`/`failed`/`cancelled`), exit code if any, whether the tmux session is alive, and the last 20 lines of `train.log`. One-shot (doesn't follow).

### [`logs.sh`](scripts/logs.sh) — live log tail

```bash
./scripts/logs.sh [exp-id]
```

`tail -F` on the remote `train.log`. `Ctrl-C` stops tailing — the training continues running in its tmux session unaffected.

### [`list.sh`](scripts/list.sh) — all experiments on the remote

```bash
./scripts/list.sh
```

Table: `EXP_ID | STATE | TMUX`. Useful to find orphaned runs, decide what to `clean` or `fetch`.

### [`fetch.sh`](scripts/fetch.sh) — pull final artifacts back

```bash
./scripts/fetch.sh [exp-id]
./scripts/fetch.sh --force [exp-id]   # override the done-check
```

Only downloads `final_model/`, `metrics.json`, `config.yaml`, `train.log`, `status` to `$LOCAL_MODELS_DIR/<exp-id>/`. Intermediate checkpoints, optimizer states, tensorboard logs — stay on Windows. Refuses to run unless `status == done` (use `--force` to override, e.g. to inspect a failed run).

### [`cancel.sh`](scripts/cancel.sh) — stop a running experiment

```bash
./scripts/cancel.sh [exp-id]
```

Kills the `train-<exp-id>` tmux session on the remote and writes `cancelled` into `status`. Does not delete anything — files and conda env remain so you can inspect. To fully remove, follow with `clean.sh`.

### [`clean.sh`](scripts/clean.sh) — remove remote artifacts of an experiment

```bash
./scripts/clean.sh [exp-id]        # asks for confirmation
./scripts/clean.sh -y [exp-id]     # no prompt (scripting)
```

Deletes on the remote:
- the cloned conda env `<exp-id>`
- the run directory `$REMOTE_RUNS_DIR/<exp-id>/`

Does NOT touch:
- `$BASE_CONDA_ENV` (the pristine base)
- `models/<exp-id>/` on Mac (your already-fetched artifacts)

**Safety:** refuses to run if the tmux session is still alive — you must `cancel.sh` first.

## Typical workflow

```bash
./scripts/submit.sh experiments/example   # kick off
./scripts/status.sh                       # check — peek once in a while
./scripts/logs.sh                         # or watch live
# when status == done:
./scripts/fetch.sh                        # → models/<exp-id>/
cat models/<exp-id>/metrics.json
./scripts/clean.sh -y                     # free space on Windows (optional)
```

## Adding your own experiment

Copy `experiments/example/` to `experiments/<my-name>/` and edit:

- `train.py` — honors the `--config <path> --output-dir <path>` contract; writes to `<output-dir>/final_model/` and `<output-dir>/metrics.json`.
- `config.yaml` — hyperparams. Dataset paths should point to locations on the Windows box (e.g. `/mnt/d/datasets/...`).
- `requirements.txt` — **optional** extras installed on top of the cloned `$BASE_CONDA_ENV`. Leave empty/commented if the base has everything.

## What gets synced, what doesn't

**Mac → Windows** (`submit`): experiment folder, excluding `__pycache__/`, `*.pyc`, `.venv/`, `data/`, `models/`, `runs/`.

**Windows → Mac** (`fetch`): only `final_model/`, `metrics.json`, `config.yaml`, `train.log`, `status`. Everything else (checkpoints, optimizer state, tb logs, pip caches, the conda env itself) stays on Windows.

## Reliability notes

- Training runs in a detached `tmux` session — SSH disconnects don't kill it.
- `rsync --partial --append-verify` resumes interrupted transfers.
- `ServerAliveInterval=30` keeps idle SSH connections alive.
- Per-experiment cloned conda env — deps for one experiment can't break another; the base `ml_base` stays pristine.
- `vmIdleTimeout=-1` in `.wslconfig` prevents WSL (and thus sshd) from suspending.
