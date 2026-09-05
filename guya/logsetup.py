"""
One logging setup for every Guya process.

The control panel, the setup wizard and the dictation widget are separate
processes. Until this module existed only the widget configured logging, so
"Saved config", "Launcher created" and every control-panel line were lost.
All three now write to the same rotating ~/.guya/logs/guya.log, and every
record carries a date and the process id so the "Assistant evaluation"
records can be attributed to a day and a session afterwards.
"""

import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler

try:
    from . import config as guya_config
except ImportError:  # run as a loose script
    import config as guya_config

LOG_FORMAT = "%(asctime)s [%(levelname)-7s] pid=%(process)d %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 5
NOISY = ("httpx", "httpcore", "urllib3", "filelock", "huggingface_hub",
         "torch", "torch.distributed", "torch._dynamo", "torch._inductor",
         "torch.fx", "torch._C")


def log_file_path() -> str:
    log_dir = os.path.join(guya_config.CONFIG_DIR, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = tempfile.gettempdir()
    return os.path.join(log_dir, "guya.log")


def setup_logging(to_stdout: bool = True) -> str:
    """Install the rotating file handler (and optionally stdout) once per
    process. Safe to call more than once. Returns the log file path."""
    path = log_file_path()
    root = logging.getLogger()
    already = any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == path
                  for h in root.handlers)
    if not already:
        fmt = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        try:
            fh = RotatingFileHandler(path, mode="a", maxBytes=MAX_BYTES,
                                     backupCount=BACKUPS, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception:
            pass
        if to_stdout and not any(isinstance(h, logging.StreamHandler)
                                 and getattr(h, "stream", None) is sys.stdout
                                 for h in root.handlers):
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            root.addHandler(sh)
        root.setLevel(logging.INFO)
        for name in NOISY:
            logging.getLogger(name).setLevel(logging.WARNING)
    return path
