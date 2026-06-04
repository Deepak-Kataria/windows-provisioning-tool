try {
    $cs   = Get-CimInstance Win32_ComputerSystem
    $os   = Get-CimInstance Win32_OperatingSystem
    $bios = Get-CimInstance Win32_BIOS
    $cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1

    # Logged-in user (works even when tool runs elevated)
    $rawUser  = $cs.UserName
    $username = if ($rawUser -match '\\') { $rawUser -replace '.*\\', '' } else { $rawUser }

    # System model — stored in $sysModel to avoid collision with monitor model variable
    $sysModel = $cs.Model.Trim()

    # Serial number — BIOS first, fallback to baseboard
    $invalid = @('', 'None', 'Default string', 'To be filled by O.E.M.', 'N/A', '0', 'Unknown')
    $sysSerial = $bios.SerialNumber.Trim()
    if (-not $sysSerial -or $sysSerial -in $invalid) {
        $sysSerial = (Get-CimInstance Win32_BaseBoard).SerialNumber.Trim()
    }
    if (-not $sysSerial -or $sysSerial -in $invalid) { $sysSerial = "N/A" }

    # Processor
    $processor = $cpu.Name -replace '\s+', ' '

    # RAM
    $ramGB = [Math]::Round($cs.TotalPhysicalMemory / 1GB, 0)
    $ram   = "$ramGB GB"

    # Primary disk
    $disk = "N/A"
    $primaryDisk = Get-CimInstance Win32_DiskDrive | Sort-Object Size -Descending | Select-Object -First 1
    if ($primaryDisk) { $disk = "$([Math]::Round($primaryDisk.Size / 1GB, 0)) GB" }

    # GPU / display adapter
    $gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
    $displayGpu = if ($gpu) { $gpu.Name.Trim() } else { "N/A" }

    # Windows version + build
    $winVersion = "$($os.Caption.Trim()) (Build $($os.BuildNumber))"

    # Last Windows Update
    $lastUpdate = "N/A"
    try {
        $hf = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn | Select-Object -Last 1
        if ($hf) { $lastUpdate = $hf.InstalledOn.ToString("yyyy-MM-dd") }
    } catch {}

    # ── Collect ALL browser emails ─────────────────────────────────
    $emailSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    function Get-ChromiumEmails($localStatePath) {
        if (-not (Test-Path $localStatePath)) { return }
        try {
            $js = Get-Content $localStatePath -Raw | ConvertFrom-Json
            # Google accounts
            foreach ($acct in $js.account_info) {
                if ($acct.email -match '@') { [void]$emailSet.Add($acct.email) }
            }
            # Microsoft/work accounts (Edge)
            $cache = $js.profile.info_cache
            if ($cache) {
                foreach ($pn in ($cache | Get-Member -MemberType NoteProperty).Name) {
                    $u = $cache.$pn.user_name
                    if ($u -match '@') { [void]$emailSet.Add($u) }
                }
            }
        } catch {}
    }

    if ($username) {
        $local  = "C:\Users\$username\AppData\Local"
        $roaming = "C:\Users\$username\AppData\Roaming"

        Get-ChromiumEmails "$local\Google\Chrome\User Data\Local State"
        Get-ChromiumEmails "$local\Microsoft\Edge\User Data\Local State"
        Get-ChromiumEmails "$local\BraveSoftware\Brave-Browser\User Data\Local State"
        Get-ChromiumEmails "$roaming\Opera Software\Opera Stable\Local State"

        # Firefox signed-in account
        try {
            Get-ChildItem "$roaming\Mozilla\Firefox\Profiles" -Directory -ErrorAction Stop | ForEach-Object {
                $siu = Join-Path $_.FullName "signedInUser.json"
                if (Test-Path $siu) {
                    $ffJson = Get-Content $siu -Raw | ConvertFrom-Json
                    $e = $ffJson.accountData.email
                    if ($e -match '@') { [void]$emailSet.Add($e) }
                }
            }
        } catch {}
    }

    $emailsOut = if ($emailSet.Count -gt 0) { ($emailSet | Sort-Object) -join '|' } else { '' }

    # ── Monitor details (brand, model name, serial) ────────────────
    $monitorList = @()
    try {
        $decode = { param($arr)
            if ($arr) { [System.Text.Encoding]::ASCII.GetString(($arr | Where-Object { $_ -ne 0 })).Trim() }
            else { "" }
        }
        foreach ($mon in (Get-WmiObject WmiMonitorID -Namespace root\wmi -ErrorAction Stop)) {
            $monBrand    = & $decode $mon.ManufacturerName
            $monModel    = & $decode $mon.UserFriendlyName
            $monSerial   = & $decode $mon.SerialNumberID
            $parts = @()
            if ($monBrand)  { $parts += $monBrand }
            if ($monModel)  { $parts += $monModel }
            if ($monSerial) { $parts += "(SN: $monSerial)" }
            if ($parts.Count -gt 0) { $monitorList += $parts -join ' ' }
        }
    } catch {}

    Write-Output "USER:$username"
    Write-Output "MODEL:$sysModel"
    Write-Output "SERIAL:$sysSerial"
    Write-Output "PROCESSOR:$processor"
    Write-Output "RAM:$ram"
    Write-Output "DISK:$disk"
    Write-Output "DISPLAY:$displayGpu"
    Write-Output "WIN_VERSION:$winVersion"
    Write-Output "WIN_LAST_UPDATE:$lastUpdate"
    Write-Output "EMAILS:$emailsOut"
    Write-Output "MONITOR_COUNT:$($monitorList.Count)"
    for ($i = 0; $i -lt $monitorList.Count; $i++) {
        Write-Output "MONITOR_$($i+1):$($monitorList[$i])"
    }
    exit 0
} catch {
    Write-Output "ERROR:$($_.Exception.Message)"
    exit 1
}
