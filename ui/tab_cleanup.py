import customtkinter as ctk
import threading
import tkinter.messagebox as msgbox
from modules.runner import run_inline_powershell
from modules.logger import log


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


def _fmt_size(n):
    if n is None:
        return "---"
    for unit, div in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


class CleanupTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._vars = {}
        self._size_labels = {}
        self._sizes = {loc["id"]: None for loc in LOCATIONS}
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        # ── Header ─────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(wrap)
        hdr.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Windows Cleanup",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        ctk.CTkLabel(hdr,
                     text="Scan sizes first, then select and clean.  [!] items show a confirm dialog.",
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=1, column=0, padx=14, pady=(0, 6), sticky="w")

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="w")

        self._scan_btn = ctk.CTkButton(btn_row, text="Scan Sizes", width=110,
                                       command=self._scan)
        self._scan_btn.grid(row=0, column=0, padx=(4, 6))

        self._clean_btn = ctk.CTkButton(btn_row, text="Clean Selected", width=130,
                                        fg_color="#c0392b", hover_color="#922b21",
                                        command=self._clean)
        self._clean_btn.grid(row=0, column=1, padx=6)

        ctk.CTkButton(btn_row, text="Select All", width=90,
                      command=self._select_all).grid(row=0, column=2, padx=6)
        ctk.CTkButton(btn_row, text="Select None", width=90,
                      command=self._select_none).grid(row=0, column=3, padx=6)

        self._total_label = ctk.CTkLabel(hdr, text="Total selected: ---",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self._total_label.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="w")

        # ── Groups ─────────────────────────────────────────────────────
        grid_row = 1
        for grp in GROUPS:
            grp_hdr = ctk.CTkFrame(wrap, fg_color=("gray85", "gray25"), corner_radius=6)
            grp_hdr.grid(row=grid_row, column=0, padx=10, pady=(10, 0), sticky="ew")
            grp_hdr.grid_columnconfigure(0, weight=1)

            inner = ctk.CTkFrame(grp_hdr, fg_color="transparent")
            inner.grid(row=0, column=0, padx=8, pady=5, sticky="ew")
            inner.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(inner, text=grp["label"],
                         font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=0, column=0, sticky="w")

            ctk.CTkButton(inner, text="All", width=36, height=22,
                          font=ctk.CTkFont(size=10),
                          command=lambda g=grp: self._group_select(g, True)).grid(
                row=0, column=1, padx=(4, 2))
            ctk.CTkButton(inner, text="None", width=44, height=22,
                          font=ctk.CTkFont(size=10),
                          command=lambda g=grp: self._group_select(g, False)).grid(
                row=0, column=2, padx=(2, 0))

            grid_row += 1

            items_card = ctk.CTkFrame(wrap, corner_radius=6)
            items_card.grid(row=grid_row, column=0, padx=10, pady=(0, 2), sticky="ew")
            items_card.grid_columnconfigure(1, weight=1)

            for i, loc in enumerate(grp["items"]):
                var = ctk.BooleanVar(value=loc["default"])
                var.trace_add("write", lambda *a: self._update_total())
                self._vars[loc["id"]] = var

                cb_kw = {
                    "text": loc["label"],
                    "variable": var,
                    "font": ctk.CTkFont(size=12),
                }
                if loc.get("confirm"):
                    cb_kw["text_color"] = ("#c0392b", "#ff7675")

                cb = ctk.CTkCheckBox(items_card, **cb_kw)
                cb.grid(row=i, column=0, padx=(14, 6), pady=5, sticky="w")

                size_lbl = ctk.CTkLabel(items_card, text="---",
                                        text_color="gray", font=ctk.CTkFont(size=11))
                size_lbl.grid(row=i, column=1, padx=(0, 14), pady=5, sticky="e")
                self._size_labels[loc["id"]] = size_lbl

            grid_row += 1

        # ── Output ─────────────────────────────────────────────────────
        ctk.CTkLabel(wrap, text="Output",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=grid_row, column=0, padx=10, pady=(12, 2), sticky="w")
        grid_row += 1

        self._output = ctk.CTkTextbox(wrap, height=220, state="disabled",
                                      font=ctk.CTkFont(family="Courier New", size=11))
        self._output.grid(row=grid_row, column=0, padx=10, pady=(0, 10), sticky="ew")

        self._update_total()

    # ── Helpers ────────────────────────────────────────────────────────

    def _append(self, text):
        self._output.configure(state="normal")
        self._output.insert("end", text + "\n")
        self._output.see("end")
        self._output.configure(state="disabled")

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _set_btn_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self._scan_btn.configure(state=state)
        self._clean_btn.configure(state=state)

    def _update_total(self):
        total = 0
        any_unknown = False
        for loc in LOCATIONS:
            if self._vars[loc["id"]].get():
                sz = self._sizes[loc["id"]]
                if sz is None:
                    any_unknown = True
                else:
                    total += sz
        if any_unknown:
            self._total_label.configure(text="Total selected: scan first to calculate")
        else:
            self._total_label.configure(text=f"Total selected: {_fmt_size(total)}")

    def _select_all(self):
        for var in self._vars.values():
            var.set(True)

    def _select_none(self):
        for var in self._vars.values():
            var.set(False)

    def _group_select(self, grp, value):
        for loc in grp["items"]:
            self._vars[loc["id"]].set(value)

    def _parse_size(self, out):
        lines = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.strip().startswith("ERR:")]
        try:
            return int(lines[-1]) if lines else 0
        except (ValueError, IndexError):
            return 0

    def _update_size_label(self, loc_id, val):
        lbl = self._size_labels[loc_id]
        color = ("#1a1a1a", "white") if val > 0 else "gray"
        lbl.configure(text=_fmt_size(val), text_color=color)

    # ── Scan ───────────────────────────────────────────────────────────

    def _scan(self):
        if self._running:
            return
        self._running = True
        self._set_btn_state(False)
        self._append("\nScanning sizes...")
        log("Cleanup: scan started")

        def task():
            for loc in LOCATIONS:
                self._safe_append(f"  Checking {loc['label']}...")
                rc, out = run_inline_powershell(loc["size_ps"])
                val = self._parse_size(out)
                self._sizes[loc["id"]] = val
                self.after(0, self._update_size_label, loc["id"], val)

            self.after(0, self._update_total)
            self._safe_append("\nScan complete.")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()

    # ── Clean ──────────────────────────────────────────────────────────

    def _clean(self):
        if self._running:
            return
        selected = [loc for loc in LOCATIONS if self._vars[loc["id"]].get()]
        if not selected:
            self._append("No locations selected.")
            return

        confirmed = []
        for loc in selected:
            if loc.get("confirm"):
                ok = msgbox.askyesno(
                    "Confirm Destructive Action",
                    loc["confirm_msg"],
                    icon="warning"
                )
                if ok:
                    confirmed.append(loc)
            else:
                confirmed.append(loc)

        if not confirmed:
            return

        slow_items = [loc["label"] for loc in confirmed if loc.get("slow")]
        if slow_items:
            msgbox.showinfo(
                "Slow Operations",
                "The following may take 5-15 minutes:\n\n"
                + "\n".join(f"  - {n}" for n in slow_items)
                + "\n\nPlease wait — the app will not respond during DISM."
            )

        self._running = True
        self._set_btn_state(False)
        total_before = sum(self._sizes[loc["id"]] or 0 for loc in confirmed)
        self._append(f"\nCleaning {len(confirmed)} location(s)...")
        log(f"Cleanup: clean {[l['id'] for l in confirmed]}")

        def task():
            for loc in confirmed:
                self._safe_append(f"\n  >>> {loc['label']}")
                rc, out = run_inline_powershell(loc["clean_ps"], callback=self._safe_append)
                if rc != 0:
                    self._safe_append(f"  [WARN] exit {rc}")
                log(f"Cleanup: {loc['id']} rc={rc}")

            self._safe_append("\nRescanning freed space...")
            total_after = 0
            for loc in confirmed:
                rc, out = run_inline_powershell(loc["size_ps"])
                val = self._parse_size(out)
                self._sizes[loc["id"]] = val
                total_after += val
                self.after(0, self._update_size_label, loc["id"], val)

            freed = max(0, total_before - total_after)
            self.after(0, self._update_total)
            self._safe_append(f"\nDone.  Freed: {_fmt_size(freed)}")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()
