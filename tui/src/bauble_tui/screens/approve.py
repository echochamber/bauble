"""ApproveAllScreen — batch approval for waiting agents.

Replaces tmux-approve-all's --popup mode. Shows all waiting panes
in an ActionList with y/n/g/s per item. Enter executes all actions,
Escape aborts.
"""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux
from bauble_tui.config import load_config, get_color, get_tab_style
from bauble_tui.state import load_pane_states
from bauble_tui.widgets.action_list import ActionList, ActionItem, Action


def _format_elapsed(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return "<1m"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    remaining = mins % 60
    if remaining:
        return f"{hours}h{remaining}m"
    return f"{hours}h"


class ApproveAllScreen(Screen):
    """Batch approval screen for waiting agents."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Approve All", id="approve-header", classes="popup-header")
        yield ActionList(id="approve-list")

    def on_mount(self) -> None:
        items = self._gather_waiting()
        if not items:
            self.query_one(Static).update("No waiting agents")
            return
        al = self.query_one(ActionList)
        al.set_items(items)

    def _gather_waiting(self) -> list[ActionItem]:
        """Gather all waiting panes."""
        pane_states = load_pane_states()
        items: list[ActionItem] = []

        for pane_id, ps in pane_states.items():
            if ps.state != "waiting":
                continue

            name = tmux.get_pane_option(pane_id, "@claude-name")
            cwd = tmux.get_pane_option(pane_id, "@claude-cwd")
            waiting_tool = tmux.get_pane_option(pane_id, "@claude-waiting-tool")

            label_parts = [name or os.path.basename(cwd) if cwd else pane_id]
            if waiting_tool:
                label_parts.append(f"→ {waiting_tool}")
            label_parts.append(f"({_format_elapsed(ps.elapsed_seconds)})")
            label_parts.append(f"[{ps.session}]")

            items.append(ActionItem(
                label="  ".join(label_parts),
                data={
                    "pane_id": pane_id,
                    "session": ps.session,
                    "window_id": ps.window_id,
                    "cwd": cwd,
                    "waiting_tool": waiting_tool,
                },
            ))

        return items

    def on_action_list_execute(self, event: ActionList.Execute) -> None:
        """Execute all actions."""
        config = load_config()
        for item in event.items:
            pane_id = item.data.get("pane_id")
            if not pane_id:
                continue

            # Re-check pane still waiting before acting
            current_state = tmux.get_pane_option(pane_id, "@bauble-state")
            if current_state != "waiting":
                continue

            if item.action == Action.YES:
                tmux.send_keys(pane_id, "Enter")

            elif item.action == Action.NO:
                tmux.send_keys(pane_id, "Escape")
                # Set cancelled state and apply red tint
                tmux.set_pane_option(pane_id, "@bauble-state", "cancelled")
                cancelled_color = get_color(config, "cancelled")
                tmux.set_pane_style(pane_id, cancelled_color)
                # Update tab bar
                window_id = item.data.get("window_id")
                if window_id:
                    tab_style = get_tab_style(config, "cancelled")
                    tmux.set_window_option(window_id, "window-status-style", tab_style)
                    tmux.set_window_option(
                        window_id,
                        "window-status-current-style",
                        f"{tab_style},underscore,overline",
                    )

            elif item.action == Action.GOTO:
                # Navigate to this pane
                session = item.data.get("session")
                current_session = tmux.display_message(
                    os.environ.get("TMUX_PANE", ""), "#{session_name}"
                )
                if session and session != current_session:
                    tmux.switch_session(session)
                tmux.select_pane(pane_id)
                self.dismiss()
                return

            # Skip does nothing

        self.dismiss()

    def on_action_list_go_to(self, event: ActionList.GoTo) -> None:
        """Immediate GoTo navigation."""
        pane_id = event.item.data.get("pane_id")
        session = event.item.data.get("session")
        if pane_id:
            current_session = tmux.display_message(
                os.environ.get("TMUX_PANE", ""), "#{session_name}"
            )
            if session and session != current_session:
                tmux.switch_session(session)
            tmux.select_pane(pane_id)
        self.dismiss()

    def on_action_list_aborted(self, event: ActionList.Aborted) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
