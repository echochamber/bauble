"""DiffScreen — file diff viewer with git and session diffs.

Replaces tmux-diff's --popup mode. Scans pane scrollback for edited files,
classifies as git diff or session diff, shows in FilterableList.
Selection opens a split with delta/less viewer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from bauble_tui import tmux, scrollback
from bauble_tui.config import load_config
from bauble_tui.widgets.filterable_list import FilterableList, ListItem


def _detect_pager() -> str:
    """Return the diff pager command (delta or less)."""
    if shutil.which("delta"):
        return "delta --paging=always"
    return "less -R"


class DiffScreen(Screen):
    """Diff file selector screen."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("Diffs", id="diff-header", classes="popup-header")
        yield FilterableList(id="diff-list")

    def on_mount(self) -> None:
        items = self._gather_diffs()
        fl = self.query_one(FilterableList)
        if not items:
            self.query_one(Static).update("No changed files found")
            return
        fl.set_items(items)

    def _gather_diffs(self) -> list[ListItem]:
        """Scan scrollback and git for changed files."""
        config = load_config()
        max_items = int(config.get("BAUBLE_MAX_MENU_ITEMS", "8"))
        scroll_lines = config.get("BAUBLE_SCROLLBACK_LINES", "5000")
        lines = 0 if scroll_lines == "-" else int(scroll_lines)

        pane_id = os.environ.get("TMUX_PANE", "")
        if not pane_id:
            return []

        text = scrollback.capture(pane_id, lines=lines)
        if not text:
            return []

        # Find files from edit markers (highest signal)
        edit_paths = scrollback.find_edit_markers(text)
        # Find file:// URLs
        url_paths = scrollback.find_file_urls(text)
        # Merge: edit markers first, then URLs, deduplicated
        seen: set[str] = set()
        all_paths: list[str] = []
        for p in edit_paths + url_paths:
            if p not in seen:
                seen.add(p)
                all_paths.append(p)

        items: list[ListItem] = []

        # Classify each path
        for p in all_paths:
            if len(items) >= max_items:
                break
            if not Path(p).is_file() or p.startswith("/tmp/"):
                continue

            basename = os.path.basename(p)
            parent = os.path.basename(os.path.dirname(p))
            fdir = os.path.dirname(p)

            # Check for git changes
            try:
                git_root = subprocess.run(
                    ["git", "-C", fdir, "rev-parse", "--show-toplevel"],
                    capture_output=True, text=True, check=True,
                ).stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                git_root = ""

            if git_root:
                rel = os.path.relpath(p, git_root)
                try:
                    has_changes = (
                        subprocess.run(
                            ["git", "-C", git_root, "diff", "--quiet", "--", rel],
                            capture_output=True,
                        ).returncode != 0
                        or subprocess.run(
                            ["git", "-C", git_root, "diff", "--cached", "--quiet", "--", rel],
                            capture_output=True,
                        ).returncode != 0
                    )
                except FileNotFoundError:
                    has_changes = False

                if has_changes:
                    items.append(ListItem(
                        label=f"{parent}/{basename}",
                        data={
                            "type": "git",
                            "path": p,
                            "git_root": git_root,
                        },
                    ))
                    continue

            # Check for session diff in scrollback
            diff_text = scrollback.extract_session_diff(text, p)
            if diff_text:
                tmpfile = scrollback.save_session_diff(diff_text)
                items.append(ListItem(
                    label=f"{parent}/{basename} (session)",
                    data={
                        "type": "session",
                        "path": p,
                        "tmpfile": tmpfile,
                    },
                ))

        # Fallback: all changed files in CWD's repo
        if not items:
            try:
                cwd_root = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True, text=True, check=True,
                ).stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                cwd_root = ""

            if cwd_root:
                try:
                    changed = subprocess.run(
                        ["git", "-C", cwd_root, "diff", "--name-only"],
                        capture_output=True, text=True,
                    ).stdout.strip()
                    cached = subprocess.run(
                        ["git", "-C", cwd_root, "diff", "--cached", "--name-only"],
                        capture_output=True, text=True,
                    ).stdout.strip()
                except FileNotFoundError:
                    changed = ""
                    cached = ""

                all_changed = set()
                if changed:
                    all_changed.update(changed.splitlines())
                if cached:
                    all_changed.update(cached.splitlines())

                for rel in sorted(all_changed):
                    if len(items) >= max_items:
                        break
                    p = os.path.join(cwd_root, rel)
                    basename = os.path.basename(rel)
                    parent = os.path.basename(os.path.dirname(rel)) or os.path.basename(cwd_root)
                    items.append(ListItem(
                        label=f"{parent}/{basename}",
                        data={
                            "type": "git",
                            "path": p,
                            "git_root": cwd_root,
                        },
                    ))

        return items

    def on_filterable_list_selected(self, event: FilterableList.Selected) -> None:
        """Open the selected diff in a split pane."""
        data = event.item.data
        pager = _detect_pager()
        pane_id = os.environ.get("TMUX_PANE", "")
        config = load_config()
        split_width = int(config.get("BAUBLE_SPLIT_WIDTH", "100"))

        if data["type"] == "git":
            git_root = data["git_root"]
            filepath = data["path"]
            rel = os.path.relpath(filepath, git_root)
            cmd = f"cd '{git_root}'; git diff HEAD -- '{rel}' | {pager}"
            tmux.split_window(pane_id, cmd, width=split_width)
        elif data["type"] == "session":
            tmpfile = data["tmpfile"]
            cmd = f"{pager} '{tmpfile}'; rm -f '{tmpfile}'"
            tmux.split_window(pane_id, cmd, width=split_width)

        self.dismiss()

    def on_filterable_list_dismissed(self, event: FilterableList.Dismissed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
