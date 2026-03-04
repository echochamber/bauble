"""Pane scrollback capture and regex scanning.

Shared by diff, files, glow, and notes screens.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from bauble_tui import tmux


def capture(pane_id: str, lines: int = 5000) -> str:
    """Capture pane scrollback content."""
    start = f"-{lines}" if lines > 0 else "-"
    return tmux.capture_pane(pane_id, start=start)


def find_file_urls(text: str) -> list[str]:
    """Extract file:// URLs from scrollback, deduplicated, most-recent-first."""
    pattern = re.compile(r'file://(/[^\s\'")\]>]+)')
    matches = pattern.findall(text)
    return _dedup_recent_first(matches)


def find_markdown_paths(text: str) -> list[str]:
    """Extract .md file paths from scrollback."""
    pattern = re.compile(r'(?:file://)?(/[^\s\'")\]>]*\.md)')
    matches = pattern.findall(text)
    # Also match ~/path patterns
    tilde_pattern = re.compile(r'(~/[^\s\'")\]>]*\.md)')
    tilde_matches = tilde_pattern.findall(text)
    # Expand ~ to home
    home = os.path.expanduser("~")
    expanded = [m.replace("~", home, 1) for m in tilde_matches]
    all_paths = matches + expanded
    # Filter to existing files
    existing = [p for p in all_paths if Path(p).is_file()]
    return _dedup_recent_first(existing)


def find_edit_markers(text: str) -> list[str]:
    """Extract files from Claude edit markers.

    Matches both formats:
      ⏺ Write(/path/to/file)   — parenthesized
      ⏺ Write /path/to/file    — space-separated
    """
    # Parenthesized format: ⏺ Write(/path)
    paren_re = re.compile(r'⏺\s*(?:Write|Update|Edit)\(([^)]+)\)', re.MULTILINE)
    paren_matches = paren_re.findall(text)

    # Space-separated format: ⏺ Write /path
    space_re = re.compile(r'⏺\s*(?:Write|Update|Edit)\s+(.+?)$', re.MULTILINE)
    space_matches = space_re.findall(text)

    all_matches = paren_matches + space_matches
    cleaned = [_clean_path(m) for m in all_matches]
    return _dedup_recent_first([p for p in cleaned if p])


def extract_session_diff(text: str, filepath: str) -> str | None:
    """Extract inline session diff content for a file from scrollback.

    Looks for the last Claude edit marker for this file and extracts the
    diff content below it. Returns the formatted diff text, or None.
    """
    home = os.path.expanduser("~")
    tilde_path = filepath.replace(home, "~", 1) if filepath.startswith(home) else filepath
    basename = os.path.basename(filepath)

    # Find the last edit marker for this file
    marker_re = re.compile(
        rf'⏺\s*(?:Write|Update|Edit)(?:\({re.escape(tilde_path)}\)'
        rf'|\({re.escape(filepath)}\)'
        rf'|\s+{re.escape(tilde_path)}'
        rf'|\s+{re.escape(filepath)})',
        re.MULTILINE,
    )

    lines = text.splitlines()
    marker_line = None
    for i, line in enumerate(lines):
        if marker_re.search(line):
            marker_line = i

    if marker_line is None:
        return None

    # Extract content below the marker until the next marker or non-diff line
    content_lines = [lines[marker_line]]
    blank_count = 0
    for line in lines[marker_line + 1:]:
        if line.startswith("⏺"):
            break
        if re.match(r'^[A-Z]', line) and len(content_lines) > 4:
            break
        if not line.strip():
            blank_count += 1
            if blank_count > 2:
                break
        else:
            blank_count = 0
        content_lines.append(line)

    if len(content_lines) <= 1:
        return None

    return f"Session diff: {basename}\nFile: {filepath}\n\n" + "\n".join(content_lines)


def find_changed_git_files(
    paths: list[str],
    *,
    max_items: int = 8,
) -> list[dict]:
    """Classify file paths as having git changes.

    Returns list of dicts with keys: path, type ("git"|"session"), git_root.
    """
    results: list[dict] = []
    seen: set[str] = set()

    for p in paths:
        if not p or p in seen or not Path(p).is_file():
            continue
        # Skip temp files
        if p.startswith("/tmp/"):
            continue
        seen.add(p)

        fdir = os.path.dirname(p)
        try:
            git_root = subprocess.run(
                ["git", "-C", fdir, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

        if not git_root:
            continue

        rel = os.path.relpath(p, git_root)
        # Check for git changes (staged or unstaged)
        try:
            unstaged = subprocess.run(
                ["git", "-C", git_root, "diff", "--quiet", "--", rel],
                capture_output=True,
            ).returncode != 0
            staged = subprocess.run(
                ["git", "-C", git_root, "diff", "--cached", "--quiet", "--", rel],
                capture_output=True,
            ).returncode != 0
        except FileNotFoundError:
            continue

        if unstaged or staged:
            results.append({"path": p, "type": "git", "git_root": git_root})
            if len(results) >= max_items:
                break

    return results


def save_session_diff(diff_text: str) -> str:
    """Save session diff text to a temp file, return the path."""
    fd, path = tempfile.mkstemp(prefix="bauble-sdiff-", suffix=".diff")
    with os.fdopen(fd, "w") as f:
        f.write(diff_text)
    return path


def _clean_path(path: str) -> str:
    """Clean a path string (strip ANSI codes, whitespace, quotes)."""
    # Strip ANSI escape sequences
    ansi_re = re.compile(r'\x1b\[[0-9;]*m')
    path = ansi_re.sub("", path).strip().strip("'\"")
    # Expand ~
    if path.startswith("~"):
        path = os.path.expanduser(path)
    return path


def _dedup_recent_first(items: list[str]) -> list[str]:
    """Deduplicate keeping most-recent-first order (last occurrence wins)."""
    seen: set[str] = set()
    result: list[str] = []
    for item in reversed(items):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
