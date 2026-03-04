"""BeadsDashboardScreen — dependency-aware beads overview.

Replaces tmux-beads popup. Wraps the existing tmux-beads-render.py
output in a scrollable Textual view with ANSI color support.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


def _render_dashboard() -> str:
    """Run the existing beads renderer and capture its output."""
    # Find the renderer script
    here = Path(__file__).resolve().parent.parent.parent.parent.parent
    renderer = here / "scripts" / "tmux-beads-render.py"
    if not renderer.is_file():
        # Try installed location
        renderer = Path.home() / ".claude" / "scripts" / "tmux-beads-render.py"

    if renderer.is_file():
        try:
            result = subprocess.run(
                ["python3", str(renderer)],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout.strip():
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: use bd commands directly
    sections = []

    try:
        # In-progress
        result = subprocess.run(
            ["bd", "list", "--status=in_progress"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            sections.append("  In Progress\n  " + "─" * 30)
            sections.append(result.stdout.strip())

        # Ready
        result = subprocess.run(
            ["bd", "ready"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            sections.append("\n  Ready\n  " + "─" * 30)
            sections.append(result.stdout.strip())

        # Stats
        result = subprocess.run(
            ["bd", "stats"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            sections.append("\n  " + result.stdout.strip())

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "  bd (beads) not found or timed out"

    return "\n".join(sections) if sections else "  No beads data"


class BeadsDashboardScreen(Screen):
    """Beads dashboard with dependency tree view."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    BeadsDashboardScreen {
        align: center middle;
    }

    BeadsDashboardScreen #beads-body {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Loading...", id="beads-body")

    def on_mount(self) -> None:
        """Load dashboard content (run in worker to avoid blocking)."""
        self.run_worker(self._load_content)

    async def _load_content(self) -> None:
        """Load and display dashboard content."""
        import asyncio
        content = await asyncio.to_thread(_render_dashboard)
        self.query_one("#beads-body", Static).update(content)

    def action_dismiss(self) -> None:
        self.dismiss()
