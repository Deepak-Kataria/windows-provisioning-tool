"""Compromise-indicator checks for the Threat Report ("has this machine been hacked?").

Same shape as modules.security_checks: id, name, description, severity, check_ps printing
PASS / INFO / WARN / FAIL / UNKNOWN: <detail>, optional evaluate(output). Instead of fixes,
each has an `action` (recommended next step) and optionally review_ps/review_label to open
the relevant console. FAIL = strong indicator, WARN = needs review, INFO = listed for review.
"""
import json
import os

from modules.paths import get_base_dir

APPROVED_ADMINS_FILE = os.path.join(get_base_dir(), "config", "approved_admins.json")

# Read a named field from an event's XML EventData.
_EVENT_FIELD_FN = r'''
function F($e, $n) { (([xml]$e.ToXml()).Event.EventData.Data | Where-Object { $_.Name -eq $n }).'#text' }
function Test-LogAccess($log) {
  try { [void][System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.GetLogInformation($log, 'LogName'); $true } catch { $false } }
function Get-Events($filter, $max) {
  # Without access, Get-WinEvent misleadingly reports "no events" — check first.
  if (-not (Test-LogAccess $filter.LogName)) { throw "Access denied to the $($filter.LogName) log (run as administrator)" }
  try { @(Get-WinEvent -FilterHashtable $filter -MaxEvents $max -EA Stop) }
  catch { if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { @() } else { throw } } }
'''


def load_approved_admins():
    try:
        with open(APPROVED_ADMINS_FILE, encoding="utf-8") as f:
            return [a.strip().lower() for a in json.load(f).get("approved", []) if a.strip()]
    except (OSError, ValueError):
        return None


def _eval_unapproved_admins(out):
    members = []
    for line in out.splitlines():
        if line.startswith("ADM\t"):
            parts = (line.split("\t") + ["", "", ""])[1:4]
            members.append(tuple(p.strip() for p in parts))
    if not members:
        err = next((ln for ln in out.splitlines() if ln.startswith("ERR:")), "")
        return "UNKNOWN", f"Could not read Administrators group {err}".strip()

    approved = load_approved_admins()
    if approved is None:
        names = ", ".join(m[0] for m in members)
        return "WARN", (f"No approved-admin list ({APPROVED_ADMINS_FILE}). "
                        f"Administrators: {names}")

    def ok(name, sid):
        short = name.split("\\")[-1].lower()
        return sid.endswith("-500") or name.lower() in approved or short in approved

    bad = [f"{n} ({src})" if src else n for n, sid, src in members if not ok(n, sid)]
    if bad:
        return "WARN", "Admins not on the approved list: " + ", ".join(bad)
    return "PASS", "All administrators are on the approved list: " + ", ".join(m[0] for m in members)


COMPROMISE_CHECKS = [
    {
        "id": "log_cleared",
        "name": "Event Log Cleared",
        "description": "Attackers clear the Security/System logs to hide what they did. Legitimate clearing is rare.",
        "action": "Find out who cleared the log and why. If nobody can explain it, treat the machine as compromised: disconnect it from the network and escalate.",
        "severity": "HIGH",
        "check_ps": _EVENT_FIELD_FN + r'''
$since = (Get-Date).AddDays(-30); $hits = @(); $err = $null
foreach ($q in @(@{LogName='Security'; Id=1102; StartTime=$since}, @{LogName='System'; Id=104; StartTime=$since})) {
  try { $hits += Get-Events $q 50 } catch { $err = "$($_.Exception.Message)" } }
$hits = @($hits | Sort-Object TimeCreated -Descending)
if ($hits) {
  $who = @($hits | Where-Object { $_.Id -eq 1102 } | ForEach-Object { F $_ 'SubjectUserName' } | Sort-Object -Unique) -join ', '
  "FAIL: Event log cleared $($hits.Count) time(s) in 30 days, last $($hits[0].TimeCreated.ToString('yyyy-MM-dd HH:mm'))" + $(if ($who) { " by $who" } else { '' }) }
elseif ($err) { "UNKNOWN: Could not read event logs ($err)" }
else { 'PASS: No event-log clearing in the last 30 days' }
''',
        "review_ps": "Start-Process eventvwr.msc; Write-Host 'Event Viewer opened.'",
        "review_label": "Open Event Viewer",
    },
    {
        "id": "failed_logons",
        "name": "Failed Logons / Lockouts",
        "description": "Bursts of failed logons (event 4625) and account lockouts (4740) point to password guessing.",
        "action": "Check the source addresses listed. Repeated failures from one remote IP: block it at the firewall and make sure RDP/SMB are not exposed to the internet. Reset the targeted account's password if it is weak.",
        "severity": "MEDIUM",
        "timeout": 180,
        "check_ps": _EVENT_FIELD_FN + r'''
$since = (Get-Date).AddDays(-7)
try { $ev = Get-Events @{LogName='Security'; Id=4625; StartTime=$since} 2000 }
catch { "UNKNOWN: Could not read Security log ($($_.Exception.Message))"; return }
$lk = @(); try { $lk = Get-Events @{LogName='Security'; Id=4740; StartTime=$since} 200 } catch { }
$top = $ev | ForEach-Object { $ip = F $_ 'IpAddress'; if (-not $ip -or $ip -eq '-') { $ip = 'local' }; "$(F $_ 'TargetUserName') from $ip" } |
       Group-Object | Sort-Object Count -Descending | Select-Object -First 3 | ForEach-Object { "$($_.Name) x$($_.Count)" }
$msg = "$($ev.Count) failed logon(s) in 7 days" + $(if ($lk) { ", $($lk.Count) lockout(s)" } else { '' }) + $(if ($top) { ". Top: $($top -join '; ')" } else { '' })
if ($ev.Count -ge 200) { "FAIL: $msg (possible brute force)" }
elseif ($ev.Count -ge 20 -or $lk) { "WARN: $msg" }
else { "PASS: $msg" }
''',
        "review_ps": "Start-Process eventvwr.msc; Write-Host 'Event Viewer opened.'",
        "review_label": "Open Event Viewer",
    },
    {
        "id": "account_changes",
        "name": "New Accounts / Admin Group Changes",
        "description": "Accounts created (4720) or added to the local Administrators group (4732) in the last 30 days — attackers add themselves an admin account for persistence.",
        "action": "Confirm each change with whoever made it (the 'by' name). Disable and investigate any account nobody recognises.",
        "severity": "HIGH",
        "check_ps": _EVENT_FIELD_FN + r'''
$since = (Get-Date).AddDays(-30)
try {
  $made = Get-Events @{LogName='Security'; Id=4720; StartTime=$since} 200
  $add  = Get-Events @{LogName='Security'; Id=4732; StartTime=$since} 500 | Where-Object { (F $_ 'TargetSid') -eq 'S-1-5-32-544' }
} catch { "UNKNOWN: Could not read Security log ($($_.Exception.Message))"; return }
$p = @()
if ($made) { $p += 'Created: ' + (($made | ForEach-Object { "$(F $_ 'TargetUserName') by $(F $_ 'SubjectUserName') ($($_.TimeCreated.ToString('yyyy-MM-dd')))" }) -join ', ') }
if ($add) {
  $p += 'Added to Administrators: ' + (($add | ForEach-Object {
    $m = F $_ 'MemberName'
    if (-not $m -or $m -eq '-') { $sid = F $_ 'MemberSid'; try { $m = ([Security.Principal.SecurityIdentifier]$sid).Translate([Security.Principal.NTAccount]).Value } catch { $m = $sid } }
    "$m by $(F $_ 'SubjectUserName') ($($_.TimeCreated.ToString('yyyy-MM-dd')))" }) -join ', ') }
if ($p) { "WARN: $($p -join ' | ')" } else { 'PASS: No accounts created or added to Administrators in 30 days' }
''',
        "review_ps": "try { Start-Process lusrmgr.msc -EA Stop } catch { Start-Process netplwiz }; Write-Host 'Local Users and Groups opened.'",
        "review_label": "Review Accounts",
    },
    {
        "id": "unapproved_admins",
        "name": "Unapproved Local Admins",
        "description": "Members of the local Administrators group that are not on the approved list (config/approved_admins.json).",
        "action": "Remove accounts that should not be admins, or add legitimate ones to config/approved_admins.json so future reports stay clean.",
        "severity": "HIGH",
        "check_ps": r'''
try { Get-LocalGroupMember -SID 'S-1-5-32-544' -EA Stop | ForEach-Object { "ADM`t$($_.Name)`t$($_.SID)`t$($_.PrincipalSource)" } }
catch { net localgroup administrators 2>$null | Select-Object -Skip 6 | Where-Object { $_ -and $_ -notmatch 'command completed' } | ForEach-Object { "ADM`t$($_.Trim())`t`t" } }
''',
        "evaluate": _eval_unapproved_admins,
        "review_ps": "try { Start-Process lusrmgr.msc -EA Stop } catch { Start-Process netplwiz }; Write-Host 'Local Users and Groups opened.'",
        "review_label": "Review Admins",
    },
    {
        "id": "rdp_logons",
        "name": "Remote Desktop Logons",
        "description": "Successful RDP logons (event 4624, logon type 10) in the last 30 days, with their source addresses.",
        "action": "Check every user/source pair is expected. Logons from public IP addresses mean RDP is reachable from the internet — close it or put it behind a VPN, and reset the passwords of those accounts.",
        "severity": "HIGH",
        "check_ps": _EVENT_FIELD_FN + r'''
$xp = "*[System[(EventID=4624) and TimeCreated[timediff(@SystemTime) <= 2592000000]]] and *[EventData[Data[@Name='LogonType']='10']]"
if (-not (Test-LogAccess 'Security')) { 'UNKNOWN: Access denied to the Security log (run as administrator)'; return }
try { $ev = @(Get-WinEvent -LogName Security -FilterXPath $xp -MaxEvents 500 -EA Stop) }
catch { if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { $ev = @() } else { "UNKNOWN: Could not read Security log ($($_.Exception.Message))"; return } }
if (-not $ev) { 'PASS: No RDP logons in 30 days'; return }
$priv = '^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|::1$|fe80:|f[cd]|-$|$)'
$pairs = $ev | ForEach-Object { [pscustomobject]@{U="$(F $_ 'TargetDomainName')\$(F $_ 'TargetUserName')"; IP="$(F $_ 'IpAddress')"} }
$pub = @($pairs | Where-Object { $_.IP -notmatch $priv } | ForEach-Object { "$($_.U) from $($_.IP)" } | Sort-Object -Unique)
$all = ($pairs | Group-Object U, IP | Sort-Object Count -Descending | Select-Object -First 6 | ForEach-Object { "$($_.Group[0].U) from $($_.Group[0].IP) x$($_.Count)" }) -join ', '
if ($pub) { "WARN: RDP logons from public IPs: $($pub -join ', ')" } else { "INFO: $($ev.Count) RDP logon(s), all from private addresses: $all" }
''',
        "review_ps": "Start-Process eventvwr.msc; Write-Host 'Event Viewer opened.'",
        "review_label": "Open Event Viewer",
    },
    {
        "id": "recent_tasks",
        "name": "Recently Created Scheduled Tasks",
        "description": "Non-Microsoft scheduled tasks registered in the last 30 days — a favourite persistence method.",
        "action": "Make sure each task belongs to software you installed. Disable unknown ones in Task Scheduler and check the program they run.",
        "severity": "MEDIUM",
        "check_ps": r'''
$since = (Get-Date).AddDays(-30)
$new = foreach ($t in Get-ScheduledTask -EA SilentlyContinue | Where-Object { $_.TaskPath -notlike '\Microsoft\*' }) {
  $d = [datetime]::MinValue
  if (-not [datetime]::TryParse("$($t.Date)", [ref]$d)) {
    $f = Get-Item -LiteralPath "$env:windir\System32\Tasks$($t.TaskPath)$($t.TaskName)" -EA SilentlyContinue
    if ($f) { $d = $f.CreationTime } }
  # Only tasks that launch a program (COM-handler tasks are Windows/app internals)
  $run = (@($t.Actions | ForEach-Object { $_.Execute }) | Where-Object { $_ }) -join ' '
  if ($run -and $d -gt $since) { "$($t.TaskPath)$($t.TaskName) ($($d.ToString('yyyy-MM-dd'))) -> $run" } }
$new = @($new)
if ($new) { "WARN: $($new.Count) task(s) created in 30 days: $($new -join ' | ')" } else { 'PASS: No new non-Microsoft scheduled tasks in 30 days' }
''',
        "review_ps": "Start-Process taskschd.msc; Write-Host 'Task Scheduler opened.'",
        "review_label": "Open Task Scheduler",
    },
    {
        "id": "startup_entries",
        "name": "Suspicious Startup Entries",
        "description": "Run/RunOnce registry keys (machine and every loaded user) and Startup folders that launch script hosts, download one-liners, or unsigned programs from user-writable folders.",
        "action": "Look up each flagged entry. Remove ones you can't attribute to installed software (Task Manager > Startup, or delete the registry value) and scan the referenced file.",
        "severity": "HIGH",
        "timeout": 180,
        "check_ps": r'''
$rx = '(?i)-enc(odedcommand)?\s|mshta|downloadstring|downloadfile|iex\s*\(|invoke-expression|certutil.+urlcache|bitsadmin|regsvr32.+/i:|rundll32.+(http|javascript)|wscript|cscript|\.vbs\b|\.js\b|\.jse\b|\.hta\b'
$wr = '(?i)\\AppData\\|\\Temp\\|\\Users\\Public\\|\\ProgramData\\|\\Downloads\\'
$skip = 'PSPath','PSParentPath','PSChildName','PSDrive','PSProvider','(default)'
function ExePath($cmd) {
  $c = [Environment]::ExpandEnvironmentVariables("$cmd").Trim()
  if ($c -match '^"([^"]+)"') { $matches[1] } elseif ($c -match '^(.+?\.(exe|com|scr|pif|bat|cmd))(\s|$)') { $matches[1] } else { ($c -split ' ')[0] } }
$keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run','HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce'
$keys += Get-ChildItem Registry::HKEY_USERS -EA SilentlyContinue | Where-Object { $_.PSChildName -match '^S-1-5-21-[\d-]+$' } |
         ForEach-Object { "Registry::HKEY_USERS\$($_.PSChildName)\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Registry::HKEY_USERS\$($_.PSChildName)\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce" }
$entries = @()
foreach ($k in $keys) {
  $p = Get-ItemProperty -Path $k -EA SilentlyContinue; if (-not $p) { continue }
  foreach ($n in $p.PSObject.Properties | Where-Object { $_.Name -notin $skip }) { $entries += [pscustomobject]@{Name=$n.Name; Cmd="$($n.Value)"} } }
$dirs = @("$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp")
$dirs += Get-ChildItem "$env:SystemDrive\Users" -Directory -EA SilentlyContinue | ForEach-Object { "$($_.FullName)\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup" }
$sh = New-Object -ComObject WScript.Shell
foreach ($d in $dirs) {
  Get-ChildItem -LiteralPath $d -File -EA SilentlyContinue | Where-Object { $_.Name -ne 'desktop.ini' } | ForEach-Object {
    $cmd = "`"$($_.FullName)`""
    if ($_.Extension -eq '.lnk') { try { $s = $sh.CreateShortcut($_.FullName); $cmd = "`"$($s.TargetPath)`" $($s.Arguments)" } catch { } }
    $entries += [pscustomobject]@{Name="$($_.Name) (Startup folder)"; Cmd=$cmd} } }
$sus = foreach ($e in $entries) {
  $hit = $e.Cmd -match $rx
  if (-not $hit) {
    $exe = ExePath $e.Cmd
    # Store-app aliases (\WindowsApps\) are protected and can't be read — skip them
    if ($exe -match $wr -and $exe -notmatch '(?i)\\Microsoft\\WindowsApps\\') {
      if (-not (Test-Path -LiteralPath $exe)) { $hit = $true }
      else {
        $sig = $null; try { $sig = Get-AuthenticodeSignature -LiteralPath $exe -EA Stop } catch { }
        $hit = (-not $sig) -or ("$($sig.Status)" -ne 'Valid') } } }
  if ($hit) { $c = $e.Cmd; if ($c.Length -gt 140) { $c = $c.Substring(0, 140) + '...' }; "$($e.Name): $c" } }
$sus = @($sus)
if ($sus) { "WARN: $($sus.Count) suspicious startup entr$(if ($sus.Count -eq 1) {'y'} else {'ies'}): $($sus -join ' | ')" }
else { "PASS: $($entries.Count) startup entries, none suspicious" }
''',
        "review_ps": "Start-Process taskmgr -ArgumentList '/0 /startup'; Write-Host 'Task Manager (Startup) opened.'",
        "review_label": "Open Startup Apps",
    },
    {
        "id": "unsigned_processes",
        "name": "Unsigned Running Processes",
        "description": "Running programs without a valid digital signature — especially from user-writable folders (AppData, Temp, Downloads, ProgramData).",
        "action": "For each flagged process, check where it came from (file properties, VirusTotal hash lookup). Kill and quarantine anything you can't identify, then run a full Defender scan.",
        "severity": "HIGH",
        "timeout": 240,
        "check_ps": r'''
$wr = '(?i)\\AppData\\|\\Temp\\|\\Users\\Public\\|\\ProgramData\\|\\Downloads\\'
$paths = @(Get-Process -EA SilentlyContinue | Where-Object { $_.Path } | ForEach-Object { $_.Path } | Sort-Object -Unique)
$bad = foreach ($p in $paths) {
  $s = Get-AuthenticodeSignature -LiteralPath $p -EA SilentlyContinue
  if ((-not $s) -or ("$($s.Status)" -ne 'Valid')) { [pscustomobject]@{P=$p; W=($p -match $wr)} } }
$w = @($bad | Where-Object { $_.W } | ForEach-Object { $_.P })
$o = @($bad | Where-Object { -not $_.W } | ForEach-Object { Split-Path $_.P -Leaf })
if ($w) { "WARN: Unsigned processes in user-writable folders: $($w -join ', ')" + $(if ($o) { " | Other unsigned: $($o -join ', ')" } else { '' }) }
elseif ($o) { "INFO: $($o.Count) unsigned process(es) outside user folders: $($o -join ', ')" }
else { "PASS: All $($paths.Count) running programs are signed" }
''',
        "review_ps": "Start-Process taskmgr -ArgumentList '/0 /details'; Write-Host 'Task Manager opened.'",
        "review_label": "Open Task Manager",
    },
    {
        "id": "outbound_connections",
        "name": "External Network Connections",
        "description": "Established connections to public IP addresses, grouped by process. Flags known backdoor/IRC/Tor ports and connections from unsigned programs in user-writable folders.",
        "action": "Make sure each flagged process is expected to talk to the internet. Look up unknown remote IPs; for anything suspicious, disconnect the machine and investigate the process.",
        "severity": "MEDIUM",
        "timeout": 180,
        "check_ps": r'''
$priv = '^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|::1$|fe80:|f[cd]|0\.0\.0\.0|::$)'
$wr = '(?i)\\AppData\\|\\Temp\\|\\Users\\Public\\|\\ProgramData\\|\\Downloads\\'
$badPorts = 4444,1337,31337,6666,6667,6697,9001,9030,9050,9150,5555,12345
$c = @(Get-NetTCPConnection -State Established -EA SilentlyContinue | Where-Object { $_.RemoteAddress -notmatch $priv })
if (-not $c) { 'PASS: No established connections to public addresses'; return }
$odd = @(); $sum = @()
foreach ($g in $c | Group-Object OwningProcess) {
  $p = Get-Process -Id ([int]$g.Name) -EA SilentlyContinue
  $name = if ($p) { $p.ProcessName } else { "PID $($g.Name)" }
  $sum += [pscustomobject]@{N=$name; C=$g.Count}
  $ports = @($g.Group | ForEach-Object { [int]$_.RemotePort } | Where-Object { $_ -in $badPorts } | Sort-Object -Unique)
  if ($ports) { $odd += "$name -> port(s) $($ports -join ',')" }
  elseif ($p -and $p.Path -and $p.Path -match $wr) {
    $s = Get-AuthenticodeSignature -LiteralPath $p.Path -EA SilentlyContinue
    if ((-not $s) -or ("$($s.Status)" -ne 'Valid')) { $odd += "$name (unsigned, $($p.Path)) -> $(@($g.Group.RemoteAddress | Sort-Object -Unique)[0..2] -join ', ')" } } }
$top = ($sum | Group-Object N | ForEach-Object { [pscustomobject]@{N=$_.Name; C=($_.Group | Measure-Object C -Sum).Sum} } |
        Sort-Object C -Descending | Select-Object -First 8 | ForEach-Object { "$($_.N) x$($_.C)" }) -join ', '
if ($odd) { "WARN: Suspicious connections: $($odd -join ' | ')" } else { "INFO: $($c.Count) external connection(s): $top" }
''',
        "review_ps": "Start-Process resmon.exe; Write-Host 'Resource Monitor opened (Network tab).'",
        "review_label": "Open Resource Monitor",
    },
    {
        "id": "recent_software",
        "name": "Recently Installed Software",
        "description": "Programs installed in the last 30 days, listed for review.",
        "action": "Confirm each program was installed on purpose. Uninstall anything nobody recognises (remote-access tools and browser add-ons especially).",
        "severity": "LOW",
        "check_ps": r'''
$since = (Get-Date).AddDays(-30).ToString('yyyyMMdd')
$keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
$new = @(Get-ItemProperty $keys -EA SilentlyContinue |
  Where-Object { $_.DisplayName -and $_.SystemComponent -ne 1 -and "$($_.InstallDate)" -match '^\d{8}$' -and "$($_.InstallDate)" -ge $since -and
                 $_.DisplayName -notmatch '(?i)^(Security )?Update for|Hotfix|\bKB\d{6,}' } |
  Sort-Object InstallDate -Descending |
  ForEach-Object { "$($_.DisplayName) $($_.DisplayVersion) ($($_.InstallDate.Substring(0,4))-$($_.InstallDate.Substring(4,2))-$($_.InstallDate.Substring(6,2)))" } |
  Sort-Object -Unique)
if ($new) { "INFO: $($new.Count) program(s) installed in 30 days: $($new -join ', ')" } else { 'PASS: No programs installed in the last 30 days' }
''',
        "review_ps": "Start-Process appwiz.cpl; Write-Host 'Programs and Features opened.'",
        "review_label": "Open Programs",
    },
    {
        "id": "system32_changes",
        "name": "New Unsigned Files in System32",
        "description": "Executables, DLLs and drivers created or modified in System32 in the last 14 days that are not validly signed. Windows Update files are always signed.",
        "action": "Check each file (properties, hash lookup). An unexplained unsigned binary in System32 is a strong sign of tampering — isolate the machine and run a Defender offline scan.",
        "severity": "HIGH",
        "timeout": 240,
        "check_ps": r'''
$since = (Get-Date).AddDays(-14)
$f = @()
foreach ($d in "$env:windir\System32", "$env:windir\System32\drivers") {
  $f += Get-ChildItem -LiteralPath $d -File -EA SilentlyContinue |
        Where-Object { $_.Extension -in '.exe','.dll','.sys','.scr','.com','.cpl' -and ($_.CreationTime -gt $since -or $_.LastWriteTime -gt $since) } }
$f = @($f | Sort-Object LastWriteTime -Descending | Select-Object -First 400)
$bad = @(foreach ($x in $f) {
  $s = Get-AuthenticodeSignature -LiteralPath $x.FullName -EA SilentlyContinue
  if ((-not $s) -or ("$($s.Status)" -ne 'Valid')) { "$($x.Name) ($($x.LastWriteTime.ToString('yyyy-MM-dd')))" } })
if ($bad) { "FAIL: $($bad.Count) unsigned file(s) changed in System32: $($bad -join ', ')" }
else { "PASS: $($f.Count) file(s) changed in 14 days, all signed" }
''',
        "review_ps": "Start-Process explorer.exe -ArgumentList \"$env:windir\\System32\"; Write-Host 'System32 opened.'",
        "review_label": "Open System32",
    },
    {
        "id": "defender_history",
        "name": "Defender Detections & Last Scan",
        "description": "Threats Defender found in the last 90 days, whether they were fully removed, and how long since the last scan.",
        "action": "Unresolved threats: run a Defender full or offline scan now and don't use the machine for anything sensitive until it's clean. Resolved threats: find out how they got in (download, USB, email). Stale scans: run a quick scan.",
        "severity": "HIGH",
        "check_ps": r'''
$s = Get-MpComputerStatus -EA SilentlyContinue
if (-not $s) { 'UNKNOWN: Defender status unavailable (third-party antivirus?)'; return }
$t = @(Get-MpThreatDetection -EA SilentlyContinue | Where-Object { $_.InitialDetectionTime -gt (Get-Date).AddDays(-90) })
$names = @{}; Get-MpThreat -EA SilentlyContinue | ForEach-Object { $names["$($_.ThreatID)"] = $_.ThreatName }
$nm = { $n = $names["$($_.ThreatID)"]; if ($n) { $n } else { "ThreatID $($_.ThreatID)" } }
# 2 Cleaned, 3 Quarantined, 4 Removed, 6 Blocked — anything else is not resolved
$active = @($t | Where-Object { $_.ThreatStatusID -notin 2,3,4,6 })
$scan = [math]::Min([double]$s.QuickScanAge, [double]$s.FullScanAge)
$scanTxt = if ($scan -ge 10000) { 'never scanned' } else { "last scan $scan day(s) ago" }
if ($active) { "FAIL: Unresolved threats: $((@($active | ForEach-Object $nm) | Sort-Object -Unique) -join ', ') ($scanTxt)" }
elseif ($t) { "WARN: $($t.Count) threat(s) in 90 days, all resolved: $((@($t | ForEach-Object $nm) | Sort-Object -Unique) -join ', ') ($scanTxt)" }
elseif ($scan -gt 7) { "WARN: No threats recorded, but $scanTxt" }
else { "PASS: No threats in 90 days, $scanTxt" }
''',
        "review_ps": "Start-Process 'windowsdefender://threat'; Write-Host 'Windows Security opened.'",
        "review_label": "Open Windows Security",
    },
    {
        "id": "hosts_file",
        "name": "Hosts File Tampering",
        "description": "Hosts-file entries that redirect or block Windows Update, antivirus, Microsoft/Google login or banking sites — malware does this to block updates or phish credentials.",
        "action": "Remove the flagged lines from C:\\Windows\\System32\\drivers\\etc\\hosts (as admin), then run a full antivirus scan to find what added them.",
        "severity": "HIGH",
        "check_ps": r'''
$h = @(Get-Content "$env:windir\System32\drivers\etc\hosts" -EA SilentlyContinue |
  ForEach-Object { ($_ -replace '#.*$', '').Trim() -replace '\s+', ' ' } |
  Where-Object { $_ -and $_ -notmatch '^(127\.0\.0\.1|::1) localhost$' })
$crit = '(?i)windowsupdate|update\.microsoft|login\.(microsoftonline|live)|microsoft\.com|office\.com|outlook|google\.com|accounts\.google|paypal|bank|defender|smartscreen|wdcp|symantec|norton|mcafee|kaspersky|eset|sophos|avast|avg\.com|bitdefender|malwarebytes|crowdstrike|virustotal'
$okRx = '(?i)telemetry|vortex|watson|settings-win\.data|diagnostics'
$bad = @($h | Where-Object { $_ -match $crit -and $_ -notmatch $okRx })
if ($bad) { "FAIL: Hosts file redirects security/login sites: $($bad -join ' | ')" }
elseif ($h) { "INFO: $($h.Count) custom hosts entr$(if ($h.Count -eq 1) {'y'} else {'ies'}): $(($h | Select-Object -First 8) -join ' | ')" }
else { 'PASS: Hosts file has no custom entries' }
''',
        "review_ps": "Start-Process notepad.exe -ArgumentList \"$env:windir\\System32\\drivers\\etc\\hosts\"; Write-Host 'Hosts file opened.'",
        "review_label": "Open Hosts File",
    },
]

COMPROMISE_BY_ID = {c["id"]: c for c in COMPROMISE_CHECKS}
for _c in COMPROMISE_CHECKS:
    _c["category"] = "Compromise"


def compromise_level(results):
    """CLEAN / LOW / MEDIUM / HIGH / CRITICAL for the 'Signs of Compromise' section."""
    statuses = [(c["severity"], results.get(c["id"], ("UNKNOWN",))[0]) for c in COMPROMISE_CHECKS]
    if any(sev == "HIGH" and st == "FAIL" for sev, st in statuses):
        return "CRITICAL"
    if any(st == "FAIL" for _, st in statuses):
        return "HIGH"
    if any(st == "WARN" and sev == "HIGH" for sev, st in statuses):
        return "MEDIUM"
    if any(st == "WARN" for _, st in statuses):
        return "LOW"
    return "CLEAN"
