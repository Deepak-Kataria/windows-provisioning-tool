param(
    [Parameter(Mandatory=$true)]
    [string]$DomainName,
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [string]$OUPath = "",
    [string]$ServerIP = ""
)

$Password = [Console]::In.ReadLine()

try {
    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $Credential = New-Object System.Management.Automation.PSCredential("$DomainName\$Username", $SecurePassword)

    $params = @{
        DomainName = $DomainName
        Credential = $Credential
        Force      = $true
        ErrorAction = "Stop"
    }
    if ($OUPath -ne "") { $params["OUPath"] = $OUPath }
    if ($ServerIP -ne "") { $params["Server"] = $ServerIP }

    Add-Computer @params

    Write-Output "SUCCESS: Joined domain $DomainName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
