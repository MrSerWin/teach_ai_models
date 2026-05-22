#!/usr/bin/env bash
# A/B-test RVC checkpoints (ТЗ §5.4): run one source clip through several
# epochs of a trained model and pull all results back to Mac for listening.
#
# Usage:
#   ./scripts/rvc/infer.sh <model_name> <local_test_audio> [options]
#
# Options (with defaults):
#   --epochs "200 250 280 best"   which checkpoints to try. Numbers match the
#                                 epoch in <model>_<N>e_*.pth; "best" picks the
#                                 *_best_epoch.pth. Default: all <name>_*e_*s*.pth.
#   --pitch -1                    semitone shift (ТЗ §2 per character)
#   --index-rate 0.5              0.3-0.5 = more natural, 0.6-0.75 = stronger timbre
#   --protect 0.33                consonant protection
#   --volume-envelope 0.25        RMS mix
#   --f0 rmvpe                    rmvpe | crepe | crepe-tiny | fcpe
#   --embedder contentvec        MUST match training
#   --formant 0                   formant shift for cross-gender. 0 = off.
#                                 >1.0 raises formants (male->female/child),
#                                 e.g. 1.2-1.5. <1.0 lowers (female->male).
#                                 Pair with a big --pitch (male->female ~ +12).
#
# Output: models/<model_name>_tests/<epoch>_ir<index_rate>_p<pitch>.wav  (on Mac)
# Open them in Finder and compare by ear.
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

MODEL="${1:?usage: infer.sh <model_name> <local_test_audio> [options]}"; shift
SRC_LOCAL="${1:?need a local test audio file}"; shift
[ -f "$SRC_LOCAL" ] || { echo "no such file: $SRC_LOCAL" >&2; exit 1; }

EPOCHS=""          # empty = autodiscover all weights
PITCH=-1
INDEX_RATE=0.5
PROTECT=0.33
VOL_ENV=0.25
F0=rmvpe
EMBEDDER=contentvec
FORMANT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --epochs)          EPOCHS="$2"; shift 2 ;;
    --pitch)           PITCH="$2"; shift 2 ;;
    --index-rate)      INDEX_RATE="$2"; shift 2 ;;
    --protect)         PROTECT="$2"; shift 2 ;;
    --volume-envelope) VOL_ENV="$2"; shift 2 ;;
    --f0)              F0="$2"; shift 2 ;;
    --embedder)        EMBEDDER="$2"; shift 2 ;;
    --formant)         FORMANT="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Build formant args once. RVC: --formant_shifting True + qfrency/timbre > 1.0
# raises formants (male->female). Off by default.
FORMANT_ARGS="--formant_shifting False"
if [ "$FORMANT" != "0" ]; then
  FORMANT_ARGS="--formant_shifting True --formant_qfrency $FORMANT --formant_timbre $FORMANT"
fi

APPLIO_DIR="/home/$WIN_USER/applio"
LOGS="$APPLIO_DIR/logs/$MODEL"
REMOTE_SRC="/home/$WIN_USER/_abtest_input.wav"
OUT_DIR="$ROOT_DIR/models/${MODEL}_tests"
mkdir -p "$OUT_DIR"

# 1. Convert source to clean 40k mono wav locally, then upload (avoids the
# MP4-renamed-as-wav trap and sample-rate surprises).
TMP_SRC="$(mktemp -t abtest).wav"
trap 'rm -f "$TMP_SRC"' EXIT
ffmpeg -hide_banner -loglevel error -y -i "$SRC_LOCAL" -ac 1 -ar 40000 "$TMP_SRC"
echo "[infer] uploading source -> $SSH_TARGET:$REMOTE_SRC"
rsync_push "$TMP_SRC" "$SSH_TARGET:$REMOTE_SRC"

# 2. Resolve which checkpoint files to run.
if [ -z "$EPOCHS" ]; then
  echo "[infer] autodiscovering all weights for '$MODEL'"
  mapfile -t PTHS < <(rsh "ls $LOGS/${MODEL}_*e_*s*.pth 2>/dev/null")
else
  PTHS=()
  for e in $EPOCHS; do
    if [ "$e" = "best" ]; then
      f=$(rsh "ls $LOGS/${MODEL}_*_best_epoch.pth 2>/dev/null | head -1")
    else
      f=$(rsh "ls $LOGS/${MODEL}_${e}e_*s*.pth 2>/dev/null | grep -v best_epoch | head -1")
    fi
    [ -n "$f" ] && PTHS+=("$f") || echo "[infer] WARN: no checkpoint for epoch '$e'"
  done
fi
[ "${#PTHS[@]}" -gt 0 ] || { echo "[infer] no checkpoints found in $LOGS" >&2; exit 1; }

INDEX="$LOGS/$MODEL.index"

# 3. Run inference per checkpoint, pull each result back.
for pth in "${PTHS[@]}"; do
  base=$(basename "$pth" .pth)
  tag=$(echo "$base" | sed -E "s/^${MODEL}_//; s/_[0-9]+s.*//")   # e.g. 280e
  echo "$base" | grep -q best_epoch && tag="${tag}_best"
  remote_out="/home/$WIN_USER/_abtest_${tag}.wav"
  local_out="$OUT_DIR/${tag}_ir${INDEX_RATE}_p${PITCH}_fmt${FORMANT}.wav"
  echo "[infer] === $tag ==="
  rsh bash -s <<REMOTE
set -e
source /home/$WIN_USER/miniconda3/etc/profile.d/conda.sh
conda activate $BASE_CONDA_ENV
cd $APPLIO_DIR
python core.py infer \
  --pth_path "$pth" \
  --index_path "$INDEX" \
  --input_path "$REMOTE_SRC" \
  --output_path "$remote_out" \
  --pitch $PITCH --index_rate $INDEX_RATE --protect $PROTECT \
  --f0_method $F0 --embedder_model $EMBEDDER --volume_envelope $VOL_ENV \
  $FORMANT_ARGS
REMOTE
  rsync_pull "$SSH_TARGET:$remote_out" "$local_out"
  rsh "rm -f '$remote_out'" || true
  echo "[infer] -> $local_out"
done

rsh "rm -f '$REMOTE_SRC'" || true
echo ""
echo "[infer] done. Compare:"
echo "  open '$OUT_DIR'"
