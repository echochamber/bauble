"""BaubleApp — Textual application shell.

Screen registry and theme loading from bauble.conf colors.
Screens are registered by name and launched via `bauble-ui <screen>`.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from bauble_tui.config import load_config, get_color

# Import screens to trigger registration
def _register_screens() -> None:
    """Register all available screens."""
    from bauble_tui.screens.picker import SessionPickerScreen
    from bauble_tui.screens.approve import ApproveAllScreen
    from bauble_tui.screens.diff import DiffScreen
    from bauble_tui.screens.files import FilesScreen
    from bauble_tui.screens.notes import NotesScreen
    from bauble_tui.screens.glow import GlowScreen
    from bauble_tui.screens.worktree import WorktreeScreen
    from bauble_tui.screens.capture import CaptureScreen
    from bauble_tui.screens.note import NoteScreen
    from bauble_tui.screens.rename import RenameScreen
    from bauble_tui.screens.cheatsheet import CheatsheetScreen
    from bauble_tui.screens.beads import BeadsDashboardScreen
    BaubleApp.register_screen("picker", SessionPickerScreen)
    BaubleApp.register_screen("approve", ApproveAllScreen)
    BaubleApp.register_screen("diff", DiffScreen)
    BaubleApp.register_screen("files", FilesScreen)
    BaubleApp.register_screen("notes", NotesScreen)
    BaubleApp.register_screen("glow", GlowScreen)
    BaubleApp.register_screen("worktree", WorktreeScreen)
    BaubleApp.register_screen("capture", CaptureScreen)
    BaubleApp.register_screen("note", NoteScreen)
    BaubleApp.register_screen("rename", RenameScreen)
    BaubleApp.register_screen("cheatsheet", CheatsheetScreen)
    BaubleApp.register_screen("beads", BeadsDashboardScreen)

# CSS file path — resolve from package location to bauble/config/
# __file__ is bauble/tui/src/bauble_tui/app.py → up 4 levels → bauble/config/
_PKG_DIR = Path(__file__).resolve().parent
CSS_PATH = _PKG_DIR.parent.parent.parent / "config" / "bauble.tcss"


class BaubleApp(App):
    """Bauble TUI application."""

    TITLE = "bauble"
    CSS_PATH = CSS_PATH if CSS_PATH.is_file() else None

    # Screen name → Screen class (populated by register_screen)
    _screen_registry: dict[str, type] = {}

    def __init__(self, screen_name: str | None = None, screen_args: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._initial_screen = screen_name
        self._screen_args = screen_args or []
        self._config = load_config()
        _register_screens()

    @classmethod
    def register_screen(cls, name: str, screen_class: type) -> None:
        """Register a screen class by name."""
        cls._screen_registry[name] = screen_class

    @classmethod
    def available_screens(cls) -> list[str]:
        """List registered screen names."""
        return sorted(cls._screen_registry.keys())

    def on_mount(self) -> None:
        """Push the requested screen on startup."""
        if self._initial_screen and self._initial_screen in self._screen_registry:
            screen_cls = self._screen_registry[self._initial_screen]
            # Exit the app when the screen is dismissed (popup should close)
            self.push_screen(screen_cls(*self._screen_args), callback=lambda _: self.exit())
        elif not self._initial_screen:
            # No screen specified — show help and exit
            self.exit(message="No screen specified")

    @property
    def config(self) -> dict[str, str]:
        """Access loaded bauble config."""
        return self._config

    def get_color(self, state: str) -> str:
        """Get pane background color for a state."""
        return get_color(self._config, state)
