#!/usr/bin/env bash
# =====================================================
#   Guya — one-double-click installer for macOS
# =====================================================
# Double-click this file to install Guya. It will:
#   1. Make sure Python is available (and help you install it if not)
#   2. Set up Guya (one time)
#   3. Open the Guya setup wizard
# You don't need to type anything.

cd "$(dirname "$0")" || exit 1
clear

BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; RED=$'\033[31m'; CYAN=$'\033[36m'; OFF=$'\033[0m'

echo "${BOLD}${CYAN}"
echo "   ┌─────────────────────────────────────────┐"
echo "   │   گویا  ·  Guya — Speech to Text          │"
echo "   │   Installer                               │"
echo "   └─────────────────────────────────────────┘"
echo "${OFF}"

# ---------------------------------------------------------------
# 1. Find a suitable Python (3.10–3.12; PyQt6 has no newer wheels yet)
# ---------------------------------------------------------------
find_python() {
    for cand in python3.11 python3.12 python3.10 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            ver="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
            major="${ver%%.*}"; minor="${ver#*.}"
            if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
                echo "$cand"; return 0
            fi
        fi
    done
    return 1
}

echo "${BOLD}Step 1/3 — Checking for Python…${OFF}"
PYTHON_BIN="$(find_python)"

if [ -z "$PYTHON_BIN" ]; then
    echo "${DIM}  No suitable Python found (need 3.10–3.12).${OFF}"
    if command -v brew >/dev/null 2>&1; then
        echo "  Installing Python automatically with Homebrew (a few minutes)…"
        brew install python@3.11 || true
        PYTHON_BIN="$(find_python)"
    fi
    if [ -z "$PYTHON_BIN" ]; then
        echo
        echo "${RED}  Python needs to be installed first.${OFF}"
        echo "  Opening a simple guide and the download page…"
        open "python-setup.html" 2>/dev/null || open "docs/python-setup.html" 2>/dev/null
        open "https://www.python.org/downloads/release/python-3119/" 2>/dev/null
        echo
        echo "  ${BOLD}After installing Python, double-click ‘Install Guya’ again.${OFF}"
        echo
        echo "  Press any key to close."
        read -r -n 1 -s
        exit 1
    fi
fi
echo "${GREEN}  ✓ Using $($PYTHON_BIN --version)${OFF}"
echo

# ---------------------------------------------------------------
# 2. Audio support (portaudio) + Python environment + components
# ---------------------------------------------------------------
echo "${BOLD}Step 2/3 — Setting up Guya (one time)…${OFF}"

if command -v brew >/dev/null 2>&1; then
    if ! brew list portaudio >/dev/null 2>&1; then
        echo "  Installing audio support (portaudio)…"
        brew install portaudio || true
    fi
fi

if [ ! -d venv ]; then
    echo "  Creating the Guya environment…"
    "$PYTHON_BIN" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null 2>&1

echo "  Installing components (this can take a few minutes)…"
if command -v brew >/dev/null 2>&1; then
    BREW_PREFIX="$(brew --prefix)"
    export CFLAGS="-I${BREW_PREFIX}/include ${CFLAGS:-}"
    export LDFLAGS="-L${BREW_PREFIX}/lib ${LDFLAGS:-}"
fi
if python -m pip install -r requirements.txt; then
    echo "${GREEN}  ✓ Guya is set up.${OFF}"
else
    echo "${RED}  Something went wrong installing components.${OFF}"
    echo "  Please check your internet connection and try again."
    echo "  Press any key to close."
    read -r -n 1 -s
    exit 1
fi
echo

# ---------------------------------------------------------------
# 3. Launch the setup wizard
# ---------------------------------------------------------------
echo "${BOLD}Step 3/3 — Opening Guya…${OFF}"
echo "${DIM}  The setup wizard will appear in a moment. You can close this window after it opens.${OFF}"
echo
exec python -m guya
