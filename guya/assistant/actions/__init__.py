"""Select the platform-specific desktop adapter."""

import sys

from .macos import MacOSActions
from .windows import WindowsActions


def create_action_executor(roots=None, default_directory=None, platform=None):
    platform = platform or sys.platform
    if platform == "win32":
        return WindowsActions(roots=roots, default_directory=default_directory)
    return MacOSActions(roots=roots, default_directory=default_directory)


__all__ = ["create_action_executor", "MacOSActions", "WindowsActions"]
