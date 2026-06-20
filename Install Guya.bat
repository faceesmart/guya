@echo off
REM =====================================================
REM    Guya - one-double-click installer for Windows
REM =====================================================
REM Double-click this file to install Guya. It will:
REM   1. Make sure Python is available (and install it for you if not)
REM   2. Set up Guya (one time)
REM   3. Open the Guya setup wizard
REM You don't need to type anything.

setlocal enabledelayedexpansion
cd /d "%~dp0"
title Guya - Installer
cls
echo ===============================================
echo     Guya  -  Speech to Text  -  Installer
echo ===============================================
echo.

REM ---------------------------------------------------------------
REM 1. Find a suitable Python (3.10-3.12; PyQt6 has no newer wheels)
REM ---------------------------------------------------------------
echo [Step 1/3]  Checking for Python...
set "PYEXE="
for %%V in (3.11 3.12 3.10) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>&1 && set "PYEXE=py -%%V"
    )
)
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE (
            "%%P" -c "import sys;exit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>&1 && set "PYEXE=%%P"
        )
    )
)

if not defined PYEXE (
    echo    No suitable Python found. Installing it for you...
    where winget >nul 2>&1
    if !errorlevel! == 0 (
        winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements --silent
        REM PATH may not refresh in this window; try the py launcher
        py -3.11 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.11"
    )
)

if not defined PYEXE (
    echo.
    echo    Python needs to be installed first.
    echo    Opening a simple guide and the download page...
    start "" "docs\python-setup.html"
    start "" "https://www.python.org/downloads/windows/"
    echo.
    echo    IMPORTANT: on the installer, tick "Add Python to PATH".
    echo    After installing, double-click "Install Guya" again.
    echo.
    pause
    exit /b 1
)
echo    OK - Python found.
echo.

REM ---------------------------------------------------------------
REM 2. Create the environment and install components
REM ---------------------------------------------------------------
echo [Step 2/3]  Setting up Guya (one time)...
if not exist venv (
    echo    Creating the Guya environment...
    %PYEXE% -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel >nul 2>&1

echo    Installing components (this can take a few minutes)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo    Retrying audio component via pipwin...
    python -m pip install pipwin >nul 2>&1
    python -m pipwin install pyaudio >nul 2>&1
    python -m pip install -r requirements.txt
)
if errorlevel 1 (
    echo.
    echo    Something went wrong installing components.
    echo    Please check your internet connection and try again.
    echo.
    pause
    exit /b 1
)
echo    OK - Guya is set up.
echo.

REM ---------------------------------------------------------------
REM 3. Launch the setup wizard
REM ---------------------------------------------------------------
echo [Step 3/3]  Opening Guya...
echo    The setup wizard will appear in a moment.
echo    You can close this window after it opens.
echo.
python -m guya
