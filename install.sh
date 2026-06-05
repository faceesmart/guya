#!/usr/bin/env bash
# =====================================================
#   Guya — macOS / Linux installer
# =====================================================
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Guya — Speech-to-Text setup"
echo "============================================"
echo

# ---- Python 3.10–3.12 (PyQt6 has no 3.13/3.14 wheels yet) ----
PYTHON_BIN=""
for cand in python3.11 python3.12 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver="$("$cand" -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
        major="${ver%%.*}"; minor="${ver#*.}"
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_BIN="$cand"; break
        fi
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Need Python 3.10–3.12. Install: brew install python@3.11"
    exit 1
fi
echo "[OK] Using $PYTHON_BIN ($($PYTHON_BIN --version))"

# ---- portaudio for PyAudio (macOS) ----
if command -v brew >/dev/null 2>&1; then
    brew list portaudio >/dev/null 2>&1 || { echo "[1/3] Installing portaudio..."; brew install portaudio; }
fi

# ---- venv ----
echo "[2/3] Creating virtual environment..."
[ -d venv ] || "$PYTHON_BIN" -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null

# ---- deps ----
echo "[3/3] Installing dependencies..."
if command -v brew >/dev/null 2>&1; then
    BREW_PREFIX="$(brew --prefix)"
    export CFLAGS="-I${BREW_PREFIX}/include ${CFLAGS:-}"
    export LDFLAGS="-L${BREW_PREFIX}/lib ${LDFLAGS:-}"
fi
python -m pip install -r requirements.txt

echo
echo "Done. Run Guya with:  ./run.sh"
echo "First run shows the setup wizard."
