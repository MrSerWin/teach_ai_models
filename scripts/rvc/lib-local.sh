#!/usr/bin/env bash
# Shared bits for the LOCAL (Mac) RVC inference scripts: infer-local.sh, dub-local.sh.
#
# Unlike scripts/rvc/{infer,dub}.sh — which ship audio to the Windows box over SSH —
# these run Applio directly on the Mac against the checkpoints already in models/.
# No .env / WIN_HOST needed, so they keep working while the training box is offline.
#
# Requirements (one-time):
#   git clone https://github.com/IAHispano/Applio.git ~/1_dev/my/ai/Applio
#   cd ~/1_dev/my/ai/Applio && uv venv --managed-python --python 3.12 .venv
#   uv pip install --python .venv/bin/python -r requirements.txt
#   .venv/bin/python core.py prerequisites --models True --exe False --pretraineds_hifigan False
# Override the location with APPLIO_DIR=/path/to/Applio.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLIO_DIR="${APPLIO_DIR:-$HOME/1_dev/my/ai/Applio}"
APPLIO_PY="$APPLIO_DIR/.venv/bin/python"
MODELS_DIR="$ROOT_DIR/models"

[ -x "$APPLIO_PY" ] || {
  echo "error: no Applio venv at $APPLIO_PY (see header of $(basename "${BASH_SOURCE[0]}"))" >&2
  exit 1
}

# Applio segfaults on macOS when its OpenMP libs are allowed to spawn a thread
# pool (torch + faiss + numba each bring their own). Pinning to one thread is
# the fix — do NOT remove. Inference is short-clip work, so the cost is small.
export OMP_NUM_THREADS=1
export KMP_DUPLICATE_LIB_OK=TRUE

# ── Checkpoint resolution ─────────────────────────────────────────────────────
# The 3 trained models cover all 5 roles via pitch/formant (see dub.sh).
# Paths are globbed so a re-fetch under a new exp-id keeps working.
pick_latest() { ls -1d $1 2>/dev/null | sort | tail -1; }

PTH_NARR_V1="$MODELS_DIR/narrator_v1_crh/narrator_300e_12000s_best_epoch.pth"
IDX_NARR_V1="$MODELS_DIR/narrator_v1_crh/narrator.index"

V2_DIR="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model" )"
PTH_NARR_V2="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model/narrator_v2_oralhan.pth")"
IDX_NARR_V2="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model/narrator_v2_oralhan.index")"
PTH_TEACHER="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model/teacher.pth")"
IDX_TEACHER="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model/teacher.index")"

# ⚠️ The accepted remote recipe (dub.sh) pins teacher to the *100-epoch* snapshot.
# fetch.sh only pulls the last 5 snapshots, so 100e is NOT on the Mac — the local
# teacher/girl voices run off the final checkpoint instead and may differ from
# the approved dub. Copy teacher_100e_*.pth into the final_model/checkpoints/ dir
# (from the Windows box) to restore parity; it is used automatically if present.
TEACHER_100E="$(pick_latest "$MODELS_DIR/*-04_rvc_voice_clone/final_model/checkpoints/teacher_100e_*s*.pth")"
if [ -n "$TEACHER_100E" ]; then
  PTH_TEACHER="$TEACHER_100E"
else
  echo "[warn] teacher_100e checkpoint not on this Mac — falling back to $(basename "$PTH_TEACHER")." >&2
  echo "[warn] teacher/girl voices may not match the approved remote dub." >&2
fi

for v in "$PTH_NARR_V1" "$PTH_NARR_V2" "$PTH_TEACHER"; do
  [ -n "$v" ] && [ -f "$v" ] || { echo "error: missing checkpoint ($v)" >&2; exit 1; }
done

# recipe <role-or-folder-name> -> pth|index|pitch|index_rate|protect|formant|role
# Same table as scripts/rvc/dub.sh — keep the two in sync.
recipe() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    grandpa|*qartbaba*) echo "$PTH_NARR_V1|$IDX_NARR_V1|-4|0.4|0.4|0|grandpa" ;;
    teacher|*oca*)      echo "$PTH_TEACHER|$IDX_TEACHER|12|0.5|0.4|0|teacher" ;;
    girl|*qiz*)         echo "$PTH_TEACHER|$IDX_TEACHER|17|0.5|0.4|1.4|girl" ;;
    boy|*oglan*)        echo "$PTH_NARR_V2|$IDX_NARR_V2|10|0.5|0.4|1.2|boy" ;;
    *)                  echo "$PTH_NARR_V2|$IDX_NARR_V2|-1|0.5|0.4|0|narrator" ;;
  esac
}

# formant_args <formant>  (0 = off)
formant_args() {
  if [ "$1" = "0" ]; then echo "--formant_shifting False"
  else echo "--formant_shifting True --formant_qfrency $1 --formant_timbre $1"; fi
}

# rvc_infer <pth> <index> <src> <out> <pitch> <index_rate> <protect> <formant> [f0] [embedder]
rvc_infer() {
  local pth="$1" idx="$2" src="$3" out="$4" pitch="$5" ir="$6" prot="$7" fmt="$8"
  local f0="${9:-rmvpe}" emb="${10:-contentvec}"
  mkdir -p "$(dirname "$out")"
  # shellcheck disable=SC2046  # formant_args must word-split
  (cd "$APPLIO_DIR" && "$APPLIO_PY" core.py infer \
      --pth_path "$pth" --index_path "$idx" \
      --input_path "$src" --output_path "$out" \
      --pitch "$pitch" --index_rate "$ir" --protect "$prot" \
      --f0_method "$f0" --embedder_model "$emb" --volume_envelope 0.25 \
      $(formant_args "$fmt")) >/dev/null 2>&1
  [ -s "$out" ]
}

# to_wav40k <src> <dst> — normalize any input to 40 kHz mono (what the models expect).
to_wav40k() { ffmpeg -hide_banner -loglevel error -y -i "$1" -ac 1 -ar 40000 "$2"; }
