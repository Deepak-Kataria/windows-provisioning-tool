param(
    [Parameter(Mandatory=$true)]
    [string]$NewName
)

try {
    Rename-Computer -NewName $NewName -Force -ErrorAction Stop
    Write-Output "SUCCESS: Computer renamed to $NewName. Reboot required."
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
