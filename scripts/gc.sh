#!/usr/bin/env bash
# Usage:
#   ./scripts/gc.sh [--older-than <N>d|<N>h] [--only-done] [--dry-run] [-y]
#
# List remote experiments older than the cutoff and offer to clean them via
# clean.sh (removes the conda env AND /mnt/d/runs/<exp-id>/). --dry-run just
# reports what would be deleted. --only-done skips running/failed so you
# never nuke an exp you're still debugging.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

OLDER_THAN="30d"
ONLY_DONE=0
DRY_RUN=0
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --older-than) OLDER_THAN="${2:?--older-than needs a value like 30d or 12h}"; shift 2 ;;
    --only-done)  ONLY_DONE=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    -y|--yes)     YES=1; shift ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

# Parse threshold → seconds.
NUM="${OLDER_THAN%[dhm]}"
UNIT="${OLDER_THAN: -1}"
case "$UNIT" in
  d) CUTOFF_SEC=$(( NUM * 86400 )) ;;
  h) CUTOFF_SEC=$(( NUM * 3600 ))  ;;
  m) CUTOFF_SEC=$(( NUM * 60 ))    ;;
  *) echo "bad --older-than '$OLDER_THAN' (use Nd/Nh/Nm)" >&2; exit 2 ;;
esac
NOW_EPOCH=$(date +%s)

echo "[gc] scanning $REMOTE_RUNS_DIR for runs older than $OLDER_THAN ..."

# Ask remote for exp-id + state; we parse timestamp from the exp-id itself.
MAPFILE=$(rsh bash -s <<REMOTE
cd "$REMOTE_RUNS_DIR" 2>/dev/null || exit 0
for d in */; do
  exp="\${d%/}"
  state=\$([ -f "\$exp/status" ] && cat "\$exp/status" || echo unknown)
  printf '%s\t%s\n' "\$exp" "\$state"
done
REMOTE
)

TO_DELETE=()
while IFS=$'\t' read -r exp state; do
  [ -z "$exp" ] && continue
  [ "$ONLY_DONE" -eq 1 ] && [ "$state" != "done" ] && continue
  # exp-id format: YYYYMMDD-HHMMSS-<name>
  ts="${exp%%-*}-${exp#*-}"; ts="${ts%%-*}"    # YYYYMMDD
  hms="${exp#*-}"; hms="${hms%%-*}"            # HHMMSS
  # macOS date doesn't accept -d "YYYYMMDD HHMMSS"; use formatted -j -f
  if epoch=$(date -j -f "%Y%m%d%H%M%S" "$ts$hms" +%s 2>/dev/null); then
    :
  else
    # GNU date fallback (works inside Linux tools too)
    epoch=$(date -d "${ts:0:4}-${ts:4:2}-${ts:6:2} ${hms:0:2}:${hms:2:2}:${hms:4:2}" +%s 2>/dev/null || echo 0)
  fi
  age=$(( NOW_EPOCH - epoch ))
  if [ "$age" -gt "$CUTOFF_SEC" ]; then
    days=$(( age / 86400 ))
    printf '  %-50s %-10s  %d days old\n' "$exp" "$state" "$days"
    TO_DELETE+=("$exp")
  fi
done <<<"$MAPFILE"

if [ ${#TO_DELETE[@]} -eq 0 ]; then
  echo "[gc] nothing to clean."
  exit 0
fi

echo
echo "[gc] ${#TO_DELETE[@]} experiment(s) match."
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[gc] --dry-run: no changes made."
  exit 0
fi

if [ "$YES" -ne 1 ]; then
  printf '[gc] delete all listed above? [y/N] '
  read -r ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "[gc] aborted"; exit 0; }
fi

for exp in "${TO_DELETE[@]}"; do
  "$(dirname "$0")/clean.sh" -y "$exp" || echo "[gc] failed to clean $exp (continuing)"
done
echo "[gc] done."
