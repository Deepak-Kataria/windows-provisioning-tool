@echo off
REM ── RUN THIS ON YOUR DEV PC ONLY (requires Python installed) ──────────────
REM    Builds dist\IT-Provisioning-Tool.exe - fully standalone, no dependencies.
REM    After build: copy dist\IT-Provisioning-Tool.exe to the network share.
REM    Network machines run the exe via run.bat - they do NOT need to build.
REM ─────────────────────────────────────────────────────────────────────────
powershell -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0build.ps1""' -Verb RunAs -Wait"
pause
