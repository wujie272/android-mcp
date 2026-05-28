"""Command risk assessment: SAFE / WARNING / DANGEROUS.

集成 execute_command(check_risk=True)，FORCE=1 前缀绕过。"""

import re
from typing import Tuple


class RiskLevel:
    SAFE = "safe"
    WARNING = "warning"
    DANGEROUS = "dangerous"


DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/\s*$',
    r'rm\s+-rf\s+~(\s|$)',
    r'rm\s+-rf\s+/\*',
    r'rm\s+-rf\s+--no-preserve-root',
    r'dd\s+if=\s*/dev/zero\s+of=\s*/dev/block/',
    r'dd\s+if=\s*/dev/urandom\s+of=\s*/dev/block/',
    r'mkfs\.\w+\s+/dev/block/',
    r'mkswap\s+/dev/block/',
    r'fdisk\s+/dev/block/',
    r'chmod\s+-R\s+000\s+/',
    r'chown\s+-R\s+\d+\s+/',
    r'>\s*/dev/block/',
    r':\(\)\s*\{.*:.*\|.*&\s*\};:',
    r'pkg\s+(remove|uninstall)\s+termux-tools',
    r'pkg\s+(remove|uninstall)\s+python\s*$',
    r'apt\s+(purge|remove)\s+-y\s+termux-tools',
]

WARNING_PATTERNS = [
    r'rm\s+-rf\s',
    r'rm\s+-r\s',
    r'rm\s+-f\s',
    r'rm\s+.*-rf',
    r'rm\s+.*-r\s',
    r'chmod\s+-r',
    r'chown\s+-r',
    r'chmod\s+777',
    r'find\s+.*-delete',
    r'sudo\s',
    r'su\s+',
    r'mount\s',
    r'umount\s',
    r'kill\s+-9\s+\d+',
    r'pkill\s+-9',
    r'dd\s+if=',
    r'mkfs\.',
    r'pvcreate|vgcreate|lvcreate',
    r'wget\s+.*\|\s*(bash|sh)',
    r'curl\s+.*\|\s*(bash|sh)',
    r'wget\s+.*&&\s*(bash|sh)',
    r'curl\s+.*&&\s*(bash|sh)',
    r'>\s*/system/',
    r'>\s*/etc/',
    r'reboot', r'halt', r'poweroff', r'shutdown',
    r'init\s+0', r'init\s+6',
    r'setenforce\s+0',
]

PROTECTED_PATHS = ['/system', '/vendor', '/boot', '/proc', '/sys']


def assess_risk(cmd: str) -> Tuple[str, str, str]:
    """Return (risk_level, message, suggestion)."""
    cmd_stripped = cmd.strip()
    if not cmd_stripped or len(cmd_stripped) < 3:
        return RiskLevel.SAFE, "", ""

    if cmd_stripped.startswith('FORCE=1 '):
        return RiskLevel.SAFE, "✅ 用户强制绕过安全检查", ""

    cmd_lower = cmd_stripped.lower()

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return (
                RiskLevel.DANGEROUS,
                f"🚨 危险命令，已拦截！",
                f"匹配: `{pattern}`\n这条命令可能导致系统崩溃或数据丢失。\n如需执行，加 `FORCE=1 ` 前缀强制绕过。"
            )

    for pattern in WARNING_PATTERNS:
        if re.search(pattern, cmd_lower):
            return (
                RiskLevel.WARNING,
                f"⚠️ 高危命令",
                f"匹配: `{pattern}`\n这条命令可能造成破坏性影响。\n如需强制执行，加 `FORCE=1 ` 前缀或确认执行。"
            )

    for redirect in ['>', '>>']:
        if redirect in cmd:
            for protected in PROTECTED_PATHS:
                if protected in cmd:
                    return (
                        RiskLevel.WARNING,
                        f"⚠️ 尝试写入受保护路径: {protected}",
                        f"写入系统关键路径可能导致不稳定。如需强制执行，加 FORCE=1。"
                    )

    return RiskLevel.SAFE, "✅ 安全", ""


def get_assessment(cmd: str) -> dict:
    level, message, suggestion = assess_risk(cmd)
    return {
        "command": cmd,
        "risk_level": level,
        "message": message,
        "suggestion": suggestion,
        "blocked": level == RiskLevel.DANGEROUS,
        "requires_confirmation": level == RiskLevel.WARNING,
    }