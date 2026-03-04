# Bauble tmux Configuration

Full reference for tmux integration. The install script adds `source-file` to `~/.tmux.conf` automatically — this doc covers what it sets up and how to customize it.

## What gets sourced

`bauble.tmux.conf` configures:

- `allow-rename off` — prevents processes from overriding window names (needed for `tmux-claim-bead`)
- `monitor-bell off` — bauble uses per-window styles instead of bell
- Keybindings in the `bauble` key table (accessed via `prefix+g`)
- Pane tint manual overrides (`g,y` and `g,Y`)

## Keybindings

All under `prefix+g` (custom tmux key table, no conflicts with defaults).

| Key | Action |
|-----|--------|
| `m` | Markdown viewer — scan pane for `.md` paths, open in glow split |
| `b` | Beads dashboard — in-progress, epics, ready tasks |
| `w` | Worktree picker — switch or open split |
| `d` | Diff viewer — per-file diffs with delta |
| `n` | Notes browser — saved notes grouped by session |
| `c` | Quick capture — note, bead, or Linear task |
| `?` | Cheatsheet |
| `y` | Clear pane tint (reset to working state) |
| `Y` | Force green (mark done) |

### Markdown viewer (`g,m`)

Scans scrollback for `file:///path.md`, `/absolute/path.md`, `~/path.md`. Opens in glow split. After quitting: `s` save to `~/notes/`, `c` copy path, `q` close.

### Beads dashboard (`g,b`)

Shows in-progress beads, epics, and ready tasks in a popup. Requires [beads](https://github.com/steveyegge/beads).

### Claim bead

```bash
tmux-claim-bead manapool-0ch
# → renames tmux window to "0ch: Investigate Inngest event ti…"
```

## Status bar

Add the agent status widget to your tmux status bar:

```bash
set -g status-right '#(~/.claude/scripts/tmux-agent-status) %b %d  %H:%M'
set -g status-interval 5
```

`tmux-agent-status` reads `@bauble-state` across all panes. Output examples:
- `🟡2` — two panes waiting for approval
- `✅3` — three panes done
- `🔓 1h30m (2/3)` — cullis yolo mode active

## Hook events

| Event | Tab | Pane bg | Sound |
|-------|-----|---------|-------|
| `UserPromptSubmit` | default | `#1a1b26` | — |
| `PreToolUse` | default | `#1a1b26` | — |
| `PostToolUse` | default | `#1a1b26` | — |
| `Stop` | green | `#192b1e` | Hero.aiff |
| `PermissionRequest` | yellow | `#302a1a` | Glass.aiff |

Reset hooks clear state back to working baseline on every new prompt or tool use.

## Customization

**Colors** — edit hex values in `config/hooks.json`: `#1a1b26` (working), `#192b1e` (done), `#302a1a` (waiting).

**Sounds** — configure in `bauble.conf`: set `BAUBLE_SOUND_ENABLED=0` to disable, or `BAUBLE_SOUND_DONE`/`BAUBLE_SOUND_WAITING` to custom file paths. Cross-platform: uses system sounds on macOS (afplay) and Linux (pw-play/paplay/aplay).

**Hyperlinks** — enable OSC 8 clickable `file://` URLs by uncommenting in `bauble.tmux.conf`:

```bash
set -as terminal-features ',xterm-ghostty:hyperlinks'
# or for iTerm2:
set -as terminal-features ',xterm-256color:hyperlinks'
```
