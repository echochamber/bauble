#!/usr/bin/env bash
# Handles tmux alert-silence events for cancel detection.
# Part of bauble — ambient session UX for Claude Code
#
# Registered as: set-hook -g alert-silence 'run-shell -b ...'
# Fires when a window with monitor-silence enabled produces no output
# for the configured duration.
#
# DIAGNOSTIC MODE: logs detections to /tmp/claude-safe/silence-detections.log
# without changing any visual state.

LOG="/tmp/claude-safe/silence-detections.log"
mkdir -p -m 700 /tmp/claude-safe 2>/dev/null
echo "$(date '+%H:%M:%S') HOOK INVOKED" >> "$LOG"

# Immediately suppress tmux's built-in alert styling on all windows
# (we handle state ourselves — don't want tab highlighting or OS dock bounce)
for win_id in $(tmux list-windows -a -F '#{window_id} #{window_silence_flag}' 2>/dev/null | awk '$2 == 1 {print $1}'); do
  # Toggle monitor-silence off/on to clear the flag without visual alert
  cur=$(tmux show-option -w -t "$win_id" -qv monitor-silence 2>/dev/null)
  tmux set-option -w -t "$win_id" -q monitor-silence 0 2>/dev/null
  [ -n "$cur" ] && [ "$cur" -gt 0 ] && tmux set-option -w -t "$win_id" -q monitor-silence "$cur" 2>/dev/null
done

# Check all windows for Claude panes with stale state
for win_id in $(tmux list-windows -a -F '#{window_id}' 2>/dev/null); do
  for pane_id in $(tmux list-panes -t "$win_id" -F '#{pane_id}' 2>/dev/null); do
    state=$(tmux show-option -p -t "$pane_id" -qv @bauble-state 2>/dev/null)
    case "$state" in
      working|waiting)
        cwd=$(tmux show-option -p -t "$pane_id" -qv @claude-cwd 2>/dev/null)
        echo "$(date '+%H:%M:%S') CANCEL DETECTED — pane=$pane_id win=$win_id state=$state cwd=$(basename "${cwd:-?}")" >> "$LOG"
        ;;
    esac
  done
done

true
