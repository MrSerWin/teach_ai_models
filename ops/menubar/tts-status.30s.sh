#!/usr/bin/env bash
# SwiftBar/xbar plugin — training status in the Mac menu bar.
# Install: symlink into ~/.swiftbar-plugins/ (sits next to nas-status.30s.sh).
# <xbar.title>TTS status</xbar.title>
CONTROL="${TTS_CONTROL:-http://servin-backup:8080}"

json=$(curl -s --max-time 4 "$CONTROL/api/status" 2>/dev/null)
if [ -z "$json" ]; then
  echo "TTS ⚠️"; echo "---"; echo "Control plane unreachable"; echo "$CONTROL"; exit 0
fi

online=$(echo "$json" | /usr/bin/python3 -c 'import sys,json;print(json.load(sys.stdin)["online"])' 2>/dev/null)
read -r ep eps st sts <<<"$(echo "$json" | /usr/bin/python3 -c '
import sys, json
d = json.load(sys.stdin)
r = d.get("running") or [{}]
p = (r[0] or {}).get("progress") or {}
print(p.get("epoch",0), p.get("epochs",0), p.get("step",0), p.get("steps",0))' 2>/dev/null)"

if [ "$online" != "True" ]; then
  echo "TTS 🔴"
else
  [ "${eps:-0}" != "0" ] && echo "TTS ${ep}/${eps}" || echo "TTS 🟢"
fi
echo "---"
echo "Box: $([ "$online" = "True" ] && echo online || echo OFFLINE)"
[ "${eps:-0}" != "0" ] && echo "Epoch ${ep}/${eps} · step ${st}/${sts}"
echo "Open dashboard | href=$CONTROL"
