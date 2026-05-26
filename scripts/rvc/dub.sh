#!/usr/bin/env bash
# Batch-dub a folder of source recordings into the 5 cartoon character voices.
#
# Each clip's CHARACTER is inferred from its parent folder name (Crimean Tatar
# role words, case-insensitive substring):
#   oca       -> teacher  (Учительница)  model=teacher            pitch +12
#   qartbaba  -> grandpa  (Дедушка)      model=narrator (v1)      pitch  -4
#   qiz       -> girl     (Девочка)      model=teacher  + formant pitch +17
#   oglan     -> boy      (Мальчик)      model=narrator_v2 +formant pitch +10
#   (anything else, incl. bare "1"/muelif) -> narrator (Автор) model=narrator_v2 pitch -1
#
# Pipeline: rsync source tree -> Win, run all RVC inference there in ONE pass
# (3 models cover 5 roles), rsync the dubbed tree back to the Mac mirroring
# the input layout.
#
# Usage:
#   ./scripts/rvc/dub.sh <local_source_dir> [local_output_dir]
#   default output: models/<basename>_dubbed/
set -euo pipefail
source "$(cd "$(dirname "$0")/../.." && pwd)/config.sh"

# Optional --role <narrator|teacher|grandpa|girl|boy> forces every clip to that
# character, overriding folder-name auto-detection (use when a subfolder name
# doesn't carry the role, e.g. a nested "1/").
ROLE_OVERRIDE=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE_OVERRIDE="$2"; shift 2 ;;
    *)      ARGS+=("$1"); shift ;;
  esac
done
set -- "${ARGS[@]}"

SRC="${1:?usage: dub.sh [--role NAME] <local_source_dir> [output_dir]}"
[ -d "$SRC" ] || { echo "no such dir: $SRC" >&2; exit 1; }
SRC="$(cd "$SRC" && pwd)"
OUT="${2:-$ROOT_DIR/models/$(basename "$SRC")_dubbed}"
mkdir -p "$OUT"
[ -n "$ROLE_OVERRIDE" ] && echo "[dub] role override: all clips -> $ROLE_OVERRIDE"

APPLIO="/home/$WIN_USER/applio"
R_IN="/home/$WIN_USER/_dub_in"
R_OUT="/home/$WIN_USER/_dub_out"

# Resumable: keep $R_OUT across runs so already-dubbed files are skipped.
# Re-run this script to fill any gaps left by transient infer/SSH failures.
echo "[dub] uploading source tree -> $SSH_TARGET:$R_IN"
rsh "mkdir -p '$R_IN' '$R_OUT'"
rsync_push --exclude '.DS_Store' "$SRC/" "$SSH_TARGET:$R_IN/"
# Seed remote output with whatever we already dubbed locally, so a re-run
# skips done files instead of redoing them.
if [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "[dub] seeding remote with already-dubbed files from $OUT"
  rsync_push --exclude '.DS_Store' --exclude '_*.log' "$OUT/" "$SSH_TARGET:$R_OUT/"
fi

# Remote batch: classify each file by parent dir, run inference with that
# character's accepted recipe. Recipes are resolved against the 3 trained
# models in $APPLIO/logs/.
rsh bash -s <<REMOTE
set -uo pipefail
source /home/$WIN_USER/miniconda3/etc/profile.d/conda.sh
conda activate $BASE_CONDA_ENV
cd "$APPLIO"

# Resolve checkpoint paths once.
PTH_NARR_V2=\$(ls logs/narrator_v2_oralhan/*_best_epoch.pth 2>/dev/null | head -1)
IDX_NARR_V2="logs/narrator_v2_oralhan/narrator_v2_oralhan.index"
PTH_NARR_V1=\$(ls logs/narrator/*_best_epoch.pth 2>/dev/null | head -1)
IDX_NARR_V1="logs/narrator/narrator.index"
PTH_TEACHER=\$(ls logs/teacher/teacher_100e_*s*.pth 2>/dev/null | grep -v best_epoch | head -1)
IDX_TEACHER="logs/teacher/teacher.index"

for v in "\$PTH_NARR_V2" "\$PTH_NARR_V1" "\$PTH_TEACHER"; do
  [ -n "\$v" ] && [ -f "\$v" ] || { echo "[remote] ERROR: missing checkpoint (\$v)"; exit 1; }
done
echo "[remote] narrator_v2=\$PTH_NARR_V2"
echo "[remote] narrator_v1=\$PTH_NARR_V1"
echo "[remote] teacher    =\$PTH_TEACHER"

# recipe(): given a lowercased parent-folder name, echo:
#   pth|index|pitch|index_rate|protect|formant|role
# Matches both an explicit role name (override) and a folder-name substring.
recipe() {
  case "\$1" in
    grandpa|*qartbaba*) echo "\$PTH_NARR_V1|\$IDX_NARR_V1|-4|0.4|0.4|0|grandpa" ;;
    teacher|*oca*)      echo "\$PTH_TEACHER|\$IDX_TEACHER|12|0.5|0.4|0|teacher" ;;
    girl|*qiz*)         echo "\$PTH_TEACHER|\$IDX_TEACHER|17|0.5|0.4|1.4|girl" ;;
    boy|*oglan*)        echo "\$PTH_NARR_V2|\$IDX_NARR_V2|10|0.5|0.4|1.2|boy" ;;
    *)                  echo "\$PTH_NARR_V2|\$IDX_NARR_V2|-1|0.5|0.4|0|narrator" ;;
  esac
}
ROLE_OVERRIDE="$ROLE_OVERRIDE"

n=0; fail=0; skip=0
rm -f "$R_OUT/_failures.log" "$R_OUT/_infer.log"
while IFS= read -r -d '' f; do
  # f is absolute (from find over an absolute root). realpath gives a clean
  # relative path regardless of slash quirks — avoids the prefix-strip bug.
  rel=\$(realpath --relative-to="$R_IN" "\$f")
  parent=\$(basename "\$(dirname "\$f")" | tr '[:upper:]' '[:lower:]')
  key="\${ROLE_OVERRIDE:-\$parent}"
  IFS='|' read -r pth idx pitch ir prot fmt role <<< "\$(recipe "\$key")"

  out="$R_OUT/\$rel"
  mkdir -p "\$(dirname "\$out")"

  # Resume: skip files already dubbed (non-empty output).
  if [ -s "\$out" ]; then skip=\$((skip+1)); continue; fi

  # Normalize source to 40k mono wav first (robust against odd encodings).
  tmp=\$(mktemp --suffix=.wav)
  ffmpeg -hide_banner -loglevel error -y -i "\$f" -ac 1 -ar 40000 "\$tmp" || { echo "[skip bad] \$rel"; rm -f "\$tmp"; echo "ffmpeg: \$rel" >>"$R_OUT/_failures.log"; fail=\$((fail+1)); continue; }

  if [ "\$fmt" = "0" ]; then FORMANT_ARGS="--formant_shifting False"
  else FORMANT_ARGS="--formant_shifting True --formant_qfrency \$fmt --formant_timbre \$fmt"; fi

  echo "[\$role] \$rel  (pitch \$pitch, fmt \$fmt)"
  # Retry once on transient failure (intermittent CUDA/load errors).
  ok=0
  for attempt in 1 2; do
    if python core.py infer \
        --pth_path "\$pth" --index_path "\$idx" \
        --input_path "\$tmp" --output_path "\$out" \
        --pitch "\$pitch" --index_rate "\$ir" --protect "\$prot" \
        --f0_method rmvpe --embedder_model contentvec --volume_envelope 0.25 \
        \$FORMANT_ARGS >>"$R_OUT/_infer.log" 2>&1 && [ -s "\$out" ]; then
      ok=1; break
    fi
    sleep 1
  done
  rm -f "\$tmp"
  if [ "\$ok" = "1" ]; then n=\$((n+1)); else echo "infer: \$rel" >>"$R_OUT/_failures.log"; fail=\$((fail+1)); rm -f "\$out"; fi
done < <(find "$R_IN" -type f \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' \) -print0)

echo "[remote] dubbed \$n new file(s), skipped \$skip already-done, \$fail failure(s)"
[ -f "$R_OUT/_failures.log" ] && { echo "[remote] failures:"; cat "$R_OUT/_failures.log"; }
REMOTE
# A flaky SSH teardown can return non-zero even after the batch ran; don't let
# that abort the script before we pull results.
true

echo "[dub] pulling dubbed tree -> $OUT"
# Pull only the leaf files for THIS run's roles; strip the remote-abs mirror if
# byte-corruption created one. --prune-empty-dirs keeps the tree clean.
rsync_pull --prune-empty-dirs "$SSH_TARGET:$R_OUT/" "$OUT/"
# Keep $R_OUT on the remote for resume; only drop the uploaded sources.
rsh "rm -rf '$R_IN'" || true

echo ""
echo "[dub] done. Dubbed audio mirrors the input layout under:"
echo "  $OUT"
echo "[dub] open '$OUT'"
