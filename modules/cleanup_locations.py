"""Cleanup locations shared by the desktop Cleanup Hub and the web agent.

Windows cleanup: GROUPS / LOCATIONS (size_ps prints bytes, clean_ps deletes).
User profiles: junk_categories(local_path) -> same shape, scoped to one profile folder.
Moved here unchanged from ui/cleanup_windows.py and ui/cleanup_profiles.py.
"""


GROUPS = [
    {
        "label": "Temp & Cache",
        "items": [
            {
                "id": "user_temp",
                "label": "User Temp  (%TEMP%)",
                "default": True,
                "size_ps": (
                    "$s=(Get-ChildItem $env:TEMP -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Remove-Item \"$env:TEMP\\*\" -Recurse -Force -EA SilentlyContinue;"
                    " Write-Host 'User Temp cleaned.'"
                ),
            },
            {
                "id": "win_temp",
                "label": "Windows Temp  (C:\\Windows\\Temp)",
                "default": True,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\Temp\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Remove-Item \"$env:SystemRoot\\Temp\\*\" -Recurse -Force -EA SilentlyContinue;"
                    " Write-Host 'Windows Temp cleaned.'"
                ),
            },
            {
                "id": "prefetch",
                "label": "Prefetch  (C:\\Windows\\Prefetch)",
                "default": True,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\Prefetch\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Remove-Item \"$env:SystemRoot\\Prefetch\\*\" -Recurse -Force -EA SilentlyContinue;"
                    " Write-Host 'Prefetch cleaned.'"
                ),
            },
            {
                "id": "all_users_temp",
                "label": "All Users - Local Temp",
                "default": True,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Temp\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Temp\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'All users Local Temp cleaned.'"
                ),
            },
        ],
    },
    {
        "label": "Browser Cache",
        "items": [
            {
                "id": "chrome",
                "label": "Chrome Cache  (current user)",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Google\\Chrome\\User Data\";"
                    " if (Test-Path $b) {"
                    " $s=(Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Google\\Chrome\\User Data\";"
                    " if (Test-Path $b) {"
                    " Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Chrome cache cleaned.'"
                ),
            },
            {
                "id": "edge",
                "label": "Edge Cache  (current user)",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\";"
                    " if (Test-Path $b) {"
                    " $s=(Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\";"
                    " if (Test-Path $b) {"
                    " Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Edge cache cleaned.'"
                ),
            },
            {
                "id": "firefox",
                "label": "Firefox Cache  (current user)",
                "default": False,
                "size_ps": (
                    "$b=\"$env:APPDATA\\Mozilla\\Firefox\\Profiles\";"
                    " if (Test-Path $b) {"
                    " $s=(Get-ChildItem $b -Filter cache2 -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "$b=\"$env:APPDATA\\Mozilla\\Firefox\\Profiles\";"
                    " if (Test-Path $b) {"
                    " Get-ChildItem $b -Filter cache2 -Recurse -Directory -EA SilentlyContinue"
                    " | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Firefox cache cleaned.'"
                ),
            },
            {
                "id": "all_chrome",
                "label": "All Users - Chrome Cache",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Google\\Chrome\\User Data\";"
                    "   if (Test-Path $b) {"
                    "     $s=(Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    "       | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Google\\Chrome\\User Data\";"
                    "   if (Test-Path $b) {"
                    "     Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    "     | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } } };"
                    " Write-Host 'All users Chrome cache cleaned.'"
                ),
            },
            {
                "id": "all_edge",
                "label": "All Users - Edge Cache",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Edge\\User Data\";"
                    "   if (Test-Path $b) {"
                    "     $s=(Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    "       | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Edge\\User Data\";"
                    "   if (Test-Path $b) {"
                    "     Get-ChildItem $b -Filter Cache -Recurse -Directory -EA SilentlyContinue"
                    "     | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } } };"
                    " Write-Host 'All users Edge cache cleaned.'"
                ),
            },
            {
                "id": "all_firefox",
                "label": "All Users - Firefox Cache",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Mozilla\\Firefox\\Profiles\";"
                    "   if (Test-Path $b) {"
                    "     $s=(Get-ChildItem $b -Filter cache2 -Recurse -Directory -EA SilentlyContinue"
                    "       | ForEach-Object { Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $b=\"$($_.FullName)\\AppData\\Local\\Mozilla\\Firefox\\Profiles\";"
                    "   if (Test-Path $b) {"
                    "     Get-ChildItem $b -Filter cache2 -Recurse -Directory -EA SilentlyContinue"
                    "     | ForEach-Object { Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue } } };"
                    " Write-Host 'All users Firefox cache cleaned.'"
                ),
            },
        ],
    },
    {
        "label": "User Profile Junk",
        "items": [
            {
                "id": "all_ie_cache",
                "label": "All Users - Internet Cache  (INetCache)",
                "default": True,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Windows\\INetCache\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Windows\\INetCache\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Internet Cache cleaned.'"
                ),
            },
            {
                "id": "all_thumbcache",
                "label": "All Users - Thumbnail Cache",
                "default": True,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Windows\\Explorer\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Filter 'thumbcache_*.db' -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Local\\Microsoft\\Windows\\Explorer\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\thumbcache_*.db\" -Force -EA SilentlyContinue } };"
                    " Write-Host 'Thumbnail caches cleaned.'"
                ),
            },
            {
                "id": "all_cookies",
                "label": "All Users - Cookies",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Roaming\\Microsoft\\Windows\\Cookies\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Roaming\\Microsoft\\Windows\\Cookies\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Cookies cleaned.'"
                ),
            },
            {
                "id": "all_recent",
                "label": "All Users - Recent Items",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Roaming\\Microsoft\\Windows\\Recent\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\Roaming\\Microsoft\\Windows\\Recent\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Recent Items cleaned.'"
                ),
            },
            {
                "id": "all_iconcache",
                "label": "All Users - Icon Cache  (rebuilds on next login)",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $f=\"$($_.FullName)\\AppData\\Local\\IconCache.db\";"
                    "   if (Test-Path $f) { $t+=(Get-Item $f -Force -EA SilentlyContinue).Length } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $f=\"$($_.FullName)\\AppData\\Local\\IconCache.db\";"
                    "   if (Test-Path $f) { Remove-Item $f -Force -EA SilentlyContinue } };"
                    " Write-Host 'Icon caches cleaned.'"
                ),
            },
            {
                "id": "all_java",
                "label": "All Users - Java Cache",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\LocalLow\\Sun\\Java\\Deployment\\cache\";"
                    "   if (Test-Path $p) {"
                    "     $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Get-ChildItem 'C:\\Users' -Directory -EA SilentlyContinue"
                    " | Where-Object { $_.Name -notin @('Public','Default','Default User','All Users') }"
                    " | ForEach-Object {"
                    "   $p=\"$($_.FullName)\\AppData\\LocalLow\\Sun\\Java\\Deployment\\cache\";"
                    "   if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Java cache cleaned.'"
                ),
            },
        ],
    },
    {
        "label": "Windows Update",
        "items": [
            {
                "id": "wu_cache",
                "label": "WU Download Cache  (SoftwareDistribution\\Download)",
                "default": True,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\SoftwareDistribution\\Download\""
                    " -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Stop-Service wuauserv -Force -EA SilentlyContinue;"
                    " Remove-Item \"$env:SystemRoot\\SoftwareDistribution\\Download\\*\""
                    " -Recurse -Force -EA SilentlyContinue;"
                    " Start-Service wuauserv -EA SilentlyContinue;"
                    " Write-Host 'Windows Update cache cleared.'"
                ),
            },
            {
                "id": "wu_logs",
                "label": "WU DataStore Logs  (SoftwareDistribution\\DataStore\\Logs)",
                "default": False,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\SoftwareDistribution\\DataStore\\Logs\""
                    " -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Stop-Service wuauserv -Force -EA SilentlyContinue;"
                    " Remove-Item \"$env:SystemRoot\\SoftwareDistribution\\DataStore\\Logs\\*\""
                    " -Recurse -Force -EA SilentlyContinue;"
                    " Start-Service wuauserv -EA SilentlyContinue;"
                    " Write-Host 'WU DataStore logs cleared.'"
                ),
            },
        ],
    },
    {
        "label": "System Logs & Reports",
        "items": [
            {
                "id": "wer",
                "label": "Windows Error Reports  (WER)",
                "default": False,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:ProgramData\\Microsoft\\Windows\\WER\""
                    " -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Remove-Item \"$env:ProgramData\\Microsoft\\Windows\\WER\\*\""
                    " -Recurse -Force -EA SilentlyContinue;"
                    " Write-Host 'Windows Error Reports cleaned.'"
                ),
            },
            {
                "id": "win_logs",
                "label": "Windows Logs  (C:\\Windows\\Logs)",
                "default": False,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\Logs\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Get-ChildItem \"$env:SystemRoot\\Logs\" -Recurse -Force -EA SilentlyContinue"
                    " | Where-Object { -not $_.PSIsContainer }"
                    " | Remove-Item -Force -EA SilentlyContinue;"
                    " Write-Host 'Windows Logs cleaned.'"
                ),
            },
            {
                "id": "win_debug",
                "label": "Windows Debug Logs  (C:\\Windows\\Debug)",
                "default": False,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\Debug\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Get-ChildItem \"$env:SystemRoot\\Debug\" -Recurse -Force -EA SilentlyContinue"
                    " | Where-Object { -not $_.PSIsContainer }"
                    " | Remove-Item -Force -EA SilentlyContinue;"
                    " Write-Host 'Windows Debug logs cleaned.'"
                ),
            },
            {
                "id": "minidump",
                "label": "Crash MiniDumps  (C:\\Windows\\MiniDump)",
                "default": False,
                "size_ps": (
                    "if (Test-Path \"$env:SystemRoot\\MiniDump\") {"
                    " $s=(Get-ChildItem \"$env:SystemRoot\\MiniDump\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "if (Test-Path \"$env:SystemRoot\\MiniDump\") {"
                    " Remove-Item \"$env:SystemRoot\\MiniDump\\*\" -Recurse -Force -EA SilentlyContinue };"
                    " Write-Host 'MiniDump files cleaned.'"
                ),
            },
            {
                "id": "wmi_logs",
                "label": "WMI Logs  (System32\\Wbem\\Logs)",
                "default": False,
                "size_ps": (
                    "if (Test-Path \"$env:SystemRoot\\System32\\Wbem\\Logs\") {"
                    " $s=(Get-ChildItem \"$env:SystemRoot\\System32\\Wbem\\Logs\""
                    " -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "if (Test-Path \"$env:SystemRoot\\System32\\Wbem\\Logs\") {"
                    " Remove-Item \"$env:SystemRoot\\System32\\Wbem\\Logs\\*\""
                    " -Recurse -Force -EA SilentlyContinue };"
                    " Write-Host 'WMI logs cleaned.'"
                ),
            },
            {
                "id": "event_logs",
                "label": "Windows Event Logs",
                "default": False,
                "size_ps": (
                    "$t=0;"
                    " Get-WinEvent -ListLog * -EA SilentlyContinue"
                    " | Where-Object { $_.FileSize -gt 0 }"
                    " | ForEach-Object { $t+=$_.FileSize }; $t"
                ),
                "clean_ps": (
                    "Get-WinEvent -ListLog * -EA SilentlyContinue"
                    " | Where-Object { $_.IsEnabled }"
                    " | ForEach-Object {"
                    "   try {"
                    "     [System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.ClearLog($_.LogName)"
                    "   } catch {} };"
                    " Write-Host 'Event logs cleared.'"
                ),
            },
            {
                "id": "defender_history",
                "label": "Windows Defender Scan History",
                "default": False,
                "size_ps": (
                    "$p=\"$env:ProgramData\\Microsoft\\Windows Defender\\Scans\\History\\Results\";"
                    " if (Test-Path $p) {"
                    " $s=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "Remove-Item \"$env:ProgramData\\Microsoft\\Windows Defender\\Scans\\History\\Results\\*\""
                    " -Recurse -Force -EA SilentlyContinue;"
                    " Write-Host 'Defender scan history cleared.'"
                ),
            },
        ],
    },
    {
        "label": "System & Hardware",
        "items": [
            {
                "id": "recycle",
                "label": "Recycle Bin  (all drives)",
                "default": True,
                "size_ps": (
                    "$t=0;"
                    " Get-PSDrive -PSProvider FileSystem -EA SilentlyContinue"
                    " | ForEach-Object {"
                    "   $rb=$_.Root+'$Recycle.Bin';"
                    "   if (Test-Path $rb) {"
                    "     $s=(Get-ChildItem $rb -Recurse -Force -EA SilentlyContinue"
                    "       | Measure-Object -Property Length -Sum).Sum;"
                    "     if ($s) { $t+=$s } } }; $t"
                ),
                "clean_ps": (
                    "Clear-RecycleBin -Force -EA SilentlyContinue;"
                    " Write-Host 'Recycle Bin emptied.'"
                ),
            },
            {
                "id": "print_spool",
                "label": "Print Spooler Queue  (clears stuck print jobs)",
                "default": False,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\System32\\spool\\PRINTERS\""
                    " -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Stop-Service Spooler -Force -EA SilentlyContinue;"
                    " Remove-Item \"$env:SystemRoot\\System32\\spool\\PRINTERS\\*\""
                    " -Recurse -Force -EA SilentlyContinue;"
                    " Start-Service Spooler -EA SilentlyContinue;"
                    " Write-Host 'Print spooler queue cleared.'"
                ),
            },
        ],
    },
    {
        "label": "Deep Clean  (may take several minutes)",
        "items": [
            {
                "id": "winsxs",
                "label": "WinSxS Component Cleanup  (DISM - 5 to 15 min)",
                "default": False,
                "slow": True,
                "size_ps": (
                    "$s=(Get-ChildItem \"$env:SystemRoot\\WinSxS\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Write-Host 'Running DISM - please wait (5-15 min)...';"
                    " & dism.exe /online /cleanup-image /StartComponentCleanup;"
                    " Write-Host 'DISM WinSxS cleanup complete.'"
                ),
            },
            {
                "id": "windows_old",
                "label": "[!] Windows.old  (previous Windows installation)",
                "default": False,
                "confirm": True,
                "confirm_msg": (
                    "Permanently delete C:\\Windows.old?\n\n"
                    "This removes the previous Windows installation.\n"
                    "You will NOT be able to roll back to the prior Windows version.\n\n"
                    "This cannot be undone. Continue?"
                ),
                "size_ps": (
                    "if (Test-Path 'C:\\Windows.old') {"
                    " $s=(Get-ChildItem 'C:\\Windows.old' -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "if (Test-Path 'C:\\Windows.old') {"
                    " & takeown /F 'C:\\Windows.old' /R /D Y 2>&1 | Out-Null;"
                    " & icacls 'C:\\Windows.old' /grant 'administrators:F' /T 2>&1 | Out-Null;"
                    " Remove-Item 'C:\\Windows.old' -Recurse -Force -EA SilentlyContinue;"
                    " if (Test-Path 'C:\\Windows.old') { Write-Host 'Partial - some locked files remain.' }"
                    " else { Write-Host 'Windows.old removed.' }"
                    " } else { Write-Host 'Windows.old not found.' }"
                ),
            },
        ],
    },
    {
        "label": "Advanced  (use with caution)",
        "items": [
            {
                "id": "hibernate",
                "label": "[!] Disable Hibernate  (removes hiberfil.sys)",
                "default": False,
                "confirm": True,
                "confirm_msg": (
                    "Disable Windows Hibernate?\n\n"
                    "This deletes hiberfil.sys and disables hibernate mode.\n"
                    "Sleep/fast startup is not affected.\n\n"
                    "Can be re-enabled later with: powercfg -h on\n\n"
                    "Continue?"
                ),
                "size_ps": (
                    "if (Test-Path 'C:\\hiberfil.sys') {"
                    " (Get-Item 'C:\\hiberfil.sys' -Force -EA SilentlyContinue).Length"
                    " } else { 0 }"
                ),
                "clean_ps": (
                    "& powercfg.exe -h off;"
                    " Write-Host 'Hibernate disabled. hiberfil.sys removed.'"
                ),
            },
            {
                "id": "shadow_copies",
                "label": "[!] Delete All Shadow Copies  (System Restore Points)",
                "default": False,
                "confirm": True,
                "confirm_msg": (
                    "Delete ALL Shadow Copies and System Restore Points?\n\n"
                    "You will NOT be able to restore Windows to any previous state.\n\n"
                    "This cannot be undone. Continue?"
                ),
                "size_ps": (
                    "$t=0;"
                    " try {"
                    "   Get-WmiObject Win32_ShadowStorage -EA SilentlyContinue"
                    "   | ForEach-Object { $t+=$_.UsedSpace }"
                    " } catch {}; $t"
                ),
                "clean_ps": (
                    "& vssadmin.exe delete shadows /All /Quiet;"
                    " Write-Host 'All shadow copies deleted.'"
                ),
            },
        ],
    },
]


LOCATIONS = [item for grp in GROUPS for item in grp["items"]]


def junk_categories(local_path):
    """Build size/clean PowerShell for the standard junk locations, scoped to one profile."""
    lp = local_path.rstrip("\\")
    cats = []

    def add_dir(id_, label, subpath):
        full = f"{lp}\\{subpath}"
        cats.append({
            "id": id_,
            "label": label,
            "size_ps": (
                f"if (Test-Path \"{full}\") {{"
                f" $s=(Get-ChildItem \"{full}\" -Recurse -Force -EA SilentlyContinue"
                f" | Measure-Object -Property Length -Sum).Sum;"
                f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
            ),
            "clean_ps": (
                f"if (Test-Path \"{full}\") {{"
                f" Remove-Item \"{full}\\*\" -Recurse -Force -EA SilentlyContinue }};"
                f" Write-Host '{label} cleaned.'"
            ),
        })

    def add_filtered_dir(id_, label, subpath, filter_):
        base = f"{lp}\\{subpath}"
        cats.append({
            "id": id_,
            "label": label,
            "size_ps": (
                f"$b=\"{base}\"; if (Test-Path $b) {{"
                f" $s=(Get-ChildItem $b -Filter {filter_} -Recurse -Directory -EA SilentlyContinue"
                f" | ForEach-Object {{ Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }}"
                f" | Measure-Object -Property Length -Sum).Sum;"
                f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
            ),
            "clean_ps": (
                f"$b=\"{base}\"; if (Test-Path $b) {{"
                f" Get-ChildItem $b -Filter {filter_} -Recurse -Directory -EA SilentlyContinue"
                f" | ForEach-Object {{ Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue }} }};"
                f" Write-Host '{label} cleaned.'"
            ),
        })

    add_dir("temp", "Local Temp", r"AppData\Local\Temp")
    add_dir("inetcache", "Internet Cache", r"AppData\Local\Microsoft\Windows\INetCache")
    add_filtered_dir("chrome", "Chrome Cache", r"AppData\Local\Google\Chrome\User Data", "Cache")
    add_filtered_dir("edge", "Edge Cache", r"AppData\Local\Microsoft\Edge\User Data", "Cache")
    add_filtered_dir("firefox", "Firefox Cache", r"AppData\Local\Mozilla\Firefox\Profiles", "cache2")
    add_dir("cookies", "Cookies", r"AppData\Roaming\Microsoft\Windows\Cookies")
    add_dir("recent", "Recent Items", r"AppData\Roaming\Microsoft\Windows\Recent")
    add_dir("wer", "Crash/Error Reports", r"AppData\Local\Microsoft\Windows\WER")

    thumb_dir = f"{lp}\\AppData\\Local\\Microsoft\\Windows\\Explorer"
    cats.append({
        "id": "thumbcache",
        "label": "Thumbnail Cache",
        "size_ps": (
            f"if (Test-Path \"{thumb_dir}\") {{"
            f" $s=(Get-ChildItem \"{thumb_dir}\" -Filter 'thumbcache_*.db' -Force -EA SilentlyContinue"
            f" | Measure-Object -Property Length -Sum).Sum;"
            f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
        ),
        "clean_ps": (
            f"if (Test-Path \"{thumb_dir}\") {{"
            f" Remove-Item \"{thumb_dir}\\thumbcache_*.db\" -Force -EA SilentlyContinue }};"
            f" Write-Host 'Thumbnail Cache cleaned.'"
        ),
    })

    icon_file = f"{lp}\\AppData\\Local\\IconCache.db"
    cats.append({
        "id": "iconcache",
        "label": "Icon Cache",
        "size_ps": (
            f"if (Test-Path \"{icon_file}\") {{"
            f" (Get-Item \"{icon_file}\" -Force -EA SilentlyContinue).Length }} else {{ 0 }}"
        ),
        "clean_ps": (
            f"if (Test-Path \"{icon_file}\") {{ Remove-Item \"{icon_file}\" -Force -EA SilentlyContinue }};"
            f" Write-Host 'Icon Cache cleaned.'"
        ),
    })

    return cats
