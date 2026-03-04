#!/bin/bash
# session-track.sh — SessionStart hook for session map
# Part of bauble — ambient session UX for Claude Code
#
# Reads session_id, cwd, source from hook stdin JSON.
# Writes/updates ~/.claude/hooks/session-map.json.
# Sets tmux pane user options: @claude-session, @claude-cwd.
#
# On source=clear: old session entry replaced (keyed by pane).
# On source=startup: fresh entry, stale pane entries pruned.

SESSION_MAP="$HOME/.claude/hooks/session-map.json"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
SOURCE=$(echo "$INPUT" | jq -r '.source // "startup"' 2>/dev/null)
PANE="${TMUX_PANE:-}"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Capture git info (best-effort)
GIT_BRANCH=""
GIT_WORKTREE=""
if [ -n "$CWD" ] && { [ -d "$CWD/.git" ] || [ -f "$CWD/.git" ]; }; then
  GIT_BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null || true)
  # Detect worktree: .git is a file (not dir) in worktrees
  if [ -f "$CWD/.git" ]; then
    GIT_WORKTREE=$(grep -oP 'gitdir: \K.*' "$CWD/.git" 2>/dev/null | sed 's|/\.git/worktrees/.*||' || true)
    GIT_WORKTREE=$(basename "$GIT_WORKTREE" 2>/dev/null || true)
  fi
fi

# Set tmux pane options if in tmux
if [ -n "$PANE" ]; then
    tmux set-option -p -t "$PANE" @claude-session "$SESSION_ID" 2>/dev/null
    [ -n "$CWD" ] && tmux set-option -p -t "$PANE" @claude-cwd "$CWD" 2>/dev/null
fi

# Initialize session map if missing
[ -f "$SESSION_MAP" ] || echo '{}' > "$SESSION_MAP"

# Build the new entry
NEW_ENTRY=$(jq -n \
    --arg cwd "$CWD" \
    --arg pane "$PANE" \
    --arg started_at "$NOW" \
    --arg source "$SOURCE" \
    --arg git_branch "$GIT_BRANCH" \
    --arg git_worktree "$GIT_WORKTREE" \
    '{cwd: $cwd, pane: $pane, started_at: $started_at, source: $source,
      git_branch: (if $git_branch == "" then null else $git_branch end),
      git_worktree: (if $git_worktree == "" then null else $git_worktree end)}')

# Get list of live panes for cleanup
LIVE_PANES=""
if [ -n "$PANE" ]; then
    LIVE_PANES=$(tmux list-panes -a -F '#{pane_id}' 2>/dev/null | tr '\n' '|')
fi

# Update the map atomically:
# 1. Remove any existing entry for this pane (handles clear/restart)
# 2. Add the new session entry
# 3. Prune entries for dead panes
SESSION_MAP="$SESSION_MAP" SESSION_ID="$SESSION_ID" PANE="$PANE" LIVE_PANES="$LIVE_PANES" NEW_ENTRY="$NEW_ENTRY" \
python3 -c "
import json, sys, os

map_path = os.environ['SESSION_MAP']
session_id = os.environ['SESSION_ID']
pane = os.environ.get('PANE', '')
live_panes_str = os.environ.get('LIVE_PANES', '')

try:
    with open(map_path) as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    data = {}

name_index = data.get('_name_index', {})

# Remove old entries for this pane (handles clear/restart)
if pane:
    to_remove = [sid for sid, info in data.items()
                 if sid != '_name_index' and isinstance(info, dict)
                 and info.get('pane') == pane and sid != session_id]
    for sid in to_remove:
        old_name = data[sid].get('name')
        if old_name and name_index.get(old_name) == sid:
            del name_index[old_name]
        del data[sid]

# Add/update the new session entry (preserve name if exists)
new_entry = json.loads(os.environ['NEW_ENTRY'])
if session_id in data and isinstance(data[session_id], dict):
    existing = data[session_id]
    for key in ('name', 'named_at', 'active_bead', 'cullis_yolo', 'cullis_profile', 'remis_session'):
        if key in existing and key not in new_entry:
            new_entry[key] = existing[key]
data[session_id] = new_entry

# Prune entries for dead panes (only if we have live pane data)
if live_panes_str:
    live = set(live_panes_str.strip('|').split('|'))
    to_remove = [sid for sid, info in data.items()
                 if sid != '_name_index' and isinstance(info, dict)
                 and info.get('pane') and info['pane'] not in live]
    for sid in to_remove:
        old_name = data[sid].get('name')
        if old_name and name_index.get(old_name) == sid:
            del name_index[old_name]
        del data[sid]

data['_name_index'] = name_index

# Write atomically via temp file
tmp = map_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
os.replace(tmp, map_path)
" 2>/dev/null

exit 0
