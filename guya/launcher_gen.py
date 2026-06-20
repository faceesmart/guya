"""
Create a clean double-click launcher so the user can start Guya daily without
typing commands — and without a lingering terminal/console window.

  * macOS   → "Guya.app" bundle  (no Terminal; Guya itself is the app that asks
               for Accessibility, instead of Terminal/iTerm)
  * Windows → "Start Guya.vbs"   (runs pythonw — no console window at all)
  * Linux   → "Start Guya.command"

All launchers use ABSOLUTE paths to this project's venv + root, so they work no
matter where they're double-clicked from.
"""

import os
import sys
import logging

log = logging.getLogger("Guya")


def project_root() -> str:
    """Repo root = parent of the `guya` package directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _create_macos_app(root: str) -> str:
    """Build a minimal Guya.app bundle that launches the widget with no
    Terminal window. Returns the .app path."""
    py = os.path.join(root, "venv", "bin", "python")
    app = os.path.join(root, "Guya.app")
    macos_dir = os.path.join(app, "Contents", "MacOS")
    res_dir = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    # Executable: a tiny shell stub that runs the widget from the venv.
    stub = os.path.join(macos_dir, "Guya")
    with open(stub, "w") as f:
        f.write(
            "#!/bin/bash\n"
            f'cd "{root}"\n'
            f'exec "{py}" -m guya\n'
        )
    os.chmod(stub, 0o755)

    # Info.plist — keeps a normal Dock icon so the user can see it's running
    # and quit it; Guya becomes the Accessibility "responsible process".
    plist = os.path.join(app, "Contents", "Info.plist")
    with open(plist, "w") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            '  <key>CFBundleName</key><string>Guya</string>\n'
            '  <key>CFBundleDisplayName</key><string>Guya</string>\n'
            '  <key>CFBundleExecutable</key><string>Guya</string>\n'
            '  <key>CFBundleIdentifier</key><string>com.guya.app</string>\n'
            '  <key>CFBundlePackageType</key><string>APPL</string>\n'
            '  <key>CFBundleShortVersionString</key><string>1.0</string>\n'
            '  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>\n'
            '  <key>NSHighResolutionCapable</key><true/>\n'
            '  <key>NSMicrophoneUsageDescription</key>'
            '<string>Guya turns your speech into text.</string>\n'
            '</dict>\n</plist>\n'
        )

    # Ad-hoc code signature: makes Gatekeeper accept the locally-built app
    # without an "unverified developer" prompt. Free, no Apple account needed.
    try:
        os.system(f'codesign --force --deep --sign - "{app}" >/dev/null 2>&1')
    except Exception:
        pass
    # Refresh Launch Services so Finder picks up the new bundle immediately.
    try:
        os.system('/System/Library/Frameworks/CoreServices.framework/Versions/A/'
                  'Frameworks/LaunchServices.framework/Versions/A/Support/lsregister '
                  f'-f "{app}" >/dev/null 2>&1 &')
    except Exception:
        pass
    return app


def _create_windows_launcher(root: str) -> str:
    """Windowless launcher: a .vbs that starts pythonw with a hidden window."""
    pyw = os.path.join(root, "venv", "Scripts", "pythonw.exe")
    path = os.path.join(root, "Start Guya.vbs")
    r = root.replace('"', '""')
    p = pyw.replace('"', '""')
    with open(path, "w", newline="\r\n") as f:
        f.write(
            'Set sh = CreateObject("WScript.Shell")\n'
            f'sh.CurrentDirectory = "{r}"\n'
            f'sh.Run """{p}"" -m guya", 0, False\n'
        )
    return path


def _create_unix_command(root: str) -> str:
    py = os.path.join(root, "venv", "bin", "python")
    path = os.path.join(root, "Start Guya.command")
    with open(path, "w") as f:
        f.write(
            "#!/bin/bash\n"
            f'cd "{root}"\n'
            f'exec "{py}" -m guya\n'
        )
    os.chmod(path, 0o755)
    return path


def create_launcher() -> str:
    """Create the platform launcher in the project root. Returns its path
    (or "" on failure)."""
    root = project_root()
    try:
        if sys.platform == "win32":
            path = _create_windows_launcher(root)
        elif sys.platform == "darwin":
            path = _create_macos_app(root)
        else:
            path = _create_unix_command(root)
        log.info(f"Launcher created: {path}")
        return path
    except Exception as e:
        log.error(f"Could not create launcher: {e}")
        return ""
