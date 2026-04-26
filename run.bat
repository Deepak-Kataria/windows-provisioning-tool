@echo off
setlocal

set "SRC=%~dp0dist\IT-Provisioning-Tool"
set "DST=%TEMP%\IT-Provisioning-Tool-run"

if not exist "%SRC%\IT-Provisioning-Tool.exe" goto :dev_run

echo Syncing to local temp (required for network share DLL loading)...
robocopy "%SRC%" "%DST%" /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul 2>&1

start "" "%DST%\IT-Provisioning-Tool.exe"
exit /b

:dev_run
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c pushd ""%~dp0"" && python main.py && pause' -Verb RunAs"
    exit /b
)

where python >nul 2>&1
if %errorLevel% equ 0 (
    pushd "%~dp0"
    python main.py
    popd
    pause
    exit /b
)

where py >nul 2>&1
if %errorLevel% equ 0 (
    pushd "%~dp0"
    py main.py
    popd
    pause
    exit /b
)

echo ERROR: Python not found. Run build.bat first to create a standalone exe.
pause
