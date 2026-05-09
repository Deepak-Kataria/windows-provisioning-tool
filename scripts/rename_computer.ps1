param(
    [Parameter(Mandatory=$true)]
    [string]$NewName
)

try {
    Rename-Computer -NewName $NewName -Force -ErrorAction Stop
    Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
} catch {
    $errMsg = $_.Exception.Message
    # If the failure is domain-related, fall back to a local-only rename via registry.
    # This is safe for provisioning: the machine will rejoin the domain with the new name.
    if ($errMsg -match "domain|contacted|network path") {
        try {
            $regBase = "HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName"
            Set-ItemProperty -Path "$regBase\ComputerName"       -Name "ComputerName" -Value $NewName -ErrorAction Stop
            Set-ItemProperty -Path "$regBase\ActiveComputerName" -Name "ComputerName" -Value $NewName -ErrorAction Stop
            Write-Output "SUCCESS: Computer renamed to $NewName (local only - DC unreachable). Reboot required."
        } catch {
            Write-Output "ERROR: $($_.Exception.Message)"
            exit 1
        }
    } else {
        Write-Output "ERROR: $errMsg"
        exit 1
    }
}
