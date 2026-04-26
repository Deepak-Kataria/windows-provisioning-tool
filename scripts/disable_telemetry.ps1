# Disable / Restore Windows Telemetry and Data Collection
# Mode: "disable" (default) or "restore"

param(
    [string]$Mode = "disable",
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

if ($Mode -eq "restore") {

    if ($DisableTelemetry) {
        Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" "AllowTelemetry" 1
        Set-RegValue "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection" "AllowTelemetry" 1
        Write-Output "DONE: Telemetry re-enabled"
    }

    if ($DisableDiagnostics) {
        Set-Service -Name "DiagTrack" -StartupType Automatic -ErrorAction SilentlyContinue
        Start-Service -Name "DiagTrack" -ErrorAction SilentlyContinue
        Set-Service -Name "dmwappushservice" -StartupType Automatic -ErrorAction SilentlyContinue
        Start-Service -Name "dmwappushservice" -ErrorAction SilentlyContinue
        Write-Output "DONE: Diagnostic services re-enabled"
    }

    if ($DisableActivityHistory) {
        Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" "EnableActivityFeed" 1
        Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" "PublishUserActivities" 1
        Write-Output "DONE: Activity history re-enabled"
    }

    if ($DisableLocationTracking) {
        Set-RegValue "HKLM:\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors" "DisableLocation" 0
        Write-Output "DONE: Location tracking re-enabled"
    }

    if ($DisableAdvertisingId) {
        Set-RegValue "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo" "Enabled" 1
        Write-Output "DONE: Advertising ID re-enabled"
    }

    if ($DisableFeedback) {
        Set-RegValue "HKCU:\SOFTWARE\Microsoft\Siuf\Rules" "NumberOfSIUFInPeriod" 3
        Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection" `
            -Name "DoNotShowFeedbackNotifications" -ErrorAction SilentlyContinue
        Write-Output "DONE: Feedback notifications re-enabled"
    }

} else {

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

}
