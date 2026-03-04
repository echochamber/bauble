"""CaptureScreen — multi-route quick capture form.

Replaces tmux-quick-capture's popup mode. Routes input to:
  Note → ~/notes/quick/
  Bead → bd create (engineering task)
  Linear → linear-add (personal task queue)
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Static, TextArea, OptionList
from textual.widgets.option_list import Option

from bauble_tui import tmux
from bauble_tui.config import load_config


class CaptureScreen(Screen):
    """Multi-route quick capture screen."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        Binding("ctrl+d", "save_note", "Save", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Quick Capture", id="capture-header", classes="popup-header")
        yield OptionList(
            Option("Note  \u2192 save to notes/quick/"),
            Option("Bead  \u2192 bd create (engineering task)"),
            Option("Linear \u2192 personal task queue"),
            id="route-chooser",
        )
        with Vertical(id="note-form"):
            yield Input(placeholder="Title (optional \u2014 Enter to skip)", id="note-title")
            yield TextArea(id="note-body")
            yield Static("Ctrl+D to save", classes="popup-footer")
        with Vertical(id="bead-form"):
            yield Input(placeholder="Issue title", id="bead-title")
            yield OptionList(
                Option("task"), Option("bug"), Option("feature"),
                id="bead-type",
            )
            yield OptionList(
                Option("P2 (medium)"), Option("P1 (high)"),
                Option("P3 (low)"), Option("P0 (critical)"), Option("P4 (backlog)"),
                id="bead-priority",
            )
            yield Input(placeholder="Description (optional)", id="bead-desc")
            yield Static("Enter on description to create", classes="popup-footer")
        with Vertical(id="linear-form"):
            yield Input(placeholder="Task description", id="linear-title")
            yield Static("Enter to add to Linear", classes="popup-footer")

    def on_mount(self) -> None:
        # Hide all forms initially — show after route selection
        self.query_one("#note-form").display = False
        self.query_one("#bead-form").display = False
        self.query_one("#linear-form").display = False
        self.query_one("#route-chooser", OptionList).focus()
        self._route: str = ""

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle route selection or type/priority selection in bead form."""
        option_list_id = event.option_list.id

        if option_list_id == "route-chooser":
            label = str(event.option.prompt)
            self.query_one("#route-chooser").display = False
            if label.startswith("Note"):
                self._route = "note"
                self.query_one("#note-form").display = True
                self.query_one("#note-title", Input).focus()
            elif label.startswith("Bead"):
                self._route = "bead"
                self.query_one("#bead-form").display = True
                self.query_one("#bead-title", Input).focus()
            elif label.startswith("Linear"):
                self._route = "linear"
                self.query_one("#linear-form").display = True
                self.query_one("#linear-title", Input).focus()
            return

        # For bead form: type and priority selections advance to next field
        if option_list_id == "bead-type":
            self.query_one("#bead-priority", OptionList).focus()
        elif option_list_id == "bead-priority":
            self.query_one("#bead-desc", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input fields."""
        input_id = event.input.id

        if input_id == "note-title":
            self.query_one("#note-body", TextArea).focus()
        elif input_id == "bead-title":
            self.query_one("#bead-type", OptionList).focus()
        elif input_id == "bead-desc":
            self._create_bead()
        elif input_id == "linear-title":
            self._create_linear()

    def action_save_note(self) -> None:
        """Save note on Ctrl+D (priority binding overrides TextArea)."""
        if self._route == "note":
            self._save_note()

    def _save_note(self) -> None:
        """Save note to quick dir."""
        config = load_config()
        quick_dir = Path(config.get("BAUBLE_QUICK_DIR", os.path.expanduser("~/notes/quick")))
        quick_dir.mkdir(parents=True, exist_ok=True)

        title = self.query_one("#note-title", Input).value.strip()
        body = self.query_one("#note-body", TextArea).text.strip()

        if not title and not body:
            self._show_status("Nothing to save.", style="dim")
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
        self._show_status(f"Saved \u2192 {tilde_dir}/{filename}", style="green")

    def _create_bead(self) -> None:
        """Create a beads issue."""
        title = self.query_one("#bead-title", Input).value.strip()
        if not title:
            self._show_status("No title.", style="dim")
            return

        # Get type from selection
        type_list = self.query_one("#bead-type", OptionList)
        type_idx = type_list.highlighted or 0
        bead_type = str(type_list.get_option_at_index(type_idx).prompt)

        # Get priority from selection
        prio_list = self.query_one("#bead-priority", OptionList)
        prio_idx = prio_list.highlighted or 0
        prio_label = str(prio_list.get_option_at_index(prio_idx).prompt)
        prio_num = prio_label[1] if len(prio_label) > 1 else "2"

        desc = self.query_one("#bead-desc", Input).value.strip()

        args = ["bd", "create", f"--title={title}", f"--type={bead_type}", f"--priority={prio_num}"]
        if desc:
            args.append(f"--description={desc}")

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Try to extract bead ID from output
                match = re.search(r'[A-Za-z]+-[a-z0-9]+', result.stdout)
                bead_id = match.group() if match else ""
                if bead_id:
                    self._show_status(f"Created bead {bead_id}: {title}", style="yellow")
                else:
                    self._show_status(f"Created bead: {title}", style="yellow")
            else:
                self._show_status(f"Failed: {result.stderr.strip()}", style="red")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self._show_status(f"Failed: {e}", style="red")
            return

    def _create_linear(self) -> None:
        """Add task to Linear."""
        title = self.query_one("#linear-title", Input).value.strip()
        if not title:
            self._show_status("No title.", style="dim")
            return

        try:
            result = subprocess.run(
                ["linear-add", title],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                self._show_status("Added to Linear backlog", style="magenta")
            else:
                self._show_status(f"Failed: {result.stderr.strip()}", style="red")
                return
        except FileNotFoundError:
            self._show_status("linear-add not found on PATH", style="red")
            return
        except subprocess.TimeoutExpired:
            self._show_status("Timed out adding to Linear", style="red")
            return

    def _show_status(self, message: str, style: str = "") -> None:
        """Flash message in tmux status bar and dismiss immediately."""
        tmux.flash_message(message)
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
