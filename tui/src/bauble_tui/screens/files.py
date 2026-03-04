"""FilesScreen — file:// URL selector with viewer split.

Replaces tmux-files' --popup mode. Scans pane scrollback for file:// URLs,
validates they exist on disk, shows in FilterableList.
Selection opens a split with bat/less viewer.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux, scrollback
from bauble_tui.config import load_config
from bauble_tui.widgets.filterable_list import FilterableList, ListItem


def _viewer_script() -> str:
    """Return the path to the file viewer script."""
    # Resolve through symlinks to find scripts dir
    here = Path(__file__).resolve().parent.parent.parent.parent.parent
    viewer = here / "scripts" / "tmux-files-viewer"
    if viewer.is_file():
        return str(viewer)
    # Fallback: try installed location
    installed = Path.home() / ".claude" / "scripts" / "tmux-files-viewer"
    if installed.is_file():
        return str(installed)
    # Last resort: bat or less
    if shutil.which("bat"):
        return "bat --style=plain --paging=always"
    return "less"


class FilesScreen(Screen):
    """File URL selector screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Files", id="files-header", classes="popup-header")
        yield FilterableList(id="files-list")

    def on_mount(self) -> None:
        items = self._gather_files()
        fl = self.query_one(FilterableList)
        if not items:
            self.query_one(Static).update("No file:// URLs found in pane")
            return
        fl.set_items(items)

    def _gather_files(self) -> list[ListItem]:
        """Scan scrollback for file:// URLs."""
        config = load_config()
        max_items = int(config.get("BAUBLE_MAX_MENU_ITEMS", "8"))
        scroll_lines = config.get("BAUBLE_SCROLLBACK_LINES", "-")
        lines = 0 if scroll_lines == "-" else int(scroll_lines)

        pane_id = os.environ.get("TMUX_PANE", "")
        if not pane_id:
            return []

        text = scrollback.capture(pane_id, lines=lines)
        if not text:
            return []

        urls = scrollback.find_file_urls(text)
        items: list[ListItem] = []

        for p in urls:
            if len(items) >= max_items:
                break
            if not Path(p).is_file():
                continue
            basename = os.path.basename(p)
            parent = os.path.basename(os.path.dirname(p))
            items.append(ListItem(
                label=f"{parent}/{basename}",
                data={"path": p},
            ))

        return items

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        """Open the selected file in a viewer split."""
        filepath = event.item.data.get("path")
        if not filepath:
            self.dismiss()
            return

        pane_id = os.environ.get("TMUX_PANE", "")
        config = load_config()
        split_width = int(config.get("BAUBLE_SPLIT_WIDTH", "100"))
        viewer = _viewer_script()

        cmd = f"'{viewer}' '{filepath}'"
        tmux.split_window(pane_id, cmd, width=split_width)
        self.dismiss()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
