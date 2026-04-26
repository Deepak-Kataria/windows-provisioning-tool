$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir    = $ScriptDir

# If on a UNC path, copy source to local temp — cmd elevation breaks on UNC
if ($ScriptDir -like "\\*") {
    Write-Host "Network share detected. Copying to local temp..."
    $RunDir = Join-Path $env:TEMP "IT-Provisioning-Tool-src"
    robocopy $ScriptDir $RunDir /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    Write-Host "Running from: $RunDir"
}

# Find Python — check PATH first, then common install locations
# (elevated processes lose user-level PATH entries)
$PythonExe = $null

foreach ($cmd in @("python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$ver" -match "Python 3") {
            $PythonExe = $cmd
            break
        }
    } catch {}
}

if (-not $PythonExe) {
    $SearchRoots = @(
        $env:LOCALAPPDATA,
        $env:APPDATA,
        "C:\",
        "C:\Program Files",
        "C:\Program Files (x86)"
    )
    $Candidates = @()
    foreach ($root in $SearchRoots) {
        if ($root) {
            $Candidates += Get-ChildItem -Path $root -Filter "python.exe" -Recurse -Depth 5 `
                -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch "WindowsApps" }
        }
    }
    if ($Candidates.Count -gt 0) {
        $PythonExe = $Candidates[0].FullName
        Write-Host "Found Python at: $PythonExe"
    }
}

if (-not $PythonExe) {
    Write-Host ""
    Write-Host "ERROR: Python not found."
    Write-Host "Install Python from https://python.org and run: pip install -r requirements.txt"
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
