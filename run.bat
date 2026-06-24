@echo off
REM ── Launches IT Provisioning Tool. ──────────────────────────────────────
REM    SOURCE MODE (testing) — remove -DevMode below after building final exe
REM ── To build standalone exe: run build.bat ───────────────────────────────
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$f='%~dp0launch.ps1'; Start-Process powershell -ArgumentList '-ExecutionPolicy','Bypass','-File',$f,'-DevMode' -WindowStyle Hidden -Verb RunAs -Wait"
if %errorlevel% neq 0 pause
