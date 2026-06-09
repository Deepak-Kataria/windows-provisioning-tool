param(
    [Parameter(Mandatory=$true)]
    [string]$NewName,
    [string]$DomainUser = ""
)

try {
    if ($DomainUser) {
        $passPlain = [Console]::In.ReadLine()
        $SecurePass = ConvertTo-SecureString $passPlain -AsPlainText -Force
        $Cred = New-Object System.Management.Automation.PSCredential($DomainUser, $SecurePass)
        Rename-Computer -NewName $NewName -DomainCredential $Cred -Force -ErrorAction Stop
    } else {
        Rename-Computer -NewName $NewName -Force -ErrorAction Stop
    }
    Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
