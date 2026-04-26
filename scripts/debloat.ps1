param(
    [Parameter(Mandatory=$true)]
    [string]$Packages
)

$PackageList = $Packages -split ','

foreach ($pkg in $PackageList) {
    $pkg = $pkg.Trim()
    $removed = $false

    # Current user
    Get-AppxPackage -Name $pkg -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Remove-AppxPackage -Package $_.PackageFullName -ErrorAction Stop
            $removed = $true
        } catch {}
    }

    # All users
    Get-AppxPackage -AllUsers -Name $pkg -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Remove-AppxPackage -Package $_.PackageFullName -AllUsers -ErrorAction Stop
            $removed = $true
        } catch {}
    }

    # Provisioned — prevents reinstall for new user profiles
    Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like $pkg } |
        ForEach-Object {
            try {
                Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction Stop | Out-Null
                $removed = $true
            } catch {}
        }

    if ($removed) {
        Write-Output "REMOVED: $pkg"
    } else {
        Write-Output "NOT_FOUND: $pkg"
    }
}
