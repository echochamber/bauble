"""ActionList — per-item action list widget for bauble popups.

Each item has an action state: Skip (default) / Yes / No / GoTo.
Keys on focused item: y=approve, n=cancel, g=goto, s=skip.
Color-coded badges per item. Enter executes all actions, Escape aborts.
GoTo on any item triggers immediate navigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import OptionList
from textual.widgets.option_list import Option


class Action(Enum):
    """Possible actions for an item."""

    SKIP = "skip"
    YES = "yes"
    NO = "no"
    GOTO = "goto"


# Display badges for each action state
_BADGES = {
    Action.SKIP: "[ Skip ]",
    Action.YES: "[ Yes  ]",
    Action.NO: "[ No   ]",
    Action.GOTO: "[ GoTo ]",
}


@dataclass
class ActionItem:
    """An item in the ActionList with an action state."""

    label: str
    data: dict[str, Any] = field(default_factory=dict)
    action: Action = Action.SKIP


class ActionList(Widget):
    """List with per-item action states.

    Args:
        items: List of ActionItem objects.
        title: Optional title.
    """

    DEFAULT_CSS = """
    ActionList {
        height: 1fr;
        layout: vertical;
    }

    ActionList #action-option-list {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("y", "set_yes", "Approve", show=False),
        Binding("n", "set_no", "Cancel", show=False),
        Binding("g", "set_goto", "GoTo", show=False),
        Binding("s", "set_skip", "Skip", show=False),
        Binding("escape", "abort", "Abort", show=False),
    ]

    class Execute(Message):
        """Emitted when Enter is pressed — carries all items with their actions."""

        def __init__(self, items: list[ActionItem]) -> None:
            super().__init__()
            self.items = items

    class Aborted(Message):
        """Emitted when Escape is pressed — no actions taken."""

    class GoTo(Message):
        """Emitted immediately when GoTo is set on an item."""

        def __init__(self, item: ActionItem) -> None:
            super().__init__()
            self.item = item

    def __init__(
        self,
        items: list[ActionItem] | None = None,
        *,
        title: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._items = items or []
        self._title = title

    def compose(self) -> ComposeResult:
        yield OptionList(id="action-option-list")

    def on_mount(self) -> None:
        """Populate the list."""
        self._rebuild_options()
        self.query_one("#action-option-list", OptionList).focus()

    def _rebuild_options(self) -> None:
        """Rebuild the option list from current items and their actions."""
        option_list = self.query_one("#action-option-list", OptionList)
        # Remember current highlight
        highlighted = option_list.highlighted
        option_list.clear_options()

        for item in self._items:
            badge = _BADGES[item.action]
            option_list.add_option(Option(f"{badge}  {item.label}"))

        # Restore highlight position
        if highlighted is not None and highlighted < len(self._items):
            option_list.highlighted = highlighted

    def _get_highlighted_index(self) -> int | None:
        """Get the index of the currently highlighted item."""
        option_list = self.query_one("#action-option-list", OptionList)
        return option_list.highlighted

    def _set_action(self, action: Action) -> None:
        """Set action on the currently highlighted item."""
        idx = self._get_highlighted_index()
        if idx is None or idx >= len(self._items):
            return
        self._items[idx].action = action
        self._rebuild_options()

        # If GoTo, emit immediately
        if action == Action.GOTO:
            self.post_message(self.GoTo(self._items[idx]))

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Enter on any option triggers execute (submit all actions)."""
        event.stop()
        self.action_execute()

    def action_set_yes(self) -> None:
        self._set_action(Action.YES)

    def action_set_no(self) -> None:
        self._set_action(Action.NO)

    def action_set_goto(self) -> None:
        self._set_action(Action.GOTO)

    def action_set_skip(self) -> None:
        self._set_action(Action.SKIP)

    def action_execute(self) -> None:
        """Emit all items with their action states."""
        self.post_message(self.Execute(list(self._items)))

    def action_abort(self) -> None:
        """Abort — no actions taken."""
        self.post_message(self.Aborted())

    def set_items(self, items: list[ActionItem]) -> None:
        """Replace all items and rebuild."""
        self._items = items
        self._rebuild_options()

    @property
    def items(self) -> list[ActionItem]:
        """Current items."""
        return self._items
