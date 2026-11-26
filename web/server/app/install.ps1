# IT Provisioning agent installer. ASCII only.
# Served by the web console at /install.ps1. Run in an elevated PowerShell, using the one-line
# command shown by "Add machine". It contains no secrets: the agent can only be downloaded with
# a valid, unused enrollment code.
param(
    [Parameter(Mandatory = $true)][string]$Code
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Server = "__SERVER_URL__"
$ServiceName = "ITOpsAgent"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Run PowerShell as Administrator and paste the command again." -ForegroundColor Red
    return
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Dir = Join-Path $env:ProgramFiles "ITOpsAgent"
$StateDir = Join-Path $env:ProgramData "ITOpsAgent"
$Exe = Join-Path $Dir "itops-agent.exe"

# Only Administrators and SYSTEM may read or change the agent and its token.
function Set-Locked($path) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    & icacls.exe $path /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" | Out-Null
}

try {
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Write-Step "Removing the existing agent"
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        & sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 2
        Remove-Item -LiteralPath (Join-Path $StateDir "state.json") -Force -ErrorAction SilentlyContinue
    }

    Set-Locked $Dir
    Set-Locked $StateDir

    Write-Step "Downloading agent from $Server"
    $tmp = "$Exe.download"
    $body = @{ code = $Code } | ConvertTo-Json
    $resp = Invoke-WebRequest -Uri "$Server/api/agent/download" -Method Post -ContentType "application/json" `
        -Body $body -OutFile $tmp -PassThru -UseBasicParsing
    $want = [string]$resp.Headers["X-Agent-SHA256"]
    $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash.ToLower()
    if ($want -and $want.ToLower() -ne $got) {
        Remove-Item -LiteralPath $tmp -Force
        throw "Downloaded file is damaged (checksum mismatch). Try again."
    }
    Move-Item -LiteralPath $tmp -Destination $Exe -Force

    Write-Step "Enrolling this PC"
    & $Exe enroll --server $Server --code $Code
    if ($LASTEXITCODE -ne 0) { throw "Enrollment failed (see message above)." }

    Write-Step "Installing the Windows service"
    & $Exe service install
    if ($LASTEXITCODE -ne 0) { throw "Service install failed." }
    & $Exe service start
    if ($LASTEXITCODE -ne 0) { throw "Service start failed." }

    Write-Host ""
    Write-Host "Done. This PC ($env:COMPUTERNAME) now shows up in the web console." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "Install failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        try {
            $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())
            Write-Host ("Server said: " + $reader.ReadToEnd()) -ForegroundColor Red
        } catch {}
    }
}
