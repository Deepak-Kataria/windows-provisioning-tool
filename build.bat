@echo off
REM ── BUILDS standalone IT-Provisioning-Tool.exe ────────────────────────────
REM    Finds/downloads Python, installs deps, runs PyInstaller.
REM    Output: dist\IT-Provisioning-Tool.exe  (copy to any machine, no deps needed)
REM ── FOR DEV MODE (run from source): use run.bat instead ───────────────────
powershell -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0build.ps1""' -Verb RunAs -Wait"
pause
