@echo off
REM ── Launches IT Provisioning Tool. ──────────────────────────────────────
REM    Runs built exe if present; falls back to Python source (dev mode).
REM ── To build standalone exe: run build.bat ───────────────────────────────
powershell -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0launch.ps1""' -Verb RunAs -Wait"
if %errorlevel% neq 0 pause
