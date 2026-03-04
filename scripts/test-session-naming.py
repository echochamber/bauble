#!/usr/bin/env python3
"""Test suite for session naming feature (session-map.json manipulation).

Tests the Python JSON logic embedded in:
  - session-track.sh (SessionStart: entry creation, name preservation, _name_index)
  - pane-cleanup.sh (SessionEnd: entry removal, _name_index cleanup)
  - tmux-session-rename (rename: name set/clear, enrichment, _name_index)

Each test creates a temp session-map.json file and runs the embedded Python
logic against it, verifying the resulting JSON state.
"""

import json
import os
import tempfile
import textwrap


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_map(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _read_map(path):
    with open(path) as f:
        return json.load(f)


def _run_python(code, **env_vars):
    """Run a Python code block (simulating the inline scripts)."""
    import subprocess
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True, text=True,
        env={**os.environ, **env_vars},
    )
    if result.returncode != 0:
        raise RuntimeError(f"Python block failed: {result.stderr}")
    return result.stdout


# ── Session-track logic (extracted) ──────────────────────────────────────────

def run_session_track_update(map_path, session_id, pane, new_entry_json, live_panes_str=""):
    """Simulate the Python block in session-track.sh."""
    code = textwrap.dedent(f"""\
        import json, os

        map_path = '{map_path}'
        session_id = '{session_id}'
        pane = '{pane}'
        live_panes_str = '{live_panes_str}'

        try:
            with open(map_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {{}}

        name_index = data.get('_name_index', {{}})

        if pane:
            to_remove = [sid for sid, info in data.items()
                         if sid != '_name_index' and isinstance(info, dict)
                         and info.get('pane') == pane and sid != session_id]
            for sid in to_remove:
                old_name = data[sid].get('name')
                if old_name and name_index.get(old_name) == sid:
                    del name_index[old_name]
                del data[sid]

        new_entry = json.loads('''{new_entry_json}''')
        if session_id in data and isinstance(data[session_id], dict):
            existing = data[session_id]
            for key in ('name', 'named_at', 'active_bead', 'cullis_yolo', 'cullis_profile', 'remis_session'):
                if key in existing and key not in new_entry:
                    new_entry[key] = existing[key]
        data[session_id] = new_entry

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

        tmp = map_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\\n')
        os.replace(tmp, map_path)
    """)
    _run_python(code)
    return _read_map(map_path)


# ── Pane-cleanup logic (extracted) ───────────────────────────────────────────

def run_pane_cleanup(map_path, pane):
    """Simulate the Python block in pane-cleanup.sh."""
    code = textwrap.dedent(f"""\
        import json, os

        path = '{map_path}'
        pane = '{pane}'

        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {{}}

        name_index = data.get('_name_index', {{}})
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
            f.write('\\n')
        os.replace(tmp, path)
    """)
    _run_python(code)
    return _read_map(map_path)


# ── Rename logic (extracted) ─────────────────────────────────────────────────

def run_rename_update(map_path, session_id, name, enrichment=None):
    """Simulate the Python block in tmux-session-rename."""
    enrichment = enrichment or {}
    git_branch = enrichment.get("git_branch", "")
    git_worktree = enrichment.get("git_worktree", "")
    active_bead = enrichment.get("active_bead", "")
    cullis_yolo = "true" if enrichment.get("cullis_yolo") else "false"
    cullis_profile = enrichment.get("cullis_profile", "")
    remis_session = enrichment.get("remis_session", "")
    now = "2026-02-24T21:15:00Z"

    code = textwrap.dedent(f"""\
        import json, os

        map_path = '{map_path}'
        session_id = '{session_id}'
        name = '''{name}'''
        now = '{now}'
        git_branch = '{git_branch}' or None
        git_worktree = '{git_worktree}' or None
        active_bead = '{active_bead}' or None
        cullis_yolo = '{cullis_yolo}' == 'true'
        cullis_profile = '{cullis_profile}' or None
        remis_session = '{remis_session}' or None

        try:
            with open(map_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {{}}

        name_index = data.get('_name_index', {{}})

        if session_id in data and isinstance(data[session_id], dict):
            entry = data[session_id]
            old_name = entry.get('name')
            if old_name and name_index.get(old_name) == session_id:
                del name_index[old_name]
        else:
            entry = {{}}

        if name:
            entry['name'] = name
            entry['named_at'] = now
            name_index[name] = session_id
        else:
            entry.pop('name', None)
            entry.pop('named_at', None)

        entry['git_branch'] = git_branch
        entry['git_worktree'] = git_worktree
        entry['active_bead'] = active_bead
        entry['cullis_yolo'] = cullis_yolo
        entry['cullis_profile'] = cullis_profile
        entry['remis_session'] = remis_session

        data[session_id] = entry
        data['_name_index'] = name_index

        tmp = map_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\\n')
        os.replace(tmp, map_path)
    """)
    _run_python(code)
    return _read_map(map_path)


# ── Tab title truncation (pure function) ─────────────────────────────────────

def truncate_tab_title(name):
    """Replicate the bash truncation logic from tmux-session-rename."""
    if len(name) <= 10:
        return name
    return name[:10] + "..."


# ── Name column formatting (pure function) ───────────────────────────────────

def format_name_column(name):
    """Replicate the bash name column logic from tmux-claude-list."""
    if not name:
        return "—"
    if len(name) > 15:
        return name[:12] + "..."
    return name


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

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


# ── session-track tests ─────────────────────────────────────────────────────

def test_session_track_basic_entry():
    """New session creates entry with git fields."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        path = f.name
    try:
        entry = json.dumps({"cwd": "/code/proj", "pane": "%1", "started_at": "2026-01-01T00:00:00Z",
                            "source": "startup", "git_branch": "main", "git_worktree": None})
        result = run_session_track_update(path, "sess-abc", "%1", entry, "%1|%2|")
        check("entry exists", "sess-abc" in result, True)
        check("git_branch set", result["sess-abc"]["git_branch"], "main")
        check("git_worktree null", result["sess-abc"]["git_worktree"], None)
        check("_name_index exists", "_name_index" in result, True)
    finally:
        os.unlink(path)


def test_session_track_preserves_name():
    """SessionStart (clear) preserves existing name and named_at."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {
                "cwd": "/code/proj", "pane": "%1", "started_at": "2026-01-01T00:00:00Z",
                "source": "startup", "name": "pricing API", "named_at": "2026-01-01T00:05:00Z"
            },
            "_name_index": {"pricing API": "sess-abc"}
        })
        entry = json.dumps({"cwd": "/code/proj", "pane": "%1", "started_at": "2026-01-01T01:00:00Z",
                            "source": "clear", "git_branch": "main", "git_worktree": None})
        result = run_session_track_update(path, "sess-abc", "%1", entry, "%1|")
        check("name preserved", result["sess-abc"]["name"], "pricing API")
        check("named_at preserved", result["sess-abc"]["named_at"], "2026-01-01T00:05:00Z")
        check("name_index preserved", result["_name_index"]["pricing API"], "sess-abc")
    finally:
        os.unlink(path)


def test_session_track_replaces_old_pane_session():
    """New session on same pane removes old session and cleans name index."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-old": {
                "cwd": "/code/proj", "pane": "%1", "started_at": "2026-01-01T00:00:00Z",
                "source": "startup", "name": "old task"
            },
            "_name_index": {"old task": "sess-old"}
        })
        entry = json.dumps({"cwd": "/code/proj", "pane": "%1", "started_at": "2026-01-01T01:00:00Z",
                            "source": "startup", "git_branch": None, "git_worktree": None})
        result = run_session_track_update(path, "sess-new", "%1", entry, "%1|")
        check("old session removed", "sess-old" not in result, True)
        check("new session exists", "sess-new" in result, True)
        check("old name removed from index", "old task" not in result["_name_index"], True)
    finally:
        os.unlink(path)


def test_session_track_prunes_dead_panes():
    """Dead panes are pruned and their names removed from index."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-alive": {"cwd": "/a", "pane": "%1", "started_at": "T", "source": "startup", "name": "alive"},
            "sess-dead": {"cwd": "/b", "pane": "%99", "started_at": "T", "source": "startup", "name": "dead task"},
            "_name_index": {"alive": "sess-alive", "dead task": "sess-dead"}
        })
        entry = json.dumps({"cwd": "/a", "pane": "%1", "started_at": "T2",
                            "source": "clear", "git_branch": None, "git_worktree": None})
        result = run_session_track_update(path, "sess-alive", "%1", entry, "%1|%2|")
        check("dead session pruned", "sess-dead" not in result, True)
        check("dead name removed from index", "dead task" not in result["_name_index"], True)
        check("alive session kept", "sess-alive" in result, True)
        check("alive name kept in index", result["_name_index"].get("alive"), "sess-alive")
    finally:
        os.unlink(path)


def test_session_track_skips_name_index_key():
    """_name_index is never treated as a session entry."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "_name_index": {"foo": "sess-x"},
            "sess-x": {"cwd": "/a", "pane": "%1", "started_at": "T", "source": "startup"}
        })
        entry = json.dumps({"cwd": "/b", "pane": "%2", "started_at": "T2",
                            "source": "startup", "git_branch": None, "git_worktree": None})
        # All panes are live — _name_index should survive intact
        result = run_session_track_update(path, "sess-y", "%2", entry, "%1|%2|")
        check("_name_index not deleted", "_name_index" in result, True)
        check("_name_index is dict", isinstance(result["_name_index"], dict), True)
    finally:
        os.unlink(path)


# ── pane-cleanup tests ───────────────────────────────────────────────────────

def test_pane_cleanup_removes_entry():
    """Cleanup removes session entry for the exiting pane."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {"cwd": "/a", "pane": "%5", "name": "my task"},
            "sess-other": {"cwd": "/b", "pane": "%6", "name": "other"},
            "_name_index": {"my task": "sess-abc", "other": "sess-other"}
        })
        result = run_pane_cleanup(path, "%5")
        check("session removed", "sess-abc" not in result, True)
        check("other session kept", "sess-other" in result, True)
        check("name removed from index", "my task" not in result["_name_index"], True)
        check("other name kept", result["_name_index"]["other"], "sess-other")
    finally:
        os.unlink(path)


def test_pane_cleanup_no_entry():
    """Cleanup with no matching pane is a no-op."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        original = {"sess-abc": {"cwd": "/a", "pane": "%5"}, "_name_index": {}}
        _write_map(path, original)
        result = run_pane_cleanup(path, "%99")
        check("no entries removed", "sess-abc" in result, True)
    finally:
        os.unlink(path)


def test_pane_cleanup_multiple_sessions_same_pane():
    """Edge case: multiple sessions on same pane (shouldn't happen, but handles it)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-1": {"cwd": "/a", "pane": "%5", "name": "first"},
            "sess-2": {"cwd": "/b", "pane": "%5", "name": "second"},
            "_name_index": {"first": "sess-1", "second": "sess-2"}
        })
        result = run_pane_cleanup(path, "%5")
        check("both sessions removed", "sess-1" not in result and "sess-2" not in result, True)
        check("both names removed", len(result["_name_index"]), 0)
    finally:
        os.unlink(path)


# ── rename tests ─────────────────────────────────────────────────────────────

def test_rename_sets_name():
    """Rename sets name, named_at, and updates _name_index."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {"cwd": "/a", "pane": "%1", "started_at": "T"},
            "_name_index": {}
        })
        result = run_rename_update(path, "sess-abc", "pricing API")
        check("name set", result["sess-abc"]["name"], "pricing API")
        check("named_at set", result["sess-abc"]["named_at"], "2026-02-24T21:15:00Z")
        check("name_index updated", result["_name_index"]["pricing API"], "sess-abc")
    finally:
        os.unlink(path)


def test_rename_replaces_old_name():
    """Renaming removes old name from index, adds new one."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {"cwd": "/a", "pane": "%1", "name": "old name", "named_at": "T"},
            "_name_index": {"old name": "sess-abc"}
        })
        result = run_rename_update(path, "sess-abc", "new name")
        check("old name removed from index", "old name" not in result["_name_index"], True)
        check("new name in index", result["_name_index"]["new name"], "sess-abc")
        check("entry has new name", result["sess-abc"]["name"], "new name")
    finally:
        os.unlink(path)


def test_rename_clears_name():
    """Empty name clears name and named_at fields."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {"cwd": "/a", "pane": "%1", "name": "old", "named_at": "T"},
            "_name_index": {"old": "sess-abc"}
        })
        result = run_rename_update(path, "sess-abc", "")
        check("name removed", "name" not in result["sess-abc"], True)
        check("named_at removed", "named_at" not in result["sess-abc"], True)
        check("old name removed from index", "old" not in result["_name_index"], True)
    finally:
        os.unlink(path)


def test_rename_adds_enrichment():
    """Rename captures enrichment snapshot."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {
            "sess-abc": {"cwd": "/a", "pane": "%1"},
            "_name_index": {}
        })
        result = run_rename_update(path, "sess-abc", "my task", {
            "git_branch": "feature/x",
            "git_worktree": "proj-feature-x",
            "active_bead": "PROJ-abc",
            "cullis_yolo": True,
            "cullis_profile": "dev",
            "remis_session": "rally-123",
        })
        entry = result["sess-abc"]
        check("git_branch", entry["git_branch"], "feature/x")
        check("git_worktree", entry["git_worktree"], "proj-feature-x")
        check("active_bead", entry["active_bead"], "PROJ-abc")
        check("cullis_yolo", entry["cullis_yolo"], True)
        check("cullis_profile", entry["cullis_profile"], "dev")
        check("remis_session", entry["remis_session"], "rally-123")
    finally:
        os.unlink(path)


def test_rename_nonexistent_session():
    """Rename on a session not yet in the map creates a new entry."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        _write_map(path, {"_name_index": {}})
        result = run_rename_update(path, "sess-new", "fresh")
        check("new entry created", "sess-new" in result, True)
        check("name set", result["sess-new"]["name"], "fresh")
        check("index updated", result["_name_index"]["fresh"], "sess-new")
    finally:
        os.unlink(path)


# ── tab title truncation tests ───────────────────────────────────────────────

def test_truncation_short():
    check("short name no truncation", truncate_tab_title("pricing"), "pricing")

def test_truncation_exact_10():
    check("exactly 10 chars", truncate_tab_title("0123456789"), "0123456789")

def test_truncation_11():
    check("11 chars truncated", truncate_tab_title("01234567890"), "0123456789...")

def test_truncation_long():
    check("long name truncated", truncate_tab_title("cancel detection flow"), "cancel det...")


# ── name column formatting tests ────────────────────────────────────────────

def test_column_empty():
    check("empty name shows dash", format_name_column(""), "—")

def test_column_none():
    check("None shows dash", format_name_column(None), "—")

def test_column_short():
    check("short name passes through", format_name_column("pricing"), "pricing")

def test_column_exact_15():
    check("exactly 15 chars", format_name_column("0123456789abcde"), "0123456789abcde")

def test_column_16():
    check("16 chars truncated", format_name_column("0123456789abcdef"), "0123456789ab...")

def test_column_long():
    check("long name truncated", format_name_column("cancel detection flow"), "cancel detec...")


# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # Session-track tests
    test_session_track_basic_entry()
    test_session_track_preserves_name()
    test_session_track_replaces_old_pane_session()
    test_session_track_prunes_dead_panes()
    test_session_track_skips_name_index_key()

    # Pane-cleanup tests
    test_pane_cleanup_removes_entry()
    test_pane_cleanup_no_entry()
    test_pane_cleanup_multiple_sessions_same_pane()

    # Rename tests
    test_rename_sets_name()
    test_rename_replaces_old_name()
    test_rename_clears_name()
    test_rename_adds_enrichment()
    test_rename_nonexistent_session()

    # Tab title truncation tests
    test_truncation_short()
    test_truncation_exact_10()
    test_truncation_11()
    test_truncation_long()

    # Name column formatting tests
    test_column_empty()
    test_column_none()
    test_column_short()
    test_column_exact_15()
    test_column_16()
    test_column_long()

    print(f"\n{TESTS_PASSED}/{TESTS_RUN} tests passed")
    if TESTS_PASSED < TESTS_RUN:
        print(f"  {TESTS_RUN - TESTS_PASSED} FAILED")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
