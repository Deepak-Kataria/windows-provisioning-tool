"""Utility to run PowerShell scripts and winget commands."""
import subprocess
import os

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")


def run_powershell(script_name: str, args: list = None, callback=None):
    """Run a PowerShell script and return (returncode, output)."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path]
    if args:
        cmd.extend(args)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)

    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_winget(winget_id: str, callback=None):
    """Install an app via winget and return (returncode, output)."""
    cmd = ["winget", "install", "--id", winget_id, "--silent", "--accept-package-agreements",
           "--accept-source-agreements"]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)

    process.wait()
    return process.returncode, "\n".join(output_lines)


def run_inline_powershell(script: str, callback=None):
    """Run an inline PowerShell command string."""
    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    output_lines = []
    for line in process.stdout:
        line = line.strip()
        if line:
            output_lines.append(line)
            if callback:
                callback(line)
    process.wait()
    return process.returncode, "\n".join(output_lines)
