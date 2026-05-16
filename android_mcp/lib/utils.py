"""Shared utilities: command execution, Termux API wrappers, formatting."""

import os
import subprocess
import json
from pathlib import Path

BLOCKED_COMMANDS = {
    'rm', 'rmdir', 'mkfs', 'dd', 'format',
    'shutdown', 'reboot', 'halt', 'poweroff',
}

HOME = '/data/data/com.termux/files/home'

_ADB_REQUIRED_CMDS = {
    'screencap', 'uiautomator', 'input', 'am', 'pm', 'wm',
    'settings', 'getprop', 'dumpsys', 'monkey', 'cmd', 'content',
}


def ensure_path_env() -> dict:
    """Return env dict with /system/bin in PATH."""
    env = os.environ.copy()
    path = env.get('PATH', '')
    if '/system/bin' not in path:
        env['PATH'] = f"/system/bin:{path}"
    return env


def adb_get_device() -> str | None:
    """Get the serial of the first online adb device."""
    try:
        r = subprocess.run(
            ['adb', 'devices'], capture_output=True, text=True, timeout=5,
            env=ensure_path_env(),
        )
        for line in r.stdout.strip().split('\n')[1:]:
            if '\tdevice' in line:
                return line.split('\t')[0]
    except Exception:
        pass
    return None


def adb_connected() -> bool:
    """Check if adb is connected to the device."""
    return adb_get_device() is not None


def adb_shell(cmd: str, timeout: int = 30) -> dict:
    """Run a command via 'adb -s <device> shell'."""
    device = adb_get_device()
    adb_cmd = ['adb']
    if device:
        adb_cmd += ['-s', device]
    adb_cmd += ['shell', cmd]
    try:
        result = subprocess.run(
            adb_cmd,
            capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=ensure_path_env(),
        )
        return {
            'success': result.returncode == 0,
            'returncode': result.returncode,
            'stdout': result.stdout.strip(),
            'stderr': result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Timed out after {timeout}s'}
    except FileNotFoundError:
        return {'success': False, 'error': 'adb not found. Run: pkg install android-tools'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def run(cmd: list[str] | str, timeout: int = 30, shell: bool = False) -> dict:
    """Run a command. Auto-routes through adb shell if needed on Android 12+."""
    env = ensure_path_env()

    first_word = ''
    if shell and isinstance(cmd, str):
        first_word = cmd.strip().split()[0] if cmd.strip() else ''
    elif isinstance(cmd, list) and cmd:
        first_word = os.path.basename(cmd[0])

    if first_word in _ADB_REQUIRED_CMDS and adb_connected():
        if shell and isinstance(cmd, str):
            return adb_shell(cmd, timeout=timeout)
        elif isinstance(cmd, list):
            return adb_shell(' '.join(cmd), timeout=timeout)

    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=env,
        )
        return {
            'success': result.returncode == 0,
            'returncode': result.returncode,
            'stdout': result.stdout.strip(),
            'stderr': result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Timed out after {timeout}s'}
    except FileNotFoundError:
        cmd_name = cmd if isinstance(cmd, str) else cmd[0]
        return {'success': False, 'error': f'Command not found: {cmd_name}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def termux(cmd: str, args: list[str] | None = None, timeout: int = 30) -> str:
    """Run a termux-api command and return output or error message."""
    full_cmd = [cmd] + (args or [])
    r = run(full_cmd, timeout=timeout)
    if not r.get('success'):
        return f"Error: {r.get('error', r.get('stderr', 'Unknown error'))}"
    return r.get('stdout', '')


def format_json(raw: str) -> str:
    """Pretty-format JSON output, or return raw if not JSON."""
    try:
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return raw
