$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Find Python first (dev mode preferred when Python available) ──────────────
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

# ── MODE 1: Dev mode - Python found, run from source ─────────────────────────
if ($PythonExe) {
    Write-Host "Python found: $PythonExe"
    Write-Host "Running from source (dev mode)..."

    $RunDir = $ScriptDir

    # If on UNC, copy source to local temp
    if ($ScriptDir -like "\\*") {
        Write-Host "Network share detected. Copying to local temp..."
        $RunDir = Join-Path $env:TEMP "IT-Provisioning-Tool-src"
        robocopy $ScriptDir $RunDir /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
        Write-Host "Running from: $RunDir"
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

    Set-Location $RunDir
    & $PythonExe main.py
    exit
}

# ── MODE 2: No Python - run built exe ────────────────────────────────────────
$ExePath = Join-Path $ScriptDir "dist\IT-Provisioning-Tool.exe"
if (Test-Path $ExePath) {
    Write-Host "No Python found. Launching IT-Provisioning-Tool.exe..."
    Start-Process $ExePath
    exit
}

# ── Neither available ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "ERROR: No built exe and no Python found."
Write-Host "Option 1: Run build.bat to create the standalone exe."
Write-Host "Option 2: Install Python from https://python.org"
Read-Host "Press Enter to exit"
exit 1
