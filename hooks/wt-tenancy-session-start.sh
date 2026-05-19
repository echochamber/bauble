#!/usr/bin/env bash
# wt-tenancy-session-start.sh — SessionStart hook
#
# If cwd is inside a known tenancy, refresh last_session_at + session_id.
# If cwd is a {repo}_tenant_N path but not tracked, auto-adopt as active.
# Silent fallthrough on any failure — must never block session start.

set -u

WT_TENANCY="${WT_TENANCY_BIN:-$HOME/.claude/scripts/wt-tenancy}"
[ -x "$WT_TENANCY" ] || exit 0

# Read SessionStart payload from stdin (best-effort JSON parse via jq)
PAYLOAD=$(cat 2>/dev/null || true)
SESSION_ID=""
if command -v jq >/dev/null 2>&1 && [ -n "$PAYLOAD" ]; then
  SESSION_ID=$(echo "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null || true)
fi

# Determine current worktree root (silent fallthrough if not in git)
WT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# Try refresh first (idempotent — no-op if untracked)
if [ -n "$SESSION_ID" ]; then
  "$WT_TENANCY" refresh-session "$WT_ROOT" --session-id "$SESSION_ID" >/dev/null 2>&1 || true
else
  "$WT_TENANCY" refresh-session "$WT_ROOT" >/dev/null 2>&1 || true
fi

# Auto-adopt unclaimed tenant slots: if path matches {repo}_tenant_N pattern,
# adopt so the slot appears in `list`/`pool` going forward.
COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null) || exit 0
REPO_ROOT=$(cd "$(dirname "$COMMON_DIR")" 2>/dev/null && pwd) || exit 0
REPO_NAME=$(basename "$REPO_ROOT")
BASENAME=$(basename "$WT_ROOT")
if [[ "$BASENAME" =~ ^${REPO_NAME}_tenant_[0-9]+$ ]]; then
  # Already tracked? `status` exits 0 if found, 1 if not.
  if ! "$WT_TENANCY" status "$WT_ROOT" >/dev/null 2>&1; then
    if [ -n "$SESSION_ID" ]; then
      "$WT_TENANCY" adopt "$WT_ROOT" --session-id "$SESSION_ID" >/dev/null 2>&1 || true
    else
      "$WT_TENANCY" adopt "$WT_ROOT" >/dev/null 2>&1 || true
    fi
  fi
fi

exit 0
