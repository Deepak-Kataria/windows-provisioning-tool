param(
    [Parameter(Mandatory=$true)]
    [string]$Packages
)

$PackageList = $Packages -split ','

foreach ($pkg in $PackageList) {
    try {
        $app = Get-AppxPackage -Name $pkg -AllUsers -ErrorAction SilentlyContinue
        if ($app) {
            Remove-AppxPackage -Package $app.PackageFullName -AllUsers -ErrorAction Stop
            Write-Output "REMOVED: $pkg"
        } else {
            Write-Output "NOT_FOUND: $pkg"
        }
    } catch {
        Write-Output "ERROR: $pkg - $($_.Exception.Message)"
    }
}
