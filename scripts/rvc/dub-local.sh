#!/usr/bin/env bash
# Batch-dub a folder of source recordings into the 5 cartoon voices — ON THE MAC.
# Local twin of scripts/rvc/dub.sh (which needs the Windows GPU box over SSH).
# Same role table, same recipes; only the execution host differs.
#
# Character is inferred from each clip's PARENT FOLDER name (case-insensitive):
#   *oca*      -> teacher   model=teacher       pitch +12
#   *qartbaba* -> grandpa   model=narrator v1   pitch  -4
#   *qiz*      -> girl      model=teacher       pitch +17, formant 1.4
#   *oglan*    -> boy       model=narrator v2   pitch +10, formant 1.2
#   anything else          -> narrator          model=narrator v2   pitch -1
#
# Usage:
#   ./scripts/rvc/dub-local.sh [--role NAME] <source_dir> [output_dir]
#   default output: models/<basename>_dubbed_local/
#
# Resumable: re-running skips clips that already have a non-empty output.
set -uo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib-local.sh"

ROLE_OVERRIDE=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE_OVERRIDE="$2"; shift 2 ;;
    *)      ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]}"

SRC="${1:?usage: dub-local.sh [--role NAME] <source_dir> [output_dir]}"
[ -d "$SRC" ] || { echo "no such dir: $SRC" >&2; exit 1; }
SRC="$(cd "$SRC" && pwd)"
OUT="${2:-$MODELS_DIR/$(basename "$SRC")_dubbed_local}"
mkdir -p "$OUT"
[ -n "$ROLE_OVERRIDE" ] && echo "[dub] role override: all clips -> $ROLE_OVERRIDE"
echo "[dub] $SRC -> $OUT"

n=0; skip=0; fail=0
FAILLOG="$OUT/_failures.log"; rm -f "$FAILLOG"

while IFS= read -r -d '' f; do
  rel="${f#"$SRC"/}"
  out="$OUT/$rel"
  out="${out%.*}.wav"
  if [ -s "$out" ]; then skip=$((skip+1)); continue; fi

  parent="$(basename "$(dirname "$f")")"
  IFS='|' read -r pth idx pitch ir prot fmt role <<< "$(recipe "${ROLE_OVERRIDE:-$parent}")"

  tmp="$(mktemp -t dubsrc).wav"
  if ! to_wav40k "$f" "$tmp"; then
    echo "ffmpeg: $rel" >>"$FAILLOG"; fail=$((fail+1)); rm -f "$tmp"; continue
  fi

  printf '[%s] %s (pitch %s, fmt %s)\n' "$role" "$rel" "$pitch" "$fmt"
  if rvc_infer "$pth" "$idx" "$tmp" "$out" "$pitch" "$ir" "$prot" "$fmt"; then
    n=$((n+1))
  else
    echo "infer: $rel" >>"$FAILLOG"; fail=$((fail+1)); rm -f "$out"
  fi
  rm -f "$tmp"
done < <(find "$SRC" -type f \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' \) -print0)

echo "[dub] dubbed $n new, skipped $skip already-done, $fail failed"
[ -s "$FAILLOG" ] && { echo "[dub] failures:"; cat "$FAILLOG"; }
echo "[dub] open '$OUT'"
