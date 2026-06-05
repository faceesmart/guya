#!/usr/bin/env bash
# Launch Guya (macOS/Linux). First run shows the setup wizard.
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source venv/bin/activate
exec python -m guya "$@"
