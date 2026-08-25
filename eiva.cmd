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

REM Being there is not the same as working. A virtual environment holds an
REM absolute path to the Python it was built from, and that Python can be
REM upgraded or uninstalled out from under it: the folder survives, nothing in
REM it runs, and the app just never appears. Ask it to run before trusting it.
set NEEDS_SETUP=
if not exist ".venv\Scripts\python.exe" set NEEDS_SETUP=1
if not defined NEEDS_SETUP (
  ".venv\Scripts\python.exe" -c "pass" >nul 2>&1
  if errorlevel 1 set NEEDS_SETUP=1
)

REM Setup is handed a policy for its own process only, because Windows
REM refuses to run an unsigned .ps1 that arrived from a download and a
REM .cmd is the one thing here that policy does not apply to. That is
REM also what setup.cmd is for, for anyone who goes looking for an
REM installer rather than a launcher. -NoProfile so that a user profile
REM which prints or throws cannot derail setup before it starts. The
REM comment sits out here: a REM inside a parenthesised block is read
REM as part of it, and one stray bracket in the prose ends the block.
if defined NEEDS_SETUP (
  echo Setting up - this happens on a first run, and after a repair.
  echo.
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
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
