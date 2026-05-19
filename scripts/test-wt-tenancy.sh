#!/usr/bin/env bash
# test-wt-tenancy.sh — end-to-end smoke + behavior tests for wt-tenancy
#
# Run: bash bauble/scripts/test-wt-tenancy.sh
# No deps beyond git, jq, bash. Creates an isolated test repo under $TMPDIR.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$SCRIPT_DIR/wt-tenancy"
TESTDIR="$(mktemp -d "${TMPDIR:-/tmp}/wt-tenancy-test.XXXXXX")"
# Canonicalize so /tmp vs /private/tmp on macOS doesn't trip exact path matches.
TESTDIR="$(cd "$TESTDIR" && pwd -P)"
export WT_TENANCY_STATE="$TESTDIR/state.json"
export WT_TENANCY_LOCK="$TESTDIR/state.lock"

pass=0
fail=0
trap 'echo; echo "Tests: $pass passed, $fail failed"; rm -rf "$TESTDIR"' EXIT

assert() {
  local label="$1"; shift
  if "$@"; then
    echo "  ok  $label"
    pass=$((pass + 1))
  else
    echo "  FAIL  $label"
    fail=$((fail + 1))
  fi
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ok  $label"
    pass=$((pass + 1))
  else
    echo "  FAIL  $label"
    echo "         expected: $expected"
    echo "         actual:   $actual"
    fail=$((fail + 1))
  fi
}

# --- set up bare origin + main clone ---
mkdir -p "$TESTDIR"
( cd "$TESTDIR" && git init -q --bare origin.git )
git clone -q "$TESTDIR/origin.git" "$TESTDIR/mainrepo"
(
  cd "$TESTDIR/mainrepo"
  git checkout -q -B main
  echo seed > README.md
  git add README.md
  git -c user.email=a@b -c user.name=t commit -q -m init
  git push -q -u origin main
) >/dev/null

cd "$TESTDIR/mainrepo"

echo "=== claim-or-create grows pool ==="
PATH_A=$("$WT" claim-or-create feature-a --issue owner/r#42)
assert "creates tenant_1" test -d "$PATH_A"
assert_eq "path is tenant_1" "$TESTDIR/mainrepo_tenant_1" "$PATH_A"
assert_eq "branch matches" "feature-a" "$(git -C "$PATH_A" symbolic-ref --short HEAD)"

echo "=== idempotent claim ==="
PATH_A2=$("$WT" claim-or-create feature-a)
assert_eq "same path on re-claim" "$PATH_A" "$PATH_A2"

echo "=== second branch grows ==="
PATH_B=$("$WT" claim-or-create feature-b)
assert_eq "tenant_2 created" "$TESTDIR/mainrepo_tenant_2" "$PATH_B"

echo "=== soft cap refuses ==="
WT_TENANCY_SOFT_CAP=2 "$WT" claim-or-create feature-c >/dev/null 2>&1 && cap_ok=false || cap_ok=true
assert "soft cap refused growth" $cap_ok

echo "=== --force-grow bypasses cap ==="
PATH_C=$(WT_TENANCY_SOFT_CAP=2 "$WT" claim-or-create feature-c --force-grow)
assert_eq "tenant_3 created via --force-grow" "$TESTDIR/mainrepo_tenant_3" "$PATH_C"

echo "=== dirty release refused ==="
echo dirt > "$PATH_B/scratch.txt"
"$WT" release "$PATH_B" >/dev/null 2>&1 && dirty_ok=false || dirty_ok=true
assert "dirty release refused" $dirty_ok

echo "=== --force release works dirty ==="
"$WT" release "$PATH_B" --force >/dev/null 2>&1
status_b=$(jq -r --arg p "$PATH_B" '.tenancies[] | select(.worktree_path==$p) | .status' "$WT_TENANCY_STATE")
assert_eq "tenant_2 is free after --force release" "free" "$status_b"
# Clean up dirt that was left behind
rm -f "$PATH_B/scratch.txt"

echo "=== clean release works ==="
# Recover PATH_C (was claimed clean). Commit + push first.
(
  cd "$PATH_C"
  echo x > x.txt
  git add x.txt
  git -c user.email=a@b -c user.name=t commit -q -m feat
  git push -q -u origin feature-c
) >/dev/null
"$WT" release "$PATH_C" >/dev/null
status_c=$(jq -r --arg p "$PATH_C" '.tenancies[] | select(.worktree_path==$p) | .status' "$WT_TENANCY_STATE")
assert_eq "tenant_3 is free after clean release" "free" "$status_c"
# detached head check
detached=$(git -C "$PATH_C" symbolic-ref -q HEAD || echo "")
assert_eq "released slot is on detached HEAD" "" "$detached"

echo "=== reuse: free slot picked up for new branch ==="
PATH_D=$("$WT" claim-or-create feature-d)
assert "reuse picks an existing tenant slot" \
  bash -c "[ '$PATH_D' = '$PATH_B' ] || [ '$PATH_D' = '$PATH_C' ]"

echo "=== stale-days=0 lists everything active ==="
stale_count=$("$WT" stale --days 0 --json | jq length)
assert "stale --days 0 reports >=1" test "$stale_count" -ge 1

echo "=== adopt unpooled worktree ==="
git -C "$TESTDIR/mainrepo" worktree add -q "$TESTDIR/ad-hoc-wt" -b adoptee >/dev/null
"$WT" adopt "$TESTDIR/ad-hoc-wt" >/dev/null
adopted_status=$(jq -r --arg p "$TESTDIR/ad-hoc-wt" '.tenancies[] | select(.worktree_path==$p) | .status' "$WT_TENANCY_STATE")
assert_eq "adopted worktree status=active" "active" "$adopted_status"

echo "=== refresh-session bumps last_session_at ==="
sleep 1
before=$(jq -r --arg p "$PATH_A" '.tenancies[] | select(.worktree_path==$p) | .last_session_at' "$WT_TENANCY_STATE")
(cd "$PATH_A" && "$WT" refresh-session --session-id test-sess-123)
after=$(jq -r --arg p "$PATH_A" '.tenancies[] | select(.worktree_path==$p) | .last_session_at' "$WT_TENANCY_STATE")
assert "refresh-session updates last_session_at" bash -c "[ '$before' != '$after' ]"
sid=$(jq -r --arg p "$PATH_A" '.tenancies[] | select(.worktree_path==$p) | .session_id' "$WT_TENANCY_STATE")
assert_eq "refresh-session sets session_id" "test-sess-123" "$sid"

echo "=== remove drops the entry ==="
"$WT" remove "$TESTDIR/ad-hoc-wt" >/dev/null
exists=$(jq -r --arg p "$TESTDIR/ad-hoc-wt" '[.tenancies[] | select(.worktree_path==$p)] | length' "$WT_TENANCY_STATE")
assert_eq "remove leaves no entry" "0" "$exists"

[ "$fail" = "0" ]
