param(
    [Parameter(Mandatory=$true)]
    [string]$DomainName,
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [string]$OUPath = "",
    [string]$ServerIP = ""
)

$Password = [Console]::In.ReadLine()

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Output "ERROR: Must run as administrator to join a domain."
    exit 1
}

$target = if ($ServerIP -ne "") { $ServerIP } else { $DomainName }
Write-Output "INFO: Checking connectivity to $target on port 389 (LDAP)..."
try {
    $tcp = [System.Net.Sockets.TcpClient]::new()
    $connect = $tcp.BeginConnect($target, 389, $null, $null)
    $ok = $connect.AsyncWaitHandle.WaitOne(5000)
    $tcp.Close()
    if (-not $ok) { throw "Timed out" }
    Write-Output "INFO: LDAP port reachable."
} catch {
    Write-Output "ERROR: Cannot reach $target on port 389. Check DC IP, DNS, and firewall. Detail: $($_.Exception.Message)"
    exit 1
}

try {
    $EffectiveUser = if ($Username -match '\\|@') {
        $Username
    } else {
        $netbios = $DomainName.Split('.')[0].ToUpper()
        "$netbios\$Username"
    }

    $SecurePassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $Credential = New-Object System.Management.Automation.PSCredential($EffectiveUser, $SecurePassword)

    # Domain join must go through PDC emulator FSMO role holder.
    # If a specific DC IP is given, find the PDC from it; do not pass the DC IP
    # directly to Add-Computer since it may be a secondary DC.
    $joinServer = $null
    if ($ServerIP -ne "") {
        Write-Output "INFO: Locating PDC emulator for $DomainName via $ServerIP ..."
        try {
            $ctx = New-Object System.DirectoryServices.ActiveDirectory.DirectoryContext(
                [System.DirectoryServices.ActiveDirectory.DirectoryContextType]::DirectoryServer,
                $ServerIP, $EffectiveUser, $Password)
            $dc = [System.DirectoryServices.ActiveDirectory.DomainController]::GetDomainController($ctx)
            $pdc = $dc.Domain.PdcRoleOwner.Name
            Write-Output "INFO: PDC emulator is $pdc"
            $joinServer = $pdc
        } catch {
            Write-Output "WARNING: Could not resolve PDC ($($_.Exception.Message)) - joining without specifying DC."
        }
    }

    $params = @{
        DomainName            = $DomainName
        Credential            = $Credential
        UnjoinDomainCredential = $Credential
        Force                 = $true
        ErrorAction           = "Stop"
    }
    if ($OUPath -ne "") { $params["OUPath"] = $OUPath }
    if ($joinServer) { $params["Server"] = $joinServer }

    Write-Output "INFO: Joining domain $DomainName as $EffectiveUser ..."
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
