"""Shared utilities: command execution, Termux API wrappers, logging, UI cache."""

import os
import time
import asyncio
import subprocess
import json
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

from android_mcp.lib.constants import HOME, LOG_DIR, RISH as _RISH_PATH

STARTUP_TIME = time.time()

LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger('android-mcp')
logger.setLevel(logging.DEBUG)

_fh = RotatingFileHandler(
    str(LOG_DIR / 'android_mcp.log'),
    maxBytes=1_000_000, backupCount=3, encoding='utf-8',
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S',
))
logger.addHandler(_fh)

_sh = logging.StreamHandler()
_sh.setLevel(logging.INFO)
_sh.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(_sh)


def ok(msg: str, data: str = "") -> str:
    return f"✅ {msg}" + (f"\n{data}" if data else "")


def warn(msg: str) -> str:
    return f"⚠️ {msg}"


def err(msg: str, detail: str = "") -> str:
    return f"❌ {msg}" + (f"\n{detail}" if detail else "")


HOME = str(HOME)
RISH = str(_RISH_PATH)

_ADB_REQUIRED_CMDS = {
    'screencap', 'uiautomator', 'input', 'am', 'pm', 'wm',
    'settings', 'getprop', 'dumpsys', 'monkey', 'cmd', 'content',
}


def _decode_output(val):
    """Normalize subprocess output to str (handles bytes in Python 3.13)."""
    if val is None:
        return ''
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='replace')
    return str(val)


# ── Shizuku / rish support ──

_shizuku_cache = None
_shizuku_cache_time = 0.0
_SHIZUKU_CACHE_TTL_OK = 30.0
_SHIZUKU_CACHE_TTL_FAIL = 60.0


def shizuku_available() -> bool:
    """Check Shizuku availability with TTL cache (30s on success, 5s on failure)."""
    global _shizuku_cache, _shizuku_cache_time
    now = time.time()
    if _shizuku_cache is not None:
        ttl = _SHIZUKU_CACHE_TTL_OK if _shizuku_cache else _SHIZUKU_CACHE_TTL_FAIL
        if now - _shizuku_cache_time < ttl:
            return _shizuku_cache

    try:
        r = subprocess.run(
            [RISH, '-c', 'echo ok'], capture_output=True, text=True, timeout=10,
            env=ensure_path_env(),
        )
        out = (r.stdout + " " + r.stderr).strip()
        _shizuku_cache = (r.returncode == 0 and 'ok' in out)
        _shizuku_cache_time = now
        logger.info("Shizuku available" if _shizuku_cache else f"Shizuku check failed: exit={r.returncode}")
        return _shizuku_cache
    except Exception as e:
        _shizuku_cache = False
        _shizuku_cache_time = now
        logger.debug(f"Shizuku check: {e}")
        return False


def invalidate_shizuku_cache():
    global _shizuku_cache, _shizuku_cache_time
    _shizuku_cache = None
    _shizuku_cache_time = 0.0


def rish_shell(cmd: str, timeout: int = 30) -> dict:
    """Run command via 'rish -c' (Shizuku). Handles TimeoutExpired output."""
    try:
        result = subprocess.run(
            [RISH, '-c', cmd], capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=ensure_path_env(),
        )
        combined = (result.stdout + "\n" + result.stderr).strip()
        return {'success': result.returncode == 0, 'returncode': result.returncode,
                'stdout': combined, 'stderr': result.stderr.strip()}
    except subprocess.TimeoutExpired as e:
        invalidate_shizuku_cache()
        return {'success': False, 'returncode': None,
                'stdout': _decode_output(e.stdout).strip(), 'stderr': _decode_output(e.stderr).strip(),
                'error': f'rish timed out ({timeout}s)', 'timed_out': True}
    except FileNotFoundError:
        _shizuku_cache = False
        _shizuku_cache_time = time.time()
        return {'success': False, 'error': f'rish not found at {RISH}'}
    except Exception as e:
        invalidate_shizuku_cache()
        return {'success': False, 'error': str(e)}


def ensure_path_env() -> dict:
    """Return env with /system/bin in PATH."""
    env = os.environ.copy()
    if '/system/bin' not in env.get('PATH', ''):
        env['PATH'] = f"/system/bin:{env['PATH']}"
    return env


def adb_get_device() -> str | None:
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
    return adb_get_device() is not None


def adb_shell(cmd: str, timeout: int = 30) -> dict:
    device = adb_get_device()
    adb_cmd = ['adb'] + (['-s', device] if device else []) + ['shell', cmd]
    try:
        result = subprocess.run(
            adb_cmd, capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=ensure_path_env(),
        )
        return {'success': result.returncode == 0, 'returncode': result.returncode,
                'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except subprocess.TimeoutExpired as e:
        return {'success': False, 'returncode': None,
                'stdout': _decode_output(e.stdout).strip(), 'stderr': _decode_output(e.stderr).strip(),
                'error': f'Timed out ({timeout}s)', 'timed_out': True}
    except FileNotFoundError:
        return {'success': False, 'error': 'adb not found. Run: pkg install android-tools'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _try_direct(cmd: list[str] | str, shell: bool, env: dict, timeout: int, cwd: str | None) -> dict | None:
    """Try running a command directly in Termux. Returns result dict or None on failure."""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=env, cwd=cwd,
        )
        success = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        # Direct success if returncode 0 and we got actual output (not "not found" etc.)
        if success and stdout:
            return {'success': True, 'returncode': result.returncode,
                    'stdout': stdout, 'stderr': stderr, 'via': 'direct'}
        # If command not found at all, return None to try fallback
        if not success and ('not found' in stderr.lower() or 'no such file' in stderr.lower()):
            return None
        # If it ran but failed (e.g. permission denied), still report failure
        if not success:
            return {'success': False, 'returncode': result.returncode,
                    'stdout': stdout, 'stderr': stderr, 'via': 'direct'}
        # success but no stdout — might be a command that produces no output, keep it
        return {'success': True, 'returncode': result.returncode,
                'stdout': stdout, 'stderr': stderr, 'via': 'direct'}
    except subprocess.TimeoutExpired as e:
        return {'success': False, 'returncode': None,
                'stdout': _decode_output(e.stdout).strip(), 'stderr': _decode_output(e.stderr).strip(),
                'error': f'Timed out ({timeout}s)', 'timed_out': True, 'via': 'direct'}
    except FileNotFoundError:
        return None
    except Exception as e:
        return {'success': False, 'error': str(e), 'via': 'direct'}


def run(cmd: list[str] | str, timeout: int = 30, shell: bool = False, cwd: str | None = None) -> dict:
    """Run command. Priority: Shizuku (rish) 🥇 → ADB 🥈 → Direct (Termux) 🥉.

    Shizuku has the highest privilege level, tried first for system commands.
    Falls back to ADB, then Direct Termux execution.
    """
    env = ensure_path_env()
    first_word = ''
    raw_cmd = ''
    if shell and isinstance(cmd, str):
        raw_cmd = cmd.strip()
        first_word = raw_cmd.split()[0] if raw_cmd else ''
    elif isinstance(cmd, list) and cmd:
        raw_cmd = ' '.join(cmd)
        first_word = os.path.basename(cmd[0])

    # Only apply privilege chain for commands that need system-level access
    if first_word in _ADB_REQUIRED_CMDS:
        # 🥇 Shizuku: highest privilege, tried first
        if shizuku_available():
            return rish_shell(raw_cmd, timeout=timeout)

        # 🥈 ADB: fallback when Shizuku unavailable
        if adb_connected():
            if shell and isinstance(cmd, str):
                return adb_shell(raw_cmd, timeout=timeout)
            return adb_shell(' '.join(cmd), timeout=timeout)

        # 🥉 Direct: lowest privilege, last resort
        direct_result = _try_direct(cmd, shell, env, timeout, cwd)
        if direct_result is not None:
            return direct_result

        return {'success': False, 'error': f'Command `{first_word}` not available in Shizuku, ADB, or Termux'}

    # Non-ADB commands: just run directly
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=env, cwd=cwd,
        )
        return {'success': result.returncode == 0, 'returncode': result.returncode,
                'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}
    except subprocess.TimeoutExpired as e:
        return {'success': False, 'returncode': None,
                'stdout': _decode_output(e.stdout).strip(), 'stderr': _decode_output(e.stderr).strip(),
                'error': f'Timed out ({timeout}s)', 'timed_out': True}
    except FileNotFoundError:
        return {'success': False, 'error': f'Command not found: {cmd if isinstance(cmd, str) else cmd[0]}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def async_run(cmd: list[str] | str, timeout: int = 30, shell: bool = False, cwd: str | None = None) -> dict:
    """Async wrapper for run() — runs in thread pool to avoid blocking event loop."""
    return await asyncio.to_thread(run, cmd, timeout, shell, cwd)


# ── Streaming shell execution ──

async def async_run_streaming(cmd: str, timeout: int = 30, shell: bool = True) -> dict:
    """Execute command with streaming output (asyncio.subprocess).

    Returns partial output on timeout instead of raising, useful for long commands.
    """
    stdout_lines = []
    stderr_lines = []
    timed_out = False

    try:
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=ensure_path_env(),
        )

        async def _read(stream, store, name):
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace')
                    store.append(decoded)
            except Exception:
                pass

        await asyncio.wait_for(
            asyncio.gather(
                _read(process.stdout, stdout_lines, 'out'),
                _read(process.stderr, stderr_lines, 'err'),
                process.wait(),
            ),
            timeout=timeout,
        )
        returncode = process.returncode
    except asyncio.TimeoutError:
        timed_out = True
        returncode = None
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
    except Exception as e:
        return {'success': False, 'returncode': None, 'stdout': ''.join(stdout_lines).strip(),
                'stderr': f"Exception: {e}", 'timed_out': False}

    return {
        'success': returncode == 0 if returncode is not None else False,
        'returncode': returncode,
        'stdout': ''.join(stdout_lines).strip(),
        'stderr': ''.join(stderr_lines).strip(),
        'timed_out': timed_out,
    }


# ── Termux API helpers ──

def termux(cmd: str, args: list[str] | None = None, timeout: int = 30) -> str:
    full_cmd = [cmd] + (args or [])
    r = run(full_cmd, timeout=timeout)
    if not r.get('success'):
        return f"Error: {r.get('error', r.get('stderr', 'Unknown'))}"
    return r.get('stdout', '')


async def async_termux(cmd: str, args: list[str] | None = None, timeout: int = 30) -> str:
    full_cmd = [cmd] + (args or [])
    r = await async_run(full_cmd, timeout=timeout)
    if not r.get('success'):
        return f"Error: {r.get('error', r.get('stderr', 'Unknown'))}"
    return r.get('stdout', '')


def privileged_shell(cmd: str, timeout: int = 30) -> dict:
    """Run via rish (Shizuku) 🥇 if available, fallback to ADB 🥈, then direct 🥉."""
    if shizuku_available():
        result = rish_shell(cmd, timeout=timeout)
        if result.get('success') or not result.get('timed_out'):
            return result

    if adb_connected():
        result = adb_shell(cmd, timeout=timeout)
        if result.get('success'):
            return result

    # 🥉 Direct: last resort
    return run(cmd, timeout=timeout, shell=True)


def privileged_available() -> bool:
    """Check if Shizuku or ADB is available for system-level commands. Direct always available."""
    return shizuku_available() or adb_connected() or True


def get_uptime() -> float:
    return time.time() - STARTUP_TIME


def format_json(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return raw


# ── Security gates ──

READONLY_MODE = os.environ.get('ANDROID_MCP_READONLY', '').lower() in ('true', '1', 'yes', 'readonly')
ALLOW_SHELL = os.environ.get('ANDROID_MCP_ALLOW_SHELL', 'true').lower() in ('true', '1', 'yes', 'allow')

DANGER_READONLY = "🔒 只读"
DANGER_LOW = "🔓 低风险"
DANGER_MEDIUM = "⚡ 中风险"
DANGER_HIGH = "🚨 高风险"


def check_readonly() -> bool:
    return READONLY_MODE


def check_write_permission(action: str = "write") -> str | None:
    if READONLY_MODE:
        return f"❌ 写入已禁止：只读模式。设置 ANDROID_MCP_READONLY=false 启用。"
    return None


def check_shell_permission(action: str = "shell") -> str | None:
    if not ALLOW_SHELL:
        return f"❌ Shell 命令已禁止。设置 ANDROID_MCP_ALLOW_SHELL=true 启用。"
    return None


# ── UI dump cache ──

_ui_dump_cache_xml: str | None = None
_ui_dump_cache_time: float = 0.0
UI_DUMP_CACHE_TTL: float = 0.3


def get_cached_ui_dump() -> str | None:
    global _ui_dump_cache_xml, _ui_dump_cache_time
    if _ui_dump_cache_xml is not None and time.time() - _ui_dump_cache_time < UI_DUMP_CACHE_TTL:
        return _ui_dump_cache_xml
    return None


def set_ui_dump_cache(xml: str) -> None:
    global _ui_dump_cache_xml, _ui_dump_cache_time
    _ui_dump_cache_xml = xml
    _ui_dump_cache_time = time.time()


def invalidate_ui_cache() -> None:
    global _ui_dump_cache_xml, _ui_dump_cache_time
    _ui_dump_cache_xml = None
    _ui_dump_cache_time = 0.0