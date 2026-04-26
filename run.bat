@echo off
setlocal

set "SRCDIR=%~dp0"
set "RUNDIR=%~dp0"

REM If running from a UNC path, copy source to local temp first.
REM Elevated processes lose UNC access, and Python path resolution can break on shares.
echo %SRCDIR% | findstr /b "\\\\" >nul 2>&1
if %errorLevel% equ 0 (
    echo Detected network share. Copying to local temp...
    set "RUNDIR=%TEMP%\IT-Provisioning-Tool-src\"
    robocopy "%SRCDIR%" "%TEMP%\IT-Provisioning-Tool-src" /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul 2>&1
    echo Done. Running from local copy...
)

pushd "%RUNDIR%"

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d ""%RUNDIR%"" && python main.py && pause' -Verb RunAs"
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
