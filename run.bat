@echo off
setlocal

set "EXE=%~dp0dist\IT-Provisioning-Tool.exe"

if exist "%EXE%" (
    start "" "%EXE%"
    exit /b
)

REM No built exe — run from source (dev mode)
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
