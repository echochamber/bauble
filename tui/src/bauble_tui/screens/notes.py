"""NotesScreen — two-level notes browser.

Pick a directory under ~/notes/, then pick a file within it.
Selection opens in a glow viewer split.
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux
from bauble_tui.config import load_config
from bauble_tui.widgets.filterable_list import FilterableList, ListItem


def _viewer_script() -> str:
    """Return the path to the glow viewer script."""
    here = Path(__file__).resolve().parent.parent.parent.parent.parent
    viewer = here / "scripts" / "tmux-glow-viewer"
    if viewer.is_file():
        return str(viewer)
    installed = Path.home() / ".claude" / "scripts" / "tmux-glow-viewer"
    if installed.is_file():
        return str(installed)
    return "less"


class NotesScreen(Screen):
    """Two-level notes browser: pick dir → pick file."""

    BINDINGS = [("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("Notes", id="notes-header", classes="popup-header")
        yield FilterableList(id="notes-list")

    def on_mount(self) -> None:
        config = load_config()
        self._notes_dir = Path(config.get("BAUBLE_NOTES_DIR", os.path.expanduser("~/notes")))
        self._level = "dir"
        self._show_dirs()

    def _show_dirs(self) -> None:
        """Show subdirectories of notes dir."""
        self._level = "dir"
        header = self.query_one("#notes-header", Static)
        tilde = str(self._notes_dir).replace(os.path.expanduser("~"), "~", 1)
        header.update(f"Notes  {tilde}/")

        if not self._notes_dir.is_dir():
            header.update("No notes directory")
            return

        items: list[ListItem] = []

        # Top-level files get a virtual "(root)" entry
        root_files = [f for f in self._notes_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if root_files:
            items.append(ListItem(
                label=f". ({len(root_files)} files)",
                data={"dir": str(self._notes_dir)},
            ))

        # Subdirectories sorted alphabetically
        for d in sorted(self._notes_dir.iterdir(), key=lambda p: p.name.lower()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            file_count = sum(1 for f in d.iterdir() if f.is_file() and not f.name.startswith("."))
            if file_count == 0:
                continue
            items.append(ListItem(
                label=f"{d.name}/ ({file_count})",
                data={"dir": str(d)},
            ))

        fl = self.query_one(FilterableList)
        if not items:
            header.update("No notes found")
            return
        fl.set_items(items)
        fl.query_one("#option-list").focus()

    def _show_files(self, dir_path: Path) -> None:
        """Show files within a directory, most recent first."""
        self._level = "files"
        self._current_dir = dir_path

        tilde = str(dir_path).replace(os.path.expanduser("~"), "~", 1)
        header = self.query_one("#notes-header", Static)
        header.update(f"Notes  {tilde}/")

        files = sorted(
            [f for f in dir_path.iterdir() if f.is_file() and not f.name.startswith(".")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        items: list[ListItem] = []
        for f in files:
            items.append(ListItem(
                label=f.name,
                data={"path": str(f)},
            ))

        fl = self.query_one(FilterableList)
        if not items:
            header.update(f"{tilde}/ is empty")
            self.set_timer(1.0, lambda: self._show_dirs())
            return
        fl.set_items(items)
        fl.query_one("#option-list").focus()

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        """Handle selection — dir or file depending on level."""
        if self._level == "dir":
            dir_path = event.item.data.get("dir")
            if dir_path:
                self._show_files(Path(dir_path))
        elif self._level == "files":
            filepath = event.item.data.get("path")
            if not filepath:
                self.dismiss()
                return
            self._open_file(filepath)

    def _open_file(self, filepath: str) -> None:
        """Open selected file in a glow viewer split."""
        pane_id = os.environ.get("TMUX_PANE", "")
        config = load_config()
        split_width = int(config.get("BAUBLE_SPLIT_WIDTH", "100"))
        viewer = _viewer_script()

        cmd = f"'{viewer}' '{filepath}'"
        tmux.split_window(pane_id, cmd, width=split_width)
        self.dismiss()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.action_go_back()

    def action_go_back(self) -> None:
        """Escape: go back to dirs, or dismiss if already at dir level."""
        if self._level == "files":
            self._show_dirs()
        else:
            self.dismiss()
