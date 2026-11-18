try {
    $profiles = Get-CimInstance Win32_UserProfile -EA Stop | Where-Object { -not $_.Special }

    foreach ($p in $profiles) {
        $sid = $p.SID
        $localPath = $p.LocalPath

        $username = $sid
        try {
            $ntAccount = (New-Object System.Security.Principal.SecurityIdentifier($sid)).Translate([System.Security.Principal.NTAccount])
            $username = $ntAccount.Value -replace '.*\\', ''
        } catch {
            if ($localPath) { $username = Split-Path $localPath -Leaf }
        }

        $lastUse = "Unknown"
        if ($p.LastUseTime) {
            try { $lastUse = $p.LastUseTime.ToString("yyyy-MM-dd") } catch {}
        }

        $loaded = if ($p.Loaded) { "1" } else { "0" }

        Write-Output "$sid|$username|$localPath|$lastUse|$loaded"
    }
    exit 0
} catch {
    Write-Output "ERROR|$($_.Exception.Message)"
    exit 1
}
