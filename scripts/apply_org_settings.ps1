param(
    [Parameter(Mandatory=$true)]
    [string]$SettingsJson,
    [string]$Mode = "apply"
)

$settings = $SettingsJson | ConvertFrom-Json

function Set-RegValue {
    param($Path, $Name, $Value, $Type)
    if (!(Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
    Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type $Type -Force
}

if ($Mode -eq "restore") {
    foreach ($tweak in $settings) {
        try {
            if ($tweak.rollback_delete) {
                Remove-ItemProperty -Path $tweak.key -Name $tweak.value_name -ErrorAction SilentlyContinue
            } else {
                Set-RegValue $tweak.key $tweak.value_name $tweak.rollback_data $tweak.value_type
            }
            Write-Output "RESTORED: $($tweak.name)"
        } catch {
            Write-Output "ERROR: $($tweak.name) - $($_.Exception.Message)"
        }
    }
} else {
    foreach ($tweak in $settings) {
        try {
            Set-RegValue $tweak.key $tweak.value_name $tweak.value_data $tweak.value_type
            Write-Output "APPLIED: $($tweak.name)"
        } catch {
            Write-Output "ERROR: $($tweak.name) - $($_.Exception.Message)"
        }
    }
}
