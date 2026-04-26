$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir    = $ScriptDir

# If on a UNC path, copy source to local temp — cmd elevation breaks on UNC
if ($ScriptDir -like "\\*") {
    Write-Host "Network share detected. Copying to local temp..."
    $RunDir = Join-Path $env:TEMP "IT-Provisioning-Tool-src"
    robocopy $ScriptDir $RunDir /E /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    Write-Host "Running from: $RunDir"
}

# Find Python — registry first (survives elevation), then PATH, then known dirs
$PythonExe = $null

# 1. Registry (most reliable — works in both normal and elevated context)
$RegRoots = @(
    "HKCU:\Software\Python\PythonCore",
    "HKLM:\Software\Python\PythonCore",
    "HKLM:\Software\Wow6432Node\Python\PythonCore"
)
foreach ($reg in $RegRoots) {
    if (Test-Path $reg) {
        foreach ($ver in (Get-ChildItem $reg -ErrorAction SilentlyContinue)) {
            $ipKey = "$($ver.PSPath)\InstallPath"
            if (Test-Path $ipKey) {
                $ip = (Get-ItemProperty $ipKey -ErrorAction SilentlyContinue)
                $candidate = if ($ip.ExecutablePath) { $ip.ExecutablePath }
                             elseif ($ip.'(default)') { Join-Path $ip.'(default)' "python.exe" }
                             else { $null }
                if ($candidate -and (Test-Path $candidate)) {
                    $PythonExe = $candidate
                    break
                }
            }
        }
    }
    if ($PythonExe) { break }
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

# 3. Known install dirs
if (-not $PythonExe) {
    $KnownDirs = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        "C:\Python311", "C:\Python312", "C:\Python310",
        "C:\Program Files\Python311", "C:\Program Files\Python312"
    )
    foreach ($dir in $KnownDirs) {
        $candidate = Join-Path $dir "python.exe"
        if (Test-Path $candidate) { $PythonExe = $candidate; break }
        # also check subdirs one level deep (e.g. Programs\Python\Python311\)
        if (Test-Path $dir) {
            foreach ($sub in (Get-ChildItem $dir -Directory -ErrorAction SilentlyContinue)) {
                $candidate = Join-Path $sub.FullName "python.exe"
                if (Test-Path $candidate) { $PythonExe = $candidate; break }
            }
        }
        if ($PythonExe) { break }
    }
}

if (-not $PythonExe) {
    Write-Host ""
    Write-Host "ERROR: Python not found."
    Write-Host "Install Python from https://python.org and run: pip install -r requirements.txt"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Python: $PythonExe"

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
