@echo off
setlocal
REM =====================================================
REM   Guya - Windows installer
REM =====================================================
cd /d "%~dp0"

echo ============================================
echo   Guya - Speech-to-Text setup
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10-3.12 from python.org
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment...
if not exist venv ( python -m venv venv )
call venv\Scripts\activate.bat

echo [2/3] GPU (optional): faster-whisper needs NVIDIA cuBLAS for CUDA 12 and cuDNN 9 installed separately; without them Guya uses the CPU.

echo [3/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] pyaudio may have failed. Try: pip install pipwin ^&^& pipwin install pyaudio
)

echo.
echo Done. Run Guya with:  run.bat
echo First run shows the setup wizard.
pause
