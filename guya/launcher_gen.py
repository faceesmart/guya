"""
Create a double-click launcher so the user can start Guya without typing
commands. Written by the setup wizard once setup completes.

  * Windows → "Start Guya.bat"
  * macOS   → "Start Guya.command"  (double-click opens Terminal and runs it)

The launcher uses ABSOLUTE paths to this project's venv + the project root, so
it works no matter where it's double-clicked from.
"""

import os
import sys
import logging

log = logging.getLogger("Guya")


def project_root() -> str:
    """Repo root = parent of the `guya` package directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_launcher() -> str:
    """Create the platform launcher in the project root. Returns its path
    (or "" on failure)."""
    root = project_root()
    try:
        if sys.platform == "win32":
            path = os.path.join(root, "Start Guya.bat")
            py = os.path.join(root, "venv", "Scripts", "python.exe")
            content = (
                "@echo off\r\n"
                "title Guya\r\n"
                f'cd /d "{root}"\r\n'
                f'"{py}" -m guya\r\n'
            )
            with open(path, "w", newline="") as f:
                f.write(content)
        else:
            path = os.path.join(root, "Start Guya.command")
            py = os.path.join(root, "venv", "bin", "python")
            content = (
                "#!/bin/bash\n"
                "# Double-click to start Guya. Keep this window open while using\n"
                "# the widget; close it (or Ctrl+C) to quit.\n"
                f'cd "{root}"\n'
                'clear\n'
                'echo "Starting Guya — keep this window open. Close it to quit."\n'
                f'"{py}" -m guya\n'
            )
            with open(path, "w") as f:
                f.write(content)
            os.chmod(path, 0o755)
        log.info(f"Launcher created: {path}")
        return path
    except Exception as e:
        log.error(f"Could not create launcher: {e}")
        return ""
