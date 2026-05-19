#!/usr/bin/env bash
# wt-tenancy-session-end.sh — SessionEnd hook
#
# Async best-effort: check if cwd's tenancy has a merged PR; if so, release it.
# Backgrounded so it doesn't slow shutdown. Silent fallthrough.

set -u

WT_TENANCY="${WT_TENANCY_BIN:-$HOME/.claude/scripts/wt-tenancy}"
[ -x "$WT_TENANCY" ] || exit 0

WT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# Background gc against just this tenancy (cheap; gc walks all tenancies but it's bounded)
( "$WT_TENANCY" gc >/dev/null 2>&1 || true ) &
disown 2>/dev/null || true

exit 0
