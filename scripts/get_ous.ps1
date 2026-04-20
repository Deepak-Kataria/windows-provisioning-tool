param(
    [Parameter(Mandatory=$true)]
    [string]$DomainName,
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [string]$ServerIP = ""
)

$Password = [Console]::In.ReadLine()

$ldapTarget = if ($ServerIP -ne "") { $ServerIP } else { $DomainName }

try {
    $entry = New-Object System.DirectoryServices.DirectoryEntry(
        "LDAP://$ldapTarget",
        "$DomainName\$Username",
        $Password
    )
    $searcher = New-Object System.DirectoryServices.DirectorySearcher($entry)
    $searcher.Filter = "(objectClass=organizationalUnit)"
    $searcher.PropertiesToLoad.Add("distinguishedName") | Out-Null
    $searcher.SearchScope = "Subtree"
    $searcher.PageSize = 500

    $results = $searcher.FindAll()
    foreach ($r in $results) {
        Write-Output $r.Properties["distinguishedName"][0]
    }
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
