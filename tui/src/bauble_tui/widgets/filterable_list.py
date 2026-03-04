"""FilterableList — browse-first list widget for bauble popups.

Default mode: arrow keys navigate, Enter selects, Escape dismisses.
'/' activates filter input at top — fuzzy match as you type.
Escape in filter mode returns to browse. Escape in browse dismisses.

Items carry a .data dict (replaces delimiter hacks in bash scripts).
Optional section headers (non-selectable group dividers).
Auto-select if single selectable item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option


@dataclass
class ListItem:
    """An item in the FilterableList."""

    label: str
    data: dict[str, Any] = field(default_factory=dict)
    section: str | None = None  # Group header (shown above first item in group)


class FilterableList(Widget):
    """Browse-first list with optional filter.

    Args:
        items: List of ListItem objects.
        show_count: Show item count in header.
        empty_message: Message when no items match.
        title: Optional title shown above the list.
    """

    DEFAULT_CSS = """
    FilterableList {
        height: 1fr;
        layout: vertical;
    }

    FilterableList #filter-input {
        dock: top;
        display: none;
        height: 3;
        margin: 0 1;
        border: tall $accent;
    }

    FilterableList #filter-input.visible {
        display: block;
    }

    FilterableList #option-list {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("slash", "activate_filter", "Filter", show=False),
        Binding("escape", "escape", "Back", show=False),
    ]

    filter_active: reactive[bool] = reactive(False)

    class Selected(Message):
        """Emitted when an item is selected."""

        def __init__(self, item: ListItem) -> None:
            super().__init__()
            self.item = item

    class Dismissed(Message):
        """Emitted when the list is dismissed (Escape in browse mode)."""

    def __init__(
        self,
        items: list[ListItem] | None = None,
        *,
        show_count: bool = False,
        empty_message: str = "No items",
        title: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._items = items or []
        self._show_count = show_count
        self._empty_message = empty_message
        self._title = title
        # Map option index → ListItem (excludes separators)
        self._index_map: dict[int, ListItem] = {}

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Type to filter...",
            id="filter-input",
        )
        yield OptionList(id="option-list")

    def on_mount(self) -> None:
        """Populate the list and handle auto-select."""
        self._rebuild_options()

        # Focus the option list for keyboard navigation
        self.query_one("#option-list", OptionList).focus()

        # Auto-select if single selectable item
        selectable = [i for i in self._items if i.section is None or i.label != i.section]
        if len(selectable) == 1:
            self.post_message(self.Selected(selectable[0]))

    def _rebuild_options(self, filter_text: str = "") -> None:
        """Rebuild the option list, optionally filtering."""
        option_list = self.query_one("#option-list", OptionList)
        option_list.clear_options()
        self._index_map.clear()

        filter_lower = filter_text.lower()
        seen_sections: set[str] = set()
        idx = 0

        for item in self._items:
            # Apply filter
            if filter_lower and filter_lower not in item.label.lower():
                # Check data values too for fuzzy matching
                data_match = any(
                    filter_lower in str(v).lower()
                    for v in item.data.values()
                )
                if not data_match:
                    continue

            # Add section header if new section
            if item.section and item.section not in seen_sections:
                seen_sections.add(item.section)
                if idx > 0:
                    option_list.add_option(None)
                    idx += 1
                option_list.add_option(None)
                # Use a disabled option for section header
                header_opt = Option(f"  {item.section}", disabled=True)
                option_list.add_option(header_opt)
                idx += 2

            # Add the item
            prompt = item.label
            if filter_lower:
                # Could highlight matches here in future
                pass
            option_list.add_option(Option(prompt))
            self._index_map[idx] = item
            idx += 1

        if idx == 0:
            option_list.add_option(Option(self._empty_message, disabled=True))

    def _get_selected_item(self) -> ListItem | None:
        """Get the ListItem for the currently highlighted option."""
        option_list = self.query_one("#option-list", OptionList)
        highlighted = option_list.highlighted
        if highlighted is not None and highlighted in self._index_map:
            return self._index_map[highlighted]
        return None

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle Enter on an option."""
        event.stop()
        item = self._index_map.get(event.option_index)
        if item:
            self.post_message(self.Selected(item))

    @on(Input.Changed, "#filter-input")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        """Filter items as user types."""
        event.stop()
        self._rebuild_options(event.value)

    @on(Input.Submitted, "#filter-input")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        """Enter in filter selects the highlighted item."""
        event.stop()
        item = self._get_selected_item()
        if item:
            self.post_message(self.Selected(item))

    def action_activate_filter(self) -> None:
        """Show filter input and focus it."""
        self.filter_active = True
        filter_input = self.query_one("#filter-input", Input)
        filter_input.add_class("visible")
        filter_input.value = ""
        filter_input.focus()

    def action_escape(self) -> None:
        """Escape: deactivate filter or dismiss."""
        if self.filter_active:
            self.filter_active = False
            filter_input = self.query_one("#filter-input", Input)
            filter_input.remove_class("visible")
            filter_input.value = ""
            self._rebuild_options()
            self.query_one("#option-list", OptionList).focus()
        else:
            self.post_message(self.Dismissed())

    def set_items(self, items: list[ListItem]) -> None:
        """Replace all items and rebuild."""
        self._items = items
        self._rebuild_options()

    @property
    def items(self) -> list[ListItem]:
        """Current items."""
        return self._items
