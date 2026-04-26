$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir    = $ScriptDir

# If on a UNC path, copy source to local temp — cmd elevation breaks on UNC
if ($ScriptDir -like "\\*") {
    Write-Host "Network share detected. Copying to local temp..."
    $RunDir = Join-Path $env:TEMP "IT-Provisioning-Tool-src"
    robocopy $ScriptDir $RunDir /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    Write-Host "Running from: $RunDir"
}

# Find Python
$PythonExe = $null

# 1. Direct glob — fastest, works even without registry
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

# 2. PATH
if (-not $PythonExe) {
    foreach ($cmd in @("python", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$ver" -match "Python 3") { $PythonExe = $cmd; break }
        } catch {}
    }
}

# 3. Registry fallback
if (-not $PythonExe) {
    foreach ($reg in @("HKCU:\Software\Python\PythonCore","HKLM:\Software\Python\PythonCore")) {
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

Write-Host "Python search result: $PythonExe"

if (-not $PythonExe) {
    Write-Host ""
    Write-Host "ERROR: Python not found. LOCALAPPDATA=$env:LOCALAPPDATA"
    Write-Host "Install Python from https://python.org then: pip install -r requirements.txt"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if already admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    # Relaunch elevated
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Run the tool
Set-Location $RunDir
& $PythonExe main.py
