#!/usr/bin/env python3
"""Beads dashboard renderer for tmux-beads popup.

Parses `bd export` JSONL and renders a dependency-aware tree view
with progress bars, blocked indicators, and epic children.
"""

import json
import subprocess
import sys

# ── ANSI ──

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"

PRI_COLOR = {0: RED, 1: YELLOW, 2: CYAN, 3: DIM, 4: DIM}


def pri(p):
    return f"{PRI_COLOR.get(p, DIM)}P{p}{RESET}"


def bar(done, total, w=10):
    if total == 0:
        return ""
    f = round(done / total * w)
    return f"{done}/{total} {GREEN}{'█' * f}{'░' * (w - f)}{RESET}"


def sid(full_id):
    return full_id.split("-", 1)[1] if "-" in full_id else full_id


def trunc(s, n=55):
    return s[:n - 1] + "…" if len(s) > n else s


# ── Data ──

def load():
    try:
        r = subprocess.run(["bd", "export"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    beads = []
    for line in r.stdout.strip().split("\n"):
        if line:
            try:
                beads.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return beads


def index(beads):
    by_id = {b["id"]: b for b in beads}
    children_of = {}
    parent_of = {}
    blocked_by = {}

    for b in beads:
        bid = b["id"]
        for dep in b.get("dependencies", []):
            dep_on = dep.get("depends_on_id", "")
            dtype = dep.get("type", "")
            if dtype == "blocks":
                blocked_by.setdefault(bid, []).append(dep_on)
            elif dtype == "parent":
                parent_of[bid] = dep_on
                children_of.setdefault(dep_on, []).append(bid)

    # Epics that block tasks → treat as parent/child
    for b in beads:
        if b.get("issue_type") == "epic":
            bid = b["id"]
            for child_id in blocked_by.keys():
                if bid in blocked_by.get(child_id, []) and child_id not in parent_of:
                    parent_of[child_id] = bid
                    children_of.setdefault(bid, []).append(child_id)

    return by_id, children_of, parent_of, blocked_by


def open_blockers(bid, blocked_by, by_id):
    return [
        d for d in blocked_by.get(bid, [])
        if by_id.get(d, {}).get("status") != "closed"
    ]


# ── Render ──

def bead_line(b, by_id, blocked_by, indent="  ", show_blocked=True):
    bid = b["id"]
    st = b.get("status", "open")
    title = trunc(b.get("title", ""))
    labels = b.get("labels", [])

    if st == "closed":
        icon = f"{GREEN}✓{RESET}"
        title = f"{DIM}{title}{RESET}"
    elif st == "in_progress":
        icon = f"{YELLOW}◉{RESET}"
    else:
        icon = "○"

    # Assignee hint
    assignee = ""
    if "human" in labels or b.get("title", "").lower().startswith("human:"):
        assignee = f" {MAGENTA}👤{RESET}"

    line = f"{indent}{icon} {DIM}{sid(bid)}{RESET} {title}{assignee}"

    if show_blocked and st != "closed":
        ob = open_blockers(bid, blocked_by, by_id)
        if ob:
            names = ", ".join(sid(x) for x in ob[:3])
            extra = f" +{len(ob) - 3}" if len(ob) > 3 else ""
            line += f" {RED}← {names}{extra}{RESET}"

    return line


def epic_block(epic, by_id, children_of, blocked_by):
    eid = epic["id"]
    title = trunc(epic.get("title", ""), 48)
    p = epic.get("priority", 2)
    labels = epic.get("labels", [])
    kids = [by_id[k] for k in children_of.get(eid, []) if k in by_id]

    done = sum(1 for k in kids if k.get("status") == "closed")
    total = len(kids)

    # Epic header
    icon = f"{YELLOW}◉{RESET}" if "epic-active" in labels else "▸"
    if "epic-closeable" in labels:
        icon = f"{GREEN}✓{RESET}"
    prog = bar(done, total) if total > 0 else ""
    lines = [f"  {icon} {BOLD}{sid(eid)}{RESET} [{pri(p)}] {title}  {prog}"]

    # Children: in_progress → open → closed
    order = {"in_progress": 0, "open": 1, "closed": 2}
    for kid in sorted(kids, key=lambda b: order.get(b.get("status", "open"), 1)):
        lines.append(bead_line(kid, by_id, blocked_by, indent="    "))

    return lines


def main():
    beads = load()
    if not beads:
        print(f"\n  {DIM}bd export returned no data{RESET}\n")
        return

    by_id, children_of, parent_of, blocked_by = index(beads)
    open_beads = [b for b in beads if b.get("status") != "closed"]

    # ── In Progress (non-epic) ──
    in_prog = sorted(
        [b for b in open_beads if b.get("status") == "in_progress" and b.get("issue_type") != "epic"],
        key=lambda x: x.get("priority", 2),
    )

    print()
    print(f"  {BOLD}{YELLOW}◉ IN PROGRESS{RESET}")
    if in_prog:
        for b in in_prog:
            print(bead_line(b, by_id, blocked_by))
    else:
        print(f"    {DIM}(none){RESET}")

    # ── Epics with children ──
    epics = sorted(
        [e for e in open_beads if e.get("issue_type") == "epic" and e["id"] in children_of],
        key=lambda x: x.get("priority", 2),
    )

    if epics:
        print()
        print(f"  {BOLD}{MAGENTA}▼ EPICS{RESET}")
        for epic in epics:
            for line in epic_block(epic, by_id, children_of, blocked_by):
                print(line)
            print()

    # ── Ready (not in progress, not blocked, not epic child) ──
    ready = []
    for b in open_beads:
        if b.get("status") == "in_progress":
            continue
        if b.get("issue_type") == "epic":
            continue
        bid = b["id"]
        if bid in parent_of:
            continue
        if not open_blockers(bid, blocked_by, by_id):
            ready.append(b)

    ready.sort(key=lambda x: x.get("priority", 2))

    if ready:
        print(f"  {BOLD}{GREEN}○ READY{RESET}")
        for b in ready[:10]:
            print(bead_line(b, by_id, blocked_by, show_blocked=False))
        if len(ready) > 10:
            print(f"    {DIM}… and {len(ready) - 10} more{RESET}")

    # ── Summary ──
    total_open = len(open_beads)
    total_blocked = sum(1 for b in open_beads if open_blockers(b["id"], blocked_by, by_id))
    print()
    print(f"  {DIM}{total_open} open · {total_blocked} blocked · {len(ready)} ready{RESET}")
    print()


def wait_dismiss():
    """Wait for q or Escape to close the popup."""
    import tty
    import termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("q", "Q", "\x1b"):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
    wait_dismiss()
