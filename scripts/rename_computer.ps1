param(
    [Parameter(Mandatory=$true)]
    [string]$NewName,
    [string]$DomainUser = ""
)

try {
    $partOfDomain = (Get-WmiObject Win32_ComputerSystem -EA SilentlyContinue).PartOfDomain -eq $true

    if ($DomainUser) {
        $passPlain = [Console]::In.ReadLine()
        $SecurePass = ConvertTo-SecureString $passPlain -AsPlainText -Force
        $Cred = New-Object System.Management.Automation.PSCredential($DomainUser, $SecurePass)
        Rename-Computer -NewName $NewName -DomainCredential $Cred -Force -ErrorAction Stop
    } else {
        Rename-Computer -NewName $NewName -Force -ErrorAction Stop
    }
    # Rename-Computer can leave the TCP/IP DNS hostname (shown as "Device name"
    # in Settings > About) out of sync with the NetBIOS ComputerName on
    # domain-joined machines. Force both to match the new name.
    $tcpipPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
    Set-ItemProperty -Path $tcpipPath -Name "Hostname" -Value $NewName -ErrorAction Stop
    Set-ItemProperty -Path $tcpipPath -Name "NV Hostname" -Value $NewName -ErrorAction Stop

    Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    if ($partOfDomain) {
        Write-Output "RENAME_CONTEXT: DOMAIN_JOINED"
    } else {
        Write-Output "RENAME_CONTEXT: LOCAL"
    }
    exit 1
}
