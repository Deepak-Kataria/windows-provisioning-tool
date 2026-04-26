try {
    $serial = (Get-WmiObject Win32_BaseBoard).SerialNumber

    $invalid = @('', 'None', 'Default string', 'To be filled by O.E.M.', 'N/A', '0', 'Unknown')
    if (-not $serial -or $serial.Trim() -in $invalid) {
        $serial = (Get-WmiObject Win32_ComputerSystemProduct).UUID
    }

    if (-not $serial -or $serial.Trim() -eq '') {
        Write-Output "ERROR: No stable hardware identifier found on this machine."
        exit 1
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($serial.Trim())
    $hash  = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    $hex   = ([System.BitConverter]::ToString($hash) -replace '-', '')
    Write-Output $hex.Substring(0, 8).ToUpper()
} catch {
    Write-Output "ERROR: $($_.Exception.Message)"
    exit 1
}
