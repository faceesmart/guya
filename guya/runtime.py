"""
Tiny file-based IPC so the Control Panel and the running widget stay in sync
live (without restarting the widget).

  * The widget WRITES its live state to rt_state.json every ~0.4s
    (enabled, backend, language, hybrid, heartbeat ts).
  * The panel WRITES commands to rt_cmd.json (a monotonically increasing seq +
    the field to change); the widget reads + applies them.

Two separate files avoid one process clobbering the other. Writes are atomic
(temp file + os.replace).
"""

import os
import json
import tempfile

_DIR = os.path.join(os.path.expanduser("~"), ".guya")
STATE_PATH = os.path.join(_DIR, "rt_state.json")
CMD_PATH = os.path.join(_DIR, "rt_cmd.json")


def _write(path, data):
    os.makedirs(_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(data):
    _write(STATE_PATH, data)


def read_state():
    return _read(STATE_PATH)


def write_cmd(data):
    _write(CMD_PATH, data)


def read_cmd():
    return _read(CMD_PATH)


def clear():
    for p in (STATE_PATH, CMD_PATH):
        try:
            os.remove(p)
        except OSError:
            pass
