# Disable Windows Telemetry and Data Collection

param(
    [bool]$DisableTelemetry = $true,
    [bool]$DisableDiagnostics = $true,
    [bool]$DisableActivityHistory = $true,
    [bool]$DisableLocationTracking = $true,
    [bool]$DisableAdvertisingId = $true,
    [bool]$DisableFeedback = $true
)

function Set-RegValue {
    param($Path, $Name, $Value, $Type = "DWORD")
    if (!(Test-Path $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type $Type -Force
}

if ($DisableTelemetry) {
    Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" "AllowTelemetry" 0
    Set-RegValue "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection" "AllowTelemetry" 0
    Write-Output "DONE: Telemetry disabled"
}

if ($DisableDiagnostics) {
    Stop-Service -Name "DiagTrack" -Force -ErrorAction SilentlyContinue
    Set-Service -Name "DiagTrack" -StartupType Disabled -ErrorAction SilentlyContinue
    Stop-Service -Name "dmwappushservice" -Force -ErrorAction SilentlyContinue
    Set-Service -Name "dmwappushservice" -StartupType Disabled -ErrorAction SilentlyContinue
    Write-Output "DONE: Diagnostic services disabled"
}

if ($DisableActivityHistory) {
    Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" "EnableActivityFeed" 0
    Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" "PublishUserActivities" 0
    Write-Output "DONE: Activity history disabled"
}

if ($DisableLocationTracking) {
    Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors" "DisableLocation" 1
    Write-Output "DONE: Location tracking disabled"
}

if ($DisableAdvertisingId) {
    Set-RegValue "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" "Enabled" 0
    Write-Output "DONE: Advertising ID disabled"
}

if ($DisableFeedback) {
    Set-RegValue "HKCU:\SOFTWARE\Microsoft\Siuf\Rules" "NumberOfSIUFInPeriod" 0
    Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" "DoNotShowFeedbackNotifications" 1
    Write-Output "DONE: Feedback notifications disabled"
}
