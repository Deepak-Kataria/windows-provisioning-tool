param(
    [Parameter(Mandatory=$true)]
    [string]$AppsJson
)

$apps = $AppsJson | ConvertFrom-Json

foreach ($app in $apps) {
    $name    = $app.name
    $package = $app.package

    # Strip wildcards — winget can't match wildcard package names
    $searchName = $name -replace '[*?]', ''

    try {
        # Try winget msstore by package family / display name
        $out = winget install --name $searchName --source msstore --silent `
            --accept-package-agreements --accept-source-agreements `
            --disable-interactivity 2>&1

        if ($LASTEXITCODE -eq 0) {
            Write-Output "REINSTALLED: $name"
        } else {
            # Fallback: winget default source
            $out2 = winget install --name $searchName --silent `
                --accept-package-agreements --accept-source-agreements `
                --disable-interactivity 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Output "REINSTALLED: $name"
            } else {
                Write-Output "FAILED: $name"
            }
        }
    } catch {
        Write-Output "ERROR: $name - $($_.Exception.Message)"
    }
}
