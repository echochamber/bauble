#!/usr/bin/env python3
"""Test suite for tmux-agent-status state counting and cancel detection.

Tests the Python logic embedded in tmux-agent-status that:
  - Reads bauble-state.json and counts waiting/done/cancelled sessions
  - Detects stale 'working' sessions as cancelled (when both hook state
    and window activity are stale)
  - Prunes entries for dead panes
  - Handles malformed/missing data gracefully

Each test creates a temp bauble-state.json and runs the state-counting
logic against it with mocked tmux pane data.
"""

import json
import os
import subprocess
import tempfile
import textwrap
import time


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_state(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _read_state(path):
    with open(path) as f:
        return json.load(f)


def run_state_counter(state_path, cancel_threshold, live_panes_output):
    """Run the Python state-counting block from tmux-agent-status.

    Args:
        state_path: path to bauble-state.json
        cancel_threshold: seconds before marking working as cancelled
        live_panes_output: simulated output of `tmux list-panes -a -F ...`
            Format: "pane_id\\twindow_activity\\n" per pane

    Returns:
        tuple: (waiting, done, cancelled, modified_state)
        modified_state is the state file contents after the run (may have
        cancel detection mutations).
    """
    # We mock subprocess.run to avoid needing tmux. The Python block calls
    # subprocess.run twice: once for list-panes (we mock the output), and
    # potentially for tmux set-option (cancel detection). We inject our mock.
    code = f"""
import json, time, os, sys

class MockResult:
    def __init__(self, stdout='', returncode=0):
        self.stdout = stdout
        self.stderr = ''
        self.returncode = returncode

_list_panes_output = '''{live_panes_output}'''

class MockSubprocess:
    @staticmethod
    def run(cmd, capture_output=False, text=False):
        if 'list-panes' in cmd:
            return MockResult(stdout=_list_panes_output)
        return MockResult()

subprocess = MockSubprocess()

path = '{state_path}'
threshold = {cancel_threshold}

try:
    with open(path) as f:
        data = json.load(f)
except (OSError, json.JSONDecodeError):
    print('0 0 0')
    sys.exit(0)

if not data:
    print('0 0 0')
    sys.exit(0)

now = time.time()
waiting = 0
done = 0
cancelled = 0
modified = False

result = subprocess.run(
    ['tmux', 'list-panes', '-a', '-F', '#{{pane_id}}\\t#{{window_activity}}'],
    capture_output=True, text=True
)
live_panes = {{}}
if result.stdout.strip():
    for line in result.stdout.strip().split('\\n'):
        parts = line.split('\\t', 1)
        try:
            activity = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        except (ValueError, IndexError):
            activity = 0
        live_panes[parts[0]] = activity

dead = []
for pane_id, info in data.items():
    if pane_id not in live_panes:
        dead.append(pane_id)
        continue

    state = info.get('state', '')
    updated_at = info.get('updated_at', 0)
    age = now - updated_at

    window_activity = live_panes.get(pane_id, 0)
    pane_idle = now - window_activity

    if state == 'working' and age > threshold and pane_idle > 15:
        info['state'] = 'cancelled'
        info['updated_at'] = now
        modified = True

        win_id = info.get('window_id', '')
        subprocess.run(['tmux', 'set-option', '-p', '-t', pane_id, '-q', 'window-style', 'bg=#2a1a1a'], capture_output=True)

    state = info.get('state', '')
    if state == 'waiting': waiting += 1
    elif state == 'done': done += 1
    elif state == 'cancelled': cancelled += 1

for pane_id in dead:
    del data[pane_id]
    modified = True

if modified:
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\\n')
    os.replace(tmp, path)

print(f'{{waiting}} {{done}} {{cancelled}}')
"""

    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Python block failed:\n{result.stderr}")

    parts = result.stdout.strip().split()
    waiting = int(parts[0])
    done_count = int(parts[1])
    cancelled = int(parts[2])

    # Read back state file (may have been modified by cancel detection)
    try:
        modified_state = _read_state(state_path)
    except (OSError, json.JSONDecodeError):
        modified_state = {}

    return waiting, done_count, cancelled, modified_state


# ── Test infrastructure ──────────────────────────────────────────────────────

TESTS_RUN = 0
TESTS_PASSED = 0


def check(description, actual, expected):
    global TESTS_RUN, TESTS_PASSED
    TESTS_RUN += 1
    if actual == expected:
        TESTS_PASSED += 1
    else:
        print(f"  FAIL: {description}")
        print(f"    expected: {expected}")
        print(f"    actual:   {actual}")


# ── State counting tests ─────────────────────────────────────────────────────

def test_counts_all_states():
    """Counts waiting, done, and cancelled states correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "waiting", "updated_at": now, "window_id": "@1"},
            "%2": {"state": "done", "updated_at": now, "window_id": "@2"},
            "%3": {"state": "done", "updated_at": now, "window_id": "@3"},
            "%4": {"state": "cancelled", "updated_at": now, "window_id": "@4"},
            "%5": {"state": "working", "updated_at": now, "window_id": "@5"},
        })
        panes = "%1\t{ts}\n%2\t{ts}\n%3\t{ts}\n%4\t{ts}\n%5\t{ts}".format(ts=int(now))
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("waiting count", w, 1)
        check("done count", d, 2)
        check("cancelled count", c, 1)
    finally:
        os.unlink(path)


def test_empty_state_file():
    """Empty state file returns all zeros."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        path = f.name
    try:
        w, d, c, _ = run_state_counter(path, 30, "")
        check("waiting", w, 0)
        check("done", d, 0)
        check("cancelled", c, 0)
    finally:
        os.unlink(path)


def test_missing_state_file():
    """Missing state file returns all zeros."""
    path = tempfile.mktemp(suffix=".json")
    # Don't create the file
    w, d, c, _ = run_state_counter(path, 30, "")
    check("waiting", w, 0)
    check("done", d, 0)
    check("cancelled", c, 0)


def test_malformed_json():
    """Malformed JSON returns all zeros."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{bad json")
        path = f.name
    try:
        w, d, c, _ = run_state_counter(path, 30, "")
        check("waiting", w, 0)
        check("done", d, 0)
        check("cancelled", c, 0)
    finally:
        os.unlink(path)


def test_all_done():
    """All sessions done shows correct count."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
            "%2": {"state": "done", "updated_at": now, "window_id": "@2"},
            "%3": {"state": "done", "updated_at": now, "window_id": "@3"},
        })
        panes = "%1\t{ts}\n%2\t{ts}\n%3\t{ts}".format(ts=int(now))
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("waiting", w, 0)
        check("done", d, 3)
        check("cancelled", c, 0)
    finally:
        os.unlink(path)


def test_working_not_counted():
    """Working state is not counted as waiting/done/cancelled."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "working", "updated_at": now, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=int(now))
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("waiting", w, 0)
        check("done", d, 0)
        check("cancelled", c, 0)
    finally:
        os.unlink(path)


# ── Dead pane pruning tests ──────────────────────────────────────────────────

def test_prunes_dead_panes():
    """Panes not in tmux are pruned from state."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
            "%99": {"state": "done", "updated_at": now, "window_id": "@2"},
        })
        # Only %1 is live
        panes = "%1\t{ts}".format(ts=int(now))
        w, d, c, state = run_state_counter(path, 30, panes)
        check("done count (only live pane)", d, 1)
        check("dead pane pruned", "%99" not in state, True)
        check("live pane kept", "%1" in state, True)
    finally:
        os.unlink(path)


def test_prunes_all_dead():
    """All panes dead results in empty state."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%98": {"state": "done", "updated_at": now, "window_id": "@1"},
            "%99": {"state": "waiting", "updated_at": now, "window_id": "@2"},
        })
        # No live panes match
        panes = "%1\t{ts}".format(ts=int(now))
        w, d, c, state = run_state_counter(path, 30, panes)
        check("waiting", w, 0)
        check("done", d, 0)
        check("dead panes pruned from file", len(state), 0)
    finally:
        os.unlink(path)


# ── Cancel detection tests ───────────────────────────────────────────────────

def test_cancel_detection_stale_working():
    """Working session with stale hooks AND stale window gets cancelled."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        stale_time = now - 60  # 60 seconds ago (beyond 30s threshold)
        stale_activity = int(now - 30)  # window idle 30s (beyond 15s threshold)
        _write_state(path, {
            "%1": {"state": "working", "updated_at": stale_time, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=stale_activity)
        w, d, c, state = run_state_counter(path, 30, panes)
        check("cancelled count", c, 1)
        check("state changed to cancelled", state["%1"]["state"], "cancelled")
    finally:
        os.unlink(path)


def test_cancel_detection_fresh_hooks():
    """Working session with fresh hooks is NOT cancelled."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "working", "updated_at": now, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=int(now))
        w, d, c, state = run_state_counter(path, 30, panes)
        check("not cancelled", c, 0)
        check("state still working", state["%1"]["state"], "working")
    finally:
        os.unlink(path)


def test_cancel_detection_stale_hooks_fresh_window():
    """Working with stale hooks but active window is NOT cancelled."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        stale_time = now - 60  # hooks stale
        fresh_activity = int(now - 5)  # window recently active
        _write_state(path, {
            "%1": {"state": "working", "updated_at": stale_time, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=fresh_activity)
        w, d, c, state = run_state_counter(path, 30, panes)
        check("not cancelled (window active)", c, 0)
        check("state still working", state["%1"]["state"], "working")
    finally:
        os.unlink(path)


def test_cancel_detection_done_not_affected():
    """Done sessions are never re-evaluated for cancellation."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        stale_time = now - 120
        _write_state(path, {
            "%1": {"state": "done", "updated_at": stale_time, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=int(stale_time))
        w, d, c, state = run_state_counter(path, 30, panes)
        check("still done", d, 1)
        check("not cancelled", c, 0)
    finally:
        os.unlink(path)


def test_cancel_detection_waiting_not_affected():
    """Waiting sessions are not auto-cancelled (human may be deciding)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        stale_time = now - 120
        _write_state(path, {
            "%1": {"state": "waiting", "updated_at": stale_time, "window_id": "@1"},
        })
        panes = "%1\t{ts}".format(ts=int(stale_time))
        w, d, c, state = run_state_counter(path, 30, panes)
        check("still waiting", w, 1)
        check("not cancelled", c, 0)
    finally:
        os.unlink(path)


# ── Activity value parsing tests ─────────────────────────────────────────────

def test_empty_activity_value():
    """Empty activity value (the original bug) doesn't crash."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
        })
        # Empty activity value (the original bug trigger)
        panes = "%1\t"
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("done count with empty activity", d, 1)
    finally:
        os.unlink(path)


def test_missing_activity_tab():
    """Missing tab separator doesn't crash."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
        })
        # No tab at all, just pane ID
        panes = "%1"
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("done count with no tab", d, 1)
    finally:
        os.unlink(path)


def test_non_numeric_activity():
    """Non-numeric activity value doesn't crash."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
        })
        panes = "%1\tnot_a_number"
        w, d, c, _ = run_state_counter(path, 30, panes)
        check("done count with bad activity", d, 1)
    finally:
        os.unlink(path)


# ── Mixed scenario tests ─────────────────────────────────────────────────────

def test_mixed_live_and_dead_with_cancel():
    """Complex scenario: live + dead + cancellable panes."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        stale_time = now - 60
        _write_state(path, {
            "%1": {"state": "waiting", "updated_at": now, "window_id": "@1"},
            "%2": {"state": "done", "updated_at": now, "window_id": "@2"},
            "%3": {"state": "working", "updated_at": stale_time, "window_id": "@3"},  # stale -> cancel
            "%4": {"state": "done", "updated_at": now, "window_id": "@4"},  # dead pane
        })
        stale_activity = int(now - 30)
        panes = "%1\t{now}\n%2\t{now}\n%3\t{stale}".format(
            now=int(now), stale=stale_activity
        )
        w, d, c, state = run_state_counter(path, 30, panes)
        check("waiting", w, 1)
        check("done", d, 1)
        check("cancelled", c, 1)
        check("dead pane pruned", "%4" not in state, True)
        check("cancelled state written", state["%3"]["state"], "cancelled")
    finally:
        os.unlink(path)


def test_no_live_panes():
    """No live tmux panes (tmux not running or empty)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        now = time.time()
        _write_state(path, {
            "%1": {"state": "done", "updated_at": now, "window_id": "@1"},
        })
        w, d, c, state = run_state_counter(path, 30, "")
        check("all pruned (no live panes)", d, 0)
        check("state file empty", len(state), 0)
    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # State counting
    test_counts_all_states()
    test_empty_state_file()
    test_missing_state_file()
    test_malformed_json()
    test_all_done()
    test_working_not_counted()

    # Dead pane pruning
    test_prunes_dead_panes()
    test_prunes_all_dead()

    # Cancel detection
    test_cancel_detection_stale_working()
    test_cancel_detection_fresh_hooks()
    test_cancel_detection_stale_hooks_fresh_window()
    test_cancel_detection_done_not_affected()
    test_cancel_detection_waiting_not_affected()

    # Activity value parsing (regression tests for the original bug)
    test_empty_activity_value()
    test_missing_activity_tab()
    test_non_numeric_activity()

    # Mixed scenarios
    test_mixed_live_and_dead_with_cancel()
    test_no_live_panes()

    print(f"\n{TESTS_PASSED}/{TESTS_RUN} tests passed")
    if TESTS_PASSED < TESTS_RUN:
        print(f"  {TESTS_RUN - TESTS_PASSED} FAILED")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
