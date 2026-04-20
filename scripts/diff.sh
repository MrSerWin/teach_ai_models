#!/usr/bin/env bash
# Usage: ./scripts/diff.sh <exp-id-a> <exp-id-b>
# Side-by-side diff of two experiments (both must be fetched locally).
# Shows: config.yaml diff, final metrics side-by-side, git-commit diff.
set -euo pipefail
source "$(cd "$(dirname "$0")/.." && pwd)/config.sh"

A="${1:?usage: diff.sh <exp-id-a> <exp-id-b>}"
B="${2:?usage: diff.sh <exp-id-a> <exp-id-b>}"
DA="$LOCAL_MODELS_DIR/$A"
DB="$LOCAL_MODELS_DIR/$B"

[ -d "$DA" ] || { echo "error: $DA not fetched" >&2; exit 1; }
[ -d "$DB" ] || { echo "error: $DB not fetched" >&2; exit 1; }

echo "=============================================================="
echo "  A: $A"
echo "  B: $B"
echo "=============================================================="
echo

echo "--- config.yaml diff (A vs B) ---"
if diff -u "$DA/config.yaml" "$DB/config.yaml" | sed '1,2d'; then :; fi
echo

echo "--- final metrics ---"
python3 - "$DA/metrics.json" "$DB/metrics.json" <<'PY'
import json, sys
a = json.loads(open(sys.argv[1]).read())
b = json.loads(open(sys.argv[2]).read())
keys = sorted(set(a) | set(b))
fmt = lambda v: "—" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))
pad = max(len(k) for k in keys) + 2
print(f"{'key'.ljust(pad)} {'A'.ljust(16)} {'B'.ljust(16)}  Δ")
print("-" * (pad + 40))
for k in keys:
    if k == "history":
        continue
    va, vb = a.get(k), b.get(k)
    delta = ""
    if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
        d = vb - va
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "=")
        delta = f"{arrow} {d:+.4f}"
    print(f"{k.ljust(pad)} {fmt(va).ljust(16)} {fmt(vb).ljust(16)}  {delta}")
PY
echo

echo "--- git commits ---"
for dir in "$DA" "$DB"; do
  label="${dir##*/}"
  if [ -f "$dir/git_info.json" ]; then
    python3 -c "
import json
g = json.load(open('$dir/git_info.json'))
print(f\"  {'$label'}:\", g.get('commit','—')[:12], g.get('branch',''), '(dirty)' if g.get('dirty') else '')"
  else
    echo "  $label: (no git_info.json)"
  fi
done
