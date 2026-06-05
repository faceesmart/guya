@echo off
REM Launch Guya (Windows). First run shows the setup wizard.
cd /d "%~dp0"
call venv\Scripts\activate.bat
python -m guya %*
