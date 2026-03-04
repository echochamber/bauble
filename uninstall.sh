#!/usr/bin/env bash
set -euo pipefail

# uninstall.sh — Remove bauble hook script and print cleanup guidance.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

TARGET="$HOME/.claude/hooks/pane-tint.sh"

echo ""
echo -e "${BOLD}=== Bauble Uninstall ===${RESET}"
echo ""

if [[ -L "$TARGET" ]]; then
  rm "$TARGET"
  echo -e "  ${GREEN}Removed${RESET} symlink: $TARGET"
elif [[ -e "$TARGET" ]]; then
  echo -e "  ${YELLOW}Warning:${RESET} $TARGET exists but is not a symlink (not managed by bauble)"
  echo -e "  Remove manually if desired: rm $TARGET"
else
  echo -e "  ${YELLOW}Nothing to remove${RESET} — $TARGET does not exist"
fi

echo ""
echo -e "${BOLD}Manual cleanup:${RESET}"
echo -e "  Remove bauble hook entries from ~/.claude/settings.json:"
echo -e "    - UserPromptSubmit: the pane-tint reset entry"
echo -e "    - PreToolUse: the FIRST entry (no matcher, pane-tint reset)"
echo -e "      Do NOT remove cullis/evidens entries that follow it"
echo -e "    - PostToolUse: the pane-tint reset entry"
echo -e "    - Stop: the window-status-style + pane-tint + afplay Hero entries"
echo -e "      Do NOT remove drain-queue or turn-counter entries"
echo -e "    - PermissionRequest: the window-status-style + pane-tint + afplay Glass entries"
echo -e "      Do NOT remove log-permission-request or tool-timing entries"
echo ""
echo -e "  Remove the bauble source-file line from ~/.tmux.conf:"
echo -e "    ${RED}source-file .../bauble/tmux/bauble.tmux.conf${RESET}"
echo ""
