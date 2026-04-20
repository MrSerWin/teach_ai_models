#!/usr/bin/env bash
# Usage: _notify.sh <title> <message> [priority]
# Sends notifications via any configured channel. Never fails the caller.
#   - macOS: native notification if NOTIFY_MACOS=1 (default on Darwin)
#   - ntfy.sh: HTTP POST if NTFY_TOPIC is set (works to phone, desktop, etc.)
set +e

TITLE="${1:-teach_ai_models}"
MSG="${2:-done}"
PRIO="${3:-default}"      # default|low|high|urgent — ntfy uses these

# macOS notification
if [ "${NOTIFY_MACOS:-$([ "$(uname)" = Darwin ] && echo 1 || echo 0)}" = "1" ] && command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"${MSG//\"/\\\"}\" with title \"${TITLE//\"/\\\"}\"" >/dev/null 2>&1 || true
fi

# ntfy.sh (https://ntfy.sh/docs/publish/)
if [ -n "${NTFY_TOPIC:-}" ] && command -v curl >/dev/null 2>&1; then
  SERVER="${NTFY_SERVER:-https://ntfy.sh}"
  curl -fsS -X POST \
    -H "Title: $TITLE" \
    -H "Priority: $PRIO" \
    -d "$MSG" \
    "$SERVER/$NTFY_TOPIC" >/dev/null 2>&1 || true
fi

exit 0
