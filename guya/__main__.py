"""
Guya entry point.

    python -m guya            → normal launch
    python -m guya --setup    → force the setup wizard (reconfigure)
    python -m guya --reset    → delete config, then run the wizard

Decision rule:
    config missing  → run the setup wizard, then launch the widget
    config present  → launch the widget directly
"""

import sys

from . import config as guya_config


def _run_wizard() -> bool:
    """Run the setup wizard. Returns True if setup completed (config saved).

    NOTE: The full Qt wizard is Milestone 2. Until it lands, this writes the
    default config so the widget is runnable, and tells the user. This keeps
    `python -m guya` working end-to-end during development.
    """
    try:
        from . import wizard  # noqa: F401  (exists once M2 lands)
        return wizard.run()
    except ImportError:
        print("[guya] Setup wizard not built yet (Milestone 2).")
        print("[guya] Writing default configuration so the widget can run...")
        ok = guya_config.save_config(guya_config.DEFAULT_CONFIG)
        if ok:
            print(f"[guya] Default config written to {guya_config.CONFIG_PATH}")
        return ok


def main():
    args = set(sys.argv[1:])

    if "--reset" in args:
        guya_config.reset_config()
        print("[guya] Configuration reset.")
        if not _run_wizard():
            sys.exit(1)
    elif "--setup" in args:
        if not _run_wizard():
            sys.exit(1)
    elif not guya_config.config_exists():
        print("[guya] First run — no configuration found.")
        if not _run_wizard():
            print("[guya] Setup did not complete. Exiting.")
            sys.exit(1)

    # Launch the widget. Importing widget triggers config load + logging setup.
    from . import widget
    widget.main()


if __name__ == "__main__":
    main()
