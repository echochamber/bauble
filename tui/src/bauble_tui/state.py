"""Read bauble state files: bauble-state.json and session-map.json.

These files are written by bash hooks (pane-tint.sh, session-track.sh)
and read by popup scripts for display.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


STATE_FILE = Path(os.path.expanduser("~/.claude/hooks/bauble-state.json"))
SESSION_MAP_FILE = Path(os.path.expanduser("~/.claude/hooks/session-map.json"))


@dataclass
class PaneState:
    """State of a single pane from bauble-state.json."""

    pane_id: str
    state: str  # working, waiting, done, cancelled
    updated_at: float
    session: str = ""
    window_id: str = ""
    cwd: str = ""

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since last state update."""
        return time.time() - self.updated_at

    @property
    def elapsed_display(self) -> str:
        """Human-readable elapsed time (e.g., '2m', '1h 5m')."""
        secs = int(self.elapsed_seconds)
        if secs < 60:
            return f"{secs}s"
        mins = secs // 60
        if mins < 60:
            return f"{mins}m"
        hours = mins // 60
        remaining_mins = mins % 60
        if remaining_mins:
            return f"{hours}h {remaining_mins}m"
        return f"{hours}h"


@dataclass
class SessionInfo:
    """Metadata for a session from session-map.json."""

    pane_id: str
    name: str = ""
    cwd: str = ""
    git_branch: str = ""
    bead_id: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def load_pane_states() -> dict[str, PaneState]:
    """Load all pane states from bauble-state.json."""
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    states: dict[str, PaneState] = {}
    for pane_id, info in data.items():
        if not isinstance(info, dict):
            continue
        states[pane_id] = PaneState(
            pane_id=pane_id,
            state=info.get("state", "working"),
            updated_at=info.get("updated_at", 0),
            session=info.get("session", ""),
            window_id=info.get("window_id", ""),
            cwd=info.get("cwd", ""),
        )
    return states


def load_session_map() -> dict[str, SessionInfo]:
    """Load session metadata from session-map.json."""
    if not SESSION_MAP_FILE.is_file():
        return {}
    try:
        data = json.loads(SESSION_MAP_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    sessions: dict[str, SessionInfo] = {}
    for pane_id, info in data.items():
        if not isinstance(info, dict):
            continue
        sessions[pane_id] = SessionInfo(
            pane_id=pane_id,
            name=info.get("name", ""),
            cwd=info.get("cwd", ""),
            git_branch=info.get("git_branch", ""),
            bead_id=info.get("bead_id", ""),
            extra={k: v for k, v in info.items()
                   if k not in ("name", "cwd", "git_branch", "bead_id")},
        )
    return sessions


def get_pane_state(pane_id: str) -> PaneState | None:
    """Get state for a specific pane."""
    states = load_pane_states()
    return states.get(pane_id)


def get_waiting_panes() -> list[PaneState]:
    """Get all panes in the waiting state, sorted by elapsed time (longest first)."""
    states = load_pane_states()
    waiting = [s for s in states.values() if s.state == "waiting"]
    waiting.sort(key=lambda s: s.updated_at)
    return waiting
