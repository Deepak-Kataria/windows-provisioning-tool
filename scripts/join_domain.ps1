param(
    [Parameter(Mandatory=$true)]
    [string]$DomainName,
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [Parameter(Mandatory=$true)]
    [string]$Password,
    [string]$OUPath = ""
)

try {
    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $Credential = New-Object System.Management.Automation.PSCredential("$DomainName\$Username", $SecurePassword)

    if ($OUPath -ne "") {
        Add-Computer -DomainName $DomainName -Credential $Credential -OUPath $OUPath -Force -ErrorAction Stop
    } else {
        Add-Computer -DomainName $DomainName -Credential $Credential -Force -ErrorAction Stop
    }

    Write-Output "SUCCESS: Joined domain $DomainName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
