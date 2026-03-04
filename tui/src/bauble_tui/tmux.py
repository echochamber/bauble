"""Thin wrappers around tmux CLI.

All functions accept explicit pane/window targets — never rely on implicit
focus. See pane-tint.sh header comment for why this matters: hooks run as
background processes where the implicit "current" window is the focused
window, not the pane's window.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


def _run(args: list[str], check: bool = False) -> str:
    """Run a tmux command, return stdout. Silently returns '' on failure."""
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            check=check,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


@dataclass
class PaneInfo:
    """Parsed tmux pane information."""

    session: str
    window_index: str
    window_id: str
    pane_id: str
    pane_current_path: str
    pane_width: int
    pane_height: int


def list_panes(session: str | None = None) -> list[PaneInfo]:
    """List all panes, optionally filtered by session."""
    fmt = "#{session_name}\t#{window_index}\t#{window_id}\t#{pane_id}\t#{pane_current_path}\t#{pane_width}\t#{pane_height}"
    args = ["list-panes", "-a", "-F", fmt]
    if session:
        args = ["list-panes", "-s", "-t", session, "-F", fmt]
    output = _run(args)
    if not output:
        return []
    panes = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        panes.append(PaneInfo(
            session=parts[0],
            window_index=parts[1],
            window_id=parts[2],
            pane_id=parts[3],
            pane_current_path=parts[4],
            pane_width=int(parts[5]),
            pane_height=int(parts[6]),
        ))
    return panes


def get_pane_option(pane_id: str, key: str) -> str:
    """Read a pane option (e.g., @bauble-state). Returns '' if unset."""
    return _run(["show-option", "-p", "-t", pane_id, "-qv", key])


def set_pane_option(pane_id: str, key: str, value: str) -> None:
    """Set a pane option."""
    _run(["set-option", "-p", "-t", pane_id, "-q", key, value])


def unset_pane_option(pane_id: str, key: str) -> None:
    """Unset (remove) a pane option."""
    _run(["set-option", "-p", "-t", pane_id, "-qu", key])


def display_message(pane_id: str, fmt: str) -> str:
    """Run tmux display-message with a format string targeting a pane."""
    return _run(["display-message", "-p", "-t", pane_id, fmt])


def get_window_id(pane_id: str) -> str:
    """Get the window ID containing a pane."""
    return display_message(pane_id, "#{window_id}")


def send_keys(pane_id: str, keys: str) -> None:
    """Send keys to a pane."""
    _run(["send-keys", "-t", pane_id, keys])


def select_pane(pane_id: str) -> None:
    """Focus a pane (includes selecting its window)."""
    _run(["select-window", "-t", pane_id])
    _run(["select-pane", "-t", pane_id])


def switch_session(session: str) -> None:
    """Switch the client to a different session."""
    _run(["switch-client", "-t", session])


def split_window(
    pane_id: str,
    command: str,
    width: int = 100,
    vertical_pct: str = "60%",
) -> None:
    """Open a split window with adaptive direction.

    Horizontal split at `width` columns if the pane is wide enough,
    otherwise vertical split at `vertical_pct`.
    """
    pane_width = int(display_message(pane_id, "#{pane_width}") or "0")
    if pane_width // 2 > width:
        _run(["split-window", "-h", "-l", str(width), "-t", pane_id, command])
    else:
        _run(["split-window", "-v", "-l", vertical_pct, "-t", pane_id, command])


def capture_pane(pane_id: str, start: str = "-5000") -> str:
    """Capture pane scrollback content."""
    return _run(["capture-pane", "-p", "-S", start, "-t", pane_id])


def list_windows(session: str | None = None) -> list[dict[str, str]]:
    """List windows with index and current path."""
    fmt = "#{window_index}\t#{window_id}\t#{window_name}\t#{pane_current_path}"
    args = ["list-windows", "-F", fmt]
    if session:
        args.insert(1, "-t")
        args.insert(2, session)
    output = _run(args)
    if not output:
        return []
    windows = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        windows.append({
            "index": parts[0],
            "id": parts[1],
            "name": parts[2],
            "path": parts[3],
        })
    return windows


def set_window_option(window_id: str, key: str, value: str) -> None:
    """Set a window option."""
    _run(["set-window-option", "-t", window_id, "-q", key, value])


def set_pane_style(pane_id: str, bg_color: str) -> None:
    """Set pane background color (both focused and unfocused)."""
    style = f"bg={bg_color}"
    _run(["set-option", "-p", "-t", pane_id, "-q", "window-style", style])
    _run(["set-option", "-p", "-t", pane_id, "-q", "window-active-style", style])


def flash_message(message: str) -> None:
    """Show a brief message in the tmux status bar."""
    _run(["display-message", message])


def rename_window(window_id: str, name: str) -> None:
    """Rename a tmux window."""
    _run(["rename-window", "-t", window_id, name])


def new_window(path: str, name: str | None = None) -> None:
    """Create a new window at the given path."""
    args = ["new-window", "-c", path]
    if name:
        args.extend(["-n", name])
    _run(args)
