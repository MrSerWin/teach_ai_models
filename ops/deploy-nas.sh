#!/usr/bin/env bash
#
# Deploy the QO control plane + tv-archiver on the Synology NAS.
#
# Run this ON the NAS (the Docker socket is root-only, so sudo is required):
#
#     sudo bash /volume1/tts/deploy.sh              # apply code changes (fast)
#     sudo bash /volume1/tts/deploy.sh --replan     # + rebuild the recording schedule
#     sudo bash /volume1/tts/deploy.sh --rebuild-tv # + full tv-archiver image rebuild
#
# Files are synced to the NAS from the Mac beforehand; this script only APPLIES
# what is already on disk:
#   1. rebuilds the control-plane container  (app.py + static UI)
#   2. pushes updated tv-archiver python into its running container (no slow
#      Playwright reinstall), and restarts the agent — UNLESS a recording is in
#      progress, in which case it never interrupts it.
#   3. with --replan: cancels queued recordings and re-runs the planner so the
#      whole schedule is rebuilt with the CURRENT rules (film windows, titles…).
#
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:$PATH

CONTROL_DIR=/volume1/tts/control
TV_APP=/volume1/tv/app
TV_CONTAINER=tv-archiver
API=http://localhost:8080

REPLAN=0
REBUILD_TV=0
for a in "${@:-}"; do
  case "$a" in
    "")            ;;
    --replan)      REPLAN=1 ;;
    --rebuild-tv)  REBUILD_TV=1 ;;
    *) echo "unknown flag: $a  (use --replan and/or --rebuild-tv)"; exit 2 ;;
  esac
done

log(){ printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

retry_build(){  # retry_build <compose-args...> — Docker Hub throws transient 502s
  local ok=0 i
  for i in 1 2 3; do
    if docker compose "$@" up -d --build; then ok=1; break; fi
    echo "  build attempt $i failed, retrying in 5s…"; sleep 5
  done
  [ "$ok" = 1 ]
}

running_recordings(){
  curl -s "$API/api/tv/status" 2>/dev/null | python3 -c \
    "import sys,json;print(sum(1 for j in json.load(sys.stdin).get('jobs',[]) if j['status']=='running'))" \
    2>/dev/null || echo 0
}

# ---------------------------------------------------------------- 1. control plane
log "Rebuilding control plane (app.py + UI)…"
cd "$CONTROL_DIR"
retry_build || { echo "control-plane rebuild FAILED — aborting."; exit 1; }

# ---------------------------------------------------------------- 2. tv-archiver
if [ "$REBUILD_TV" = 1 ]; then
  log "Full tv-archiver image rebuild (deps/Dockerfile changed)…"
  cd "$TV_APP"
  retry_build -f docker-compose.nas.yml || { echo "tv-archiver rebuild FAILED."; exit 1; }
else
  log "Updating tv-archiver code in the running container (no rebuild)…"
  n=0
  for f in "$TV_APP"/*.py; do
    docker cp "$f" "$TV_CONTAINER:/app/$(basename "$f")"; n=$((n+1))
  done
  echo "  copied $n python files"
  rec=$(running_recordings)
  if [ "${rec:-0}" -gt 0 ]; then
    echo "  ⚠ $rec recording(s) in progress — NOT restarting the agent (would abort them)."
    echo "    Planner/classifier changes are already live (run per exec)."
    echo "    Agent/recorder changes will apply after the recording finishes, or re-run this later."
  else
    docker restart "$TV_CONTAINER" >/dev/null
    echo "  agent restarted — recorder/agent changes are live"
  fi
fi

# ---------------------------------------------------------------- 3. re-plan
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
