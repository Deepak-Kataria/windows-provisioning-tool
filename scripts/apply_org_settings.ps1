param(
    [Parameter(Mandatory=$true)]
    [string]$SettingsJson
)

$settings = $SettingsJson | ConvertFrom-Json

foreach ($tweak in $settings) {
    try {
        $key = $tweak.key
        $valueName = $tweak.value_name
        $valueData = $tweak.value_data
        $valueType = $tweak.value_type

        if (!(Test-Path $key)) {
            New-Item -Path $key -Force | Out-Null
        }
        Set-ItemProperty -Path $key -Name $valueName -Value $valueData -Type $valueType -Force
        Write-Output "APPLIED: $($tweak.name)"
    } catch {
        Write-Output "ERROR: $($tweak.name) - $($_.Exception.Message)"
    }
}
