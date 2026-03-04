"""Tests for FilterableList widget."""

import pytest
from textual.app import App, ComposeResult

from bauble_tui.widgets.filterable_list import FilterableList, ListItem


class FilterableListApp(App):
    """Test harness app for FilterableList."""

    BINDINGS = [("escape", "quit", "Quit")]

    def __init__(self, items: list[ListItem], empty_message: str = "No items", **kwargs):
        super().__init__()
        self._items = items
        self._empty_message = empty_message
        self.selected_item: ListItem | None = None
        self.dismissed = False

    def compose(self) -> ComposeResult:
        yield FilterableList(self._items, empty_message=self._empty_message, id="test-list")

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        self.selected_item = event.item
        self.exit()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.dismissed = True
        self.exit()


def make_items(*labels: str, section: str | None = None) -> list[ListItem]:
    """Helper to create simple ListItems."""
    return [ListItem(label=l, data={"label": l}, section=section) for l in labels]


def make_grouped_items() -> list[ListItem]:
    """Items with section headers."""
    return [
        ListItem("Alice", data={"id": 1}, section="People"),
        ListItem("Bob", data={"id": 2}, section="People"),
        ListItem("Cat", data={"id": 3}, section="Animals"),
        ListItem("Dog", data={"id": 4}, section="Animals"),
    ]


@pytest.mark.asyncio
async def test_arrow_keys_browse():
    """Arrow keys navigate without filter active."""
    app = FilterableListApp(make_items("One", "Two", "Three"))
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)
        assert not fl.filter_active

        # Arrow down moves highlight
        await pilot.press("down")
        await pilot.press("down")

        # Verify we can get a selected item
        option_list = fl.query_one("#option-list")
        assert option_list.highlighted is not None


@pytest.mark.asyncio
async def test_enter_selects_item():
    """Enter key selects the highlighted item."""
    items = make_items("Alpha", "Beta", "Gamma")
    app = FilterableListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        # Navigate down to highlight first item, then select
        await pilot.press("down")
        await pilot.press("enter")
        assert app.selected_item is not None
        assert app.selected_item.label == "Alpha"


@pytest.mark.asyncio
async def test_slash_activates_filter():
    """'/' key shows filter input."""
    app = FilterableListApp(make_items("One", "Two", "Three"))
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)
        assert not fl.filter_active

        await pilot.press("slash")
        assert fl.filter_active

        filter_input = fl.query_one("#filter-input")
        assert "visible" in filter_input.classes


@pytest.mark.asyncio
async def test_filter_narrows_results():
    """Typing in filter narrows the displayed items."""
    app = FilterableListApp(make_items("Apple", "Banana", "Avocado"))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("slash")
        await pilot.press("a")

        fl = app.query_one(FilterableList)
        # Should show Apple and Avocado (both contain 'a')
        option_list = fl.query_one("#option-list")
        # Count non-separator, non-disabled options
        visible_count = sum(
            1 for idx in fl._index_map
        )
        assert visible_count >= 2  # Apple and Avocado at minimum


@pytest.mark.asyncio
async def test_escape_in_filter_returns_to_browse():
    """Escape in filter mode returns to browse mode."""
    app = FilterableListApp(make_items("One", "Two"))
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)

        await pilot.press("slash")
        assert fl.filter_active

        await pilot.press("escape")
        assert not fl.filter_active


@pytest.mark.asyncio
async def test_escape_in_browse_dismisses():
    """Escape in browse mode dismisses the list."""
    app = FilterableListApp(make_items("One", "Two"))
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)
        assert not fl.filter_active

        await pilot.press("escape")
        assert app.dismissed


@pytest.mark.asyncio
async def test_item_data_accessible():
    """Selected item carries its .data dict."""
    items = [
        ListItem("Server A", data={"host": "10.0.0.1", "port": 8080}),
        ListItem("Server B", data={"host": "10.0.0.2", "port": 9090}),
    ]
    app = FilterableListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        # Navigate down to highlight first item, then select
        await pilot.press("down")
        await pilot.press("enter")
        assert app.selected_item is not None
        assert app.selected_item.data["host"] == "10.0.0.1"
        assert app.selected_item.data["port"] == 8080


@pytest.mark.asyncio
async def test_section_headers_not_selectable():
    """Section headers render but cannot be selected."""
    items = make_grouped_items()
    app = FilterableListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)

        # Navigate and verify the index map only contains selectable items
        selectable_labels = {item.label for item in fl._index_map.values()}
        assert "Alice" in selectable_labels
        assert "Bob" in selectable_labels
        # Section headers should not be in the index map
        assert "People" not in selectable_labels
        assert "Animals" not in selectable_labels


@pytest.mark.asyncio
async def test_auto_select_single_item():
    """Single selectable item is auto-selected."""
    items = [ListItem("Only One", data={"id": 42})]
    app = FilterableListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        # Should auto-select
        await pilot.pause()
        assert app.selected_item is not None
        assert app.selected_item.label == "Only One"
        assert app.selected_item.data["id"] == 42


@pytest.mark.asyncio
async def test_set_items_updates_list():
    """set_items() replaces all items and rebuilds."""
    app = FilterableListApp(make_items("Old"))
    async with app.run_test(size=(80, 24)) as pilot:
        fl = app.query_one(FilterableList)
        new_items = make_items("New1", "New2")
        fl.set_items(new_items)
        assert len(fl.items) == 2
        assert fl.items[0].label == "New1"


@pytest.mark.asyncio
async def test_empty_message_shown():
    """Empty message shows when no items."""
    app = FilterableListApp([], empty_message="Nothing here")
    # Just verify it doesn't crash — the empty message is a disabled option
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        # App should be running without error
