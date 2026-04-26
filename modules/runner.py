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


def run_winget(winget_id: str, callback=None):
    cmd = ["winget", "install", "--id", winget_id, "--silent",
           "--accept-package-agreements", "--accept-source-agreements",
           "--disable-interactivity"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)
    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_winget_uninstall(winget_id: str, callback=None):
    cmd = ["winget", "uninstall", "--id", winget_id, "--silent",
           "--accept-source-agreements", "--disable-interactivity"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
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


def run_inline_powershell(script: str, callback=None):
    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script]
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
