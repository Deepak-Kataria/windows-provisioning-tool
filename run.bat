@echo off
REM ── DEV ONLY — requires Python installed ─────────────────────────────────
REM For deployment: run build.bat to produce dist\IT-Provisioning-Tool.exe
REM That exe is fully self-contained — no Python or other installs needed.
REM ─────────────────────────────────────────────────────────────────────────
powershell -ExecutionPolicy Bypass -File "%~dp0launch.ps1"
