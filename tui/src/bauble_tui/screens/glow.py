"""GlowScreen — markdown file selector with glow viewer.

Replaces tmux-glow's popup mode. Scans pane scrollback for .md file paths,
validates they exist, shows in FilterableList.
Selection opens in a glow viewer split.
"""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux, scrollback
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


class GlowScreen(Screen):
    """Markdown file selector screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Markdown Files", id="glow-header", classes="popup-header")
        yield FilterableList(id="glow-list")

    def on_mount(self) -> None:
        items = self._gather_markdown()
        fl = self.query_one(FilterableList)
        if not items:
            self.query_one(Static).update("No .md files found in pane")
            return
        fl.set_items(items)

    def _gather_markdown(self) -> list[ListItem]:
        """Scan scrollback for .md file paths."""
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

        paths = scrollback.find_markdown_paths(text)
        items: list[ListItem] = []

        for p in paths:
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
        """Open the selected markdown file in a glow viewer split."""
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
