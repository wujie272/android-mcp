"""App Management: running apps, packages, launch app, open URL, force-stop, current app."""

from android_mcp.app import mcp
from android_mcp.lib.utils import run, termux, format_json


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
    r = run(['am', 'start', '-n', f'{package_or_action}/.MainActivity'], timeout=10)
    if not r['success']:
        r = run(['monkey', '-p', package_or_action, '-c',
                 'android.intent.category.LAUNCHER', '1'], timeout=10)
    if not r['success']:
        r = run(f'am start $(pm resolve-activity --brief {package_or_action} | tail -1)',
                shell=True, timeout=10)
    return r.get('stdout', '') + ('\n' + r.get('stderr', '') if r.get('stderr') else '')


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
    r = run(f'dumpsys usagestats | head -200', shell=True, timeout=15)
    return r.get('stdout', r.get('error', 'Failed to get usage stats'))


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

    trigger_reason = reason or "手动触发"

    # 关键实现：通过 subprocess.Popen + os.setpgrp 将重启命令
    # 完全脱离父进程的进程组，这样父进程被 kill 后子进程不会死。
    # 使用 close_fds=True 避免继承父进程的文件描述符。
    subprocess.Popen(
        ['nohup', 'bash', '-c',
         f'sleep 1 && exec bash /data/data/com.termux/files/home/mcp-manager.sh restart --android'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setpgrp,
        close_fds=True,
    )

    return f"🔄 android-mcp 即将重启 (原因: {trigger_reason})，约 2~3 秒后恢复..."
