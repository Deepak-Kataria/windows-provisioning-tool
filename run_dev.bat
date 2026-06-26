@echo off
REM ── Dev/test launcher: always runs from source, skips built exe ──────────
REM    Use this to test source changes without running build.bat first.
REM ─────────────────────────────────────────────────────────────────────────
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$f='%~dp0launch.ps1'; Start-Process powershell -ArgumentList '-ExecutionPolicy','Bypass','-File',$f,'-DevMode' -WindowStyle Hidden -Verb RunAs -Wait"
if %errorlevel% neq 0 pause
