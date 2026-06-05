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

import os
import sys

from . import config as guya_config


def _run_wizard() -> bool:
    """Show the setup wizard. Returns True if setup completed (config saved)."""
    try:
        from . import wizard
        return wizard.run()
    except Exception as e:
        # Safety net: if the wizard can't run (e.g. missing Qt during a headless
        # test), fall back to writing defaults so the app is still usable.
        print(f"[guya] Wizard unavailable ({e}); writing default config.")
        return guya_config.save_config(guya_config.DEFAULT_CONFIG)


def _relaunch_fresh():
    """Re-exec `python -m guya` so the next start has a clean, Qt-free process
    for model loading. Config now exists, so it goes straight to the widget."""
    os.execv(sys.executable, [sys.executable, "-m", "guya"])


def main():
    args = set(sys.argv[1:])

    need_wizard = False
    if "--reset" in args:
        guya_config.reset_config()
        print("[guya] Configuration reset.")
        need_wizard = True
    elif "--setup" in args:
        need_wizard = True
    elif not guya_config.config_exists():
        print("[guya] First run — no configuration found. Starting setup…")
        need_wizard = True

    if need_wizard:
        if not _run_wizard():
            print("[guya] Setup cancelled or did not complete. Exiting.")
            sys.exit(1)
        print("[guya] Setup complete. Starting Guya…")
        _relaunch_fresh()   # replaces this process; does not return
        return

    # Config present → launch the widget (model loads before Qt is imported).
    from . import widget
    widget.main()


if __name__ == "__main__":
    main()
