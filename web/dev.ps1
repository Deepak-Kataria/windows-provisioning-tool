# Local development helper for the web version. ASCII only (see repo rule for .ps1 files).
#
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 setup        create web\.venv, install deps
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 test         run server + agent tests
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 admin        create first admin (prompts)
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 server       run API on http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 enroll CODE  enroll this PC's agent to the local server
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 agent        run the agent in the foreground
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1 cli ARGS     API client: login, code, machines, run, jobs, audit
#
# Dev data lives in web\.dev\ (SQLite DB, agent state). Delete that folder to start fresh.
param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest = @()
)
$Arg = if ($Rest.Count -gt 0) { $Rest[0] } else { "" }
$ErrorActionPreference = "Stop"

$Web = $PSScriptRoot
$Venv = Join-Path $Web ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"
$DevDir = Join-Path $Web ".dev"
$Port = 8000

New-Item -ItemType Directory -Force $DevDir | Out-Null
$env:ITOPS_DATABASE_URL = "sqlite:///" + ((Join-Path $DevDir "itops-dev.db") -replace '\\', '/')
$env:ITOPS_SECRET_KEY = "dev-only-secret"
$env:ITOPS_BASE_URL = "http://127.0.0.1:$Port"
$env:ITOPS_AGENT_STATE = Join-Path $DevDir "agent-state"
$env:ITOPS_AGENT_DEV = "1"

function Assert-Venv {
    if (-not (Test-Path $Py)) { throw "Run 'web\dev.ps1 setup' first." }
}

switch ($Command) {
    "setup" {
        if (-not (Test-Path $Py)) { python -m venv $Venv }
        & $Py -m pip install --upgrade pip -q
        & $Py -m pip install -q -r (Join-Path $Web "server\requirements-dev.txt") -r (Join-Path $Web "agent\requirements.txt")
        Write-Host "Setup done. Next: web\dev.ps1 test"
    }
    "test" {
        Assert-Venv
        Push-Location (Join-Path $Web "server"); try { & $Py -m pytest -q -p no:warnings tests; $s = $LASTEXITCODE } finally { Pop-Location }
        Push-Location (Join-Path $Web "agent"); try { & $Py -m pytest -q -p no:warnings tests; $a = $LASTEXITCODE } finally { Pop-Location }
        if ($s -ne 0 -or $a -ne 0) { exit 1 }
    }
    "admin" {
        Assert-Venv
        $name = if ($Arg) { $Arg } else { "admin" }
        Push-Location (Join-Path $Web "server"); try { & $Py -m app.cli create-admin $name } finally { Pop-Location }
    }
    "server" {
        Assert-Venv
        Write-Host "API on http://127.0.0.1:$Port   (docs: http://127.0.0.1:$Port/api/docs)"
        Push-Location (Join-Path $Web "server"); try { & $Py -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload } finally { Pop-Location }
    }
    "enroll" {
        Assert-Venv
        if (-not $Arg) { throw "Usage: web\dev.ps1 enroll <CODE>" }
        $env:PYTHONPATH = Join-Path $Web "agent"
        & $Py -m itops_agent enroll --server "http://127.0.0.1:$Port" --code $Arg
    }
    "agent" {
        Assert-Venv
        $env:PYTHONPATH = Join-Path $Web "agent"
        & $Py -m itops_agent run
    }
    "cli" {
        Assert-Venv
        & $Py (Join-Path $Web "tools\apicli.py") @Rest
    }
    default {
        Get-Content $PSCommandPath | Select-Object -Skip 1 -First 10 | ForEach-Object { $_ -replace '^# ?', '' }
    }
}
