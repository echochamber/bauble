#!/usr/bin/env bash
# Clears pane tint, @bauble-state, and session tracking options when
# Claude Code exits. Recomputes the window tab style afterward.
# Triggered by SessionEnd hook.
#
# Reuses the same explicit-target pattern as pane-tint.sh — hooks run
# as background processes where the implicit "current" is unreliable.

PANE="$TMUX_PANE"
[ -z "$PANE" ] && exit 0

# Source bauble.conf for configurable colors
# Resolve symlink to find the repo's config directory
_BAUBLE_SELF="${BASH_SOURCE[0]:-$0}"
[ -L "$_BAUBLE_SELF" ] && _BAUBLE_SELF="$(readlink "$_BAUBLE_SELF")"
_BAUBLE_CONF_DIR="$(cd "$(dirname "$_BAUBLE_SELF")/../" 2>/dev/null && pwd)"
_BAUBLE_CONF="${_BAUBLE_CONF_DIR:+$_BAUBLE_CONF_DIR/config/bauble.conf}"
[ -f "${_BAUBLE_CONF:-}" ] && source "$_BAUBLE_CONF"

WINDOW=$(tmux display-message -p -t "$PANE" '#{window_id}' 2>/dev/null)
[ -z "$WINDOW" ] && exit 0

# Clear pane background
tmux set-option -p -t "$PANE" -qu window-style 2>/dev/null
tmux set-option -p -t "$PANE" -qu window-active-style 2>/dev/null

# Clear all bauble/claude pane options
tmux set-option -p -t "$PANE" -qu @bauble-state 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-session 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-cwd 2>/dev/null
tmux set-option -p -t "$PANE" -qu @bauble-nav-via-cycle 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-name 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-origin-pane 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-origin-session 2>/dev/null
tmux set-option -p -t "$PANE" -qu @claude-waiting-tool 2>/dev/null

# Remove from state file
STATE_FILE="$HOME/.claude/hooks/bauble-state.json"
STATE_FILE="$STATE_FILE" PANE="$PANE" \
python3 -c "
import json, os
path = os.environ['STATE_FILE']
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    data = {}
data.pop(os.environ['PANE'], None)
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
os.replace(tmp, path)
" 2>/dev/null

# Remove from session-map.json and clean _name_index
SESSION_MAP="$HOME/.claude/hooks/session-map.json"
if [ -f "$SESSION_MAP" ]; then
  SESSION_MAP="$SESSION_MAP" PANE="$PANE" \
  python3 -c "
import json, os
path = os.environ['SESSION_MAP']
pane = os.environ['PANE']
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    data = {}
name_index = data.get('_name_index', {})
to_remove = [sid for sid, info in data.items()
             if sid != '_name_index' and isinstance(info, dict)
             and info.get('pane') == pane]
for sid in to_remove:
    old_name = data[sid].get('name')
    if old_name and name_index.get(old_name) == sid:
        del name_index[old_name]
    del data[sid]
data['_name_index'] = name_index
tmp = path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
os.replace(tmp, path)
" 2>/dev/null
fi

# Recompute window tab style from remaining panes
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
    tmux set-window-option -t "$WINDOW" -qu window-status-current-style 2>/dev/null
  else
    tmux set-window-option -t "$WINDOW" -q window-status-current-style "${_TAB_WORKING},underscore,overline"
  fi
fi

tmux refresh-client -S 2>/dev/null

true
