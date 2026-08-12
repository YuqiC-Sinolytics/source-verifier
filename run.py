#!/usr/bin/env python3
r"""Start the web UI without needing the `uvicorn` command on PATH.

    python run.py            # first free port from 8000 upward
    python run.py 8080       # start looking from 8080 instead

On Windows, pip often installs console scripts into a Scripts\ directory that
is not on PATH, so `uvicorn ...` fails while the package itself is fine. This
launches the same server through the Python API instead.

It also skips past ports that are already taken — a leftover server from an
earlier run is the usual cause of WinError 10048.
"""

import socket
import sys
import threading
import webbrowser

REQUIRED = ["fastapi", "uvicorn", "httpx", "anthropic", "dotenv"]

missing = []
for mod in REQUIRED:
    try:
        __import__(mod)
    except ImportError:
        missing.append("python-dotenv" if mod == "dotenv" else mod)

if missing:
    print("Missing packages:", ", ".join(missing))
    print("\nInstall them with the SAME interpreter you are running now:\n")
    print(f'  "{sys.executable}" -m pip install -r requirements.txt\n')
    sys.exit(1)

import uvicorn  # noqa: E402

from app.config import cfg  # noqa: E402


def free_port(start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit(
        f"No free port between {start} and {start + tries - 1}. "
        f"Close the other server, or pass a port: python run.py 9000"
    )


start_at = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
port = free_port(start_at)
url = f"http://localhost:{port}"

if port != start_at:
    print(f"Port {start_at} is in use — using {port} instead.")
print(f"Source Verifier -> {url}")
print(f"Mode: {'MOCK (offline fixtures, no API calls)' if cfg.mock else 'live'}")
print("Press Ctrl+C to stop.\n")

threading.Timer(1.2, lambda: webbrowser.open(url)).start()
uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
