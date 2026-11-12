"""Security check definitions shared by the Security tab and reports.

Each check: id, name, description, impact, severity (HIGH/MEDIUM/LOW), check_ps
(prints PASS / WARN: ... / FAIL: ...), optional fix_ps/fix_label, undo_ps/undo_label,
optional evaluate(output) -> (status, detail) for checks whose raw output is parsed in Python.
"""
import re

CHECKS = [
    {
        "id": "firewall",
        "name": "Windows Firewall",
        "description": "All firewall profiles (Domain/Private/Public) must be enabled.",
        "impact": "Blocks inbound connections not explicitly allowed. May interrupt LAN services (file sharing, remote mgmt tools) on the Public profile if their inbound rules aren't already defined.",
        "severity": "HIGH",
        "check_ps": (
            "$off = Get-NetFirewallProfile -EA SilentlyContinue"
            " | Where-Object { $_.Enabled -eq $false }"
            " | Select-Object -ExpandProperty Name;"
            " if ($off) { \"FAIL: Profiles disabled: $($off -join ', ')\" } else { 'PASS' }"
        ),
        "fix_ps":  "Set-NetFirewallProfile -All -Enabled True; Write-Host 'Firewall enabled.'",
        "fix_label": "Enable Firewall",
        "undo_ps": "Set-NetFirewallProfile -All -Enabled False; Write-Host 'Firewall disabled.'",
        "undo_label": "Revert (Disable)",
    },
    {
        "id": "rdp",
        "name": "RDP Exposure",
        "description": "RDP should be disabled on machines not requiring remote access.",
        "impact": "Fully closes RDP — no one (incl. IT) can remote in until re-enabled locally or via other tooling. Confirm an alternate remote-support path exists first.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -EA SilentlyContinue).fDenyTSConnections;"
            " if ($v -eq 0) { 'FAIL: RDP is enabled (port 3389 open)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -Value 1 -Force; Write-Host 'RDP disabled.'"
        ),
        "fix_label": "Disable RDP",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -Value 0 -Force; Write-Host 'RDP re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable RDP)",
    },
    {
        "id": "smb1",
        "name": "SMBv1 Protocol",
        "description": "SMBv1 enables EternalBlue/WannaCry exploits. Must be disabled.",
        "impact": "Breaks connections to very old NAS boxes, some scanners/printers, and legacy XP/2003 systems that only speak SMBv1. No effect on modern devices.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-SmbServerConfiguration -EA SilentlyContinue).EnableSMB1Protocol;"
            " if ($v) { 'FAIL: SMBv1 enabled (EternalBlue/WannaCry risk)' } else { 'PASS' }"
        ),
        "fix_ps":  "Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force; Write-Host 'SMBv1 disabled.'",
        "fix_label": "Disable SMBv1",
        "undo_ps": "Set-SmbServerConfiguration -EnableSMB1Protocol $true -Force; Write-Host 'SMBv1 re-enabled.'",
        "undo_label": "Revert (Re-enable SMBv1)",
    },
    {
        "id": "guest",
        "name": "Guest Account",
        "description": "Guest account provides unauthenticated access. Must be disabled.",
        "impact": "No impact on normal users. Breaks setups that intentionally rely on Guest for kiosk-style shared access.",
        "severity": "HIGH",
        "check_ps": (
            "$g = Get-LocalUser -Name 'Guest' -EA SilentlyContinue;"
            " if ($g -and $g.Enabled) { 'FAIL: Guest account is enabled' } else { 'PASS' }"
        ),
        "fix_ps":  "Disable-LocalUser -Name 'Guest'; Write-Host 'Guest account disabled.'",
        "fix_label": "Disable Guest",
        "undo_ps": "Enable-LocalUser -Name 'Guest'; Write-Host 'Guest account re-enabled.'",
        "undo_label": "Revert (Re-enable Guest)",
    },
    {
        "id": "autologon",
        "name": "Auto-Login (AutoLogon)",
        "description": "AutoLogon stores plaintext credentials in the registry.",
        "impact": "User must type their password at next boot instead of auto sign-in. Expected loss of convenience only, no functional break.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " -Name AutoAdminLogon -EA SilentlyContinue).AutoAdminLogon;"
            " if ($v -eq '1') { 'FAIL: Auto-login enabled (credentials in registry)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "$p = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon';"
            " Set-ItemProperty $p AutoAdminLogon '0' -Force;"
            " Remove-ItemProperty $p DefaultPassword -EA SilentlyContinue;"
            " Write-Host 'Auto-login disabled.'"
        ),
        "fix_label": "Disable Auto-Login",
        "undo_ps": (
            "Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " AutoAdminLogon '1' -Force; Write-Host 'Auto-login re-enabled (no password set).'"
        ),
        "undo_label": "Revert (Re-enable AutoLogon)",
    },
    {
        "id": "defender",
        "name": "Windows Defender",
        "description": "Real-time protection must be active.",
        "impact": "Restores real-time malware scanning. May cause a brief performance dip during the first scan; no functional loss for normal use.",
        "severity": "HIGH",
        "check_ps": (
            "$s = Get-MpComputerStatus -EA SilentlyContinue;"
            " if (-not $s) { 'WARN: Could not query Defender status' }"
            " elseif (-not $s.RealTimeProtectionEnabled) { 'FAIL: Real-time protection disabled' }"
            " else { 'PASS' }"
        ),
        "fix_ps":  "Set-MpPreference -DisableRealtimeMonitoring $false; Write-Host 'Defender enabled.'",
        "fix_label": "Enable Defender",
        "undo_ps": "Set-MpPreference -DisableRealtimeMonitoring $true; Write-Host 'Defender real-time disabled.'",
        "undo_label": "Revert (Disable Defender)",
    },
    {
        "id": "uac",
        "name": "User Account Control (UAC)",
        "description": "UAC prevents unauthorised privilege escalation.",
        "impact": "Restores admin-action prompts. Scripts/users that silently auto-elevated will now see a UAC prompt — expected behavior, not a bug.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -EA SilentlyContinue).EnableLUA;"
            " if ($v -eq 0) { 'FAIL: UAC is disabled' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -Value 1 -Force; Write-Host 'UAC enabled. Restart required.'"
        ),
        "fix_label": "Enable UAC",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -Value 0 -Force; Write-Host 'UAC disabled. Restart required.'"
        ),
        "undo_label": "Revert (Disable UAC)",
    },
    {
        "id": "windows_updates",
        "name": "Windows Updates",
        "description": "System should have recent updates installed (within 30 days).",
        "impact": "Only opens Settings; no change until updates are installed. Installing may require a restart and, rarely, surface a driver/compat issue — standard patch-management risk.",
        "severity": "MEDIUM",
        "check_ps": (
            "$h = Get-HotFix -EA SilentlyContinue | Sort-Object InstalledOn -Descending | Select-Object -First 1;"
            " if ($h -and $h.InstalledOn) {"
            " $days = [int]((Get-Date) - $h.InstalledOn).TotalDays;"
            " if ($days -gt 30) { \"WARN: Last update $days days ago ($($h.InstalledOn.ToString('yyyy-MM-dd')))\" }"
            " else { \"PASS: Last update $days days ago\" } }"
            " else { 'WARN: No Windows Update history found' }"
        ),
        "fix_ps": "Start-Process 'ms-settings:windowsupdate'; Write-Host 'Windows Update opened.'",
        "fix_label": "Open Updates",
    },
    {
        "id": "bitlocker",
        "name": "BitLocker (Drive C:)",
        "description": "Full-disk encryption protects data if device is lost or stolen.",
        "impact": "Only opens the control panel; no change until enabled. Turning it on encrypts the whole drive (takes time) and requires safely storing the recovery key — losing it makes data unrecoverable.",
        "severity": "MEDIUM",
        "check_ps": (
            "$bl = Get-BitLockerVolume -MountPoint 'C:' -EA SilentlyContinue;"
            " if (-not $bl) { 'WARN: BitLocker not available or could not query' }"
            " elseif ($bl.ProtectionStatus -ne 'On') { 'WARN: BitLocker not enabled on C: (data unencrypted)' }"
            " else { 'PASS: BitLocker protection active' }"
        ),
        "fix_ps": "control /name Microsoft.BitLockerDriveEncryption; Write-Host 'BitLocker panel opened.'",
        "fix_label": "Open BitLocker",
    },
    {
        "id": "smb_signing",
        "name": "SMB Signing",
        "description": "SMB signing prevents man-in-the-middle relay attacks.",
        "impact": "May slightly reduce file-transfer throughput and can break very old SMB clients that don't support signing.",
        "severity": "MEDIUM",
        "check_ps": (
            "$v = (Get-SmbServerConfiguration -EA SilentlyContinue).RequireSecuritySignature;"
            " if ($v -eq $false) { 'WARN: SMB signing not required (MITM risk)' } else { 'PASS' }"
        ),
        "fix_ps":  "Set-SmbServerConfiguration -RequireSecuritySignature $true -Force; Write-Host 'SMB signing required.'",
        "fix_label": "Require SMB Signing",
        "undo_ps": "Set-SmbServerConfiguration -RequireSecuritySignature $false -Force; Write-Host 'SMB signing reverted.'",
        "undo_label": "Revert SMB Signing",
    },
    {
        "id": "password_policy",
        "name": "Password Max Age Policy",
        "description": "Passwords should expire within 90 days.",
        "impact": "Users get expiry prompts and must pick new passwords every 90 days — expected friction. Make sure users know how to reset if locked out.",
        "severity": "MEDIUM",
        "check_ps": (
            "$out = net accounts 2>&1 | Out-String;"
            " if ($out -match 'Maximum password age:\\s+(\\S+)') {"
            " $age = $matches[1];"
            " if ($age -eq 'Unlimited') { 'WARN: Password max age: Unlimited' }"
            " elseif ([int]$age -gt 90) { \"WARN: Password max age: $age days (>90)\" }"
            " else { \"PASS: Max age $age days\" } }"
            " else { 'WARN: Could not read password policy' }"
        ),
        "fix_ps":  "net accounts /maxpwage:90; Write-Host 'Password max age set to 90 days.'",
        "fix_label": "Set 90-Day Expiry",
        "undo_ps": "net accounts /maxpwage:unlimited; Write-Host 'Password max age set to Unlimited.'",
        "undo_label": "Revert (Set Unlimited)",
    },
    {
        "id": "remote_registry",
        "name": "Remote Registry Service",
        "description": "Remote Registry allows remote editing of registry hives. Should be disabled.",
        "impact": "Breaks remote-management/monitoring tools that read registry values remotely (some RMM/inventory tools). Confirm none are in use before disabling fleet-wide.",
        "severity": "LOW",
        "check_ps": (
            "$s = Get-Service -Name RemoteRegistry -EA SilentlyContinue;"
            " if ($s -and $s.Status -eq 'Running') { 'WARN: Remote Registry service is running' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Stop-Service RemoteRegistry -Force -EA SilentlyContinue;"
            " Set-Service RemoteRegistry -StartupType Disabled;"
            " Write-Host 'Remote Registry disabled.'"
        ),
        "fix_label": "Disable Service",
        "undo_ps": (
            "Set-Service RemoteRegistry -StartupType Automatic;"
            " Start-Service RemoteRegistry -EA SilentlyContinue;"
            " Write-Host 'Remote Registry re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable)",
    },
    {
        "id": "telnet",
        "name": "Telnet Client",
        "description": "Telnet transmits data in plaintext. Should not be installed.",
        "impact": "No impact for normal users. Only affects admins scripting against Telnet for legacy device management (should migrate to SSH anyway).",
        "severity": "LOW",
        "check_ps": (
            "$f = Get-WindowsOptionalFeature -Online -FeatureName TelnetClient -EA SilentlyContinue;"
            " if ($f -and $f.State -eq 'Enabled') { 'WARN: Telnet client installed (insecure)' } else { 'PASS' }"
        ),
        "fix_ps":  "Disable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart; Write-Host 'Telnet removed.'",
        "fix_label": "Remove Telnet",
        "undo_ps": "Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart; Write-Host 'Telnet installed.'",
        "undo_label": "Revert (Install Telnet)",
    },
    {
        "id": "rdp_nla",
        "name": "RDP Network Level Authentication",
        "description": "RDP without NLA lets attackers reach the logon screen before authenticating (pre-auth attack surface).",
        "impact": "Requires full authentication before the RDP session starts. Very old RDP clients (pre-Windows 7 era, some old thin clients) may fail to connect until updated.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp'"
            " -Name UserAuthentication -EA SilentlyContinue).UserAuthentication;"
            " if ($v -eq 0) { 'FAIL: NLA not required (pre-auth RDP exposure)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp'"
            " -Name UserAuthentication -Value 1 -Force; Write-Host 'NLA required for RDP.'"
        ),
        "fix_label": "Require NLA",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp'"
            " -Name UserAuthentication -Value 0 -Force; Write-Host 'NLA requirement removed.'"
        ),
        "undo_label": "Revert (Remove NLA requirement)",
    },
    {
        "id": "asr_office",
        "name": "Office Macro Attack Surface Reduction",
        "description": "Office apps spawning child processes is the #1 macro-malware execution chain (malspam).",
        "impact": "Blocks Word/Excel/Outlook from launching child processes. May break legitimate macro workflows that intentionally launch external tools (mail-merge scripts, automation macros) — add a Defender exclusion for those specific processes if needed.",
        "severity": "HIGH",
        "check_ps": (
            "$id='D4F940AB-401B-4EFC-AAD8-FD0B60B84F19';"
            " $p = Get-MpPreference -EA SilentlyContinue;"
            " if (-not $p) { 'WARN: Could not query Defender ASR status' }"
            " else { $idx = [array]::IndexOf($p.AttackSurfaceReductionRules_Ids, $id);"
            " if ($idx -lt 0 -or $p.AttackSurfaceReductionRules_Actions[$idx] -ne 1)"
            " { 'FAIL: ASR rule (block Office child processes) not enabled' } else { 'PASS' } }"
        ),
        "fix_ps": (
            "Add-MpPreference -AttackSurfaceReductionRules_Ids D4F940AB-401B-4EFC-AAD8-FD0B60B84F19"
            " -AttackSurfaceReductionRules_Actions Enabled; Write-Host 'ASR rule enabled.'"
        ),
        "fix_label": "Enable ASR Rule",
        "undo_ps": (
            "Add-MpPreference -AttackSurfaceReductionRules_Ids D4F940AB-401B-4EFC-AAD8-FD0B60B84F19"
            " -AttackSurfaceReductionRules_Actions Disabled; Write-Host 'ASR rule disabled.'"
        ),
        "undo_label": "Revert (Disable ASR Rule)",
    },
    {
        "id": "wdigest",
        "name": "WDigest Cleartext Credentials",
        "description": "WDigest can cache plaintext passwords in LSASS memory, extractable via Mimikatz-style tools.",
        "impact": "No functional loss for normal use — only legacy apps expecting WDigest auth (rare) are affected. Closes a plaintext-credential-theft path.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest'"
            " -Name UseLogonCredential -EA SilentlyContinue).UseLogonCredential;"
            " if ($v -eq 1) { 'FAIL: WDigest caches plaintext credentials in LSASS' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest'"
            " -Name UseLogonCredential -Value 0 -Force; Write-Host 'WDigest cleartext caching disabled.'"
        ),
        "fix_label": "Disable WDigest",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\WDigest'"
            " -Name UseLogonCredential -Value 1 -Force; Write-Host 'WDigest cleartext caching re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable WDigest)",
    },
    {
        "id": "lsa_protection",
        "name": "LSA Protection (RunAsPPL)",
        "description": "Without LSA Protection, unsigned tools can read LSASS memory and dump credentials.",
        "impact": "Blocks unsigned/untrusted drivers from reading LSASS memory. Requires a restart to take effect; may break older third-party security/AV drivers not signed for Protected Process Light.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RunAsPPL -EA SilentlyContinue).RunAsPPL;"
            " if ($v -ne 1) { 'FAIL: LSA Protection (RunAsPPL) not enabled' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RunAsPPL -Value 1 -Type DWord -Force; Write-Host 'LSA Protection enabled. Restart required.'"
        ),
        "fix_label": "Enable LSA Protection",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RunAsPPL -Value 0 -Type DWord -Force; Write-Host 'LSA Protection disabled. Restart required.'"
        ),
        "undo_label": "Revert (Disable LSA Protection)",
    },
    {
        "id": "print_spooler",
        "name": "Print Spooler Exposure",
        "description": "Print Spooler running unnecessarily widens the PrintNightmare-class (CVE-2021-34527 and successors) attack surface.",
        "impact": "Disables printing (local and network) from this machine entirely. Only safe on machines that don't need to print (servers, kiosks, workstations with no local printer use).",
        "severity": "MEDIUM",
        "check_ps": (
            "$s = Get-Service -Name Spooler -EA SilentlyContinue;"
            " if ($s -and $s.Status -eq 'Running') { 'WARN: Print Spooler running (PrintNightmare-class exposure if unpatched)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Stop-Service Spooler -Force -EA SilentlyContinue;"
            " Set-Service Spooler -StartupType Disabled; Write-Host 'Print Spooler disabled.'"
        ),
        "fix_label": "Disable Spooler",
        "undo_ps": (
            "Set-Service Spooler -StartupType Automatic;"
            " Start-Service Spooler -EA SilentlyContinue; Write-Host 'Print Spooler re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable Spooler)",
    },
    {
        "id": "smb_null_session",
        "name": "SMB Null Session / Anonymous Enumeration",
        "description": "Without RestrictAnonymous, unauthenticated users can enumerate account and share names over the network.",
        "impact": "Blocks anonymous enumeration of accounts/shares. Some legacy trust relationships or old NAS/backup agents relying on anonymous access may break.",
        "severity": "MEDIUM",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RestrictAnonymous -EA SilentlyContinue).RestrictAnonymous;"
            " if ($v -ne 1) { 'FAIL: Anonymous SAM/share enumeration not restricted' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RestrictAnonymous -Value 1 -Type DWord -Force; Write-Host 'Anonymous enumeration restricted.'"
        ),
        "fix_label": "Restrict Anonymous",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa'"
            " -Name RestrictAnonymous -Value 0 -Type DWord -Force; Write-Host 'Anonymous enumeration restriction removed.'"
        ),
        "undo_label": "Revert (Allow Anonymous)",
    },
    {
        "id": "cached_logons",
        "name": "Cached Domain Logon Count",
        "description": "High CachedLogonsCount stores many domain credential hashes locally for offline logon — a bigger offline-crack target if the disk is stolen.",
        "impact": "Laptops used away from the domain network can still log in with the last 4 cached credentials instead of 10. Users who haven't connected to the domain in a long time may need network/VPN access to log in sooner than before.",
        "severity": "MEDIUM",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " -Name CachedLogonsCount -EA SilentlyContinue).CachedLogonsCount;"
            " if ($v -eq $null) { 'WARN: CachedLogonsCount not set (default 10)' }"
            " elseif ([int]$v -gt 4) { \"WARN: CachedLogonsCount is $v (>4)\" } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " -Name CachedLogonsCount -Value '4' -Force; Write-Host 'CachedLogonsCount set to 4.'"
        ),
        "fix_label": "Set to 4",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " -Name CachedLogonsCount -Value '10' -Force; Write-Host 'CachedLogonsCount set to 10.'"
        ),
        "undo_label": "Revert (Set to 10)",
    },
    {
        "id": "unquoted_service_path",
        "name": "Unquoted Service Paths",
        "description": "A service path with spaces and no quotes lets a planted exe in a path gap run as SYSTEM (local privilege escalation).",
        "impact": "No automatic fix applied (blanket-editing service paths can break vendor updates). Opens Services console for manual review — flagged services need quotes added around their path in the registry ImagePath value.",
        "severity": "MEDIUM",
        "check_ps": (
            "$bad = Get-CimInstance Win32_Service -EA SilentlyContinue | Where-Object {"
            " $_.PathName -and $_.PathName -notmatch '^\"' -and $_.PathName -match ' ' -and"
            " $_.PathName -match '\\.exe' -and $_.PathName -notmatch '\\.exe\"?$' }"
            " | Select-Object -ExpandProperty Name;"
            " if ($bad) { \"WARN: Unquoted service paths: $($bad -join ', ')\" } else { 'PASS' }"
        ),
        "fix_ps": "Start-Process services.msc; Write-Host 'Services console opened for manual review.'",
        "fix_label": "Review Services",
    },
    {
        "id": "admin_shares",
        "name": "Default Admin Shares (C$/ADMIN$)",
        "description": "Hidden admin shares are recreated at every boot and are a common lateral-movement path for an attacker with local admin creds.",
        "impact": "Breaks remote admin tools that rely on these shares (some RMM/backup software, PsExec, remote MMC disk management) — verify no management tooling depends on them first. Requires a restart.",
        "severity": "MEDIUM",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters'"
            " -Name AutoShareWks -EA SilentlyContinue).AutoShareWks;"
            " if ($v -ne 0) { 'WARN: Default admin shares (C$/ADMIN$) enabled' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters'"
            " -Name AutoShareWks -Value 0 -Type DWord -Force; Write-Host 'Default admin shares disabled. Restart required.'"
        ),
        "fix_label": "Disable Admin Shares",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters'"
            " -Name AutoShareWks -Value 1 -Type DWord -Force; Write-Host 'Default admin shares re-enabled. Restart required.'"
        ),
        "undo_label": "Revert (Re-enable)",
    },
    {
        "id": "tls_weak_protocols",
        "name": "Weak TLS Protocols (SChannel)",
        "description": "TLS 1.0 left enabled allows downgrade attacks (POODLE-class) on inbound connections.",
        "impact": "May break very old clients, printers, or legacy line-of-business apps that only support TLS 1.0 — test critical integrations before deploying broadly. Requires a restart of dependent services.",
        "severity": "MEDIUM",
        "check_ps": (
            "$p = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.0\\Server';"
            " $v = (Get-ItemProperty $p -Name Enabled -EA SilentlyContinue).Enabled;"
            " if ($v -ne 0) { 'WARN: TLS 1.0 enabled (weak protocol, downgrade risk)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "$p = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.0\\Server';"
            " New-Item -Path $p -Force | Out-Null;"
            " Set-ItemProperty $p -Name Enabled -Value 0 -Type DWord -Force;"
            " Set-ItemProperty $p -Name DisabledByDefault -Value 1 -Type DWord -Force;"
            " Write-Host 'TLS 1.0 disabled. Restart required.'"
        ),
        "fix_label": "Disable TLS 1.0",
        "undo_ps": (
            "$p = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.0\\Server';"
            " Set-ItemProperty $p -Name Enabled -Value 1 -Type DWord -Force;"
            " Set-ItemProperty $p -Name DisabledByDefault -Value 0 -Type DWord -Force;"
            " Write-Host 'TLS 1.0 re-enabled. Restart required.'"
        ),
        "undo_label": "Revert (Re-enable TLS 1.0)",
    },
]


# ── Known-vulnerable / end-of-life software ───────────────────────────
# (display-name regex, minimum safe version or None for "any version is EOL", reason)
# Static list: review and extend periodically. Versions compare numerically.
KNOWN_VULNERABLE = [
    (r"Adobe Flash Player",                None,     "end-of-life since 2020"),
    (r"Adobe Shockwave",                   None,     "end-of-life since 2019"),
    (r"Microsoft Silverlight",             None,     "end-of-life since 2021"),
    (r"^QuickTime",                        None,     "end-of-life on Windows, unpatched CVEs"),
    (r"^Python 2\.\d",                     None,     "Python 2 end-of-life since 2020"),
    (r"^(Java|J2SE)(\(TM\))? ?(Runtime Environment )?(5|6|7)\b", None, "Java 5/6/7 end-of-life"),
    (r"^Adobe (Reader|Acrobat) (8|9|X|XI)\b", None,  "end-of-life Adobe Reader/Acrobat"),
    (r"^Microsoft Office\b(?!.*(Interop|Proofing|Language|Shared|Click-to-Run)).*\b(2007|2010|2013|2016|2019)\b",
                                           None,     "Office version past end of support"),
    (r"^WinRAR",                           "7.13",   "CVE-2025-8088 path traversal"),
    (r"^7-Zip",                            "25.01",  "CVE-2025-0411 / CVE-2025-55188"),
    (r"^PuTTY",                            "0.81",   "CVE-2024-31497 key recovery"),
]


def _ver_tuple(v):
    nums = [int(n) for n in re.findall(r"\d+", v or "")[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def _eval_vulnerable_software(out):
    apps = []
    for line in out.splitlines():
        if line.startswith("APP\t"):
            parts = line.split("\t")
            apps.append((parts[1].strip(), parts[2].strip() if len(parts) > 2 else ""))
    if not apps:
        return "UNKNOWN", "Could not read installed software list"
    hits = []
    for name, ver in apps:
        for pattern, min_ver, reason in KNOWN_VULNERABLE:
            if not re.search(pattern, name, re.IGNORECASE):
                continue
            if min_ver is None:
                hits.append(f"{name} ({reason})")
            elif ver and _ver_tuple(ver) < _ver_tuple(min_ver):
                hits.append(f"{name} {ver} (< {min_ver}, {reason})")
            break
    hits = sorted(set(hits))
    if hits:
        return "FAIL", "Vulnerable/EOL software: " + "; ".join(hits)
    return "PASS", f"{len(apps)} installed programs checked, none on the known-vulnerable list"


# ── Additional checks (open ports, services, tasks, software, drivers, accounts, ...) ──

CHECKS += [
    {
        "id": "open_ports",
        "name": "Open Listening Ports",
        "description": "Network-reachable listening ports for remote-access / database / legacy services widen the attack surface.",
        "impact": "No automatic change. Opens Windows Firewall (advanced) to block or scope the listed ports, or stop the service behind them.",
        "severity": "MEDIUM",
        "check_ps": r'''
$risky = @{21='FTP';23='Telnet';69='TFTP';1433='MSSQL';3306='MySQL';3389='RDP';5432='PostgreSQL';
           5800='VNC-HTTP';5900='VNC';5901='VNC';5985='WinRM';5986='WinRM-HTTPS';6379='Redis';27017='MongoDB'}
$l = Get-NetTCPConnection -State Listen -EA SilentlyContinue | Where-Object { $_.LocalAddress -notin '127.0.0.1','::1' }
$ports = @($l | ForEach-Object { [int]$_.LocalPort } | Sort-Object -Unique)
$hit = $ports | Where-Object { $risky.ContainsKey($_) } | ForEach-Object { "$_/$($risky[$_])" }
if (-not $l) { 'WARN: Could not enumerate listening ports' }
elseif ($hit) { "WARN: High-risk ports listening: $($hit -join ', ') ($($ports.Count) ports listening in total)" }
else { "PASS: $($ports.Count) ports listening, none high-risk" }
''',
        "fix_ps": "Start-Process wf.msc; Write-Host 'Windows Firewall (advanced) opened for review.'",
        "fix_label": "Review Firewall",
    },
    {
        "id": "shared_folders",
        "name": "Shared Folder Exposure",
        "description": "Custom SMB shares granting Everyone/Guest/Anonymous access expose data to anyone on the network.",
        "impact": "No automatic change. Opens Shared Folders console — tighten share permissions to specific groups. Users relying on open access will need to be granted it explicitly.",
        "severity": "HIGH",
        "check_ps": r'''
$sh = @(Get-SmbShare -EA SilentlyContinue | Where-Object { $_.Name -notmatch '^([A-Za-z]\$|ADMIN\$|IPC\$|print\$)$' })
if (-not $sh) { 'PASS: No custom shared folders' } else {
  $full = @(); $read = @()
  foreach ($s in $sh) {
    $a = Get-SmbShareAccess -Name $s.Name -EA SilentlyContinue |
         Where-Object { $_.AccountName -match 'Everyone|Guest|ANONYMOUS' -and "$($_.AccessControlType)" -eq 'Allow' }
    foreach ($x in $a) {
      if ("$($x.AccessRight)" -in 'Full','Change') { $full += "$($s.Name) [$($x.AccountName): $($x.AccessRight)]" }
      else { $read += "$($s.Name) [$($x.AccountName): $($x.AccessRight)]" } } }
  if ($full) { "FAIL: Shares writable by Everyone/Guest: $($full -join ', ')" }
  elseif ($read) { "WARN: Shares readable by Everyone/Guest: $($read -join ', ')" }
  else { "PASS: $($sh.Count) custom share(s), none open to Everyone/Guest: $($sh.Name -join ', ')" } }
''',
        "fix_ps": "Start-Process fsmgmt.msc; Write-Host 'Shared Folders console opened for review.'",
        "fix_label": "Review Shares",
    },
    {
        "id": "llmnr_netbios",
        "name": "LLMNR / NetBIOS Name Poisoning",
        "description": "LLMNR and NetBIOS-over-TCP broadcast name lookups let an attacker on the LAN answer them and capture NTLM hashes (Responder-style attacks).",
        "impact": "Hosts are then resolved only via DNS. Small networks with no DNS server that find PCs/NAS boxes by name may stop resolving them until DNS entries exist.",
        "severity": "HIGH",
        "check_ps": r'''
$ll = (Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -Name EnableMulticast -EA SilentlyContinue).EnableMulticast
$nb = @(Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces' -EA SilentlyContinue |
        Where-Object { (Get-ItemProperty $_.PSPath -Name NetbiosOptions -EA SilentlyContinue).NetbiosOptions -ne 2 })
$p = @()
if ($ll -ne 0) { $p += 'LLMNR enabled' }
if ($nb.Count) { $p += "NetBIOS over TCP enabled on $($nb.Count) interface(s)" }
if ($p) { "FAIL: $($p -join ', ') (credential capture risk)" } else { 'PASS' }
''',
        "fix_ps": r'''
$k = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient'
New-Item -Path $k -Force | Out-Null
Set-ItemProperty $k -Name EnableMulticast -Value 0 -Type DWord -Force
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces' |
  ForEach-Object { Set-ItemProperty $_.PSPath -Name NetbiosOptions -Value 2 -Type DWord -Force }
Write-Host 'LLMNR and NetBIOS over TCP disabled.'
''',
        "fix_label": "Disable LLMNR/NetBIOS",
        "undo_ps": r'''
Remove-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -Name EnableMulticast -EA SilentlyContinue
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces' |
  ForEach-Object { Set-ItemProperty $_.PSPath -Name NetbiosOptions -Value 0 -Type DWord -Force }
Write-Host 'LLMNR and NetBIOS restored to defaults.'
''',
        "undo_label": "Revert (Restore Defaults)",
    },
    {
        "id": "local_admins",
        "name": "Local Administrator Accounts",
        "description": "Every extra member of the local Administrators group is another account that can fully take over the machine.",
        "impact": "No automatic change. Opens Local Users and Groups — remove users who don't need admin rights. They will then need IT to install software or change system settings.",
        "severity": "HIGH",
        "check_ps": r'''
$m = @()
try { $m = @(Get-LocalGroupMember -SID 'S-1-5-32-544' -EA Stop | ForEach-Object { [pscustomobject]@{N=$_.Name; S="$($_.SID)"} }) }
catch { $m = @(net localgroup administrators 2>$null | Select-Object -Skip 6 |
          Where-Object { $_ -and $_ -notmatch 'command completed' } | ForEach-Object { [pscustomobject]@{N=$_.Trim(); S=''} }) }
if (-not $m) { 'WARN: Could not read Administrators group' } else {
  $extra = @($m | Where-Object { $_.S -notmatch '-500$' -and $_.N -notmatch '\\Domain Admins$' })
  $names = ($m.N) -join ', '
  if ($extra.Count -gt 1) { "WARN: $($extra.Count) non-built-in admin accounts: $names" } else { "PASS: Administrators: $names" } }
''',
        "fix_ps": "try { Start-Process lusrmgr.msc -EA Stop } catch { Start-Process netplwiz }; Write-Host 'Local Users and Groups opened.'",
        "fix_label": "Review Admins",
    },
    {
        "id": "laps",
        "name": "LAPS (Local Admin Password Rotation)",
        "description": "Without LAPS, the local admin password is usually identical across machines — one leaked password unlocks the whole fleet.",
        "impact": "Configured centrally (Group Policy or Intune), not on this machine. Once enabled, the local admin password is rotated and must be looked up in AD/Entra ID when needed.",
        "severity": "MEDIUM",
        "check_ps": r'''
$cs = Get-CimInstance Win32_ComputerSystem -EA SilentlyContinue
$aad = (dsregcmd /status 2>$null | Out-String) -match 'AzureAdJoined\s*:\s*YES'
if (-not $cs.PartOfDomain -and -not $aad) { 'PASS: Not applicable (not domain or Entra ID joined)' } else {
  $bd = $null
  foreach ($p in 'HKLM:\SOFTWARE\Microsoft\Policies\LAPS','HKLM:\SOFTWARE\Policies\Microsoft Windows\LAPS') {
    $v = (Get-ItemProperty $p -Name BackupDirectory -EA SilentlyContinue).BackupDirectory; if ($v) { $bd = $v } }
  $legacy = (Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft Services\AdmPwd' -Name AdmPwdEnabled -EA SilentlyContinue).AdmPwdEnabled -eq 1
  if ($bd -eq 1) { 'PASS: Windows LAPS backing up to Entra ID' }
  elseif ($bd -eq 2) { 'PASS: Windows LAPS backing up to Active Directory' }
  elseif ($legacy) { 'PASS: Legacy Microsoft LAPS enabled' }
  else { 'WARN: LAPS not configured (local admin password is not rotated)' } }
''',
    },
    {
        "id": "risky_services",
        "name": "Running Services Audit",
        "description": "Remote-access, discovery and legacy services that are running but rarely needed on a workstation.",
        "impact": "No automatic change. Opens Services — disable only services you have confirmed are unused (e.g. a TeamViewer/AnyDesk install may be IT's own remote-support tool).",
        "severity": "MEDIUM",
        "check_ps": r'''
$names = 'SNMP','SSDPSRV','upnphost','WinRM','FTPSVC','MSFTPSVC','TlntSvr','simptcp','W3SVC','sshd',
         'TeamViewer*','AnyDesk*','tvnserver','uvnc_service','vncserver*','winvnc*','ScreenConnect*','LogMeIn*','Splashtop*'
$run = @(Get-Service -EA SilentlyContinue | Where-Object { $_.Status -eq 'Running' } |
         Where-Object { $n = $_.Name; $names | Where-Object { $n -like $_ } } |
         ForEach-Object { "$($_.Name) ($($_.DisplayName))" })
if ($run) { "WARN: Review running services: $($run -join ', ')" } else { 'PASS: No high-risk services running' }
''',
        "fix_ps": "Start-Process services.msc; Write-Host 'Services console opened for review.'",
        "fix_label": "Review Services",
    },
    {
        "id": "scheduled_tasks",
        "name": "Suspicious Scheduled Tasks",
        "description": "Non-Microsoft scheduled tasks running unsigned programs from user-writable folders, or script-host/download one-liners, are a classic persistence technique.",
        "impact": "No automatic change. Opens Task Scheduler — disable or delete tasks you don't recognise after checking what installed them.",
        "severity": "MEDIUM",
        "check_ps": r'''
$rx = '(?i)-enc(odedcommand)?\s|mshta|downloadstring|downloadfile|iex\s*\(|invoke-expression|certutil.+urlcache|bitsadmin.+transfer|regsvr32.+/i:http|rundll32.+(http|javascript)'
$wr = '(?i)\\AppData\\|\\Temp\\|\\Users\\Public\\|\\ProgramData\\'
$sus = foreach ($t in Get-ScheduledTask -EA SilentlyContinue | Where-Object { $_.TaskPath -notlike '\Microsoft\*' -and "$($_.State)" -ne 'Disabled' }) {
  foreach ($a in $t.Actions) {
    if (-not $a.Execute) { continue }
    $exe = [Environment]::ExpandEnvironmentVariables($a.Execute.Trim('"'))
    $hit = "$exe $($a.Arguments)" -match $rx
    if (-not $hit -and $exe -match $wr) {
      $sig = Get-AuthenticodeSignature -FilePath $exe -EA SilentlyContinue
      $hit = (-not $sig) -or ("$($sig.Status)" -ne 'Valid') }
    if ($hit) { "$($t.TaskPath)$($t.TaskName)"; break } } }
$sus = @($sus | Sort-Object -Unique)
if ($sus) { "WARN: Suspicious scheduled tasks: $($sus -join ', ')" } else { 'PASS: No suspicious non-Microsoft scheduled tasks' }
''',
        "fix_ps": "Start-Process taskschd.msc; Write-Host 'Task Scheduler opened for review.'",
        "fix_label": "Review Tasks",
    },
    {
        "id": "vulnerable_software",
        "name": "Known-Vulnerable / EOL Software",
        "description": "Installed programs that are end-of-life or older than the first version fixing a known critical CVE (built-in list).",
        "impact": "No automatic change. Opens Programs and Features — update or uninstall the listed software. Removing EOL runtimes (Java 7, Python 2, Silverlight) can break old in-house apps that still depend on them.",
        "severity": "HIGH",
        "check_ps": r'''
$keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
Get-ItemProperty $keys -EA SilentlyContinue | Where-Object { $_.DisplayName } |
  ForEach-Object { "APP`t$($_.DisplayName)`t$($_.DisplayVersion)" }
''',
        "evaluate": _eval_vulnerable_software,
        "fix_ps": "Start-Process appwiz.cpl; Write-Host 'Programs and Features opened.'",
        "fix_label": "Open Programs",
    },
    {
        "id": "cert_expiry",
        "name": "Machine Certificate Expiry",
        "description": "Expired or soon-expiring machine certificates break Wi-Fi/VPN (802.1X) authentication and TLS services.",
        "impact": "No automatic change. Opens the machine certificate store — renew via auto-enrollment (gpupdate /force) or your CA. Expired certs can be removed once replaced.",
        "severity": "LOW",
        "check_ps": r'''
$now = Get-Date
$c = @(Get-ChildItem Cert:\LocalMachine\My -EA SilentlyContinue)
$fmt = { "$($_.GetNameInfo('SimpleName', $false)) ($($_.NotAfter.ToString('yyyy-MM-dd')))" }
$exp  = @($c | Where-Object { $_.NotAfter -lt $now } | ForEach-Object $fmt)
$soon = @($c | Where-Object { $_.NotAfter -ge $now -and $_.NotAfter -lt $now.AddDays(30) } | ForEach-Object $fmt)
$p = @()
if ($exp)  { $p += "Expired: $($exp -join ', ')" }
if ($soon) { $p += "Expiring within 30 days: $($soon -join ', ')" }
if ($p) { "WARN: $($p -join ' | ')" } else { "PASS: $($c.Count) machine certificate(s), none expiring within 30 days" }
''',
        "fix_ps": "Start-Process certlm.msc; Write-Host 'Machine certificate store opened.'",
        "fix_label": "Open Certificates",
    },
    {
        "id": "autorun",
        "name": "AutoRun on Removable Drives",
        "description": "AutoRun/AutoPlay launching content from USB drives and CDs is a classic malware-spread vector.",
        "impact": "Inserted USB drives and discs no longer launch anything automatically — users open them from File Explorer instead. No functional loss.",
        "severity": "MEDIUM",
        "check_ps": r'''
$v = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' -Name NoDriveTypeAutoRun -EA SilentlyContinue).NoDriveTypeAutoRun
if ($v -eq 255) { 'PASS' } else { 'WARN: AutoRun not disabled for all drive types' }
''',
        "fix_ps": r'''
$k = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer'
New-Item -Path $k -Force | Out-Null
Set-ItemProperty $k -Name NoDriveTypeAutoRun -Value 255 -Type DWord -Force
Write-Host 'AutoRun disabled for all drives.'
''',
        "fix_label": "Disable AutoRun",
        "undo_ps": r'''
Remove-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer' -Name NoDriveTypeAutoRun -EA SilentlyContinue
Write-Host 'AutoRun restored to Windows default.'
''',
        "undo_label": "Revert (Default)",
    },
    {
        "id": "secure_boot",
        "name": "Secure Boot / UEFI / TPM",
        "description": "Secure Boot blocks bootkits and unsigned boot loaders; a ready TPM is required for BitLocker and Windows 11 security features.",
        "impact": "Can't be changed from Windows: enable Secure Boot in the firmware (BIOS/UEFI) setup. Legacy-BIOS installs need disk conversion first (mbr2gpt) — back up before converting.",
        "severity": "HIGH",
        "check_ps": r'''
$sb = $null; $legacy = $false
try { $sb = Confirm-SecureBootUEFI -EA Stop }
catch [System.PlatformNotSupportedException] { $legacy = $true }
catch {
  # Not elevated / API unavailable: fall back to the registry
  $v = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled -EA SilentlyContinue).UEFISecureBootEnabled
  if ($v -eq 1) { $sb = $true } elseif ($v -eq 0) { $sb = $false } }
$tpm = 'TPM status unavailable'
try {
  $t = Get-Tpm -EA Stop
  $tpm = if ($t.TpmPresent) { if ($t.TpmReady) { 'TPM ready' } else { 'TPM present but not ready' } } else { 'no TPM detected' }
} catch { }
if ($legacy) { "FAIL: Legacy BIOS boot, Secure Boot unsupported ($tpm)" }
elseif ($sb -eq $true) {
  if ($tpm -in 'TPM ready','TPM status unavailable') { "PASS: Secure Boot on, $tpm" } else { "WARN: Secure Boot on, but $tpm" } }
elseif ($sb -eq $false) { "FAIL: UEFI system but Secure Boot is OFF ($tpm)" }
else { "WARN: Could not determine Secure Boot state ($tpm)" }
''',
        "fix_ps": "Start-Process msinfo32; Write-Host 'System Information opened (see BIOS Mode / Secure Boot State).'",
        "fix_label": "Open System Info",
    },
    {
        "id": "outdated_drivers",
        "name": "Driver Health / Outdated Drivers",
        "description": "Devices with driver errors, or third-party display/network/storage drivers more than 4 years old, often carry unpatched vulnerabilities.",
        "impact": "No automatic change. Opens Device Manager — update drivers from the hardware vendor. New drivers occasionally cause regressions; update one device at a time.",
        "severity": "LOW",
        "check_ps": r'''
$cut = (Get-Date).AddYears(-4)
$old = @(Get-CimInstance Win32_PnPSignedDriver -EA SilentlyContinue |
  Where-Object { $_.DriverDate -and $_.DriverDate -lt $cut -and $_.DriverDate.Year -gt 2005 -and
                 $_.DriverProviderName -notmatch 'Microsoft' -and $_.DeviceClass -in 'DISPLAY','NET','BLUETOOTH','SCSIADAPTER','HDC' } |
  ForEach-Object { "$($_.DeviceName) ($($_.DriverDate.ToString('yyyy-MM')))" } | Sort-Object -Unique)
$bad = @(Get-CimInstance Win32_PnPEntity -EA SilentlyContinue |
  Where-Object { $_.ConfigManagerErrorCode -and $_.ConfigManagerErrorCode -notin 22,45 } |
  ForEach-Object { "$($_.Name) (code $($_.ConfigManagerErrorCode))" })
function Short($a) { if ($a.Count -gt 5) { ($a[0..4] -join ', ') + " (+$($a.Count - 5) more)" } else { $a -join ', ' } }
$p = @()
if ($bad) { $p += "Driver errors: $(Short $bad)" }
if ($old) { $p += "Drivers older than 4 years: $(Short $old)" }
if ($p) { "WARN: $($p -join ' | ')" } else { 'PASS: No driver errors or old third-party drivers' }
''',
        "fix_ps": "Start-Process devmgmt.msc; Write-Host 'Device Manager opened.'",
        "fix_label": "Open Device Manager",
    },
    {
        "id": "usb_storage",
        "name": "USB Mass Storage Policy",
        "description": "Unrestricted USB storage allows data to be copied off the machine and malware to be carried in.",
        "impact": "Blocks USB flash drives and external disks entirely (keyboards, mice, printers, webcams keep working). Users who move files by USB will need another route (network share, OneDrive).",
        "severity": "LOW",
        "check_ps": r'''
$s = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' -Name Start -EA SilentlyContinue).Start
$d = (Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices' -Name Deny_All -EA SilentlyContinue).Deny_All
if ($s -eq 4 -or $d -eq 1) { 'PASS: USB mass storage blocked' } else { 'WARN: USB mass storage allowed' }
''',
        "fix_ps": "Set-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\USBSTOR' -Name Start -Value 4 -Type DWord -Force; Write-Host 'USB mass storage blocked.'",
        "fix_label": "Block USB Storage",
        "undo_ps": "Set-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\USBSTOR' -Name Start -Value 3 -Type DWord -Force; Write-Host 'USB mass storage allowed.'",
        "undo_label": "Revert (Allow USB Storage)",
    },
]


# ── Categories, disruptive fixes, scoring ─────────────────────────────

CATEGORIES = ["Network", "Accounts", "System", "Policy", "Hardware"]

_CATEGORY_OF = {
    "Network":  ["firewall", "rdp", "rdp_nla", "smb1", "smb_signing", "smb_null_session",
                 "admin_shares", "tls_weak_protocols", "open_ports", "shared_folders", "llmnr_netbios"],
    "Accounts": ["guest", "autologon", "wdigest", "lsa_protection", "local_admins", "laps"],
    "System":   ["defender", "uac", "windows_updates", "remote_registry", "telnet", "print_spooler",
                 "unquoted_service_path", "risky_services", "scheduled_tasks", "vulnerable_software", "cert_expiry"],
    "Policy":   ["password_policy", "cached_logons", "asr_office", "autorun"],
    "Hardware": ["bitlocker", "secure_boot", "outdated_drivers", "usb_storage"],
}

# Fixes that can interrupt how people work — left unticked by default in "Fix All".
DISRUPTIVE = {"rdp", "print_spooler", "admin_shares", "usb_storage", "tls_weak_protocols",
              "cached_logons", "smb1", "llmnr_netbios"}

for _cat, _ids in _CATEGORY_OF.items():
    for _id in _ids:
        next(c for c in CHECKS if c["id"] == _id)["category"] = _cat
for _c in CHECKS:
    assert "category" in _c, f"security check {_c['id']} has no category"
    _c["disruptive"] = _c["id"] in DISRUPTIVE

CHECKS_BY_ID = {c["id"]: c for c in CHECKS}

SEVERITIES = ["HIGH", "MEDIUM", "LOW"]
STATUS_ORDER = {"FAIL": 0, "WARN": 1, "UNKNOWN": 2, "PASS": 3}

# Penalty points per (severity, status) used for the 0-100 security score.
_PENALTY = {
    ("HIGH", "FAIL"): 10, ("HIGH", "WARN"): 6,
    ("MEDIUM", "FAIL"): 5, ("MEDIUM", "WARN"): 3,
    ("LOW", "FAIL"): 2, ("LOW", "WARN"): 1,
}

RISK_LEVELS = ["CLEAN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def is_auto_fixable(check):
    """A fix is applied by "Fix All" only if it changes a setting and can be reverted."""
    return bool(check.get("fix_ps") and check.get("undo_ps"))


def parse_result(out):
    lines = [ln.strip() for ln in (out or "").strip().splitlines() if ln.strip()]
    line = next((ln for ln in lines if not ln.startswith("ERR:")), lines[0] if lines else "")
    for prefix in ("FAIL:", "WARN:", "PASS:"):
        if line.upper().startswith(prefix):
            return prefix.rstrip(":"), line[len(prefix):].strip()
    if line.upper() == "PASS":
        return "PASS", ""
    return "UNKNOWN", line


def evaluate(check, out):
    """Turn a check's raw PowerShell output into (status, detail)."""
    if check.get("evaluate"):
        try:
            return check["evaluate"](out)
        except Exception as e:  # never let one bad parser break the scan
            return "UNKNOWN", f"Could not evaluate result: {e}"
    return parse_result(out)


def risk_summary(results):
    """results: {id: (status, detail)} → dict with counts, score (0-100) and level."""
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "UNKNOWN": 0}
    high_fail = penalty = max_penalty = 0
    for check in CHECKS:
        status = results.get(check["id"], ("UNKNOWN", ""))[0]
        counts[status] = counts.get(status, 0) + 1
        max_penalty += _PENALTY[(check["severity"], "FAIL")]
        penalty += _PENALTY.get((check["severity"], status), 0)
        if check["severity"] == "HIGH" and status == "FAIL":
            high_fail += 1

    medium_fail = sum(1 for c in CHECKS if c["severity"] == "MEDIUM"
                      and results.get(c["id"], ("",))[0] == "FAIL")
    high_warn = sum(1 for c in CHECKS if c["severity"] == "HIGH"
                    and results.get(c["id"], ("",))[0] == "WARN")

    if high_fail >= 3:
        level = "CRITICAL"
    elif high_fail:
        level = "HIGH"
    elif medium_fail or high_warn:
        level = "MEDIUM"
    elif counts["FAIL"] or counts["WARN"]:
        level = "LOW"
    else:
        level = "CLEAN"

    score = round(100 * (1 - penalty / max_penalty)) if max_penalty else 100
    return {"counts": counts, "score": score, "level": level, "high_fail": high_fail}
