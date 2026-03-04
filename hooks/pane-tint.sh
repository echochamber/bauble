#!/usr/bin/env bash
# Sets pane background color + stores per-pane state, then recomputes
# the window tab style from all panes (highest priority wins).
# Usage: pane-tint.sh <state> [bg-color]
#   state: working (default), waiting, done, cancelled
#   bg-color: optional override (hex). If omitted, reads from bauble.conf.
#
# IMPORTANT: All tmux commands explicitly target the pane/window via -t.
# Hooks run as background processes where the implicit "current" window
# is the focused window, not the pane's window. Without explicit targets,
# styles would be applied to the wrong window.

STATE="${1:-working}"
PANE="$TMUX_PANE"

# Source bauble.conf for configurable colors
# Resolve symlink to find the repo's config directory
_BAUBLE_SELF="${BASH_SOURCE[0]:-$0}"
[ -L "$_BAUBLE_SELF" ] && _BAUBLE_SELF="$(readlink "$_BAUBLE_SELF")"
_BAUBLE_CONF_DIR="$(cd "$(dirname "$_BAUBLE_SELF")/../" 2>/dev/null && pwd)"
_BAUBLE_CONF="${_BAUBLE_CONF_DIR:+$_BAUBLE_CONF_DIR/config/bauble.conf}"
[ -f "${_BAUBLE_CONF:-}" ] && source "$_BAUBLE_CONF"

# Map state → color from config (or use explicit override)
if [ -n "${2:-}" ]; then
  COLOR="$2"
else
  case "$STATE" in
    working)   COLOR="${BAUBLE_COLOR_WORKING:-#1a1e2e}" ;;
    waiting)   COLOR="${BAUBLE_COLOR_WAITING:-#302a1a}" ;;
    done)      COLOR="${BAUBLE_COLOR_DONE:-#192b1e}" ;;
    cancelled) COLOR="${BAUBLE_COLOR_DONE:-#192b1e}" ;;  # treat cancelled as done
    *)         COLOR="${BAUBLE_COLOR_WORKING:-#1a1e2e}" ;;
  esac
fi

[ -z "$PANE" ] && exit 0

# Derive the window containing this pane (needed for all window-level ops)
WINDOW=$(tmux display-message -p -t "$PANE" '#{window_id}' 2>/dev/null)
[ -z "$WINDOW" ] && exit 0

# Skip redundant updates: if the pane already has this state, exit early.
# This avoids style churn on hooks that fire repeatedly (PreToolUse,
# PostToolUse) with the same "working" state on every tool call.
PREV_STATE=$(tmux show-option -p -t "$PANE" -qv @bauble-state 2>/dev/null)
if [ "$PREV_STATE" = "$STATE" ]; then
  exit 0
fi

# Set pane background (visible regardless of focus)
tmux set-option -p -t "$PANE" -q window-style "bg=$COLOR" 2>/dev/null
tmux set-option -p -t "$PANE" -q window-active-style "bg=$COLOR" 2>/dev/null

# Store per-pane state for multi-pane awareness
tmux set-option -p -t "$PANE" -q @bauble-state "$STATE" 2>/dev/null

# Clear waiting-context when leaving the waiting state
# (waiting-context.sh sets @claude-waiting-tool on PermissionRequest)
if [ "$STATE" != "waiting" ]; then
  tmux set-option -p -t "$PANE" -qu @claude-waiting-tool 2>/dev/null
fi

# Write state to JSON file (source of truth for cancel detection)
# tmux-agent-status reads this every 5s and detects stale entries
STATE_FILE="$HOME/.claude/hooks/bauble-state.json"
SESSION=$(tmux display-message -p -t "$PANE" '#{session_name}' 2>/dev/null)
CWD=$(tmux show-option -p -t "$PANE" -qv @claude-cwd 2>/dev/null)
STATE_FILE="$STATE_FILE" PANE="$PANE" STATE="$STATE" SESSION="$SESSION" WINDOW="$WINDOW" CWD="$CWD" \
python3 -c "
import json, os, time
path = os.environ['STATE_FILE']
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    data = {}
data[os.environ['PANE']] = {
    'state': os.environ['STATE'],
    'updated_at': time.time(),
    'session': os.environ['SESSION'],
    'window_id': os.environ['WINDOW'],
    'cwd': os.environ.get('CWD', '')
}
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
os.replace(tmp, path)
" 2>/dev/null

# Name the window "claude" if it still has a default or version-string name
if [ "${BAUBLE_AUTO_RENAME:-1}" != "0" ]; then
  current_name=$(tmux display-message -p -t "$WINDOW" '#{window_name}' 2>/dev/null)
  case "$current_name" in
    zsh|bash|fish|sh|[0-9]*) tmux rename-window -t "$WINDOW" "claude" 2>/dev/null ;;
  esac
fi

# Recompute window tab style: waiting > done > working
# Scans all panes in THIS window (not the focused window)
has_waiting=0
has_done=0
for p in $(tmux list-panes -t "$WINDOW" -F '#{pane_id}' 2>/dev/null); do
  s=$(tmux show-option -p -t "$p" -qv @bauble-state 2>/dev/null)
  case "$s" in
    waiting) has_waiting=1 ;;
    done)    has_done=1 ;;
  esac
done

_TAB_WAITING="${BAUBLE_TAB_WAITING:-bg=yellow,fg=black,bold}"
_TAB_DONE="${BAUBLE_TAB_DONE:-bg=green,fg=black,bold}"
_TAB_WORKING="${BAUBLE_TAB_WORKING:-default}"

if [ "$has_waiting" -eq 1 ]; then
  tmux set-window-option -t "$WINDOW" -q window-status-style "$_TAB_WAITING"
  tmux set-window-option -t "$WINDOW" -q window-status-current-style "${_TAB_WAITING},underscore,overline"
elif [ "$has_done" -eq 1 ]; then
  tmux set-window-option -t "$WINDOW" -q window-status-style "$_TAB_DONE"
  tmux set-window-option -t "$WINDOW" -q window-status-current-style "${_TAB_DONE},underscore,overline"
else
  tmux set-window-option -t "$WINDOW" -q window-status-style "$_TAB_WORKING"
  if [ "$_TAB_WORKING" = "default" ]; then
    tmux set-window-option -t "$WINDOW" -q window-status-current-style 'bold,underscore'
  else
    tmux set-window-option -t "$WINDOW" -q window-status-current-style "${_TAB_WORKING},underscore,overline"
  fi
fi

# Force immediate status bar redraw (otherwise waits for status-interval)
tmux refresh-client -S 2>/dev/null

# ── Auto-return after permission approval ──
# When a pane transitions from waiting→working, it means the user just
# approved (or denied) a permission request. If tmux-claude-next brought
# them here, navigate back to where they came from.
#
# Safety guards:
#   1. Only fires on waiting→working transition (not working→working, etc.)
#   2. Only if @claude-origin-pane was set by tmux-claude-next
#   3. Only if user is STILL focused on this pane (haven't navigated away)
#   4. Origin pane must still exist
#   5. Clears origin after use (one-shot)
if [ "$PREV_STATE" = "waiting" ] && [ "$STATE" = "working" ]; then
  ORIGIN_PANE=$(tmux show-option -p -t "$PANE" -qv @claude-origin-pane 2>/dev/null)
  if [ -n "$ORIGIN_PANE" ]; then
    # Clear origin immediately (one-shot, prevent double-fire)
    tmux set-option -p -t "$PANE" -qu @claude-origin-pane 2>/dev/null
    tmux set-option -p -t "$PANE" -qu @claude-origin-session 2>/dev/null

    # Check: is the user still focused on this pane?
    # display-message -p (no -t) uses the client's focused pane, not $TMUX_PANE.
    FOCUSED_PANE=$(tmux display-message -p '#{pane_id}' 2>/dev/null)
    if [ "$FOCUSED_PANE" = "$PANE" ]; then
      # Verify origin pane still exists
      if tmux display-message -p -t "$ORIGIN_PANE" '#{pane_id}' >/dev/null 2>&1; then
        ORIGIN_SESSION=$(tmux display-message -p -t "$ORIGIN_PANE" '#{session_name}' 2>/dev/null)
        CURRENT_SESSION=$(tmux display-message -p '#{session_name}' 2>/dev/null)
        [ "$ORIGIN_SESSION" != "$CURRENT_SESSION" ] && tmux switch-client -t "$ORIGIN_SESSION" 2>/dev/null
        tmux select-window -t "$ORIGIN_PANE" 2>/dev/null
        tmux select-pane -t "$ORIGIN_PANE" 2>/dev/null
      fi
    fi
  fi
fi

true
