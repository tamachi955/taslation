@echo off
rem Double-click entry point: runs update.ps1 beside this file. Arguments are passed on (see the help in update.ps1).
rem The update copies a new update.cmd over this one while it runs, and cmd reads a batch file as it goes: the script
rem runs on the last line, with the exit after it on the same line (its code read when it runs, by call), so nothing
rem of this file is read after the copy.
setlocal
if not exist "%~dp0update.ps1" (
    echo update.ps1 is not next to this file. Run update.cmd in the TASlation folder.
    pause
    exit /b 1
)
rem update.ps1 keeps the window open to read the result, unless nobody watches (-Yes).
set "TASLATION_UPDATE_PAUSE=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %* & call exit /b %%ERRORLEVEL%%
