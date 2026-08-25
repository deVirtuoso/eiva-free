@echo off
REM EIVA (Free). Uses the project's own virtual environment.
REM
REM This window closes as soon as the app is up. eiva.py is started with
REM pythonw.exe - the console-less Python that ships alongside python.exe -
REM and handed off with start, so this script does not sit waiting for it.
REM
REM   eiva.cmd --console   keep the window and watch the output, which is
REM                         what to do when something is wrong. Otherwise
REM                         output goes to eiva.log next to this file.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run on this machine - setting up.
  echo.
  powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 (
    echo.
    echo Setup did not finish. Fix the problem above and run this again.
    pause
    exit /b 1
  )
  echo.
)

if /i "%~1"=="--console" (
  ".venv\Scripts\python.exe" eiva.py
  if errorlevel 1 pause
  exit /b
)

start "" ".venv\Scripts\pythonw.exe" eiva.py
