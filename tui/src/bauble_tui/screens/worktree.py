"""WorktreeScreen — git worktree picker.

Replaces tmux-worktree's --popup mode. Lists active git worktrees,
shows which have existing tmux windows. Selection navigates to
existing window or creates a new one.
"""

from __future__ import annotations

import os
import subprocess

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux
from bauble_tui.widgets.filterable_list import FilterableList, ListItem


class WorktreeScreen(Screen):
    """Worktree picker screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Worktrees", id="worktree-header", classes="popup-header")
        yield FilterableList(id="worktree-list")

    def on_mount(self) -> None:
        items = self._gather_worktrees()
        fl = self.query_one(FilterableList)
        if not items:
            self.query_one(Static).update("No worktrees found")
            return
        fl.set_items(items)

    def _gather_worktrees(self) -> list[ListItem]:
        """List git worktrees with window associations."""
        try:
            output = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True, text=True, check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

        # Parse porcelain output
        worktrees: list[dict] = []
        current: dict = {}
        for line in output.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[9:]}
            elif line.startswith("branch refs/heads/"):
                current["branch"] = line[18:]
            elif line == "bare":
                current["bare"] = True
        if current:
            worktrees.append(current)

        if len(worktrees) <= 1:
            return []

        # Get current tmux windows to find existing window for each worktree
        windows = tmux.list_windows()
        window_by_path: dict[str, str] = {}
        for w in windows:
            window_by_path[w["path"]] = w["index"]

        items: list[ListItem] = []
        for wt in worktrees:
            path = wt.get("path", "")
            if not path:
                continue
            dirname = os.path.basename(path)
            branch = wt.get("branch", dirname)
            existing_window = window_by_path.get(path)

            label = dirname
            if existing_window:
                label = f"{dirname} (win {existing_window})"

            items.append(ListItem(
                label=label,
                data={
                    "path": path,
                    "branch": branch,
                    "existing_window": existing_window,
                },
            ))

        return items

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        """Navigate to or create window for selected worktree."""
        data = event.item.data
        existing_window = data.get("existing_window")
        wt_path = data.get("path")

        if existing_window:
            # Select existing window
            tmux._run(["select-window", "-t", f":{existing_window}"])
        elif wt_path:
            # Create new window at worktree path
            tmux.new_window(wt_path)

        self.dismiss()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
