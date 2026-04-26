@echo off
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0build.ps1""' -Verb RunAs -Wait"
    exit /b
)
powershell -ExecutionPolicy Bypass -File "%~dp0build.ps1"
pause
