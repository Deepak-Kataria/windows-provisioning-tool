# Build the agent exe. DEV PC ONLY. ASCII only.
#
#   powershell -ExecutionPolicy Bypass -File web\agent\build.ps1 -Key C:\keys\itops-bundle.key   (production, signed)
#   powershell -ExecutionPolicy Bypass -File web\agent\build.ps1 -Unsigned                       (local testing only)
#
# Output: web\agent\dist\itops-agent.exe + version.txt
# The local dev server serves web\agent\dist automatically. For production copy both files to
# the server folder mounted at /app/agent-dist (see web/deploy/docker-compose.yml).
# Never give the exe to anyone: PCs download it from the server with their enrollment code.
param(
    [string]$Key = "",
    [switch]$Unsigned
)
$ErrorActionPreference = "Stop"

if ((-not $Key -and -not $Unsigned) -or ($Key -and $Unsigned)) {
    throw "Use either -Key <signing key> or -Unsigned"
}
$Agent = $PSScriptRoot
$Web = Split-Path $Agent -Parent
$Repo = Split-Path $Web -Parent
$Py = Join-Path $Web ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Run web\dev.ps1 setup first" }
& $Py -m pip install -q pyinstaller==6.16.0

$Build = Join-Path $Agent "build"
$Bundle = Join-Path $Build "bundle"
$Dist = Join-Path $Agent "dist"
$KeyFile = Join-Path $Agent "itops_agent\bundle_key.py"
$KeyOriginal = Get-Content -Raw $KeyFile

# 1. script bundle (actions + scripts + app catalog), signed unless -Unsigned
if ($Unsigned) {
    & $Py (Join-Path $Web "tools\bundle_tool.py") build --unsigned --out $Bundle
    $pub = ""
    $allow = "True"
} else {
    $out = & $Py (Join-Path $Web "tools\bundle_tool.py") build --key $Key --out $Bundle
    $out | Write-Host
    $pub = (($out | Select-String "public key: ") -replace ".*public key: ", "").Trim()
    if (-not $pub) { throw "could not read public key from bundle_tool output" }
    $allow = "False"
}
if ($LASTEXITCODE -ne 0) { throw "bundle build failed" }

# fail fast: PyInstaller silently skips modules that do not compile
& $Py -m compileall -q (Join-Path $Agent "itops_agent")
if ($LASTEXITCODE -ne 0) { throw "agent code has syntax errors" }
& $Py -c "import sys; sys.path[:0] = [r'$Agent', r'$Repo']; import itops_agent.handlers, modules.security_checks"
if ($LASTEXITCODE -ne 0) { throw "agent modules failed to import" }

$version = (& $Py -c "import sys; sys.path.insert(0, r'$Agent'); import itops_agent; print(itops_agent.VERSION)").Trim()

try {
    # 2. bake the public key into the exe
    Set-Content -Encoding ascii -Path $KeyFile -Value @"
# Written by build.ps1 for this build.
PUBLIC_KEY_HEX = "$pub"
ALLOW_UNSIGNED = $allow
"@
    # 3. one-file exe
    Push-Location $Agent
    try {
        & $Py -m PyInstaller --noconfirm --clean --onefile --console `
            --name itops-agent `
            --distpath $Dist --workpath (Join-Path $Build "pyi") --specpath $Build `
            --paths $Agent --paths $Repo `
            --hidden-import modules.security_checks `
            --hidden-import win32timezone `
            --collect-submodules itops_agent `
            --add-data "$Bundle;." `
            run_agent.py
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    } finally { Pop-Location }
} finally {
    Set-Content -Encoding ascii -NoNewline -Path $KeyFile -Value $KeyOriginal
}

Set-Content -Encoding ascii -Path (Join-Path $Dist "version.txt") -Value $version
$exe = Join-Path $Dist "itops-agent.exe"
$hash = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower()
Write-Host ""
Write-Host "Built $exe  v$version  $([Math]::Round((Get-Item $exe).Length / 1MB, 1)) MB" -ForegroundColor Green
Write-Host "sha256 $hash"
if ($Unsigned) { Write-Host "UNSIGNED dev build - do not put it on the production server." -ForegroundColor Yellow }
