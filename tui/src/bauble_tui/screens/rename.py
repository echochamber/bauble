"""RenameScreen — session rename form.

Replaces tmux-session-rename's popup mode. Takes a pane_id argument
(passed from tmux keybinding) and lets the user name/rename the session.

Fixes targeting bug: always operates on the provided pane_id, not the
focused pane (which inside a popup is the popup's pane).

Updates:
  1. @claude-name tmux pane option
  2. tmux window title (truncated to tab bar width)
  3. session-map.json with enrichment snapshot
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Static

from bauble_tui import tmux


class RenameScreen(Screen):
    """Session rename form screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, pane_id: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._pane_id = pane_id

    def compose(self) -> ComposeResult:
        yield Static("Name Session", id="rename-header", classes="popup-header")
        yield Input(
            placeholder="e.g. pricing API, cancel detection",
            id="rename-input",
        )
        yield Static("Enter to save  |  Empty to clear  |  Escape to cancel", classes="popup-footer")

    def on_mount(self) -> None:
        if not self._pane_id:
            self._show_status("No pane_id provided")
            return

        # Pre-fill with current name
        current_name = tmux.get_pane_option(self._pane_id, "@claude-name")
        rename_input = self.query_one("#rename-input", Input)
        if current_name:
            rename_input.value = current_name
        rename_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter — save the name."""
        if event.input.id != "rename-input":
            return

        name = event.value.strip()
        pane_id = self._pane_id
        if not pane_id:
            self.dismiss()
            return

        if not name:
            # Clear the name
            tmux.unset_pane_option(pane_id, "@claude-name")
            # Restore window name from cwd
            cwd = tmux.get_pane_option(pane_id, "@claude-cwd")
            if cwd:
                window_id = tmux.get_window_id(pane_id)
                if window_id:
                    tmux.rename_window(window_id, os.path.basename(cwd))
            self._show_status("Name cleared")
        else:
            # Set pane option
            tmux.set_pane_option(pane_id, "@claude-name", name)

            # Set window title (truncate for tab bar)
            tab_title = name if len(name) <= 20 else name[:20] + "..."
            window_id = tmux.get_window_id(pane_id)
            if window_id:
                tmux.rename_window(window_id, tab_title)

            self._show_status(f"Named \u2192 {name}")

        # Update session-map.json
        self._update_session_map(pane_id, name)

    def _update_session_map(self, pane_id: str, name: str) -> None:
        """Update session-map.json with name and enrichment snapshot."""
        session_id = tmux.get_pane_option(pane_id, "@claude-session")
        if not session_id:
            return

        map_path = Path.home() / ".claude" / "hooks" / "session-map.json"
        try:
            data = json.loads(map_path.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}

        name_index = data.get("_name_index", {})
        entry = data.get(session_id, {})
        if not isinstance(entry, dict):
            entry = {}

        # Remove old name from index
        old_name = entry.get("name")
        if old_name and name_index.get(old_name) == session_id:
            del name_index[old_name]

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if name:
            entry["name"] = name
            entry["named_at"] = now
            name_index[name] = session_id
        else:
            entry.pop("name", None)
            entry.pop("named_at", None)

        # Enrichment snapshot
        cwd = tmux.get_pane_option(pane_id, "@claude-cwd")
        if cwd and (Path(cwd) / ".git").exists():
            try:
                entry["git_branch"] = subprocess.run(
                    ["git", "-C", cwd, "branch", "--show-current"],
                    capture_output=True, text=True,
                ).stdout.strip() or None
            except FileNotFoundError:
                entry["git_branch"] = None

            # Detect worktree
            git_file = Path(cwd) / ".git"
            if git_file.is_file():
                try:
                    content = git_file.read_text()
                    for line in content.splitlines():
                        if line.startswith("gitdir: "):
                            wt_root = line[8:].split("/.git/worktrees/")[0]
                            entry["git_worktree"] = os.path.basename(wt_root)
                            break
                except OSError:
                    entry["git_worktree"] = None
            else:
                entry["git_worktree"] = None
        else:
            entry["git_branch"] = None
            entry["git_worktree"] = None

        # Active bead from window name
        window_name = tmux.display_message(pane_id, "#{window_name}")
        import re
        if re.match(r'^[A-Za-z]+-[a-z0-9]+$', window_name):
            entry["active_bead"] = window_name
        else:
            entry["active_bead"] = None

        # Cullis state
        cullis_yolo_path = Path.home() / ".claude" / "hooks" / "cullis-yolo.json"
        try:
            import time
            yolo_data = json.loads(cullis_yolo_path.read_text())
            entry["cullis_yolo"] = yolo_data.get("expires", 0) > time.time()
        except (OSError, json.JSONDecodeError):
            entry["cullis_yolo"] = False

        entry["cullis_profile"] = tmux.get_pane_option(pane_id, "@cullis-profile") or None
        entry["remis_session"] = tmux.get_pane_option(pane_id, "@remis-session") or None

        data[session_id] = entry
        data["_name_index"] = name_index

        # Atomic write
        tmp_path = str(map_path) + ".tmp"
        Path(tmp_path).write_text(json.dumps(data, indent=2) + "\n")
        os.replace(tmp_path, str(map_path))

    def _show_status(self, message: str) -> None:
        """Flash message in tmux status bar and dismiss immediately."""
        tmux.flash_message(message)
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
