@echo off
setlocal
pushd "%~dp0"

REM ── Dev mode: run directly from source (no build needed) ──────────
REM When ready to ship, run build.bat and distribute dist\IT-Provisioning-Tool.exe

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d ""%~dp0"" && python main.py && pause' -Verb RunAs"
    popd
    exit /b
)

where python >nul 2>&1
if %errorLevel% equ 0 (
    python main.py
    popd
    pause
    exit /b
)

where py >nul 2>&1
if %errorLevel% equ 0 (
    py main.py
    popd
    pause
    exit /b
)

echo ERROR: Python not found.
echo Install Python from https://python.org and run: pip install -r requirements.txt
popd
pause
