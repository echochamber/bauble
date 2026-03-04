"""Pre-fork daemon for fast Textual screen startup.

Imports all Textual screens once, then forks on each request.
Child inherits all imports (zero import overhead), redirects
stdio to the popup's TTY, runs the requested screen, and exits.

Usage:
    bauble-daemon start     # Start in background
    bauble-daemon stop      # Stop running daemon
    bauble-daemon status    # Check if running

Cold start is ~135ms which is acceptable. The daemon shaves this to
near-zero for heavy users. If the daemon is not running, bauble-ui
falls back to cold start automatically.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

_SOCK_PATH = f"/tmp/bauble-daemon-{os.getuid()}.sock"
_PID_PATH = f"/tmp/bauble-daemon-{os.getuid()}.pid"


def main() -> None:
    """Entry point for bauble-daemon command."""
    if len(sys.argv) < 2:
        print("Usage: bauble-daemon <start|stop|status>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        _start()
    elif cmd == "stop":
        _stop()
    elif cmd == "status":
        _status()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


def _start() -> None:
    """Start the daemon."""
    # Check if already running
    if _is_running():
        print(f"Daemon already running (pid {_read_pid()})")
        return

    # Pre-import everything before forking
    print("Pre-loading Textual and all screens...")
    from bauble_tui.app import BaubleApp, _register_screens
    _register_screens()

    # Verify screens loaded
    screens = BaubleApp.available_screens()
    print(f"Loaded {len(screens)} screens: {', '.join(screens)}")

    # Daemonize: fork to background
    pid = os.fork()
    if pid > 0:
        # Parent: write PID file and exit
        Path(_PID_PATH).write_text(str(pid))
        print(f"Daemon started (pid {pid})")
        return

    # Child: become session leader
    os.setsid()

    # Close inherited stdio (daemon has no terminal)
    sys.stdin.close()
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull

    # Clean up stale socket
    if os.path.exists(_SOCK_PATH):
        os.unlink(_SOCK_PATH)

    # Listen on Unix socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(_SOCK_PATH)
    server.listen(5)
    server.settimeout(1.0)  # Allow periodic signal checks

    # Handle SIGTERM gracefully
    running = True

    def _handle_sigterm(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    while running:
        try:
            conn, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            data = conn.recv(4096).decode().strip()
            if not data:
                conn.close()
                continue

            request = json.loads(data)
            screen_name = request.get("screen", "")
            tty_path = request.get("tty", "")
            env = request.get("env", {})

            if screen_name not in BaubleApp.available_screens():
                conn.sendall(b"error: unknown screen\n")
                conn.close()
                continue

            # Fork a child to handle this request
            child_pid = os.fork()
            if child_pid == 0:
                # Child process — run the screen
                server.close()
                conn.close()

                # Restore environment for tmux access
                for k, v in env.items():
                    if v:
                        os.environ[k] = v

                # Redirect stdio to the popup's TTY
                if tty_path and os.path.exists(tty_path):
                    try:
                        tty_fd = os.open(tty_path, os.O_RDWR)
                        os.dup2(tty_fd, 0)  # stdin
                        os.dup2(tty_fd, 1)  # stdout
                        os.dup2(tty_fd, 2)  # stderr
                        os.close(tty_fd)
                    except OSError:
                        os._exit(1)

                try:
                    screen_args = request.get("args", [])
                    app = BaubleApp(screen_name=screen_name, screen_args=screen_args)
                    app.run()
                except Exception:
                    pass
                os._exit(0)
            else:
                # Parent — report success and wait for child
                conn.sendall(b"ok\n")
                conn.close()
                # Reap child asynchronously (avoid zombies)
                try:
                    os.waitpid(child_pid, os.WNOHANG)
                except ChildProcessError:
                    pass

        except (json.JSONDecodeError, OSError):
            try:
                conn.sendall(b"error\n")
                conn.close()
            except OSError:
                pass

    # Cleanup
    server.close()
    if os.path.exists(_SOCK_PATH):
        os.unlink(_SOCK_PATH)
    if os.path.exists(_PID_PATH):
        os.unlink(_PID_PATH)
    os._exit(0)


def _stop() -> None:
    """Stop the daemon."""
    pid = _read_pid()
    if not pid:
        print("Daemon not running.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for clean shutdown
        for _ in range(10):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)  # Check if still alive
            except ProcessLookupError:
                break
        print(f"Daemon stopped (pid {pid})")
    except ProcessLookupError:
        print("Daemon not running (stale PID file).")

    # Clean up files
    for path in (_PID_PATH, _SOCK_PATH):
        if os.path.exists(path):
            os.unlink(path)


def _status() -> None:
    """Check daemon status."""
    if _is_running():
        pid = _read_pid()
        print(f"Daemon running (pid {pid})")
        print(f"Socket: {_SOCK_PATH}")
    else:
        print("Daemon not running.")
        latency = _measure_cold_start()
        if latency:
            print(f"Cold start: ~{latency}ms")


def _is_running() -> bool:
    """Check if daemon is currently running."""
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        # Stale PID file
        if os.path.exists(_PID_PATH):
            os.unlink(_PID_PATH)
        return False


def _read_pid() -> int | None:
    """Read PID from file."""
    try:
        return int(Path(_PID_PATH).read_text().strip())
    except (OSError, ValueError):
        return None


def _measure_cold_start() -> int | None:
    """Measure cold start time in milliseconds."""
    import subprocess
    try:
        start = time.monotonic()
        subprocess.run(
            ["bauble-ui", "--help"],
            capture_output=True, timeout=5,
        )
        elapsed = time.monotonic() - start
        return round(elapsed * 1000)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


if __name__ == "__main__":
    main()
