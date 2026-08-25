@echo off
REM EIVA - setup. Double-click this file, or type  setup  in a terminal here.
REM
REM Why this exists when setup.ps1 is sitting right next to it: Windows will
REM not run an unsigned .ps1 that arrived from the internet. Telling people to
REM "just set RemoteSigned" does not help - a file unzipped from a download
REM carries a mark saying where it came from, and RemoteSigned answers that
REM mark by demanding a signature this script does not have. So running
REM .\setup.ps1 fails twice over, with a security error both times, before a
REM line of it has run. Nothing inside a .ps1 can fix that; it has to be
REM started from something that policy does not apply to. A .cmd is that.
REM
REM The policy is set for this one PowerShell process and nothing about the
REM machine is changed. setup.ps1 then clears the download mark on the folder,
REM so from the second run onwards .\setup.ps1 works like any other script.
REM
REM   setup.cmd -NoPythonInstall    use your own Python; do not install one
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo Start EIVA with eiva.cmd, or eiva.vbs for no console window at all.
) else (
  echo Setup did not finish. The reason is above this line.
)
echo.
REM Double-clicked, this window is the only place the output exists, and
REM without a pause it closes on the very error the reader needs to see.
pause
exit /b %RC%
