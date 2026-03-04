"""Parse bauble.conf using the same layering as bash.

Load order (matching bash):
  1. User config (~/.config/bauble.conf or $BAUBLE_CONFIG) — overrides defaults
  2. Defaults — only set variables not already defined

Shell variable syntax: VAR="${VAR:-default}" or VAR="value"
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Defaults matching bauble/config/bauble.conf
DEFAULTS = {
    "BAUBLE_SNAPS_DIR": os.path.expanduser("~/notes/snaps"),
    "BAUBLE_QUICK_DIR": os.path.expanduser("~/notes/quick"),
    "BAUBLE_NOTES_DIR": os.path.expanduser("~/notes"),
    "BAUBLE_MAX_MENU_ITEMS": "8",
    "BAUBLE_SCROLLBACK_LINES": "5000",
    "BAUBLE_CANCEL_THRESHOLD": "30",
    "BAUBLE_SPLIT_WIDTH": "100",
    # State colors (pane background hex)
    "BAUBLE_COLOR_WORKING": "#1a1e2e",
    "BAUBLE_COLOR_WAITING": "#302a1a",
    "BAUBLE_COLOR_DONE": "#192b1e",
    "BAUBLE_COLOR_CANCELLED": "#2b1a1a",
    # Tab bar styles (tmux format strings)
    "BAUBLE_TAB_WORKING": "default",
    "BAUBLE_TAB_WAITING": "bg=yellow,fg=black,bold",
    "BAUBLE_TAB_DONE": "bg=green,fg=black,bold",
    "BAUBLE_TAB_CANCELLED": "bg=red,fg=white,bold",
}

# Simpler fallback for unquoted values
_ASSIGN_SIMPLE_RE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)=([^\s#"\']+)\s*$'
)

# Match VAR="${VAR:-default}" pattern (most common in bauble.conf)
_DEFAULT_RE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)="\$\{[A-Z_][A-Z0-9_]*:-([^}]*)\}"\s*$'
)

# Match VAR="literal" or VAR='literal'
_LITERAL_RE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)="([^"]*)"\s*$'
    r"|"
    r"^([A-Z_][A-Z0-9_]*)='([^']*)'\s*$"
)


def _expand_value(val: str) -> str:
    """Expand $HOME, ${HOME}, and ~ in config values."""
    home = os.path.expanduser("~")
    val = val.replace("${HOME}", home)
    val = val.replace("$HOME", home)
    if val.startswith("~/"):
        val = home + val[1:]
    return val


def _parse_conf(path: Path) -> dict[str, str]:
    """Parse a bauble.conf file, extracting variable assignments."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Try ${VAR:-default} pattern first (most common)
        m = _DEFAULT_RE.match(line)
        if m:
            result[m.group(1)] = _expand_value(m.group(2))
            continue
        # Try literal "value" or 'value'
        m = _LITERAL_RE.match(line)
        if m:
            if m.group(1) is not None:
                result[m.group(1)] = _expand_value(m.group(2))
            else:
                result[m.group(3)] = _expand_value(m.group(4))
            continue
        # Try unquoted value
        m = _ASSIGN_SIMPLE_RE.match(line)
        if m:
            result[m.group(1)] = _expand_value(m.group(2))
    return result


def _find_conf_path() -> Path:
    """Find the bauble.conf config file (repo default)."""
    # __file__ is bauble/tui/src/bauble_tui/config.py → up 4 levels → bauble/config/
    here = Path(__file__).resolve().parent
    repo_conf = here.parent.parent.parent / "config" / "bauble.conf"
    if repo_conf.is_file():
        return repo_conf
    # Fallback: user config location
    return Path(os.path.expanduser("~/.config/bauble.conf"))


def load_config() -> dict[str, str]:
    """Load bauble config with layering: env → user conf → repo conf → defaults.

    Matches bash load order: user config is sourced first (overrides),
    then defaults fill in anything not already set.
    """
    config = dict(DEFAULTS)

    # Layer 1: Parse repo defaults (bauble/config/bauble.conf)
    repo_conf = _find_conf_path()
    repo_values = _parse_conf(repo_conf)
    config.update(repo_values)

    # Layer 2: User config overrides (same as bash sourcing user conf first)
    user_conf_path = os.environ.get(
        "BAUBLE_CONFIG",
        os.path.expanduser("~/.config/bauble.conf"),
    )
    user_values = _parse_conf(Path(user_conf_path))
    config.update(user_values)

    # Layer 3: Environment variables override everything
    for key in DEFAULTS:
        env_val = os.environ.get(key)
        if env_val is not None:
            config[key] = env_val

    return config


def get_color(config: dict[str, str], state: str) -> str:
    """Get the pane background color hex for a state name."""
    key = f"BAUBLE_COLOR_{state.upper()}"
    return config.get(key, DEFAULTS.get(key, "#1a1e2e"))


def get_tab_style(config: dict[str, str], state: str) -> str:
    """Get the tmux tab bar style string for a state name."""
    key = f"BAUBLE_TAB_{state.upper()}"
    return config.get(key, DEFAULTS.get(key, "default"))
