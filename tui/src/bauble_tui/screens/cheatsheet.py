"""CheatsheetScreen — keybinding reference.

Replaces tmux-cheatsheet's less-based display. Shows all bauble
keybindings and configuration in a scrollable Textual view.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

_SHEET = """\
  Bauble Keybindings  (prefix+g, then…)
  ════════════════════════════════════════

  m     Markdown viewer (scan pane for .md → glow split)
  b     Beads dashboard (in-progress, epics, ready)
  w     Worktree picker (switch or open split)
  d     Diff viewer (scan pane for edited files → per-file diff)
  f     File viewer (scan pane for file:// URLs → bat/less split)
  n     Notes browser (saved notes by session)
  c     Quick capture (note / bead / Linear task)
  s     Session picker (all Claude panes, grouped by state)
  a     Approve all (batch-approve waiting agents from one popup)
  r     Rename session (name for tab + metadata)
  ?     This cheatsheet
  y     Clear pane tint

  Session Navigator  (direct prefix bindings)
  ──────────────────────────────────────────

  prefix+Home   Jump to next waiting agent (cycles, wraps)
                Auto-returns to origin after approval
  prefix+End    Go back (breadcrumb menu of origin panes)

  Glow Viewer  (after selecting a .md file)
  ──────────────────────────────────────────

  After quitting glow (q):
    s   Save copy to ~/notes/ (with session provenance)
    c   Copy file path to clipboard
    q   Close

  Diff Viewer
  ───────────

  Scans pane scrollback for file paths, cross-references with
  git changes. Most recently mentioned files shown first.
  Falls back to all changed files if no pane matches found.

  CLI Tools
  ─────────

  tmux-claim-bead <id>    Claim bead + rename window
  tmux-agent-status       Fleet status (in status bar)
  cullis status           Active permission profiles
  cullis yolo <duration>  Enable yolo mode
  cullis check "<cmd>"    Would this be auto-approved?

  Pane Colors
  ───────────

  dark blue     Agent is working
  dark amber    Agent needs approval (+ Glass sound)
  dark green    Agent is done (+ Hero sound)

  Tab colors match pane state. Multi-pane tabs show the
  highest-priority state (waiting > done > working).

  Status Bar
  ──────────

  🟡 N             N agents waiting for approval
  ✅ N             N agents done
  🔓 1h30m (2/3)  Cullis yolo active, time left (matched/total)

  Config
  ──────

  Create ~/.config/bauble.conf with any subset of:
    BAUBLE_COLOR_WORKING=#1a1e2e    Pane tint (working)
    BAUBLE_COLOR_WAITING=#302a1a    Pane tint (waiting)
    BAUBLE_COLOR_DONE=#192b1e       Pane tint (done)
    BAUBLE_COLOR_CANCELLED=#2b1a1a  Pane tint (cancelled)
    BAUBLE_SNAPS_DIR=~/notes/snaps  Save location for viewers
    BAUBLE_QUICK_DIR=~/notes/quick  Quick capture notes dir
    BAUBLE_NOTES_DIR=~/notes        Notes browser root dir
    BAUBLE_MAX_MENU_ITEMS=8         Max items in popup menus
    BAUBLE_SCROLLBACK_LINES=5000    Pane lines to scan
    BAUBLE_CANCEL_THRESHOLD=30      Stale detection (seconds)
    BAUBLE_SPLIT_WIDTH=100          Side viewer split width

  Env var BAUBLE_CONFIG overrides config file location.
"""


class CheatsheetScreen(Screen):
    """Scrollable keybinding reference screen."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    CheatsheetScreen {
        align: center middle;
    }

    CheatsheetScreen #cheatsheet-body {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_SHEET, id="cheatsheet-body")

    def action_dismiss(self) -> None:
        self.dismiss()
