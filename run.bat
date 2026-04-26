@echo off
REM ── DEV MODE — runs app directly from source (requires Python) ────────────
REM    Handles UNC share, auto-installs pip dependencies, elevates to admin.
REM ── FOR DEPLOYMENT: run build.bat to produce a standalone exe ─────────────
powershell -ExecutionPolicy Bypass -File "%~dp0launch.ps1"
