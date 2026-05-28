"""App Management: running apps, packages, launch app, open URL, force-stop, current app."""

from android_mcp.app import mcp
from android_mcp.lib.utils import run, termux, format_json
from android_mcp.lib.constants import MCP_MANAGER


@mcp.tool()
async def list_running_apps() -> str:
    """List currently running processes/apps on the phone with CPU and memory usage."""
    r = run(['ps', '-eo', 'pid,user,%cpu,%mem,args', '--sort=-%cpu'], timeout=10)
    if not r['success']:
        r = run('ps aux', shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed to list processes'))


@mcp.tool()
async def list_installed_packages() -> str:
    """List all installed Termux packages."""
    return termux('dpkg', ['--list'])


@mcp.tool()
async def list_android_packages(filter_keyword: str = "") -> str:
    """List installed Android apps/packages.

    Args:
        filter_keyword: Optional keyword to filter package names (e.g. 'camera', 'wechat')
    """
    if filter_keyword:
        r = run(f'pm list packages | grep -i {filter_keyword}', shell=True, timeout=15)
    else:
        r = run(['pm', 'list', 'packages'], timeout=15)
    return r.get('stdout', r.get('error', 'Failed to list packages'))


@mcp.tool()
async def open_url(url: str) -> str:
    """Open a URL in the default browser on the phone.

    Args:
        url: The URL to open
    """
    return termux('termux-open-url', [url])


@mcp.tool()
async def open_app(package_or_action: str) -> str:
    """Launch an Android app or activity.

    Args:
        package_or_action: Package name (e.g. 'com.whatsapp', 'com.android.settings')
    """
    # Try 1: Direct via MAIN/LAUNCHER intent (most reliable, works without Shizuku/ADB on most devices)
    r = run(
        f'am start -a android.intent.action.MAIN '
        f'-c android.intent.category.LAUNCHER '
        f'-p {package_or_action} 2>/dev/null',
        shell=True, timeout=10,
    )
    if r['success']:
        out = r.get('stdout', '')
        if 'Error' not in out and 'does not exist' not in out:
            return out or f"Launched {package_or_action}"

    # Try 2: Common activity name patterns
    for activity in ['.MainActivity', '.Main', '.Settings', '.activity.MainActivity',
                     '.HomeActivity', '.LaunchActivity', '.StartActivity']:
        r = run(['am', 'start', '-n', f'{package_or_action}{activity}'], timeout=10)
        if r['success']:
            out = r.get('stdout', '')
            if 'Error' not in out and 'does not exist' not in out:
                return out or f"Launched {package_or_action} ({activity})"

    # Try 3: Monkey launcher (needs Shizuku/ADB on some devices)
    r = run(['monkey', '-p', package_or_action, '-c',
             'android.intent.category.LAUNCHER', '1'], timeout=10)
    if r['success']:
        return r.get('stdout', '') or f"Launched {package_or_action} (monkey)"

    # Try 4: Resolve activity via cmd (Android 13+, needs Shizuku/ADB)
    r = run(['cmd', 'package', 'resolve-activity', '--brief', package_or_action], timeout=10)
    if r['success'] and r.get('stdout', '').strip():
        lines = r['stdout'].strip().split('\n')
        activity = lines[-1].strip() if lines else ''
        if '/' in activity:
            r2 = run(['am', 'start', '-n', activity], timeout=10)
            if r2['success']:
                return r2.get('stdout', '')

    # Try 5: dumpsys package fallback (needs Shizuku/ADB)
    r = run(
        f"dumpsys package {package_or_action} 2>/dev/null | "
        f"grep -B 1 'android.intent.action.MAIN' | "
        f"grep '{package_or_action}/' | head -1 | awk '{{print $2}}'",
        shell=True, timeout=10,
    )
    if r['success'] and r.get('stdout', '').strip():
        activity = r['stdout'].strip()
        r2 = run(['am', 'start', '-n', activity], timeout=10)
        if r2['success']:
            return r2.get('stdout', '')

    return f"Error: Could not launch {package_or_action}. Is it installed?"


@mcp.tool()
async def force_stop_app(package: str) -> str:
    """Force stop an Android app (kill background processes).

    Args:
        package: Package name to stop (e.g. 'com.tencent.mm')
    """
    r = run(f'am force-stop {package}', shell=True, timeout=5)
    if r['success']:
        return f"Force stopped: {package}"
    return f"Error: {r.get('stderr', 'Failed to stop app')}"


@mcp.tool()
async def get_current_app() -> str:
    """Get the currently focused app (package name and activity)."""
    r = run("dumpsys activity activities | grep -E 'mResumedActivity|mCurrentFocus' | head -3",
            shell=True, timeout=10)
    if r['success'] and r.get('stdout'):
        return r['stdout']
    r = run("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3",
            shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed to get current app'))


@mcp.tool()
async def app_usage_stats(days: int = 1) -> str:
    """Get app usage statistics for recent days.

    Args:
        days: Number of days to look back (default: 1)
    """
    import re as _re

    r = run(f'dumpsys usagestats {days} 2>/dev/null || dumpsys usagestats | head -300', shell=True, timeout=15)
    raw = r.get('stdout', '')
    if not raw or 'Error' in str(raw):
        return "Failed to get usage stats. Needs Shizuku/ADB or Usage Stats permission."

    # Parse structured app usage data from dumpsys output
    entries = []
    current_pkg = None
    current_time = 0

    for line in raw.split('\n'):
        line_stripped = line.strip()
        if line_stripped.startswith('package='):
            if current_pkg and current_time > 0:
                entries.append((current_pkg, current_time))
            current_pkg = line_stripped.split('package=')[1].strip()
            current_time = 0
        elif 'totalTimeUse' in line_stripped:
            # Format: "totalTimeUse: 123456 (ms)   totalTimeUseForeground: 123456"
            m = _re.search(r'totalTimeUse:\s*(\d+)', line_stripped)
            if m:
                current_time = int(m.group(1))

    if current_pkg and current_time > 0:
        entries.append((current_pkg, current_time))

    if not entries:
        return raw[:2000] + "\n\n(Unable to parse usage stats, showing raw output)"

    # Sort by usage time descending
    entries.sort(key=lambda x: -x[1])

    lines = [f"📊 App Usage Stats (last {days} day(s), top {min(len(entries), 30)}):\n"]
    for i, (pkg, time_ms) in enumerate(entries[:30], 1):
        mins = time_ms / 60_000
        pct = time_ms / (entries[0][1] or 1) * 100 if i == 1 else 0
        bar = "█" * max(1, int(mins / max(1, entries[0][1] / 60_000) * 20)) if entries else ""
        label = pkg.split('.')[-1] if '.' in pkg else pkg
        lines.append(f"  {i:2d}. {label:<25s} {mins:>8.1f} min  {bar}")

    total_mins = sum(t for _, t in entries) / 60_000
    lines.append(f"\n  ─────────────────────────────")
    lines.append(f"  Total: {len(entries)} apps, {total_mins:.0f} min ({total_mins/60:.1f} h)")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 重启 android-mcp 服务
# ──────────────────────────────────────────────

@mcp.tool()
async def restart_android(reason: str = "手动触发") -> str:
    """重启 android-mcp 服务。

    服务会在返回响应后约 1 秒自动重启，中断约 2~3 秒。
    重启后所有内存状态（剪贴板历史、Shizuku 缓存等）会丢失，
    但文件改动（如编辑 app.py）会生效。

    适合：
    - 修改了 android-mcp 自身代码（如工具模块）后生效
    - 服务异常后手动恢复
    - 清理内存状态

    Args:
        reason: 重启原因说明（会记录在日志中）
    """
    import subprocess
    import os

    # 先检查 mcp-manager.sh 是否存在
    manager_path = str(MCP_MANAGER)
    if not os.path.isfile(manager_path):
        return (f"❌ 重启失败: mcp-manager.sh 不存在 ({manager_path})\n"
                f"请手动重启: 在 Termux 中运行 `pkill -f android-mcp` 后再启动")

    trigger_reason = reason or "手动触发"

    # 关键实现：通过 subprocess.Popen + os.setpgrp 将重启命令
    # 完全脱离父进程的进程组，这样父进程被 kill 后子进程不会死。
    # 使用 close_fds=True 避免继承父进程的文件描述符。
    subprocess.Popen(
        ['nohup', 'bash', '-c',
         f'sleep 1 && exec bash {manager_path} restart --android'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setpgrp,
        close_fds=True,
    )

    return f"🔄 android-mcp 即将重启 (原因: {trigger_reason})，约 2~3 秒后恢复..."
