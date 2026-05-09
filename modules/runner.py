"""Utility to run PowerShell scripts and winget commands."""
import subprocess
import os
import shutil
import tempfile
from modules.paths import get_base_dir

SCRIPTS_DIR = os.path.join(get_base_dir(), "scripts")


def _local_script_path(script_path: str):
    """Return (path, is_temp). Copies to local temp if path is UNC — PowerShell -File rejects UNC paths."""
    if script_path.startswith('\\\\'):
        tmp = tempfile.NamedTemporaryFile(suffix='.ps1', delete=False)
        tmp.close()
        shutil.copy2(script_path, tmp.name)
        return tmp.name, True
    return script_path, False


def run_powershell(script_name: str, args: list = None, callback=None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    local_path, is_temp = _local_script_path(script_path)
    try:
        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", local_path]
        if args:
            cmd.extend(args)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                if callback:
                    callback(line)
        process.wait()
        return process.returncode, "\n".join(output_lines)
    finally:
        if is_temp:
            os.unlink(local_path)


def run_winget(winget_id: str, callback=None, process_holder: list = None):
    cmd = ["winget", "install", "--id", winget_id, "--silent",
           "--accept-package-agreements", "--accept-source-agreements",
           "--disable-interactivity"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    if process_holder is not None:
        process_holder.append(process)
    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)
    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_winget_uninstall(winget_id: str, callback=None, process_holder: list = None):
    cmd = ["winget", "uninstall", "--id", winget_id, "--silent",
           "--accept-source-agreements", "--disable-interactivity"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    if process_holder is not None:
        process_holder.append(process)
    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)
    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_powershell_with_secret(script_name: str, args: list, secret: str, callback=None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    local_path, is_temp = _local_script_path(script_path)
    try:
        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", local_path] + args
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        process.stdin.write(secret + "\n")
        process.stdin.close()
        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                if callback:
                    callback(line)
        process.wait()
        return process.returncode, "\n".join(output_lines)
    finally:
        if is_temp:
            os.unlink(local_path)


def detect_silent_args(path: str) -> tuple:
    """Sniff installer binary. Returns (detected_type, args_list). args_list is [] if unknown."""
    if path.lower().endswith('.msi'):
        return ("MSI", None)  # handled separately via msiexec
    try:
        with open(path, 'rb') as f:
            data = f.read(512 * 1024)
        if b'Nullsoft' in data or b'NSIS' in data:
            return ("NSIS", ['/S'])
        if b'Inno Setup' in data:
            return ("Inno Setup", ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'])
        if b'InstallShield' in data:
            return ("InstallShield", ['/s', '/v', '/qn'])
        if b'WiX Toolset' in data or b'Windows Installer XML' in data:
            return ("WiX", ['/quiet', '/norestart'])
        if b'Squirrel' in data:
            return ("Squirrel", ['--silent'])
    except Exception:
        pass
    return ("Unknown", [])


def run_local_installer(path: str, args: list = None, callback=None, process_holder: list = None):
    path = path.replace('/', '\\')  # normalize UNC forward slashes → backslashes
    is_batch = path.lower().endswith(('.bat', '.cmd'))
    use_console = False

    if path.lower().endswith('.msi'):
        msi_args = args if args is not None else ['/quiet', '/norestart']
        if callback:
            callback(f"  [MSI] Running: msiexec /i \"{path}\" {' '.join(msi_args)}")
        cmd = ['msiexec', '/i', path] + msi_args

    elif is_batch:
        # Batch files run in own console — they may prompt for input (e.g. 7-Zip replace prompts)
        cmd = ['cmd', '/c', path] + (args or [])
        use_console = True
        if callback:
            callback(f"  [Batch] Running in console window — watch console for any prompts.")

    else:
        if args is None:
            detected_type, detected_args = detect_silent_args(path)
            if detected_args:
                if callback:
                    callback(f"  [Auto-detect] {detected_type} installer → {' '.join(detected_args)}")
                args = detected_args
            else:
                if callback:
                    callback(f"  [Auto-detect] {detected_type} — no silent args found, installer may show GUI.")
                args = []
        cmd = [path] + args

    if use_console:
        process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")

    if process_holder is not None:
        process_holder.append(process)

    output_lines = []
    if not use_console:
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                if callback:
                    callback(line)

    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_inline_powershell(script: str, callback=None):
    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace")
    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)
    stderr_out = process.stderr.read().strip()
    process.wait()
    if stderr_out:
        for line in stderr_out.splitlines():
            line = line.strip()
            if line:
                output_lines.append(f"ERR: {line}")
    return process.returncode, "\n".join(output_lines)
