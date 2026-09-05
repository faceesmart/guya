#!/bin/bash
# Start Guya from a terminal. Double-clicking Guya.app is the normal way;
# this is for developers and for machines without the app bundle.
#
# The installer creates the environment in ~/.guya/runtime/venv on macOS and
# in ./venv elsewhere, so try both; a stock macOS has no bare `python`.
HERE="$(cd "$(dirname "$0")" && pwd)"
for PY in "$HOME/.guya/runtime/venv/bin/python" "$HERE/venv/bin/python"; do
  if [ -x "$PY" ]; then
    cd "$HERE"
    exec "$PY" -m guya "$@"
  fi
done
echo "Guya is not installed yet. Run ./install.sh (or double-click 'Install Guya.command') first." >&2
exit 1
