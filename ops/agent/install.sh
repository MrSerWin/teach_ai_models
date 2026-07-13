#!/usr/bin/env bash
# Install the box agent as a systemd service inside WSL.
#
# WSL needs systemd enabled (/etc/wsl.conf -> [boot] systemd=true; then
# `wsl --shutdown` from Windows). For the agent to come up when the machine
# boots, also add a Windows Task Scheduler task at logon running:
#     wsl.exe -d <distro> -u <user> --exec /bin/true
# which starts the distro (and thus systemd, and thus this service).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/config.env" ] || { echo "create $HERE/config.env from config.example.env first"; exit 1; }

sudo tee /etc/systemd/system/tts-agent.service >/dev/null <<UNIT
[Unit]
Description=TTS box agent (polls the NAS control plane)
After=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HERE
EnvironmentFile=$HERE/config.env
ExecStart=/usr/bin/env python3 $HERE/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now tts-agent
sudo systemctl status tts-agent --no-pager
