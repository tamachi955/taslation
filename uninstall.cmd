@echo off
rem Double-click entry point: runs uninstall.ps1 beside this file. Arguments are passed on (see the help in uninstall.ps1).
setlocal
if not exist "%~dp0uninstall.ps1" (
    echo uninstall.ps1 is not next to this file. Unpack the whole ZIP into a folder and run uninstall.cmd there.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
set "CODE=%ERRORLEVEL%"
rem The window closes with the script: keep it open to read the result, unless nobody watches (-Yes).
set "WAIT=1"
for %%A in (%*) do if /i "%%~A"=="-Yes" set "WAIT="
if defined WAIT pause
exit /b %CODE%
