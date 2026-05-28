"""Shared utilities: command execution, Termux API wrappers, formatting, logging."""

import os
import time
import asyncio
import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

from android_mcp.lib.constants import HOME, LOG_DIR, RISH as _RISH_PATH

# ── 启动时间（用于自愈健康检查）──
STARTUP_TIME = time.time()

# ── Logging（日志轮转：1MB × 3 份）──
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger('android-mcp')
logger.setLevel(logging.DEBUG)

_fh = RotatingFileHandler(
    str(LOG_DIR / 'android_mcp.log'),
    maxBytes=1_000_000,   # 1MB 轮转
    backupCount=3,         # 保留 3 份历史
    encoding='utf-8',
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
))
logger.addHandler(_fh)

# Also log to stderr at INFO level
_sh = logging.StreamHandler()
_sh.setLevel(logging.INFO)
_sh.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(_sh)


# ── Unified return helpers ──

def ok(msg: str, data: str = "") -> str:
    """Return a success message (optionally with extra data)."""
    if data:
        return f"✅ {msg}\n{data}"
    return f"✅ {msg}"


def warn(msg: str) -> str:
    """Return a warning message."""
    return f"⚠️ {msg}"


def err(msg: str, detail: str = "") -> str:
    """Return an error message (optionally with detail)."""
    if detail:
        return f"❌ {msg}\n{detail}"
    return f"❌ {msg}"

BLOCKED_COMMANDS = {
    # File operations (dangerous)
    'rm', 'rmdir', 'mkfs', 'dd', 'format',
    'chmod', 'chown', 'chattr', 'mount',
    # System operations
    'shutdown', 'reboot', 'halt', 'poweroff',
    'init', 'killall', 'pkill',
    # Privilege escalation
    'sudo', 'su', 'doas',
    # Boot/partition
    'fdisk', 'parted', 'mkswap',
}

HOME = str(HOME)
RISH = str(_RISH_PATH)

_ADB_REQUIRED_CMDS = {
    'screencap', 'uiautomator', 'input', 'am', 'pm', 'wm',
    'settings', 'getprop', 'dumpsys', 'monkey', 'cmd', 'content',
}


# ── Shizuku / rish support ──

_shizuku_cache = None

def shizuku_available() -> bool:
    """Check if Shizuku is available and rish can connect."""
    global _shizuku_cache
    if _shizuku_cache is not None:
        return _shizuku_cache
    try:
        r = subprocess.run(
            [RISH, '-c', 'echo ok'],
            capture_output=True, text=True, timeout=10,
            env=ensure_path_env(),
        )
        # rish writes output to stderr (app_process Java bridge behavior)
        out = (r.stdout + " " + r.stderr).strip()
        _shizuku_cache = (r.returncode == 0 and 'ok' in out)
        if _shizuku_cache:
            logger.info("Shizuku available via rish")
        return _shizuku_cache
    except Exception:
        _shizuku_cache = False
        return False


def invalidate_shizuku_cache():
    """Clear the shizuku cache (e.g. after a connection failure)."""
    global _shizuku_cache
    _shizuku_cache = None


def rish_shell(cmd: str, timeout: int = 30) -> dict:
    """Run a command via 'rish -c' (Shizuku's privileged shell)."""
    try:
        result = subprocess.run(
            [RISH, '-c', cmd],
            capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace',
            env=ensure_path_env(),
        )
        # rish writes output to stderr (app_process Java bridge behavior)
        combined = (result.stdout + "\n" + result.stderr).strip()
        return {
            'success': result.returncode == 0,
            'returncode': result.returncode,
            'stdout': combined,
            'stderr': result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        invalidate_shizuku_cache()
        return {'success': False, 'error': f'rish timed out after {timeout}s'}
    except FileNotFoundError:
        _shizuku_cache = False
        return {'success': False, 'error': f'rish not found at {RISH}'}
    except Exception as e:
        invalidate_shizuku_cache()
        return {'success': False, 'error': str(e)}


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
    """Run a command. Auto-routes through rish (Shizuku) or adb shell if needed."""
    env = ensure_path_env()

    first_word = ''
    raw_cmd = ''
    if shell and isinstance(cmd, str):
        raw_cmd = cmd.strip()
        first_word = raw_cmd.split()[0] if raw_cmd else ''
    elif isinstance(cmd, list) and cmd:
        raw_cmd = ' '.join(cmd)
        first_word = os.path.basename(cmd[0])

    logger.debug(f"cmd: {raw_cmd[:120]}")

    # 1) Shizuku available → use rish (preferred)
    if first_word in _ADB_REQUIRED_CMDS and shizuku_available():
        logger.debug(f"rish: {raw_cmd}")
        return rish_shell(raw_cmd, timeout=timeout)

    # 2) ADB connected → use adb shell (fallback)
    if first_word in _ADB_REQUIRED_CMDS and adb_connected():
        if shell and isinstance(cmd, str):
            return adb_shell(raw_cmd, timeout=timeout)
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


async def async_run(cmd: list[str] | str, timeout: int = 30, shell: bool = False) -> dict:
    """异步运行命令 — 使用线程池避免阻塞事件循环。
    
    与 run() 功能相同，但包装在 asyncio.to_thread 中，
    不会阻塞 Kelivo 其他并行工具调用。
    """
    return await asyncio.to_thread(run, cmd, timeout, shell)


def termux(cmd: str, args: list[str] | None = None, timeout: int = 30) -> str:
    """Run a termux-api command and return output or error message."""
    full_cmd = [cmd] + (args or [])
    r = run(full_cmd, timeout=timeout)
    if not r.get('success'):
        return f"Error: {r.get('error', r.get('stderr', 'Unknown error'))}"
    return r.get('stdout', '')


async def async_termux(cmd: str, args: list[str] | None = None, timeout: int = 30) -> str:
    """异步运行 termux-api 命令 — 不阻塞事件循环。"""
    full_cmd = [cmd] + (args or [])
    r = await async_run(full_cmd, timeout=timeout)
    if not r.get('success'):
        return f"Error: {r.get('error', r.get('stderr', 'Unknown error'))}"
    return r.get('stdout', '')


def privileged_shell(cmd: str, timeout: int = 30) -> dict:
    """Run a command via rish (Shizuku) if available, otherwise via ADB shell.

    统一的特权 shell 执行入口 — 优先 rish，回退到 ADB。
    """
    if shizuku_available():
        return rish_shell(cmd, timeout=timeout)
    if adb_connected():
        return adb_shell(cmd, timeout=timeout)
    return {'success': False, 'error': 'Neither Shizuku nor ADB is available'}


def privileged_available() -> bool:
    """Check if any privilege elevation (Shizuku or ADB) is available."""
    return shizuku_available() or adb_connected()


def get_uptime() -> float:
    """返回服务已运行秒数（用于健康检查）。"""
    return time.time() - STARTUP_TIME


def format_json(raw: str) -> str:
    """Pretty-format JSON output, or return raw if not JSON."""
    try:
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return raw


# ══════════════════════════════════════════════
# Security Gates（安全门）
# ══════════════════════════════════════════════
# 环境变量控制:
#   ANDROID_MCP_READONLY=true  → 只读模式，禁止所有写入操作
#   ANDROID_MCP_ALLOW_SHELL=true  → 是否允许 shell/ADB 命令执行

READONLY_MODE = os.environ.get('ANDROID_MCP_READONLY', '').lower() in ('true', '1', 'yes', 'readonly')
ALLOW_SHELL = os.environ.get('ANDROID_MCP_ALLOW_SHELL', 'true').lower() in ('true', '1', 'yes', 'allow')


def check_readonly() -> bool:
    """Check if server is in read-only mode."""
    return READONLY_MODE


def check_write_permission(action: str = "write") -> str | None:
    """Check write permission. Returns error message if denied, None if allowed.

    用于工具函数开头：如果返回 str 则直接返回该错误信息，禁止执行。
    """
    if READONLY_MODE:
        return (
            f"❌ 写入操作已禁止：服务器处于只读模式。\n"
            f"   请求的操作: {action}\n"
            f"   设置 ANDROID_MCP_READONLY=false 即可启用。"
        )
    return None


def check_shell_permission(action: str = "shell") -> str | None:
    """Check shell command permission."""
    if not ALLOW_SHELL:
        return (
            f"❌ Shell 命令已禁止。\n"
            f"   请求的操作: {action}\n"
            f"   设置 ANDROID_MCP_ALLOW_SHELL=true 即可启用。"
        )
    return None


# ──────────── 安全级别定义 ────────────
# 用于工具文档标注，帮助用户理解每个工具的安全级别

DANGER_READONLY = "🔒 只读"      # 仅查询信息，无副作用
DANGER_LOW = "🔓 低风险"         # 截图、UI dump 等视觉操作
DANGER_MEDIUM = "⚡ 中风险"      # 点击、输入、滑动等交互操作
DANGER_HIGH = "🚨 高风险"        # 安装/卸载、发短信、删除文件、shell 执行