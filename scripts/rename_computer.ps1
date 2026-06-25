param(
    [Parameter(Mandatory=$true)]
    [string]$NewName,
    [string]$DomainUser = "",
    [switch]$LocalOnly
)

try {
    $partOfDomain = (Get-WmiObject Win32_ComputerSystem -EA SilentlyContinue).PartOfDomain -eq $true

    if ($LocalOnly) {
        # Registry-only rename - does not update AD. Useful when computer account
        # is missing in domain (deleted or never created). AD must be fixed separately.
        $compNamePath = 'HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName'
        Set-ItemProperty -Path $compNamePath -Name 'ComputerName' -Value $NewName -ErrorAction Stop

        $tcpipPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
        Set-ItemProperty -Path $tcpipPath -Name 'Hostname'    -Value $NewName -ErrorAction Stop
        Set-ItemProperty -Path $tcpipPath -Name 'NV Hostname' -Value $NewName -ErrorAction Stop

        Write-Output "SUCCESS: Computer renamed to $NewName (local only - AD not updated). Reboot required."
    } elseif ($DomainUser) {
        $passPlain = [Console]::In.ReadLine()
        $SecurePass = ConvertTo-SecureString $passPlain -AsPlainText -Force
        $Cred = New-Object System.Management.Automation.PSCredential($DomainUser, $SecurePass)
        Rename-Computer -NewName $NewName -DomainCredential $Cred -Force -ErrorAction Stop

        $tcpipPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
        Set-ItemProperty -Path $tcpipPath -Name 'Hostname'    -Value $NewName -ErrorAction Stop
        Set-ItemProperty -Path $tcpipPath -Name 'NV Hostname' -Value $NewName -ErrorAction Stop

        Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
    } else {
        Rename-Computer -NewName $NewName -Force -ErrorAction Stop

        $tcpipPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
        Set-ItemProperty -Path $tcpipPath -Name 'Hostname'    -Value $NewName -ErrorAction Stop
        Set-ItemProperty -Path $tcpipPath -Name 'NV Hostname' -Value $NewName -ErrorAction Stop

        Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    if ($partOfDomain) {
        Write-Output "RENAME_CONTEXT: DOMAIN_JOINED"
    } else {
        Write-Output "RENAME_CONTEXT: LOCAL"
    }
    exit 1
}
