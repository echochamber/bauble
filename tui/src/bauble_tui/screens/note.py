"""NoteScreen — simple quick note form.

Replaces tmux-quick-note's popup mode. Title + body form,
saves to ~/notes/quick/ with timestamp filename.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Static, TextArea

from bauble_tui import tmux
from bauble_tui.config import load_config


class NoteScreen(Screen):
    """Quick note form screen."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        Binding("ctrl+d", "save_note", "Save", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Quick Note", id="note-header", classes="popup-header")
        yield Input(placeholder="Title (optional \u2014 Enter to skip)", id="note-title")
        yield TextArea(id="note-body")
        yield Static("Ctrl+D to save  |  Escape to cancel", classes="popup-footer")

    def on_mount(self) -> None:
        self.query_one("#note-title", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter on title moves to body."""
        if event.input.id == "note-title":
            self.query_one("#note-body", TextArea).focus()

    def action_save_note(self) -> None:
        """Save the note (priority binding overrides TextArea's ctrl+d)."""
        config = load_config()
        quick_dir = Path(config.get("BAUBLE_QUICK_DIR", os.path.expanduser("~/notes/quick")))
        quick_dir.mkdir(parents=True, exist_ok=True)

        title = self.query_one("#note-title", Input).value.strip()
        body = self.query_one("#note-body", TextArea).text.strip()

        if not title and not body:
            self._show_status("Nothing to save.")
            return

        ts = datetime.now().strftime("%Y-%m-%d-%H%M")
        if title:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            filename = f"{ts}-{slug}.md"
        else:
            filename = f"{ts}-note.md"

        content = ""
        if title:
            content = f"# {title}\n\n"
        content += body

        (quick_dir / filename).write_text(content + "\n")
        tilde_dir = str(quick_dir).replace(os.path.expanduser("~"), "~", 1)
        self._show_status(f"Saved \u2192 {tilde_dir}/{filename}")

    def _show_status(self, message: str) -> None:
        """Flash message in tmux status bar and dismiss immediately."""
        tmux.flash_message(message)
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
