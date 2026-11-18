try {
    $disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -EA Stop

    foreach ($d in $disks) {
        $letter = $d.DeviceID
        $size = if ($d.Size) { [int64]$d.Size } else { 0 }
        $free = if ($d.FreeSpace) { [int64]$d.FreeSpace } else { 0 }

        $health = "Unknown"
        try {
            $physDisk = Get-Partition -DriveLetter $letter.TrimEnd(':') -EA Stop | Get-Disk -EA Stop | Get-PhysicalDisk -EA Stop
            if ($physDisk) {
                $health = "$($physDisk | Select-Object -First 1 -ExpandProperty HealthStatus)"
            }
        } catch {}

        Write-Output "$letter|$size|$free|$health"
    }
    exit 0
} catch {
    Write-Output "ERROR|$($_.Exception.Message)"
    exit 1
}
