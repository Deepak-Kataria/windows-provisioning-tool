param(
    [Parameter(Mandatory=$true)]
    [string]$Packages
)

$PackageList = $Packages -split ','
$LogFile = "$env:TEMP\debloat_log_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
"Debloat run: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $LogFile -Encoding utf8

Write-Output "LOG: Saving removal log to $LogFile"

foreach ($pkg in $PackageList) {
    $pkg = $pkg.Trim()
    $removed = $false

    # All users (works when elevated; catches packages not visible in admin context)
    $found = Get-AppxPackage -AllUsers -Name $pkg -ErrorAction SilentlyContinue
    foreach ($item in $found) {
        try {
            Remove-AppxPackage -Package $item.PackageFullName -AllUsers -ErrorAction Stop
            $removed = $true
        } catch {
            # Try without -AllUsers as fallback
            try {
                Remove-AppxPackage -Package $item.PackageFullName -ErrorAction Stop
                $removed = $true
            } catch {}
        }
    }

    # Provisioned packages (prevents reinstall on new user profiles)
    $provisioned = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like $pkg }
    foreach ($item in $provisioned) {
        try {
            Remove-AppxProvisionedPackage -Online -PackageName $item.PackageName -ErrorAction Stop | Out-Null
            $removed = $true
        } catch {}
    }

    if ($removed) {
        $msg = "REMOVED: $pkg"
    } else {
        $msg = "NOT_FOUND: $pkg"
    }
    Write-Output $msg
    $msg | Out-File $LogFile -Append -Encoding utf8
}

"Completed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $LogFile -Append -Encoding utf8
