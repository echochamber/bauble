"""SessionPickerScreen — grouped pane list with navigation.

Replaces tmux-claude-picker's --popup mode. Shows all Claude panes
grouped by state (waiting first, then cancelled, done, working).
Uses FilterableList for browse-first selection.
"""

from __future__ import annotations

import os
import re

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux
from bauble_tui.state import load_pane_states, load_session_map
from bauble_tui.widgets.filterable_list import FilterableList, ListItem

# State display order and emoji
_STATE_ORDER = ["waiting", "cancelled", "done", "working"]
_STATE_EMOJI = {
    "waiting": "\U0001f7e1",    # 🟡
    "cancelled": "\U0001f6ab",  # 🚫
    "done": "\u2705",           # ✅
    "working": "\U0001f535",    # 🔵
}


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable string."""
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


def _extract_bead_ctx(window_name: str) -> str:
    """Extract bead context from window name (e.g., 'abc-123: description')."""
    if re.match(r'^[A-Za-z0-9]+-[A-Za-z0-9]+', window_name):
        return window_name.split(":")[0].strip()
    return ""


class SessionPickerScreen(Screen):
    """Session picker screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Sessions", id="picker-header", classes="popup-header")
        yield FilterableList(id="picker-list")

    def on_mount(self) -> None:
        items = self._gather_items()
        fl = self.query_one(FilterableList)
        fl.set_items(items)

    def _gather_items(self) -> list[ListItem]:
        """Gather all Claude panes, grouped by state."""
        panes = tmux.list_panes()
        pane_states = load_pane_states()
        session_map = load_session_map()

        # Collect pane info
        pane_infos: list[dict] = []
        for pane in panes:
            state = tmux.get_pane_option(pane.pane_id, "@bauble-state")
            if not state:
                continue

            cwd = tmux.get_pane_option(pane.pane_id, "@claude-cwd")
            name = tmux.get_pane_option(pane.pane_id, "@claude-name")
            waiting_tool = tmux.get_pane_option(pane.pane_id, "@claude-waiting-tool")
            window_name = pane.window_index  # We get this from list_panes

            # Get window name for bead context
            win_name = tmux.display_message(pane.pane_id, "#{window_name}")
            bead_ctx = _extract_bead_ctx(win_name)

            # Compute elapsed time
            ps = pane_states.get(pane.pane_id)
            elapsed = ps.elapsed_seconds if ps else 0
            elapsed_str = _format_elapsed(elapsed)

            # Build label
            label = name or os.path.basename(cwd) if cwd else f"pane {pane.pane_id}"
            location = f"{pane.session}:{pane.window_index}"

            pane_infos.append({
                "pane_id": pane.pane_id,
                "session": pane.session,
                "state": state,
                "label": label,
                "location": location,
                "elapsed": elapsed,
                "elapsed_str": elapsed_str,
                "waiting_tool": waiting_tool,
                "bead_ctx": bead_ctx,
                "cwd": cwd,
            })

        # Group by state
        grouped: dict[str, list[dict]] = {s: [] for s in _STATE_ORDER}
        for info in pane_infos:
            s = info["state"]
            if s not in grouped:
                grouped.setdefault("working", []).append(info)
            else:
                grouped[s].append(info)

        # Build ListItems
        items: list[ListItem] = []
        for state in _STATE_ORDER:
            group = grouped.get(state, [])
            if not group:
                continue
            emoji = _STATE_EMOJI.get(state, "")
            section_name = f"{state.capitalize()} ({len(group)})"

            for info in group:
                # Build display label
                parts = [f"{emoji} {info['label']}"]
                if info["bead_ctx"]:
                    parts.append(f"[{info['bead_ctx']}]")
                main_line = "  ".join(parts)

                detail_parts = []
                if info["waiting_tool"]:
                    detail_parts.append(f"→ {info['waiting_tool']}")
                detail_parts.append(info["elapsed_str"])
                detail_parts.append(info["location"])
                detail = "  ".join(detail_parts)

                display = f"{main_line}    {detail}"

                items.append(ListItem(
                    label=display,
                    data=info,
                    section=section_name,
                ))

        return items

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        """Navigate to the selected pane."""
        data = event.item.data
        pane_id = data.get("pane_id")
        session = data.get("session")
        if pane_id:
            # Switch session if different
            current_session = tmux.display_message(
                os.environ.get("TMUX_PANE", ""), "#{session_name}"
            )
            if session and session != current_session:
                tmux.switch_session(session)
            tmux.select_pane(pane_id)
        self.dismiss()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
