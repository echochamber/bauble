"""Tests for ActionList widget."""

import pytest
from textual.app import App, ComposeResult

from bauble_tui.widgets.action_list import ActionList, ActionItem, Action


class ActionListApp(App):
    """Test harness app for ActionList."""

    def __init__(self, items: list[ActionItem]):
        super().__init__()
        self._items = items
        self.executed_items: list[ActionItem] | None = None
        self.aborted = False
        self.goto_item: ActionItem | None = None

    def compose(self) -> ComposeResult:
        yield ActionList(self._items, id="test-actions")

    def on_action_list_execute(self, event: ActionList.Execute) -> None:
        self.executed_items = event.items
        self.exit()

    def on_action_list_aborted(self, event: ActionList.Aborted) -> None:
        self.aborted = True
        self.exit()

    def on_action_list_go_to(self, event: ActionList.GoTo) -> None:
        self.goto_item = event.item
        self.exit()


def make_items(*labels: str) -> list[ActionItem]:
    return [ActionItem(label=l, data={"label": l}) for l in labels]


@pytest.mark.asyncio
async def test_y_sets_yes():
    """'y' key sets focused item to Yes."""
    items = make_items("Pane 1", "Pane 2")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")  # highlight first item
        await pilot.press("y")
        al = app.query_one(ActionList)
        assert al.items[0].action == Action.YES


@pytest.mark.asyncio
async def test_n_sets_no():
    """'n' key sets focused item to No."""
    items = make_items("Pane 1", "Pane 2")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")
        await pilot.press("n")
        al = app.query_one(ActionList)
        assert al.items[0].action == Action.NO


@pytest.mark.asyncio
async def test_s_sets_skip():
    """'s' key resets to Skip."""
    items = make_items("Pane 1")
    items[0].action = Action.YES
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")
        await pilot.press("s")
        al = app.query_one(ActionList)
        assert al.items[0].action == Action.SKIP


@pytest.mark.asyncio
async def test_g_triggers_goto():
    """'g' key emits GoTo immediately."""
    items = make_items("Pane 1", "Pane 2")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")
        await pilot.press("g")
        assert app.goto_item is not None
        assert app.goto_item.label == "Pane 1"


@pytest.mark.asyncio
async def test_enter_executes_all():
    """Enter emits all items with their action states."""
    items = make_items("A", "B", "C")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")
        await pilot.press("y")  # A = Yes
        await pilot.press("down")
        await pilot.press("n")  # B = No
        await pilot.press("enter")
        assert app.executed_items is not None
        assert len(app.executed_items) == 3
        assert app.executed_items[0].action == Action.YES
        assert app.executed_items[1].action == Action.NO
        assert app.executed_items[2].action == Action.SKIP  # C untouched


@pytest.mark.asyncio
async def test_escape_aborts():
    """Escape aborts — no actions taken."""
    items = make_items("Pane 1")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("escape")
        assert app.aborted


@pytest.mark.asyncio
async def test_default_is_skip():
    """All items default to Skip."""
    items = make_items("A", "B", "C")
    for item in items:
        assert item.action == Action.SKIP


@pytest.mark.asyncio
async def test_badge_in_display():
    """Badges appear in the option text."""
    items = make_items("Pane 1")
    app = ActionListApp(items)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("down")
        await pilot.press("y")
        al = app.query_one(ActionList)
        option_list = al.query_one("#action-option-list")
        # The first option should contain "Yes" badge
        opt = option_list.get_option_at_index(0)
        assert "Yes" in str(opt.prompt)
