#!/usr/bin/env bash
# Add an audio track to an already-generated clip (run FROM the Mac).
#
#   ./experiments/05_video_gen/add_audio.sh <clip-name> --voice "English narration text"
#   ./experiments/05_video_gen/add_audio.sh <clip-name> --voice "..." --ref myvoice.wav
#
# <clip-name> is the out/<slug>_<ts> dir produced by generate.sh (it must still
# exist on the GPU box). Generates the requested audio track(s) on the box,
# mixes them onto video.mp4 with ffmpeg, writes video_av.mp4, and pulls it back.
#
# Implemented now: --voice (XTTS-v2, env voice_assistant).
# Coming next:     --sfx  (MMAudio),  --music (MusicGen).
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

VOICE_ENV="${VOICE_ENV:-voice_assistant}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/mnt/d/video_gen}"
EXP_DIR="$(cd "$(dirname "$0")" && pwd)"

VOICE_TEXT="" ; REF_WAV="" ; SFX="" ; MUSIC="" ; SPEAKER="Claribel Dervla"
NAME="${1:?usage: add_audio.sh <clip-name> --voice \"text\" [--ref voice.wav]}"; shift
while [ $# -gt 0 ]; do
  case "$1" in
    --voice)   VOICE_TEXT="${2:?--voice needs text}"; shift 2 ;;
    --ref)     REF_WAV="${2:?--ref needs a .wav}"; shift 2 ;;
    --speaker) SPEAKER="${2:?--speaker needs a name}"; shift 2 ;;
    --sfx)     SFX="${2:-}"; shift 2 ;;
    --music)   MUSIC="${2:-}"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$SFX" ] || [ -n "$MUSIC" ]; then
  echo "note: --sfx/--music backends aren't deployed yet — ignoring for now" >&2
fi
[ -n "$VOICE_TEXT" ] || { echo "error: nothing to add (pass --voice)" >&2; exit 2; }

REMOTE_DIR="$REMOTE_APP_DIR/out/$NAME"
REMOTE_VIDEO="$REMOTE_DIR/video.mp4"
REMOTE_VOICE="$REMOTE_DIR/voice.wav"
REMOTE_AV="$REMOTE_DIR/video_av.mp4"

# Push a reference voice clip if cloning is requested.
REMOTE_REF=""
if [ -n "$REF_WAV" ]; then
  [ -f "$REF_WAV" ] || { echo "error: --ref file not found: $REF_WAV" >&2; exit 2; }
  REMOTE_REF="$REMOTE_DIR/ref.wav"
  rsync_push "$REF_WAV" "$SSH_TARGET:$REMOTE_REF"
fi

echo "==> [$NAME] synthesizing voice + muxing on $SSH_TARGET"
rsh "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
source "\$HOME/miniconda3/etc/profile.d/conda.sh"
[ -f "$REMOTE_VIDEO" ] || { echo "error: $REMOTE_VIDEO not found on box (regenerate?)" >&2; exit 3; }

conda activate "$VOICE_ENV"
export COQUI_TOS_AGREED=1
python "$REMOTE_APP_DIR/add_voice.py" \
  --text "$VOICE_TEXT" \
  --out "$REMOTE_VOICE" \
  --speaker "$SPEAKER" \
  ${REMOTE_REF:+--ref "$REMOTE_REF"}

# Mux: keep full video length, pad the (usually shorter) narration with silence.
ffmpeg -y -loglevel error -i "$REMOTE_VIDEO" -i "$REMOTE_VOICE" \
  -filter_complex "[1:a]apad[a]" -map 0:v -map "[a]" \
  -c:v copy -c:a aac -b:a 192k -shortest "$REMOTE_AV"
echo "muxed -> $REMOTE_AV (\$(du -h "$REMOTE_AV" | cut -f1))"
REMOTE_SCRIPT

LOCAL_OUT="$EXP_DIR/out/$NAME"
mkdir -p "$LOCAL_OUT"
echo "==> pulling narrated clip"
rsync_pull "$SSH_TARGET:$REMOTE_AV" "$LOCAL_OUT/video_av.mp4"
echo "==> done: $LOCAL_OUT/video_av.mp4"
