# ops — TTS control plane + box agent

Remote-control the GPU box (training, synthesis, listening) from a browser or a
phone, and keep working when the box is off.

## Why it looks like this

The GPU box is unreliable by nature: it reboots, leaves the LAN, and — as of
2026-07 — can sit in a repair shop for a week. Every design choice follows from
that:

- **The control plane lives on the NAS, not the box.** The NAS is always on. If
  the dashboard lived on the box, it would vanish exactly when you need it.
- **The agent pulls, it never listens.** The box reaches *out* to the NAS, so it
  needs no inbound ports, and the queue simply waits while it is down. You can
  enqueue a training run from a phone; the box picks it up when it comes back.
- **The GPU is an exclusive lock; the CPU is not.** `device=gpu` jobs run one at
  a time. `device=cpu` jobs (probe renders) run *in parallel with training*. This
  is the point of the whole thing: previously, hearing a mid-training checkpoint
  meant **killing the training run** (we did it twice). Now the agent renders
  probes on the CPU every N epochs and uploads them to the NAS.
- **Samples live on the NAS.** So you can listen to A/B even while the box is
  dead — which is exactly the situation we were stuck in.

```
[NAS — always on, on the tailnet]           [GPU box — whenever it's up]
  control/  FastAPI + SQLite + UI             agent/  polls, runs OUR scripts
   • job queue (GPU lock)                      ├─ heartbeat  ─────────▶
   • status, logs, progress          ◀──poll───┤  (no inbound ports)
   • samples + verdicts                        ├─ train_finetune.py / synth_st2.py
   • Telegram alerts, Wake-on-LAN              └─ uploads rendered wavs ▶
```

The agent is a thin wrapper: it shells out to the **same scripts already in this
repo** (`train_finetune.py`, `synth_st2.py`, `recut_24k.py`). The CLI stays the
source of truth — there is no second implementation to drift.

## Layout

```
control/         runs on the NAS (Docker / Container Manager)
  app.py         REST API + static UI + offline watchdog
  db.py          SQLite: jobs, heartbeats, checkpoints, samples, verdicts
  notify.py      Telegram alerts + Wake-on-LAN magic packet
  static/        the dashboard (vanilla JS, no build step)
agent/           runs on the box, inside WSL
  agent.py       poll loop, job runners, checkpoint watcher, auto-CPU-synth
  install.sh     systemd unit
menubar/         SwiftBar plugin — training epoch in the Mac menu bar
```

## Job types

| type | device | what it runs |
|---|---|---|
| `train_st2` | gpu | StyleTTS2 fine-tune (`train_finetune.py -p <config>`) |
| `synth_st2` | cpu *or* gpu | render probes (`synth_st2.py`), uploads wavs to the NAS |
| `recut_24k` | cpu | rebuild the dataset at true 24 kHz |
| `audit` | cpu | dataset alignment audit |

Only these are accepted — the API never takes arbitrary shell.

## Deploy — NAS (control plane)

1. Install the **Tailscale** package from Synology's package center (so the
   dashboard is reachable from a phone), and **Container Manager**.
2. Copy `control/` to the NAS, e.g. `/volume1/tts/control`, and create the data
   dir `/volume1/tts` (holds `app.sqlite`, `logs/`, `samples/`).
3. `cp .env.example .env` and fill in: `TTS_TOKEN` (long random string),
   `TG_BOT_TOKEN` / `TG_CHAT_ID`, and `BOX_MAC` (for Wake-on-LAN).
4. Container Manager → Project → build from `docker-compose.yml`.
5. Open `http://<nas>:8080`.

> Wake-on-LAN packets are L2 broadcasts. If the Docker bridge network swallows
> them, switch the compose service to `network_mode: host`.

## Deploy — box (agent)

1. Install **Tailscale on the box** (it is *not* on the tailnet today — we only
   ever reached it over LAN `10.0.0.190`). This is what removes the
   "is it dead or am I just not home?" ambiguity for good.
2. `cp agent/config.example.env agent/config.env` and point `TTS_CONTROL` at the
   NAS **tailnet name** (not the LAN IP), with the same `TTS_TOKEN`.
3. `bash agent/install.sh` — installs a systemd unit inside WSL.
4. So the agent comes up after a Windows reboot, add a Task Scheduler task at
   logon: `wsl.exe -d <distro> -u <user> --exec /bin/true` (starts the distro,
   hence systemd, hence the agent).

## Mac menu bar

Symlink `menubar/tts-status.30s.sh` into `~/.swiftbar-plugins/` (next to the
existing `nas-status.30s.sh`). Shows `TTS 46/80` or a red dot when the box is
offline, and links to the dashboard.

## Status

Written and **tested end-to-end against a live FastAPI instance** (GPU lock,
parallel CPU claim, progress/log streaming, sample upload, verdict round-trip,
cancel, WoL, path-traversal guard). **Not yet deployed** — the GPU box is in
repair and the NAS is powered off. Deploy checklist above is the next step once
the hardware is back.
