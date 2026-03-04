#!/usr/bin/env bash
# waiting-context.sh — PermissionRequest hook: capture what tool is being approved
# Part of bauble — ambient session UX for Claude Code
#
# Reads hook stdin JSON, extracts tool_name and a short summary of tool_input.
# Stores in tmux pane option @claude-waiting-tool for display by the picker.
#
# Registered on: PermissionRequest (receives {tool_name, tool_input, ...})

PANE="${TMUX_PANE:-}"
[ -z "$PANE" ] && exit 0

INPUT=$(cat)
[ -z "$INPUT" ] && exit 0

# Extract tool_name and a short description
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
[ -z "$TOOL" ] && exit 0

# Build a compact summary: tool name + first meaningful arg
case "$TOOL" in
  Bash)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
    # First word of the command (the binary name)
    FIRST_WORD="${CMD%% *}"
    FIRST_WORD=$(basename "$FIRST_WORD" 2>/dev/null)
    if [ -n "$FIRST_WORD" ]; then
      SUMMARY="Bash: ${FIRST_WORD}"
    else
      SUMMARY="Bash"
    fi
    ;;
  Edit|Write|Read)
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    SHORT=$(basename "$FILE" 2>/dev/null)
    SUMMARY="${TOOL}: ${SHORT:-?}"
    ;;
  WebFetch)
    URL=$(echo "$INPUT" | jq -r '.tool_input.url // empty' 2>/dev/null)
    # Extract domain from URL
    DOMAIN=$(echo "$URL" | sed -E 's|https?://([^/]+).*|\1|' 2>/dev/null)
    SUMMARY="WebFetch: ${DOMAIN:-?}"
    ;;
  *)
    SUMMARY="$TOOL"
    ;;
esac

# Truncate to 40 chars for display
if [ ${#SUMMARY} -gt 40 ]; then
  SUMMARY="${SUMMARY:0:37}..."
fi

tmux set-option -p -t "$PANE" -q @claude-waiting-tool "$SUMMARY" 2>/dev/null

exit 0
