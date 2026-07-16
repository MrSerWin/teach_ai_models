#!/usr/bin/env bash
# A/B one source clip through a role's recipe — ON THE MAC.
# Local twin of scripts/rvc/infer.sh. Use it to audition a recipe (pitch/formant/
# index-rate) on a single take before committing a whole folder to dub-local.sh.
#
# Usage:
#   ./scripts/rvc/infer-local.sh <role> <audio> [options]
#     role: narrator | boy | teacher | girl | grandpa
#
# Options (default = the role's accepted recipe):
#   --pitch N            semitone shift
#   --index-rate N       0.3-0.5 natural, 0.6-0.75 stronger timbre
#   --protect N          consonant protection
#   --formant N          0 = off; >1.0 raises formants (male->child/female)
#   --f0 rmvpe|crepe|fcpe
#   --tag NAME           suffix for the output filename
#
# Output: models/<role>_tests_local/<tag>_p<pitch>_ir<ir>_fmt<formant>.wav
set -uo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib-local.sh"

ROLE="${1:?usage: infer-local.sh <narrator|boy|teacher|girl|grandpa> <audio> [options]}"; shift
SRC="${1:?need a source audio file}"; shift
[ -f "$SRC" ] || { echo "no such file: $SRC" >&2; exit 1; }

IFS='|' read -r PTH IDX PITCH IR PROT FMT ROLE_R <<< "$(recipe "$ROLE")"
F0=rmvpe
TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pitch)      PITCH="$2"; shift 2 ;;
    --index-rate) IR="$2";    shift 2 ;;
    --protect)    PROT="$2";  shift 2 ;;
    --formant)    FMT="$2";   shift 2 ;;
    --f0)         F0="$2";    shift 2 ;;
    --tag)        TAG="$2";   shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

OUT_DIR="$MODELS_DIR/${ROLE_R}_tests_local"
OUT="$OUT_DIR/${TAG:+${TAG}_}p${PITCH}_ir${IR}_fmt${FMT}.wav"

TMP="$(mktemp -t inferlocal).wav"
trap 'rm -f "$TMP"' EXIT
to_wav40k "$SRC" "$TMP" || { echo "ffmpeg failed on $SRC" >&2; exit 1; }

echo "[infer] role=$ROLE_R model=$(basename "$PTH")"
echo "[infer] pitch=$PITCH index_rate=$IR protect=$PROT formant=$FMT f0=$F0"
if rvc_infer "$PTH" "$IDX" "$TMP" "$OUT" "$PITCH" "$IR" "$PROT" "$FMT" "$F0"; then
  echo "[infer] -> $OUT"
else
  echo "[infer] FAILED" >&2; exit 1
fi
