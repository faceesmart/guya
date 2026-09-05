"""
Guya entry point.

    python -m guya            → normal launch (wizard on first run)
    python -m guya --setup    → force the setup wizard (reconfigure)
    python -m guya --reset    → delete config, then run the wizard

Decision rule:
    config missing / --setup / --reset → run the setup wizard, then (on success)
        relaunch in a FRESH process so the Whisper model loads before Qt is
        imported (required on Windows: CTranslate2's CUDA backend segfaults if
        Qt initializes first).
    config present → launch the widget directly.
"""

import logging
import os
import sys

from . import config as guya_config
from . import logsetup as guya_logsetup

log = logging.getLogger("Guya")


def _run_wizard() -> bool:
    """Show the setup wizard. Returns True if setup completed (config saved)."""
    try:
        from . import wizard
        return wizard.run()
    except Exception:
        # A crashing wizard used to be hidden by writing DEFAULT_CONFIG as if
        # setup had completed, so the wizard never ran again. Now the error is
        # logged and setup is reported as failed.
        log.exception("Setup wizard crashed")
        print("[guya] The setup wizard could not run. See ~/.guya/logs/guya.log.")
        return False


def _relaunch_fresh():
    """Re-exec `python -m guya` so the next start has a clean, Qt-free process
    for model loading. Config now exists, so it goes straight to the widget."""
    os.execv(sys.executable, [sys.executable, "-m", "guya"])


def main():
    args = set(sys.argv[1:])
    guya_logsetup.setup_logging()

    # The Control Panel starts the dictation widget as `--widget`, and runs the
    # wizard as `--setup-only` (which must NOT relaunch into a Control Panel).
    if "--widget" in args:
        from . import widget
        widget.main()
        return

    setup_only = "--setup-only" in args
    need_wizard = setup_only
    if "--reset" in args:
        guya_config.reset_config()
        print("[guya] Configuration reset.")
        need_wizard = True
    elif "--setup" in args:
        need_wizard = True
    elif not setup_only and not guya_config.config_exists():
        print("[guya] First run — no configuration found. Starting setup…")
        need_wizard = True

    if need_wizard:
        if not _run_wizard():
            print("[guya] Setup cancelled or did not complete.")
            if setup_only:
                return
            sys.exit(1)
        if setup_only:
            return   # parent Control Panel will reload + restart the widget
        print("[guya] Setup complete. Starting Guya…")
        _relaunch_fresh()   # replaces this process; opens the Control Panel
        return

    # Config present → open the Control Panel (which turns the widget on).
    from . import control_panel
    control_panel.run()


if __name__ == "__main__":
    main()
