#!/usr/bin/env bash
# gemini.sh — State detector for Gemini CLI
# Part of bauble — ambient session UX for AI coding agents
#
# Given tmux capture-pane output on stdin, prints the detected state:
#   idle, working, waiting, or unknown
#
# Patterns observed from Gemini CLI (gemini-cli 0.x, 2025-2026):
#
#   Idle: Input prompt box visible in bottom region, NO spinner:
#     ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀...
#      > <user text or placeholder>
#     ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄...
#     ~/path (branch)  ...  /model Auto (Gemini 3)
#
#   Working: Braille spinner (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) in status line.
#            NOTE: The spinner and the input prompt can BOTH be visible
#            simultaneously (Gemini is a full-screen TUI), so spinner
#            MUST be checked before the prompt.
#
#   Waiting: "Action Required" approval dialog:
#     ╭────────────────────────────╮
#     │ Action Required            │
#     ╰────────────────────────────╯
#
# Detection uses the last ~10 lines (bottom of visible pane).

detect_gemini_state() {
  local content="$1"

  # Use last 10 lines for bottom-of-screen detection
  local bottom
  bottom=$(printf '%s\n' "$content" | tail -10)

  # 1. Waiting (highest priority — needs human attention)
  #    Match the approval option menu ("Allow once" / "Allow for this session")
  #    which appears near the bottom inside a │ box-drawing frame.
  #    IMPORTANT: Do NOT match "Action Required" as free text — Gemini may echo
  #    those words in its own output when discussing detection logic. Only match
  #    the structured dialog elements that appear exclusively in approval prompts.
  #    The "● 1. Allow once" pattern is unique to the approval menu.
  if printf '%s\n' "$content" | tail -20 | grep -q 'Allow once'; then
    echo "waiting"
    return
  fi
  # Backup: match "Apply this change?" which appears on edit approval dialogs
  if printf '%s\n' "$content" | tail -20 | grep -q 'Apply this change'; then
    echo "waiting"
    return
  fi

  # 2. Working: braille spinner visible in bottom area
  #    MUST check before idle — Gemini's TUI shows both spinner AND
  #    input prompt simultaneously while generating
  if printf '%s\n' "$bottom" | grep -q '[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'; then
    echo "working"
    return
  fi

  # 3. Idle: the input prompt " > " appears in the bottom area with NO spinner
  if printf '%s\n' "$bottom" | grep -q '^[[:space:]]*> '; then
    echo "idle"
    return
  fi

  # 4. Working fallback: status bar visible but no prompt box and no spinner
  #    During generation, Gemini shows output with ✦ prefix and the status bar
  #    is at the bottom, but no ▀▀▀/prompt/▄▄▄ box
  if printf '%s\n' "$bottom" | grep -q '/model' && \
     ! printf '%s\n' "$bottom" | grep -q '^[[:space:]]*> '; then
    echo "working"
    return
  fi

  echo "unknown"
}

# Allow sourcing for tests, or direct execution
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  content=$(cat)
  detect_gemini_state "$content"
fi
