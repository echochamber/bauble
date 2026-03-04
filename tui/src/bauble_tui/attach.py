"""CLI entry point for bauble-ui.

Tries daemon socket for fast startup, falls back to cold start.
Usage: bauble-ui <screen> [--help]
"""

from __future__ import annotations

import sys


def main() -> None:
    """Entry point for bauble-ui command."""
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        _show_help()
        return

    screen_name = sys.argv[1]
    screen_args = sys.argv[2:]  # Extra args passed to the screen

    # Try daemon socket first (fast path)
    if _try_daemon(screen_name, screen_args):
        return

    # Cold start fallback
    _cold_start(screen_name, screen_args)


def _show_help() -> None:
    """Print usage information."""
    from bauble_tui.app import BaubleApp, _register_screens
    _register_screens()

    screens = BaubleApp.available_screens()
    print("Usage: bauble-ui <screen>")
    print()
    if screens:
        print("Available screens:")
        for name in screens:
            print(f"  {name}")
    else:
        print("No screens registered yet.")
    print()
    print("Run inside tmux display-popup for best experience.")


def _try_daemon(screen_name: str, screen_args: list[str] | None = None) -> bool:
    """Try connecting to the pre-fork daemon. Returns True if handled."""
    import os
    import socket

    uid = os.getuid()
    sock_path = f"/tmp/bauble-daemon-{uid}.sock"

    if not os.path.exists(sock_path):
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(sock_path)

        import json

        request = json.dumps({
            "screen": screen_name,
            "args": screen_args or [],
            "tty": os.ttyname(sys.stdin.fileno()) if sys.stdin.isatty() else "",
            "env": {
                "TMUX": os.environ.get("TMUX", ""),
                "TMUX_PANE": os.environ.get("TMUX_PANE", ""),
            },
        })
        sock.sendall(request.encode() + b"\n")

        # Wait for completion signal
        response = sock.recv(1024).decode().strip()
        sock.close()
        return response == "ok"
    except (OSError, socket.error):
        return False


def _cold_start(screen_name: str, screen_args: list[str] | None = None) -> None:
    """Launch Textual app directly (slower, ~400ms import overhead)."""
    from bauble_tui.app import BaubleApp, _register_screens
    _register_screens()

    if screen_name not in BaubleApp.available_screens():
        print(f"Unknown screen: {screen_name}")
        print(f"Available: {', '.join(BaubleApp.available_screens()) or 'none'}")
        sys.exit(1)

    app = BaubleApp(screen_name=screen_name, screen_args=screen_args or [])
    app.run()


if __name__ == "__main__":
    main()
