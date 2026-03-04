#!/usr/bin/env bash
set -euo pipefail

# install.sh — Install bauble hooks for ambient session UX.
#
# Usage:
#   ./install.sh              # install with symlinks
#   ./install.sh --dry-run    # preview what would happen
#   ./install.sh --copy       # copy files instead of symlinking

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# --- Flags ---
DRY_RUN=false
USE_COPY=false
NON_INTERACTIVE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)         DRY_RUN=true ;;
    --copy)            USE_COPY=true ;;
    --non-interactive) NON_INTERACTIVE=true ;;
    --yes)             NON_INTERACTIVE=true ;;
    -h|--help)
      echo "Usage: ./install.sh [--dry-run] [--copy] [--non-interactive]"
      echo ""
      echo "  --dry-run           Preview what would happen without making changes"
      echo "  --copy              Copy files instead of symlinking (independent of repo)"
      echo "  --non-interactive   Skip confirmation prompt"
      exit 0
      ;;
    *)         echo -e "${RED}Unknown flag: $arg${RESET}"; exit 1 ;;
  esac
done

# --- Safety warning ---
if ! $DRY_RUN && ! $NON_INTERACTIVE; then
  echo ""
  echo -e "${BOLD}${YELLOW}WARNING: Experimental AI-written code, reviewed by a human.${RESET}"
  echo ""
  echo "  AI writes code much faster than humans can review it. These tools are"
  echo "  in-progress attempts to bridge that gap. Expect rough edges, evolving"
  echo "  interfaces, and the occasional \"what was it thinking?\" moment."
  echo ""
  echo "  This installer will create symlinks from ~/.claude/ into this repo."
  echo "  Use --dry-run to preview changes without modifying anything."
  echo ""
  echo -n "  Type 'install' to continue: "
  read -r confirm
  if [[ "$confirm" != "install" ]]; then
    echo -e "  ${YELLOW}Aborted.${RESET}"
    exit 0
  fi
  echo ""
fi

# --- Prereq checks ---
if [[ "$(uname)" != "Darwin" ]]; then
  echo -e "${YELLOW}Note:${RESET} Running on $(uname). Sound alerts and screenshot detection will use platform-appropriate fallbacks."
  echo ""
fi

if ! command -v tmux &>/dev/null; then
  echo -e "${RED}Error:${RESET} tmux is required but not found."
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "  Install with: brew install tmux"
  else
    echo "  Install with your package manager (e.g. apt install tmux, dnf install tmux)"
  fi
  exit 1
fi

# --- File manifest ---
FILES=(
  "hooks/pane-tint.sh:$HOME/.claude/hooks/pane-tint.sh"
  "hooks/waiting-context.sh:$HOME/.claude/hooks/waiting-context.sh"
  "scripts/tmux-glow:$HOME/.claude/scripts/tmux-glow"
  "scripts/tmux-glow-viewer:$HOME/.claude/scripts/tmux-glow-viewer"
  "scripts/tmux-beads:$HOME/.claude/scripts/tmux-beads"
  "scripts/tmux-beads-render.py:$HOME/.claude/scripts/tmux-beads-render.py"
  "scripts/tmux-worktree:$HOME/.claude/scripts/tmux-worktree"
  "scripts/tmux-agent-status:$HOME/.claude/scripts/tmux-agent-status"
  "scripts/tmux-claim-bead:$HOME/.claude/scripts/tmux-claim-bead"
  "scripts/tmux-diff:$HOME/.claude/scripts/tmux-diff"
  "scripts/tmux-notes:$HOME/.claude/scripts/tmux-notes"
  "scripts/tmux-cheatsheet:$HOME/.claude/scripts/tmux-cheatsheet"
  "scripts/tmux-paste-screenshot:$HOME/.claude/scripts/tmux-paste-screenshot"
  "scripts/bauble-play-sound:$HOME/.claude/scripts/bauble-play-sound"
)

# --- Counters ---
CREATED=0
SKIPPED=0
BACKED_UP=0
ERRORS=0

BACKUP_DIR="$HOME/.bauble-backup/$(date +%Y%m%d-%H%M%S)"

backup() {
  local target="$1"
  if $DRY_RUN; then
    echo -e "  ${YELLOW}[dry-run] would back up${RESET} $target"
    return
  fi
  mkdir -p "$BACKUP_DIR"
  local rel_path="${target#$HOME/}"
  local backup_path="$BACKUP_DIR/$rel_path"
  mkdir -p "$(dirname "$backup_path")"
  mv "$target" "$backup_path"
  echo -e "  ${YELLOW}backed up${RESET} $target"
  BACKED_UP=$((BACKED_UP + 1))
}

# --- Header ---
echo ""
if $DRY_RUN; then
  echo -e "${BOLD}${CYAN}=== Bauble Install (DRY RUN) ===${RESET}"
else
  echo -e "${BOLD}${CYAN}=== Bauble Install ===${RESET}"
fi
echo -e "Source: ${BOLD}$REPO_DIR${RESET}"
if $USE_COPY; then
  echo -e "Mode: ${BOLD}copy${RESET} (files are independent of this repo)"
else
  echo -e "Mode: ${BOLD}symlink${RESET} (edit repo files, changes are live)"
fi
echo ""

# --- Install files ---
for entry in "${FILES[@]}"; do
  repo_rel="${entry%%:*}"
  install_path="${entry##*:}"
  source_path="$REPO_DIR/$repo_rel"

  if [[ ! -e "$source_path" ]]; then
    echo -e "  ${RED}[error]${RESET} source missing: $source_path"
    ERRORS=$((ERRORS + 1))
    continue
  fi

  install_parent="$(dirname "$install_path")"
  if [[ ! -d "$install_parent" ]]; then
    if $DRY_RUN; then
      echo -e "  ${YELLOW}[dry-run] would mkdir${RESET} $install_parent"
    else
      mkdir -p "$install_parent"
    fi
  fi

  # Already correct symlink?
  if [[ -L "$install_path" ]]; then
    current_target="$(readlink "$install_path")"
    if [[ "$current_target" == "$source_path" ]] && ! $USE_COPY; then
      echo -e "  ${YELLOW}[skip]${RESET} already correct: $install_path"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi
    if ! $DRY_RUN; then rm "$install_path"; fi
  elif [[ -e "$install_path" ]]; then
    backup "$install_path"
  fi

  if $DRY_RUN; then
    if $USE_COPY; then
      echo -e "  ${GREEN}[dry-run] would copy${RESET} $install_path"
    else
      echo -e "  ${GREEN}[dry-run] would link${RESET} $install_path -> $source_path"
    fi
  else
    if $USE_COPY; then
      cp "$source_path" "$install_path"
      echo -e "  ${GREEN}[copied]${RESET} $install_path"
    else
      ln -s "$source_path" "$install_path"
      echo -e "  ${GREEN}[linked]${RESET} $install_path -> $source_path"
    fi
  fi
  CREATED=$((CREATED + 1))
done

# --- Hook registration ---
echo ""
echo -e "${BOLD}${CYAN}=== Hook Registration ===${RESET}"
echo ""
echo "Merge these entries into ~/.claude/settings.json (under \"hooks\"):"
echo ""
cat "$REPO_DIR/config/hooks.json"
echo ""

# --- tmux.conf ---
echo -e "${BOLD}${CYAN}=== tmux Configuration ===${RESET}"
echo ""
TMUX_CONF="$HOME/.tmux.conf"
BAUBLE_CONF="$REPO_DIR/tmux/bauble.tmux.conf"
SOURCE_LINE="source-file $BAUBLE_CONF"

if [[ -f "$TMUX_CONF" ]] && grep -qF "$BAUBLE_CONF" "$TMUX_CONF"; then
  echo -e "  ${GREEN}Found${RESET} bauble source-file in $TMUX_CONF"
else
  if $DRY_RUN; then
    if [[ -f "$TMUX_CONF" ]]; then
      echo -e "  ${GREEN}[dry-run] would append${RESET} source-file to $TMUX_CONF"
    else
      echo -e "  ${GREEN}[dry-run] would create${RESET} $TMUX_CONF with source-file"
    fi
  else
    if [[ -f "$TMUX_CONF" ]]; then
      backup "$TMUX_CONF"
      cp "$BACKUP_DIR/.tmux.conf" "$TMUX_CONF"
    fi
    echo "" >> "$TMUX_CONF"
    echo "# Bauble — ambient session UX for Claude Code" >> "$TMUX_CONF"
    echo "$SOURCE_LINE" >> "$TMUX_CONF"
    echo -e "  ${GREEN}Added${RESET} source-file to $TMUX_CONF"
  fi
fi

# Check for glow
if ! command -v glow &>/dev/null; then
  echo ""
  echo -e "  ${YELLOW}Note:${RESET} glow not found. tmux-glow requires it."
  if [[ "$(uname)" == "Darwin" ]]; then
    echo -e "  ${BOLD}brew install glow${RESET}"
  else
    echo -e "  ${BOLD}See https://github.com/charmbracelet/glow#installation${RESET}"
  fi
fi
echo ""

# --- Summary ---
echo -e "${BOLD}${CYAN}=== Summary ===${RESET}"
echo -e "  Installed: ${GREEN}$CREATED${RESET}"
echo -e "  Skipped:   ${YELLOW}$SKIPPED${RESET}"
echo -e "  Backed up: ${YELLOW}$BACKED_UP${RESET}"
echo -e "  Errors:    ${RED}$ERRORS${RESET}"
if [[ $BACKED_UP -gt 0 ]] && ! $DRY_RUN; then
  echo -e "  Backup:    $BACKUP_DIR"
fi
if $DRY_RUN; then
  echo ""
  echo -e "${YELLOW}Dry run — no changes were made.${RESET}"
fi
echo ""
