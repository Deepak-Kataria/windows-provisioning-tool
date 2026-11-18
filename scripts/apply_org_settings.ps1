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

function Set-LocalSecPolicy {
    param([string]$Key, [string]$Value)
    $f  = "$env:TEMP\scp_$PID.inf"
    $db = "$env:TEMP\scp_$PID.sdb"
    "[Unicode]`r`nUnicode=yes`r`n[System Access]`r`n$Key = $Value" | Out-File $f -Encoding unicode
    secedit /configure /db $db /cfg $f /quiet
    Remove-Item $f,$db -ErrorAction SilentlyContinue
}

foreach ($tweak in $settings) {
    try {
        if ($tweak.type -eq "command") {
            if ($Mode -eq "restore") {
                if ($tweak.rollback_cmd) { Invoke-Expression $tweak.rollback_cmd }
                Write-Output "RESTORED: $($tweak.name)"
            } else {
                Invoke-Expression $tweak.apply_cmd
                Write-Output "APPLIED: $($tweak.name)"
            }
        } else {
            if ($Mode -eq "restore") {
                if ($tweak.rollback_delete) {
                    Remove-ItemProperty -Path $tweak.key -Name $tweak.value_name -ErrorAction SilentlyContinue
                } else {
                    Set-RegValue $tweak.key $tweak.value_name $tweak.rollback_data $tweak.value_type
                }
                Write-Output "RESTORED: $($tweak.name)"
            } else {
                Set-RegValue $tweak.key $tweak.value_name $tweak.value_data $tweak.value_type
                Write-Output "APPLIED: $($tweak.name)"
            }
        }
    } catch {
        Write-Output "ERROR: $($tweak.name) - $($_.Exception.Message)"
    }
}
