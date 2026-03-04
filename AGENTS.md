# Bauble

Ambient session UX for Claude Code via tmux. Pane colors, sounds, keybindings, and a status bar widget. Bash scripts + Python Textual TUI for popups.

## File structure

```
hooks/
  pane-tint.sh              Pane color tinting (the core hook)
  session-track.sh          Session start tracking
  pane-cleanup.sh           Session end cleanup
  waiting-context.sh        Permission request context
  pane-silence.sh           Stall detection
scripts/
  tmux-glow                 Markdown viewer (pane scan + glow split)
  tmux-glow-viewer          Glow wrapper with save/copy/close options
  tmux-beads                Beads dashboard popup launcher
  tmux-beads-render.py      Rich dashboard renderer (progress bars, tree view)
  tmux-worktree             Worktree picker
  tmux-diff                 Git diff viewer (with delta)
  tmux-diff-extract         Diff extraction helper
  tmux-notes                Notes browser (grouped by session)
  tmux-cheatsheet           Keybinding reference popup
  tmux-agent-status         Status bar aggregate widget
  tmux-claim-bead           Claim bead + rename tmux window
  tmux-quick-capture        Quick capture popup
  tmux-quick-note           Quick note popup
  tmux-approve-all          Approve all waiting agents
  tmux-claude-picker        Session picker
  tmux-claude-next          Next waiting agent navigator
  tmux-claude-breadcrumb    Go-back navigator
  tmux-session-rename       Rename session popup
  tmux-files                file:// URL viewer
tmux/
  bauble.tmux.conf          tmux config snippet (keybindings + settings)
tui/
  src/bauble_tui/           Python Textual TUI screens (12 screens)
  src/bauble_tui/config.py  bauble.conf parser (same layering as bash)
config/
  hooks.json                Claude Code hook registration entries
  bauble.conf               Configurable colors, paths, and behavior
  bauble.tcss               Textual CSS theme
```

## How pane-tint.sh works

The core mechanism is simple: set `window-style` and `window-active-style` on the tmux pane (so tint shows regardless of focus), and `window-status-style` on the tmux window (so the tab bar shows colored text). Uses `$TMUX_PANE` to target the correct pane.

Color scheme:
- Default / dark blue = working
- Dark amber / yellow = waiting for permission
- Dark green = done

`tmux-agent-status` reads `window-status-style` across all windows to produce the aggregate count for the status bar (`🟡2 ✓3`).

## Keybindings

"Keybind" means a bauble keybind, built on tmux key tables. All bindings are defined in `tmux/bauble.tmux.conf` — the binding maps a key to a script in `scripts/`. When editing keybinds, always look up the binding in `bauble.tmux.conf` first, then read the script it calls.

## Logging

All new scripts and commands must log before and after they do their thing, along with relevant state. Use the existing pattern: write structured entries (timestamp + context) to a JSONL or log file under `~/.claude/hooks/`. Temp files go in `/tmp/bauble-*`.

## When editing hooks

- `pane-tint.sh` receives color and state label as arguments (not stdin JSON)
- It's called from settings.json hook registrations, not directly by Claude Code
- Changes are live immediately (symlinked)

## When editing scripts

- All scripts are bash (except `tmux-beads-render.py`)
- Scripts use `tmux capture-pane`, `tmux display-popup`, and `tmux display-menu`
- All keybinding scripts use `run-shell -b` (background mode, tmux 3.2+) to avoid blocking the tmux server
- Keybindings live in a custom tmux key table (`bauble`), accessed via `prefix+g`

## When editing config

- `config/bauble.conf` — All configurable values (colors, paths, thresholds). Uses `${VAR:-default}` pattern. User overrides via `~/.config/bauble.conf`. Both bash scripts and the Python TUI read this.
- `config/hooks.json` — Claude Code hook registrations. The standalone `install.sh` prints this for manual merge into `~/.claude/settings.json`.

## Dependencies

| Tool | Required | Used by |
|------|----------|---------|
| tmux 3.2+ | yes | everything |
| sound player (afplay/paplay/aplay/pw-play) | optional | sound alerts (silent fallback) |
| glow | optional | tmux-glow, tmux-notes |
| beads (bd) | optional | tmux-beads, tmux-claim-bead |
| delta | optional | tmux-diff (falls back to less) |
