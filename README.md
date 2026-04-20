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
   **WSL IP changes on every Windows reboot** — you can automate the re-binding. Copy [scripts/windows/](scripts/windows/) to the Windows box and run from elevated PowerShell **once**:
   ```powershell
   .\install-portproxy-task.ps1
   ```
   This registers [update-portproxy.ps1](scripts/windows/update-portproxy.ps1) as a Task Scheduler job that fires on every system start — the port-forward self-heals from then on. To refresh ad-hoc (e.g. after restarting WSL without a reboot), run:
   ```powershell
   .\update-portproxy.ps1
   ```

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
| `REMOTE_RUNS_DIR`  | `/mnt/d/runs`     | Where experiment artifacts live on Windows (D: drive via WSL)   |
| `REMOTE_DATASETS_DIR` | `/mnt/d/datasets` | Where `push-data.sh` uploads dataset folders                  |
| `BASE_CONDA_ENV`   | `ml_base`         | Pre-configured conda env that every experiment clones           |
| `LOCAL_MODELS_DIR` | `./models`       | Where fetched final models land on Mac                          |
| `NOTIFY_MACOS`     | `1` on Darwin    | macOS notification after submit finishes. Set `0` to disable    |
| `NTFY_TOPIC`       | —                | If set, POST notifications to `https://ntfy.sh/<topic>`         |
| `NTFY_SERVER`      | `https://ntfy.sh` | Override for a self-hosted ntfy instance                       |
| `MIN_FREE_GIB`     | `5`              | Warn + confirm before submit if remote free space is below this |

### Multi-host

Put alternate host configs in `.env.hosts/<name>.env` and switch with the `HOST` env var:
```bash
HOST=gpu-rig-2 ./scripts/submit.sh experiments/foo
HOST=laptop    ./scripts/list.sh
```
`.env.hosts/*.env` is gitignored — safe for private LAN addresses/users.

## Scripts

All scripts live in [scripts/](scripts/) and source [config.sh](config.sh) which reads `.env`.

Every script that targets a specific run accepts `[exp-id]` as an argument; if omitted, it uses `.runs/latest` (written by `submit.sh`). Pass `<exp-id>` explicitly to act on older runs.

### [`submit.sh`](scripts/submit.sh) — start (or resume) a training run

```bash
./scripts/submit.sh <experiment-dir>            # submit and follow logs live
./scripts/submit.sh -d <experiment-dir>         # submit and return immediately
./scripts/submit.sh --resume <exp-id>           # reuse an existing exp-id + conda env + checkpoints
./scripts/submit.sh --gpu 0 <experiment-dir>    # pin to GPU 0 (CUDA_VISIBLE_DEVICES)
./scripts/submit.sh --gpu 0,1 <experiment-dir>  # multi-GPU
./scripts/submit.sh --queue <experiment-dir>    # wait behind any running job on the same GPU
./scripts/submit.sh --clone <experiment-dir>    # isolate in a per-experiment conda env
```

**Shared vs. cloned conda env** (disk vs. isolation trade-off):

- **Default** — the run uses `$BASE_CONDA_ENV` directly, no cloning. Fast (no 30s clone), uses ~no extra disk. Best when all experiments share the same deps. If `requirements.txt` has uncommented entries, the script warns and skips pip install (would pollute the shared env).
- **With `--clone`** — clones `$BASE_CONDA_ENV → <exp-id>` for this run. Full isolation: extras from `requirements.txt` install cleanly into the clone without touching other experiments. Each clone normally uses hard links and adds little real disk, but metadata accumulates, so pair with `./scripts/gc.sh` on old runs.

Recommended pattern: create a pristine master env once (`conda create --name my_base_shared --clone qrimtatar_tts`), point `BASE_CONDA_ENV=my_base_shared` in `.env`, and run everything in shared mode. Use `--clone` only when an experiment needs a conflicting package version.

**Resume** reuses the same remote dir and conda env. Your `train.py` should check `<output-dir>/checkpoints/` on startup and pick up the latest — all 3 example scripts implement this pattern. After a crash, OOM, or forced cancel, running `--resume <exp-id>` continues from the last saved epoch.

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

### [`shell.sh`](scripts/shell.sh) — open a shell on the remote

```bash
./scripts/shell.sh                  # attach to latest run's tmux session
./scripts/shell.sh <exp-id>         # same, specific run
./scripts/shell.sh --free           # plain interactive shell in $REMOTE_RUNS_DIR
```

Use `Ctrl-b d` to detach from tmux without killing training.

### [`tensorboard.sh`](scripts/tensorboard.sh) — live TB in browser

```bash
./scripts/tensorboard.sh                # latest run, localhost:6006
./scripts/tensorboard.sh <exp-id> -p 6007
```

Starts TensorBoard in the experiment's conda env and forwards the port to Mac. `Ctrl-C` tears it all down. Requires `tensorboard` in the cloned env (install via a `requirements.txt` line or `conda run -n <env> pip install tensorboard`).

### [`diff.sh`](scripts/diff.sh) — compare two fetched experiments

```bash
./scripts/diff.sh <exp-id-a> <exp-id-b>
```

Side-by-side: unified diff of `config.yaml`, final metrics with numeric deltas, git commits. Both experiments must already be fetched to `$LOCAL_MODELS_DIR`.

### [`gc.sh`](scripts/gc.sh) — garbage-collect stale runs

```bash
./scripts/gc.sh                                      # 30d default, interactive
./scripts/gc.sh --older-than 7d --only-done
./scripts/gc.sh --older-than 12h --dry-run           # preview only
./scripts/gc.sh --older-than 30d -y                  # automated
```

Lists remote experiments older than the threshold and cleans them via `clean.sh` (conda env + run dir). Threshold supports `Nd`/`Nh`/`Nm`.

### [`submit-docker.sh`](scripts/submit-docker.sh) — Docker-based alternative to `submit.sh`

```bash
./scripts/submit-docker.sh <experiment-dir>
./scripts/submit-docker.sh --image my:tag <experiment-dir>
```

Runs training in a Docker container (using `docker/Dockerfile`) with `--gpus all`. Requires `nvidia-container-toolkit` on the WSL box — see the script header. An experiment can BYO Dockerfile by placing one at the experiment root.

### [`push-data.sh`](scripts/push-data.sh) — upload a dataset folder

```bash
./scripts/push-data.sh <local-dir> [remote-subdir]
```

One-off helper to sync a local dataset folder to `$REMOTE_DATASETS_DIR/<remote-subdir>` on Windows. Idempotent: rsync only transfers what changed, so re-running is cheap. If `remote-subdir` is omitted, uses `basename "<local-dir>"`.

Philosophy: data lives on the training box and you reference it by absolute path from `config.yaml` (e.g. `/mnt/d/datasets/my_dataset`). `submit.sh` excludes `data/` from its rsync on purpose — you shouldn't re-upload gigabytes on every run.

```bash
# one-time: upload the dataset
./scripts/push-data.sh ~/projects/my_proj/data my_dataset
# then in experiments/<name>/config.yaml:
#   dataset_path: /mnt/d/datasets/my_dataset
```

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

## Examples

Three runnable examples under [experiments/](experiments/), covering the most common data patterns. Each has its own README with the exact data layout it expects, a `make_sample_data.py` helper to generate a toy dataset, and a one-line run command.

| # | Folder | Task | Dataset format | Sample-data helper |
|---|--------|------|----------------|---------------------|
| 1 | [`01_mnist_builtin/`](experiments/01_mnist_builtin/) | Image classification (10 digits) | **No upload** — `torchvision` downloads MNIST on first run | — |
| 2 | [`02_image_folder/`](experiments/02_image_folder/) | Image classification (N classes) | `train/<class>/*.jpg` + `val/<class>/*.jpg` (ImageFolder layout) | ✓ (synthetic colour images) |
| 3 | [`03_tabular_csv/`](experiments/03_tabular_csv/) | Regression **or** classification on CSV features | `train.csv` + `val.csv` (same columns, one is the target) | ✓ (regression or classification) |

### Smoke-test the pipeline

```bash
./scripts/submit.sh experiments/01_mnist_builtin
```

That's the fastest way to verify Mac→Windows→GPU→fetch works end-to-end. No data upload needed.

### End-to-end with your own image dataset

```bash
# 1. Prepare local folder  ~/my_images/{train,val}/<class>/*.jpg
./scripts/push-data.sh ~/my_images my_images
# 2. Edit experiments/02_image_folder/config.yaml → dataset_path: /mnt/d/datasets/my_images
# 3. Submit
./scripts/submit.sh experiments/02_image_folder
```

See [experiments/02_image_folder/README.md](experiments/02_image_folder/README.md) for full details.

### End-to-end with CSV data

```bash
# 1. Prepare  ~/my_csv/{train.csv, val.csv}  (same columns, one is the target)
./scripts/push-data.sh ~/my_csv my_data
# 2. Edit experiments/03_tabular_csv/config.yaml:
#      data.dataset_path: /mnt/d/datasets/my_data
#      data.target_column: <your-target-col>
#      train.task: regression     # or classification
# 3. Submit
./scripts/submit.sh experiments/03_tabular_csv
```

See [experiments/03_tabular_csv/README.md](experiments/03_tabular_csv/README.md) for full details.

## Adding your own experiment

Two layouts work:

**A. Under `experiments/`** — copy one of the `01_*`/`02_*`/`03_*` folders and tweak. Submit via `./scripts/submit.sh experiments/<my-name>`.

**B. External project folder** — when training code lives in a separate project, `submit.sh` accepts any absolute path:

```bash
./scripts/submit.sh /Volumes/T9/1_dev/my_proj/training
./scripts/submit.sh ~/projects/my_proj/pipelines/train
```

The `exp-id` takes the basename of that folder. Contents get rsynced except `__pycache__`, `*.pyc`, `.venv`, `data/`, `models/`, `runs/`.

**Contract your `train.py` must honour** (in both layouts):

1. Accept CLI args `--config <path>` and `--output-dir <path>`.
2. Read hyperparams from `<config>`.
3. Write the final model to `<output-dir>/final_model/` (any file(s) inside).
4. Write a summary to `<output-dir>/metrics.json`.
5. Anything else (checkpoints, tensorboard, logs) is free — it stays on Windows and never comes back to Mac.

`config.yaml` is yours — put whatever hyperparams make sense. Reference datasets by their **remote path** (e.g. `/mnt/d/datasets/<name>`) since training runs on Windows.

`requirements.txt` is **optional** — only used for extras on top of the cloned `$BASE_CONDA_ENV`. Leave empty/commented if the base env has everything.

## What gets synced, what doesn't

**Mac → Windows** (`submit`): experiment folder, excluding `__pycache__/`, `*.pyc`, `.venv/`, `data/`, `models/`, `runs/`.

**Windows → Mac** (`fetch`): only `final_model/`, `metrics.json`, `config.yaml`, `train.log`, `status`. Everything else (checkpoints, optimizer state, tb logs, pip caches, the conda env itself) stays on Windows.

## Recipes — common workflows

### Quick smoke-test of the whole pipeline
```bash
./scripts/submit.sh experiments/01_mnist_builtin        # ~1–2 min, no data upload
```

### Resume a crashed / OOM-killed run
```bash
./scripts/list.sh                                        # find the exp-id of the failed run
./scripts/submit.sh --resume <exp-id>                    # picks up from last saved epoch
```

### Run two experiments on one GPU sequentially (FIFO)
```bash
./scripts/submit.sh -d --queue experiments/exp_a
./scripts/submit.sh -d --queue experiments/exp_b
./scripts/list.sh                                        # both 'queued' initially
```
The first to arrive at the lock runs; the second waits (`state: queued` → `running` → `done`). Add `--gpu 0`/`--gpu 1` to target different cards — each GPU has its own lock.

### Run two experiments in parallel on separate GPUs
```bash
./scripts/submit.sh -d --gpu 0 experiments/exp_a
./scripts/submit.sh -d --gpu 1 experiments/exp_b
```

### Hyperparameter sweep (tiny shell loop)
```bash
for lr in 1e-4 3e-4 1e-3; do
  cp experiments/02_image_folder/config.yaml /tmp/cfg.yaml
  sed -i '' "s/lr: .*/lr: $lr/" /tmp/cfg.yaml
  # rsync cfg into a throwaway experiment dir, or use a template…
  ./scripts/submit.sh -d --queue experiments/02_image_folder
done
./scripts/list.sh                                        # watch the queue drain
```

### Compare two runs
```bash
./scripts/fetch.sh <exp-id-a>
./scripts/fetch.sh <exp-id-b>
./scripts/diff.sh  <exp-id-a> <exp-id-b>
```

### See live TB graphs while training
```bash
./scripts/submit.sh -d experiments/02_image_folder
./scripts/tensorboard.sh                                 # open http://localhost:6006
```

### Free disk space after a batch of runs
```bash
./scripts/gc.sh --older-than 7d --only-done --dry-run    # preview
./scripts/gc.sh --older-than 7d --only-done              # interactive confirm
```

### Switch between training boxes
```bash
# one-time: create .env.hosts/laptop.env and .env.hosts/gpu-rig.env
HOST=gpu-rig ./scripts/submit.sh experiments/foo
HOST=laptop  ./scripts/shell.sh --free                    # poke around on the other box
```

### Push to your phone / watch when training finishes
```bash
# in .env:
#   NTFY_TOPIC=my-private-topic-12345
# then install the ntfy app, subscribe to the topic:
./scripts/submit.sh -d experiments/...
# walk away — when state flips to done/failed you'll get a push
```

## Contributing

Enable the bundled pre-commit hook once per clone so you don't ship shell/python syntax errors:
```bash
git config core.hooksPath .githooks
```
It runs `bash -n`, `python3 ast.parse`, and (if installed) `shellcheck -S warning` on staged files.

## Reliability notes

- Training runs in a detached `tmux` session — SSH disconnects don't kill it.
- Auto-resume: every example `train.py` restores from `checkpoints/epoch-*.pt` on startup. Pair with `submit.sh --resume <exp-id>` to continue interrupted runs.
- `rsync --partial --append-verify` resumes interrupted transfers.
- `ServerAliveInterval=30` keeps idle SSH connections alive.
- Per-experiment cloned conda env — deps for one experiment can't break another; the base `ml_base` stays pristine.
- `vmIdleTimeout=-1` in `.wslconfig` prevents WSL (and thus sshd) from suspending.
- Scheduled task ([scripts/windows/install-portproxy-task.ps1](scripts/windows/install-portproxy-task.ps1)) refreshes the Windows→WSL port forward on every boot so a reboot doesn't break SSH.
- Every run records its source git commit in `git_info.json` and produces a `MODEL_CARD.md` on fetch — months later you can still tell exactly what code produced a given model.
