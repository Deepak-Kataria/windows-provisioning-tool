$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── MODE 1: Run built exe (preferred - no Python needed) ──────────────────
# --onefile exe self-extracts to local temp, so UNC path is fine.
$ExePath = Join-Path $ScriptDir "dist\IT-Provisioning-Tool.exe"
if (Test-Path $ExePath) {
    Write-Host "Launching IT-Provisioning-Tool.exe..."
    Start-Process $ExePath
    exit
}

# ── MODE 2: Dev mode - run from source (requires Python) ──────────────────
Write-Host "No built exe found. Running from source (dev mode)..."

$RunDir = $ScriptDir

# If on UNC, copy source to local temp - cmd elevation breaks on UNC
if ($ScriptDir -like "\\*") {
    Write-Host "Network share detected. Copying to local temp..."
    $RunDir = Join-Path $env:TEMP "IT-Provisioning-Tool-src"
    robocopy $ScriptDir $RunDir /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    Write-Host "Running from: $RunDir"
}

# Find Python - glob first, then PATH, then registry
$PythonExe = $null

foreach ($pattern in @(
    "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\python.exe",
    "C:\Python3*\python.exe",
    "C:\Program Files\Python3*\python.exe",
    "C:\Program Files (x86)\Python3*\python.exe"
)) {
    $match = Get-Item $pattern -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($match) { $PythonExe = $match.FullName; break }
}

if (-not $PythonExe) {
    foreach ($cmd in @("python", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$ver" -match "Python 3") { $PythonExe = $cmd; break }
        } catch {}
    }
}

if (-not $PythonExe) {
    foreach ($reg in @("HKCU:\Software\Python\PythonCore", "HKLM:\Software\Python\PythonCore")) {
        if (-not (Test-Path $reg)) { continue }
        foreach ($ver in (Get-ChildItem $reg -ErrorAction SilentlyContinue)) {
            $ipKey = Join-Path $ver.PSPath "InstallPath"
            if (-not (Test-Path $ipKey)) { continue }
            $ip = Get-ItemProperty $ipKey -ErrorAction SilentlyContinue
            $candidate = if ($ip.ExecutablePath) { $ip.ExecutablePath }
                         elseif ($ip.'(default)') { Join-Path $ip.'(default)'.TrimEnd('\') "python.exe" }
                         else { $null }
            if ($candidate -and (Test-Path $candidate)) { $PythonExe = $candidate; break }
        }
        if ($PythonExe) { break }
    }
}

Write-Host "Python: $PythonExe"

if (-not $PythonExe) {
    Write-Host ""
    Write-Host "ERROR: No built exe and no Python found."
    Write-Host "Option 1: Run build.bat to create the standalone exe."
    Write-Host "Option 2: Install Python from https://python.org"
    Read-Host "Press Enter to exit"
    exit 1
}

# Elevate if not admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Install dependencies
$ReqFile = Join-Path $RunDir "requirements.txt"
if (Test-Path $ReqFile) {
    Write-Host "Installing dependencies..."
    & $PythonExe -m pip install -r $ReqFile --quiet --disable-pip-version-check
    Write-Host "Done."
}

# Launch from source
Set-Location $RunDir
& $PythonExe main.py
