import customtkinter as ctk
import threading
from modules.runner import run_inline_powershell
from modules.logger import log


SECTIONS = [
    {
        "title": "User / AppData",
        "locations": [
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
                "id": "electron_cache",
                "label": "Electron App Caches  (auto-discover)",
                "default": False,
                "size_ps": (
                    "$total=0;"
                    " $skip=@('Microsoft','Packages','Temp','Programs','Google','Mozilla',"
                    "'ConnectedDevicesPlatform','D3DSCache','CrashDumps','npm-cache','pip',"
                    "'Package Cache','NVIDIA','Adobe','BraveSoftware','Vivaldi','Opera Software');"
                    " $csubs=@('Cache','Code Cache','GPUCache','DawnCache','DawnGraphiteCache','DawnWebGPUCache','Service Worker\\ScriptCache');"
                    " foreach ($root in @($env:LOCALAPPDATA,$env:APPDATA)) {"
                    " if (-not (Test-Path $root)) { continue };"
                    " Get-ChildItem $root -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $skip -notcontains $_.Name } | ForEach-Object {"
                    " foreach ($s in $csubs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz -gt 1048576) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$skip=@('Microsoft','Packages','Temp','Programs','Google','Mozilla',"
                    "'ConnectedDevicesPlatform','D3DSCache','CrashDumps','npm-cache','pip',"
                    "'Package Cache','NVIDIA','Adobe','BraveSoftware','Vivaldi','Opera Software');"
                    " $csubs=@('Cache','Code Cache','GPUCache','DawnCache','DawnGraphiteCache','DawnWebGPUCache','Service Worker\\ScriptCache');"
                    " foreach ($root in @($env:LOCALAPPDATA,$env:APPDATA)) {"
                    " if (-not (Test-Path $root)) { continue };"
                    " Get-ChildItem $root -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $skip -notcontains $_.Name } | ForEach-Object {"
                    " foreach ($s in $csubs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Electron app caches cleaned.'"
                ),
            },
            {
                "id": "squirrel_old",
                "label": "Old App Versions  (Squirrel / auto-updater)",
                "default": False,
                "size_ps": (
                    "$total=0;"
                    " if (Test-Path $env:LOCALAPPDATA) {"
                    " Get-ChildItem $env:LOCALAPPDATA -Directory -Force -EA SilentlyContinue | ForEach-Object {"
                    " $app=$_;"
                    " $vers=Get-ChildItem $app.FullName -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^app-(\\d+(?:\\.\\d+)+)' };"
                    " if ($vers.Count -gt 1) {"
                    " $newest=($vers | Sort-Object {"
                    " try{[Version]([regex]::Match($_.Name,'app-(\\d+(?:\\.\\d+)+)').Groups[1].Value)}"
                    " catch{[Version]'0.0'}} -Descending)[0];"
                    " $vers | Where-Object { $_.FullName -ne $newest.FullName } | ForEach-Object {"
                    " $sz=(Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "if (Test-Path $env:LOCALAPPDATA) {"
                    " Get-ChildItem $env:LOCALAPPDATA -Directory -Force -EA SilentlyContinue | ForEach-Object {"
                    " $app=$_;"
                    " $vers=Get-ChildItem $app.FullName -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^app-(\\d+(?:\\.\\d+)+)' };"
                    " if ($vers.Count -gt 1) {"
                    " $newest=($vers | Sort-Object {"
                    " try{[Version]([regex]::Match($_.Name,'app-(\\d+(?:\\.\\d+)+)').Groups[1].Value)}"
                    " catch{[Version]'0.0'}} -Descending)[0];"
                    " $vers | Where-Object { $_.FullName -ne $newest.FullName } | ForEach-Object {"
                    " Remove-Item $_.FullName -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Old app versions cleaned.'"
                ),
            },
            {
                "id": "pkg_cache",
                "label": "Package Manager Caches  (npm / npx / pip / yarn / NuGet / cargo)",
                "default": False,
                "size_ps": (
                    "$la=$env:LOCALAPPDATA; $up=$env:USERPROFILE; $total=0;"
                    " foreach ($p in @(\"$la\\npm-cache\\_cacache\",\"$la\\npm-cache\\_npx\","
                    "\"$la\\pip\\cache\","
                    "\"$up\\.nuget\\packages\\.cache\",\"$la\\Yarn\\Cache\","
                    "\"$up\\.cargo\\registry\\cache\",\"$up\\.gradle\\caches\")) {"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$la=$env:LOCALAPPDATA; $up=$env:USERPROFILE;"
                    " foreach ($p in @(\"$la\\npm-cache\\_cacache\",\"$la\\npm-cache\\_npx\","
                    "\"$la\\pip\\cache\","
                    "\"$up\\.nuget\\packages\\.cache\",\"$la\\Yarn\\Cache\","
                    "\"$up\\.cargo\\registry\\cache\",\"$up\\.gradle\\caches\")) {"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Package manager caches cleaned.'"
                ),
            },
            {
                "id": "chrome_cache",
                "label": "Chrome Cache  (Cache + Code Cache + GPU)",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Google\\Chrome\\User Data\"; $total=0;"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Google\\Chrome\\User Data\";"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Chrome cache cleaned.'"
                ),
            },
            {
                "id": "edge_cache",
                "label": "Edge Cache  (Cache + Code Cache + GPU)",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\"; $total=0;"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Microsoft\\Edge\\User Data\";"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Edge cache cleaned.'"
                ),
            },
            {
                "id": "firefox_cache",
                "label": "Firefox Cache",
                "default": False,
                "size_ps": (
                    "$total=0; $subs=@('cache2','startupCache','thumbnails');"
                    " foreach ($ffdir in @(\"$env:APPDATA\\Mozilla\\Firefox\\Profiles\","
                    "\"$env:LOCALAPPDATA\\Mozilla\\Firefox\\Profiles\")) {"
                    " if (Test-Path $ffdir) {"
                    " Get-ChildItem $ffdir -Directory -Force -EA SilentlyContinue | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$subs=@('cache2','startupCache','thumbnails');"
                    " foreach ($ffdir in @(\"$env:APPDATA\\Mozilla\\Firefox\\Profiles\","
                    "\"$env:LOCALAPPDATA\\Mozilla\\Firefox\\Profiles\")) {"
                    " if (Test-Path $ffdir) {"
                    " Get-ChildItem $ffdir -Directory -Force -EA SilentlyContinue | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } } };"
                    " Write-Host 'Firefox cache cleaned.'"
                ),
            },
            {
                "id": "brave_cache",
                "label": "Brave Cache",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\BraveSoftware\\Brave-Browser\\User Data\"; $total=0;"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\BraveSoftware\\Brave-Browser\\User Data\";"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Brave cache cleaned.'"
                ),
            },
            {
                "id": "vivaldi_cache",
                "label": "Vivaldi Cache",
                "default": False,
                "size_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Vivaldi\\User Data\"; $total=0;"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$b=\"$env:LOCALAPPDATA\\Vivaldi\\User Data\";"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " Get-ChildItem $b -Directory -Force -EA SilentlyContinue"
                    " | Where-Object { $_.Name -match '^(Default|Profile \\d+|Guest Profile)$' }"
                    " | ForEach-Object {"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $_.FullName $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } } };"
                    " Write-Host 'Vivaldi cache cleaned.'"
                ),
            },
            {
                "id": "opera_cache",
                "label": "Opera Cache",
                "default": False,
                "size_ps": (
                    "$b=\"$env:APPDATA\\Opera Software\\Opera Stable\"; $total=0;"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $b $s;"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$b=\"$env:APPDATA\\Opera Software\\Opera Stable\";"
                    " if (Test-Path $b) {"
                    " $subs=@('Cache','Code Cache','GPUCache','Service Worker\\CacheStorage');"
                    " foreach ($s in $subs) {"
                    " $p=Join-Path $b $s;"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } } };"
                    " Write-Host 'Opera cache cleaned.'"
                ),
            },
            {
                "id": "outlook_logs",
                "label": "Outlook Logging & Diagnostics  (%TEMP%\\Outlook Logging)",
                "default": False,
                "size_ps": (
                    "$total=0;"
                    " foreach ($p in @(\"$env:TEMP\\Outlook Logging\",\"$env:TEMP\\Diagnostics\")) {"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "foreach ($p in @(\"$env:TEMP\\Outlook Logging\",\"$env:TEMP\\Diagnostics\")) {"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'Outlook logging and diagnostics cleaned.'"
                ),
            },
            {
                "id": "user_crash",
                "label": "Crash Dumps & WER  (user)",
                "default": False,
                "size_ps": (
                    "$la=$env:LOCALAPPDATA; $total=0;"
                    " foreach ($p in @(\"$la\\CrashDumps\",\"$la\\Microsoft\\Windows\\WER\","
                    "\"$la\\Microsoft\\Windows\\INetCache\")) {"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { $total+=$sz } } };"
                    " [int64]$total"
                ),
                "clean_ps": (
                    "$la=$env:LOCALAPPDATA;"
                    " foreach ($p in @(\"$la\\CrashDumps\",\"$la\\Microsoft\\Windows\\WER\","
                    "\"$la\\Microsoft\\Windows\\INetCache\")) {"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue } };"
                    " Write-Host 'User crash dumps and WER cleaned.'"
                ),
            },
        ],
    },
    {
        "title": "Windows / System  (requires admin)",
        "locations": [
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
                "id": "wu_cache",
                "label": "Windows Update Cache  (SoftwareDistribution\\Download)",
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
                "id": "delivery_opt",
                "label": "Delivery Optimization Cache",
                "default": False,
                "size_ps": (
                    "$p='C:\\Windows\\SoftwareDistribution\\DeliveryOptimization\\Cache';"
                    " if (Test-Path $p) {"
                    " $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
                    " if ($sz) { [int64]$sz } else { 0 } } else { 0 }"
                ),
                "clean_ps": (
                    "$p='C:\\Windows\\SoftwareDistribution\\DeliveryOptimization\\Cache';"
                    " if (Test-Path $p) { Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue };"
                    " Write-Host 'Delivery Optimization cache cleared.'"
                ),
            },
            {
                "id": "wer",
                "label": "Windows Error Reports  (ProgramData)",
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
        ],
    },
    {
        "title": "Other",
        "locations": [
            {
                "id": "recycle",
                "label": "Recycle Bin  (all drives)",
                "default": True,
                "size_ps": (
                    "$s=(Get-ChildItem 'C:\\$Recycle.Bin' -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                ),
                "clean_ps": (
                    "Clear-RecycleBin -Force -EA SilentlyContinue;"
                    " Write-Host 'Recycle Bin emptied.'"
                ),
            },
        ],
    },
]


def _all_locations():
    return [loc for sec in SECTIONS for loc in sec["locations"]]


def _fmt_size(n):
    if n is None:
        return "---"
    for unit, div in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


_PROFILE_LIST_PS = (
    "$loggedIn=@{};"
    " try { Get-WmiObject Win32_LoggedOnUser -EA SilentlyContinue | ForEach-Object {"
    "   if ($_.Antecedent -match 'Name=\"([^\"]+)\"') {"
    "     $loggedIn[$Matches[1].ToLower()]=1 } } } catch {};"
    " Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList\\*'"
    " -EA SilentlyContinue"
    " | Where-Object { $_.ProfileImagePath -match 'C:\\\\Users\\\\'"
    "   -and $_.ProfileImagePath -notmatch 'systemprofile|LocalService|NetworkService|Default' }"
    " | ForEach-Object {"
    "   $path=$_.ProfileImagePath; $name=Split-Path $path -Leaf;"
    "   $last=if(Test-Path $path){"
    "     (Get-Item $path -Force -EA SilentlyContinue).LastWriteTime.ToString('yyyy-MM-dd HH:mm')"
    "   }else{'N/A'};"
    "   $active=if($loggedIn.ContainsKey($name.ToLower())){'1'}else{'0'};"
    "   Write-Output \"$name|$path|$last|$active\" }"
)


def _profile_size_ps(profile_path):
    p = profile_path.replace("'", "''")
    return (
        f"$root='{p}';"
        " $total=0;"
        " $targets=@('AppData\\Local\\Temp',"
        " 'AppData\\Local\\Microsoft\\Windows\\INetCache',"
        " 'AppData\\Local\\CrashDumps',"
        " 'AppData\\Roaming\\Microsoft\\Windows\\Recent');"
        " foreach($t in $targets){"
        "   $p=Join-Path $root $t;"
        "   if(Test-Path $p){"
        "     $sz=(Get-ChildItem $p -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum;"
        "     if($sz){$total+=$sz}"
        "   }"
        " };"
        " [int64]$total"
    )


def _profile_clean_ps(profile_path, name):
    p = profile_path.replace("'", "''")
    n = name.replace("'", "''")
    return (
        f"$root='{p}';"
        " $targets=@('AppData\\Local\\Temp',"
        " 'AppData\\Local\\Microsoft\\Windows\\INetCache',"
        " 'AppData\\Local\\CrashDumps',"
        " 'AppData\\Roaming\\Microsoft\\Windows\\Recent');"
        " foreach($t in $targets){"
        "   $p=Join-Path $root $t;"
        "   if(Test-Path $p){Remove-Item \"$p\\*\" -Recurse -Force -EA SilentlyContinue}"
        " };"
        f" Write-Host 'AppData cleaned for {n}.'"
    )


class CleanupTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._vars = {}
        self._size_labels = {}
        self._sizes = {loc["id"]: None for loc in _all_locations()}
        self._profile_data = []
        self._profile_sizes = {}
        self._profile_vars = {}
        self._profile_size_labels = {}
        self._profile_list_frame = None
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        # ── Header card ────────────────────────────────────────────
        hdr_card = ctk.CTkFrame(wrap)
        hdr_card.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        hdr_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr_card, text="Temp File & Cache Cleaner",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(12, 6), sticky="w")

        btn_row = ctk.CTkFrame(hdr_card, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="w")

        self._scan_btn = ctk.CTkButton(btn_row, text="Scan Sizes", width=110,
                                       command=self._scan)
        self._scan_btn.grid(row=0, column=0, padx=(4, 6))

        self._clean_btn = ctk.CTkButton(btn_row, text="Clean Selected", width=120,
                                        fg_color="#c0392b", hover_color="#922b21",
                                        command=self._clean)
        self._clean_btn.grid(row=0, column=1, padx=6)

        ctk.CTkButton(btn_row, text="All", width=55,
                      command=self._select_all).grid(row=0, column=2, padx=6)
        ctk.CTkButton(btn_row, text="None", width=55,
                      command=self._select_none).grid(row=0, column=3, padx=6)

        self._total_label = ctk.CTkLabel(hdr_card, text="Total selected: ---",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self._total_label.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="w")

        # ── Profile AppData card ───────────────────────────────────
        self._build_profile_card(wrap, row=1)

        # ── Section cards ──────────────────────────────────────────
        for sec_idx, sec in enumerate(SECTIONS):
            sec_card = ctk.CTkFrame(wrap)
            sec_card.grid(row=sec_idx + 2, column=0, padx=10, pady=4, sticky="ew")
            sec_card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(sec_card, text=sec["title"],
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=("gray30", "gray70")).grid(
                row=0, column=0, columnspan=2, padx=14, pady=(10, 4), sticky="w")

            for i, loc in enumerate(sec["locations"]):
                var = ctk.BooleanVar(value=loc["default"])
                var.trace_add("write", lambda *a: self._update_total())
                self._vars[loc["id"]] = var

                cb = ctk.CTkCheckBox(sec_card, text=loc["label"], variable=var,
                                     font=ctk.CTkFont(size=12))
                cb.grid(row=i + 1, column=0, padx=(14, 6), pady=4, sticky="w")

                size_lbl = ctk.CTkLabel(sec_card, text="---",
                                        text_color="gray", font=ctk.CTkFont(size=11))
                size_lbl.grid(row=i + 1, column=1, padx=(0, 14), pady=4, sticky="e")
                self._size_labels[loc["id"]] = size_lbl

        # ── Output ─────────────────────────────────────────────────
        out_row = len(SECTIONS) + 2
        ctk.CTkLabel(wrap, text="Output",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=out_row, column=0, padx=10, pady=(8, 2), sticky="w")

        self._output = ctk.CTkTextbox(wrap, height=160, state="disabled",
                                      font=ctk.CTkFont(family="Courier New", size=11))
        self._output.grid(row=out_row + 1, column=0, padx=10, pady=(0, 10), sticky="ew")

        self._update_total()

    # ── Helpers ────────────────────────────────────────────────────

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
        for loc in _all_locations():
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

    # ── Scan ───────────────────────────────────────────────────────

    def _scan(self):
        if self._running:
            return
        self._running = True
        self._set_btn_state(False)
        self._append("\nScanning sizes...")
        log("Cleanup: scan started")

        def task():
            for loc in _all_locations():
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

    # ── Clean ──────────────────────────────────────────────────────

    def _clean(self):
        if self._running:
            return
        selected = [loc for loc in _all_locations() if self._vars[loc["id"]].get()]
        if not selected:
            self._append("No locations selected.")
            return

        self._running = True
        self._set_btn_state(False)
        total_before = sum(self._sizes[loc["id"]] or 0 for loc in selected)
        self._append(f"\nCleaning {len(selected)} location(s)...")
        log(f"Cleanup: clean {[l['id'] for l in selected]}")

        def task():
            for loc in selected:
                self._safe_append(f"\n  >>> {loc['label']}")
                rc, out = run_inline_powershell(loc["clean_ps"], callback=self._safe_append)
                if rc != 0:
                    self._safe_append(f"  [WARN] exit {rc}")
                log(f"Cleanup: {loc['id']} rc={rc}")

            self._safe_append("\nRescanning freed space...")
            total_after = 0
            for loc in selected:
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

    # ── Profile AppData card ───────────────────────────────────────

    def _build_profile_card(self, wrap, row):
        import tkinter.messagebox as _msgbox
        self._msgbox = _msgbox

        card = ctk.CTkFrame(wrap)
        card.grid(row=row, column=0, padx=10, pady=4, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Other-Profile AppData Cleaner  (admin)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=("gray30", "gray70")).grid(
            row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=10, pady=(0, 4), sticky="w")

        ctk.CTkButton(btn_row, text="Refresh Profiles", width=130,
                      command=self._refresh_profiles).grid(row=0, column=0, padx=(4, 6))
        self._prof_scan_btn = ctk.CTkButton(btn_row, text="Scan Sizes", width=100,
                                             command=self._scan_profiles)
        self._prof_scan_btn.grid(row=0, column=1, padx=6)
        self._prof_clean_btn = ctk.CTkButton(btn_row, text="Clean Selected", width=120,
                                              fg_color="#c0392b", hover_color="#922b21",
                                              command=self._clean_profiles)
        self._prof_clean_btn.grid(row=0, column=2, padx=6)

        self._profile_list_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._profile_list_frame.grid(row=2, column=0, padx=10, pady=(4, 10), sticky="ew")
        self._profile_list_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._profile_list_frame, text='Click "Refresh Profiles" to load.',
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=0, column=0, columnspan=4, padx=4, pady=4, sticky="w")

    def _refresh_profiles(self):
        if self._running:
            return
        self._running = True
        self._append("\nLoading user profiles...")

        def task():
            rc, out = run_inline_powershell(_PROFILE_LIST_PS)
            profiles = []
            for line in out.splitlines():
                line = line.strip()
                if '|' not in line:
                    continue
                parts = line.split('|', 3)
                if len(parts) == 4:
                    profiles.append({
                        'name': parts[0],
                        'path': parts[1],
                        'last_login': parts[2],
                        'active': parts[3] == '1',
                    })
            self._profile_data = profiles
            self._profile_sizes = {p['name']: None for p in profiles}
            self.after(0, self._rebuild_profile_rows)
            self._safe_append(f"Found {len(profiles)} profile(s).")
            self._running = False

        threading.Thread(target=task, daemon=True).start()

    def _rebuild_profile_rows(self):
        if self._profile_list_frame is None:
            return
        for w in self._profile_list_frame.winfo_children():
            w.destroy()
        self._profile_vars = {}
        self._profile_size_labels = {}

        if not self._profile_data:
            ctk.CTkLabel(self._profile_list_frame, text="No user profiles found.",
                         text_color="gray").grid(row=0, column=0, padx=4, pady=4, sticky="w")
            return

        self._profile_list_frame.grid_columnconfigure(0, weight=0)
        self._profile_list_frame.grid_columnconfigure(1, weight=0)
        self._profile_list_frame.grid_columnconfigure(2, weight=1)
        self._profile_list_frame.grid_columnconfigure(3, weight=0)

        for i, prof in enumerate(self._profile_data):
            var = ctk.BooleanVar(value=False)
            self._profile_vars[prof['name']] = var

            label_text = f"{prof['name']}    Last: {prof['last_login']}"
            cb = ctk.CTkCheckBox(self._profile_list_frame, text=label_text, variable=var,
                                 font=ctk.CTkFont(size=12))
            cb.grid(row=i, column=0, padx=(4, 8), pady=3, sticky="w")

            if prof['active']:
                ctk.CTkLabel(self._profile_list_frame, text="ACTIVE",
                             text_color="#e74c3c",
                             font=ctk.CTkFont(size=11, weight="bold")).grid(
                    row=i, column=1, padx=(0, 12), pady=3, sticky="w")

            size_lbl = ctk.CTkLabel(self._profile_list_frame, text="---",
                                    text_color="gray", font=ctk.CTkFont(size=11))
            size_lbl.grid(row=i, column=3, padx=(0, 14), pady=3, sticky="e")
            self._profile_size_labels[prof['name']] = size_lbl

    def _scan_profiles(self):
        if self._running or not self._profile_data:
            return
        self._running = True
        self._append("\nScanning profile AppData sizes...")

        def task():
            for prof in self._profile_data:
                rc, out = run_inline_powershell(_profile_size_ps(prof['path']))
                try:
                    val = int([l for l in out.splitlines() if l.strip()][-1])
                except (ValueError, IndexError):
                    val = 0
                self._profile_sizes[prof['name']] = val
                lbl = self._profile_size_labels.get(prof['name'])
                if lbl:
                    color = ("#1a1a1a", "white") if val > 0 else "gray"
                    self.after(0, lbl.configure, {"text": _fmt_size(val), "text_color": color})
            self._safe_append("Profile scan complete.")
            self._running = False

        threading.Thread(target=task, daemon=True).start()

    def _clean_profiles(self):
        if self._running:
            return
        selected = [p for p in self._profile_data
                    if self._profile_vars.get(p['name'], ctk.BooleanVar()).get()]
        if not selected:
            self._append("No profiles selected.")
            return

        active_sel = [p for p in selected if p['active']]
        if active_sel:
            names = ', '.join(p['name'] for p in active_sel)
            proceed = self._msgbox.askyesno(
                "Active Profile Warning",
                f"Profile(s) currently active:\n  {names}\n\n"
                "Cleaning an active profile's AppData may cause app instability.\n\n"
                "Proceed anyway?"
            )
            if not proceed:
                return

        self._running = True
        self._set_btn_state(False)
        self._append(f"\nCleaning AppData for {len(selected)} profile(s)...")
        log(f"Cleanup: profile AppData clean {[p['name'] for p in selected]}")

        def task():
            for prof in selected:
                self._safe_append(f"\n  >>> {prof['name']}  ({prof['path']})")
                rc, out = run_inline_powershell(
                    _profile_clean_ps(prof['path'], prof['name']),
                    callback=self._safe_append
                )
                if rc != 0:
                    self._safe_append(f"  [WARN] exit {rc}")
                log(f"Cleanup: profile {prof['name']} rc={rc}")

            self._safe_append("\nRescanning...")
            for prof in selected:
                rc, out = run_inline_powershell(_profile_size_ps(prof['path']))
                try:
                    val = int([l for l in out.splitlines() if l.strip()][-1])
                except (ValueError, IndexError):
                    val = 0
                self._profile_sizes[prof['name']] = val
                lbl = self._profile_size_labels.get(prof['name'])
                if lbl:
                    color = ("#1a1a1a", "white") if val > 0 else "gray"
                    self.after(0, lbl.configure, {"text": _fmt_size(val), "text_color": color})

            self._safe_append("\nProfile cleanup done.")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()
