#!/usr/bin/env bash
# ONE COMMAND: prompt -> video -> voice + SFX + music -> mixed video_av.mp4.
# Run FROM the Mac. Every stage runs on the GPU box in its own conda env; the
# final ffmpeg mix layers the tracks (voice loud, SFX mid, music quiet) and
# muxes onto the clip. Result is pulled back to out/<slug>_<ts>/.
#
# Each audio track runs only if its text is given. A track whose backend isn't
# deployed yet is skipped with a warning (so "all in one" never hard-fails).
#
#   ./produce.sh --backend ltx --frames 257 --slug ester_static \
#     --video "<english video prompt>" \
#     --voice "<english narration>" \
#     --sfx   "<english sound description>" \
#     --music "<english music description>"
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

VIDEO_ENV="${VIDEO_ENV:-wan_video}"
VOICE_ENV="${VOICE_ENV:-voice_assistant}"
SFX_ENV="${SFX_ENV:-mmaudio}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"
FPS=24

BACKEND="wan"; SLUG=""; FRAMES=""; STEPS=""
VIDEO=""; VOICE=""; SFX=""; MUSIC=""; REF_WAV=""; SPEAKER="Claribel Dervla"
while [ $# -gt 0 ]; do
  case "$1" in
    --backend) BACKEND="${2:?}"; shift 2 ;;
    --slug)    SLUG="${2:?}"; shift 2 ;;
    --frames)  FRAMES="${2:?}"; shift 2 ;;
    --steps)   STEPS="${2:?}"; shift 2 ;;
    --video)   VIDEO="${2:?}"; shift 2 ;;
    --voice)   VOICE="${2:?}"; shift 2 ;;
    --sfx)     SFX="${2:?}"; shift 2 ;;
    --music)   MUSIC="${2:?}"; shift 2 ;;
    --ref)     REF_WAV="${2:?}"; shift 2 ;;
    --speaker) SPEAKER="${2:?}"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
[ -n "$VIDEO" ] || { echo "error: --video <prompt> is required" >&2; exit 2; }

DIST=""
case "$BACKEND" in
  wan)  SCRIPT="generate.py";     MODEL="/mnt/d/models/Wan2.2-TI2V-5B";             DEF_FRAMES=121 ;;
  ltx)  SCRIPT="generate_ltx.py"; MODEL="/mnt/d/models/LTX-Video";                 DEF_FRAMES=161 ;;
  ltxd) SCRIPT="generate_ltx.py"; MODEL="/mnt/d/models/LTX-Video-0.9.7-distilled"; DEF_FRAMES=161; DIST="--distilled" ;;
  *)    echo "unknown backend: $BACKEND (wan|ltx|ltxd)" >&2; exit 2 ;;
esac
EXTRA="$DIST"; [ -n "$FRAMES" ] && EXTRA="$EXTRA --frames $FRAMES"; [ -n "$STEPS" ] && EXTRA="$EXTRA --steps $STEPS"
# Audio duration target = clip length, so tracks match the video.
EFF_FRAMES="${FRAMES:-$DEF_FRAMES}"
DURATION="$(awk "BEGIN{printf \"%.1f\", $EFF_FRAMES/$FPS}")"

[ -z "$SLUG" ] && SLUG="$(echo "$VIDEO" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | tr -s '_' | sed 's/^_//;s/_$//' | cut -c1-60)"
NAME="${SLUG}_$(date +%s)"
REMOTE_DIR="$REMOTE_APP_DIR/out/$NAME"

REMOTE_REF=""
if [ -n "$REF_WAV" ]; then
  [ -f "$REF_WAV" ] || { echo "error: --ref not found: $REF_WAV" >&2; exit 2; }
  rsh "mkdir -p '$REMOTE_DIR'"; REMOTE_REF="$REMOTE_DIR/ref.wav"
  rsync_push "$REF_WAV" "$SSH_TARGET:$REMOTE_REF"
fi

echo "==> producing '$NAME' [$BACKEND ${DURATION}s]  voice=$([ -n "$VOICE" ] && echo y || echo n) sfx=$([ -n "$SFX" ] && echo y || echo n) music=$([ -n "$MUSIC" ] && echo y || echo n)"

rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"
DIR="$REMOTE_DIR"; mkdir -p "\$DIR"
env_exists() { conda env list | awk '{print \$1}' | grep -qx "\$1"; }

echo "--- video ---"
conda activate "$VIDEO_ENV"
python "$REMOTE_APP_DIR/$SCRIPT" --prompt "$VIDEO" --model-dir "$MODEL" --out "\$DIR/video.mp4" $EXTRA

if [ -n "$VOICE" ]; then
  echo "--- voice ---"
  conda activate "$VOICE_ENV"; export COQUI_TOS_AGREED=1
  python "$REMOTE_APP_DIR/add_voice.py" --text "$VOICE" --out "\$DIR/voice.wav" \
    --speaker "$SPEAKER" ${REMOTE_REF:+--ref "$REMOTE_REF"}
fi

if [ -n "$MUSIC" ]; then
  echo "--- music ---"
  conda activate "$VIDEO_ENV"
  python "$REMOTE_APP_DIR/add_music.py" --prompt "$MUSIC" --out "\$DIR/music.wav" --duration "$DURATION"
fi

if [ -n "$SFX" ]; then
  if env_exists "$SFX_ENV" && [ -f "$REMOTE_APP_DIR/add_sfx.py" ]; then
    echo "--- sfx ---"
    conda activate "$SFX_ENV"
    python "$REMOTE_APP_DIR/add_sfx.py" --video "\$DIR/video.mp4" --prompt "$SFX" \
      --out "\$DIR/sfx.wav" --duration "$DURATION" || echo "WARN: sfx failed, continuing without it" >&2
  else
    echo "WARN: SFX backend ('$SFX_ENV') not deployed yet — skipping SFX" >&2
  fi
fi

echo "--- mix + mux ---"
declare -a AIN AVOL
[ -f "\$DIR/voice.wav" ] && AIN+=("\$DIR/voice.wav") && AVOL+=("1.0")
[ -f "\$DIR/sfx.wav" ]   && AIN+=("\$DIR/sfx.wav")   && AVOL+=("0.55")
[ -f "\$DIR/music.wav" ] && AIN+=("\$DIR/music.wav") && AVOL+=("0.22")

if [ \${#AIN[@]} -eq 0 ]; then
  cp "\$DIR/video.mp4" "\$DIR/video_av.mp4"
  echo "no audio tracks — video_av.mp4 is silent copy"
else
  args=(-y -loglevel error -i "\$DIR/video.mp4")
  fc=""; labels=""
  for i in "\${!AIN[@]}"; do
    args+=(-i "\${AIN[\$i]}"); idx=\$((i+1))
    fc+="[\${idx}:a]volume=\${AVOL[\$i]},aresample=48000[a\${idx}];"
    labels+="[a\${idx}]"
  done
  n=\${#AIN[@]}
  fc+="\${labels}amix=inputs=\${n}:duration=longest:normalize=0,apad[mix]"
  args+=(-filter_complex "\$fc" -map 0:v -map "[mix]" -c:v copy -c:a aac -b:a 192k -shortest "\$DIR/video_av.mp4")
  ffmpeg "\${args[@]}"
  echo "mixed \${n} track(s) -> video_av.mp4"
fi
SIZE=\$(du -h "\$DIR/video_av.mp4" | cut -f1)
echo "DONE: \$DIR/video_av.mp4 (\$SIZE)"
REMOTE_SCRIPT

LOCAL_OUT="$EXP_DIR/out/$NAME"
mkdir -p "$LOCAL_OUT"
echo "==> pulling final clip"
rsync_pull "$SSH_TARGET:$REMOTE_DIR/video_av.mp4" "$LOCAL_OUT/video_av.mp4"
echo "==> done: $LOCAL_OUT/video_av.mp4"
