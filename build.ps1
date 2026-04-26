$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalBuild = Join-Path $env:TEMP "IT-Provisioning-Tool-build"
$BuildEnv   = Join-Path $LocalBuild "_build_env"
$PythonExe  = $null

Write-Host "Building IT Provisioning Tool..."
Write-Host ""

# Add Defender exclusion immediately - it blocks downloaded exes and the PyInstaller bootloader
New-Item -ItemType Directory -Force -Path $LocalBuild | Out-Null
Write-Host "Adding Windows Defender exclusion for build directory..."
try {
    Add-MpPreference -ExclusionPath $LocalBuild -ErrorAction Stop
    Write-Host "  Exclusion added: $LocalBuild"
} catch {
    Write-Host "  Warning: Could not add Defender exclusion ($_). Build may fail."
}
Write-Host ""

# Try system Python first
foreach ($cmd in @("py", "python")) {
    try {
        $result = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$result" -match "Python 3") {
            $PythonExe = $cmd
            Write-Host "Found system Python: $cmd ($result)"
            break
        }
    } catch {}
}

# No system Python - download and silently install full Python 3.11
if (-not $PythonExe) {
    Write-Host "No Python found. Downloading full Python 3.11 (~25MB, one-time setup)..."
    $PythonDir       = Join-Path $BuildEnv "python"
    $PythonInstaller = Join-Path $BuildEnv "python-installer.exe"

    New-Item -ItemType Directory -Force -Path $BuildEnv | Out-Null

    Write-Host "  Downloading Python installer..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" `
        -OutFile $PythonInstaller -UseBasicParsing

    Write-Host "  Installing Python silently..."
    $installArgs = @(
        "/quiet",
        "InstallAllUsers=1",
        "TargetDir=$PythonDir",
        "PrependPath=0",
        "Include_launcher=0",
        "Include_test=0",
        "Shortcuts=0"
    )
    $proc = Start-Process -FilePath $PythonInstaller -ArgumentList $installArgs -Wait -PassThru
    Write-Host "  Installer exit code: $($proc.ExitCode)"

    if (-not (Test-Path (Join-Path $PythonDir "python.exe"))) {
        Write-Host "ERROR: Python installation failed (exit code $($proc.ExitCode))."
        try { Remove-MpPreference -ExclusionPath $LocalBuild -ErrorAction SilentlyContinue } catch {}
        exit 1
    }

    $PythonExe = Join-Path $PythonDir "python.exe"
    Write-Host "  Python ready."
}

Write-Host ""
Write-Host "Installing dependencies..."
& $PythonExe -m pip install -r (Join-Path $ScriptDir "requirements.txt") --quiet

# Copy source to local temp - keeps PyInstaller fully off the UNC path
Write-Host ""
Write-Host "Copying source to local build directory..."
$LocalSrc = Join-Path $LocalBuild "src"
if (Test-Path $LocalSrc) { Remove-Item $LocalSrc -Recurse -Force }
New-Item -ItemType Directory -Force -Path $LocalSrc | Out-Null
Copy-Item -Path (Join-Path $ScriptDir "*") -Destination $LocalSrc -Recurse `
    -Exclude "_build_env","build","dist","*.spec",".git","__pycache__","logs"

$LocalDist = Join-Path $LocalBuild "dist"
$LocalWork = Join-Path $LocalBuild "work"

Write-Host ""
Write-Host "Locating bcrypt and cffi packages..."
$BcryptDir   = (& $PythonExe -c "import os,bcrypt; print(os.path.dirname(bcrypt.__file__))").Trim()
$CffiBackend = (& $PythonExe -c "import os,_cffi_backend; print(os.path.abspath(_cffi_backend.__file__))").Trim()
Write-Host "  bcrypt      : $BcryptDir"
Write-Host "  _cffi_backend: $CffiBackend"

Write-Host ""
Write-Host "Running PyInstaller (building locally)..."
& $PythonExe -m PyInstaller --noconfirm --onefile --windowed --uac-admin `
    --name "IT-Provisioning-Tool" `
    --collect-data customtkinter `
    --hidden-import bcrypt `
    --hidden-import _cffi_backend `
    "--add-binary=${BcryptDir}\_bcrypt.pyd;bcrypt" `
    "--add-data=${BcryptDir}\__init__.py;bcrypt" `
    "--add-binary=${CffiBackend};." `
    "--add-data=$LocalSrc\config;config" `
    "--add-data=$LocalSrc\scripts;scripts" `
    --distpath $LocalDist `
    --workpath $LocalWork `
    --specpath $LocalBuild `
    (Join-Path $LocalSrc "main.py")

$buildOk = ($LASTEXITCODE -eq 0)

# Always remove Defender exclusion
try { Remove-MpPreference -ExclusionPath $LocalBuild -ErrorAction SilentlyContinue } catch {}

if (-not $buildOk) {
    Write-Host ""
    Write-Host "Build failed. See output above."
    exit 1
}

# Copy output back to project dist folder
Write-Host ""
Write-Host "Copying output back..."
$FinalDist = Join-Path $ScriptDir "dist"
if (Test-Path $FinalDist) { Remove-Item $FinalDist -Recurse -Force }
Copy-Item -Path $LocalDist -Destination $FinalDist -Recurse

# Clean up local temp
Remove-Item $LocalBuild -Recurse -Force

Write-Host ""
Write-Host "Build complete: dist\IT-Provisioning-Tool.exe"
Write-Host "Copy IT-Provisioning-Tool.exe to any machine and run. No Python needed."
