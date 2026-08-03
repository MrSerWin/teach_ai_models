#!/usr/bin/env bash
#
# Deploy the QO control plane + tv-archiver on the Synology NAS.
#
# Run this ON the NAS (the Docker socket is root-only, so sudo is required):
#
#     sudo bash /volume1/tts/deploy.sh                 # apply synced code (NO container restart)
#     sudo bash /volume1/tts/deploy.sh --replan        # + rebuild the recording schedule
#     sudo bash /volume1/tts/deploy.sh --apply-compose # recreate to apply compose changes (mounts, etc.)
#     sudo bash /volume1/tts/deploy.sh --rebuild       # full image rebuild (deps/Dockerfile changed)
#
# Both containers run their code from a bind-mounted host dir, so a normal code
# deploy NEVER stops a container (no Synology "container stopped" alerts):
#   • control plane runs uvicorn --reload → synced .py hot-reloads in place;
#     static/index.html is served live from disk (no reload needed).
#   • the tv-agent reloads via SIGHUP (re-exec) — unless a recording is running,
#     which is never interrupted.
#
# Files are synced to the NAS from the Mac beforehand; this script only APPLIES
# what is already on disk.
#
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:$PATH

CONTROL_DIR=/volume1/tts/control
TV_APP=/volume1/tv/app
TV_CONTAINER=tv-archiver
API=http://localhost:8080

REPLAN=0
APPLY_COMPOSE=0
REBUILD=0
for a in "${@:-}"; do
  case "$a" in
    "")               ;;
    --replan)         REPLAN=1 ;;
    --apply-compose)  APPLY_COMPOSE=1 ;;
    --rebuild)        REBUILD=1 ;;
    *) echo "unknown flag: $a  (use --replan, --apply-compose, --rebuild)"; exit 2 ;;
  esac
done

log(){ printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

retry(){  # retry <cmd...> — Docker Hub throws transient 502s
  local ok=0 i
  for i in 1 2 3; do
    if "$@"; then ok=1; break; fi
    echo "  attempt $i failed, retrying in 5s…"; sleep 5
  done
  [ "$ok" = 1 ]
}

running_recordings(){
  curl -s "$API/api/tv/status" 2>/dev/null | python3 -c \
    "import sys,json;print(sum(1 for j in json.load(sys.stdin).get('jobs',[]) if j['status']=='running'))" \
    2>/dev/null || echo 0
}

if [ "$REBUILD" = 1 ]; then
  # Deps/Dockerfile changed → rebuild images (recreates containers, one-time alert).
  log "Rebuilding control-plane image…"
  cd "$CONTROL_DIR"; retry docker compose up -d --build || { echo "control rebuild FAILED"; exit 1; }
  log "Rebuilding tv-archiver image…"
  cd "$TV_APP"; retry docker compose -f docker-compose.nas.yml up -d --build || { echo "tv rebuild FAILED"; exit 1; }
elif [ "$APPLY_COMPOSE" = 1 ]; then
  # Compose changed (mounts/command/init) → recreate from existing images (no build,
  # fast). One-time; needed to switch a container onto the bind-mount + reload model.
  log "Applying compose changes: recreating containers (existing images)…"
  cd "$CONTROL_DIR"; retry docker compose up -d || { echo "control recreate FAILED"; exit 1; }
  cd "$TV_APP"; retry docker compose -f docker-compose.nas.yml up -d || { echo "tv recreate FAILED"; exit 1; }
else
  # Steady state: apply synced code WITHOUT restarting anything.
  log "Applying code — control plane (uvicorn --reload, no restart)…"
  echo "  control code is bind-mounted; synced .py hot-reloads, index.html serves live. Nothing to restart."

  log "Applying code — tv-agent (SIGHUP reload, no restart)…"
  rec=$(running_recordings)
  if [ "${rec:-0}" -gt 0 ]; then
    echo "  ⚠ $rec recording(s) in progress — deferring agent reload (won't interrupt it)."
    echo "    Re-run this after it finishes to pick up agent/recorder changes."
  else
    docker kill -s HUP "$TV_CONTAINER" >/dev/null && echo "  agent reloaded in place (re-exec)"
  fi
fi

if [ "$REPLAN" = 1 ]; then
  log "Rebuilding the schedule with current rules…"
  ids=$(curl -s "$API/api/tv/status" | python3 -c \
    "import sys,json;print(' '.join(str(j['id']) for j in json.load(sys.stdin).get('jobs',[]) if j['status']=='queued'))")
  for id in $ids; do curl -s -X DELETE "$API/api/tv/recordings/$id" >/dev/null; done
  echo "  cancelled queued jobs: ${ids:-none}  (manually-added picks may need re-adding from Программа)"
  echo "  scraping EPG + enqueuing (Playwright ~20s)…"
  docker exec "$TV_CONTAINER" python plan_control.py
fi

log "Done."
docker ps --format '  {{.Names}}  {{.Status}}' | grep -E "tts-control|tv-archiver" || true
