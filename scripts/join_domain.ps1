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
        DomainName            = $DomainName
        Credential            = $Credential
        UnjoinDomainCredential = $Credential
        Force                 = $true
        ErrorAction           = "Stop"
    }
    if ($OUPath -ne "") { $params["OUPath"] = $OUPath }
    if ($ServerIP -ne "") { $params["Server"] = $ServerIP }

    try {
        Add-Computer @params
    } catch {
        # "No mapping between account names" means the existing computer account
        # in AD is missing/corrupted. Remove-Computer also contacts the DC and
        # fails the same way. Use WMI instead: flag 0 = local-only, no DC contact.
        if ($_ -match "No mapping between account names|0x534|none mapped|Failed to unjoin") {
            Write-Output "WARNING: Domain unjoin failed (stale/missing computer account). Unjoining locally and retrying..."
            (Get-WmiObject Win32_ComputerSystem).UnjoinDomainOrWorkgroup($null, $null, 0) | Out-Null
            $params.Remove("UnjoinDomainCredential")
            Add-Computer @params
        } else {
            throw
        }
    }

    Write-Output "SUCCESS: Joined domain $DomainName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
