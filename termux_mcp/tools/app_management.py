"""App management: running apps, packages, launch, force-stop, usage stats, restart."""

from termux_mcp.app import mcp
from termux_mcp.lib.utils import run, termux, format_json
from termux_mcp.lib.constants import MCP_MANAGER
import subprocess
import os
import re as _re


@mcp.tool()
async def list_running_apps() -> str:
    """List running processes with CPU/memory usage."""
    r = run(['ps', '-eo', 'pid,user,%cpu,%mem,args', '--sort=-%cpu'], timeout=10)
    if not r['success']:
        r = run('ps aux', shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed'))


@mcp.tool()
async def list_installed_packages() -> str:
    """List installed Termux packages (dpkg)."""
    return termux('dpkg', ['--list'])


@mcp.tool()
async def list_android_packages(filter_keyword: str = "") -> str:
    """List Android apps/packages. filter_keyword to narrow (e.g. 'camera')."""
    cmd = f'pm list packages | grep -i {filter_keyword}' if filter_keyword else 'pm list packages'
    r = run(cmd, shell=True, timeout=15)
    return r.get('stdout', r.get('error', 'Failed'))


@mcp.tool()
async def open_url(url: str) -> str:
    """Open URL in default browser."""
    return termux('termux-open-url', [url])


@mcp.tool()
async def open_app(package_or_action: str) -> str:
    """Launch an Android app by package name.

    Tries multiple methods: direct MAIN intent, known activity patterns, monkey launcher.
    """
    r = run(
        f'am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER '
        f'-p {package_or_action} 2>/dev/null', shell=True, timeout=10)
    if r['success'] and 'Error' not in r.get('stdout', ''):
        return r.get('stdout', '') or f"Launched {package_or_action}"

    for activity in ['.MainActivity', '.Main', '.Settings', '.activity.MainActivity',
                     '.HomeActivity', '.LaunchActivity', '.StartActivity']:
        r = run(['am', 'start', '-n', f'{package_or_action}{activity}'], timeout=10)
        if r['success'] and 'Error' not in r.get('stdout', ''):
            return r.get('stdout', '') or f"Launched {package_or_action} ({activity})"

    r = run(['monkey', '-p', package_or_action, '-c', 'android.intent.category.LAUNCHER', '1'], timeout=10)
    if r['success']:
        return r.get('stdout', '') or f"Launched {package_or_action} (monkey)"

    r = run(['cmd', 'package', 'resolve-activity', '--brief', package_or_action], timeout=10)
    if r['success'] and r.get('stdout', '').strip():
        lines = r['stdout'].strip().split('\n')
        activity = lines[-1].strip() if lines else ''
        if '/' in activity:
            r2 = run(['am', 'start', '-n', activity], timeout=10)
            if r2['success']:
                return r2.get('stdout', '')

    return f"Error: Could not launch {package_or_action}. Is it installed?"


@mcp.tool()
async def force_stop_app(package: str) -> str:
    """Force stop an Android app (kills background processes)."""
    r = run(f'am force-stop {package}', shell=True, timeout=5)
    return f"Force stopped: {package}" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"


@mcp.tool()
async def get_current_app() -> str:
    """Get the currently focused app (package + activity)."""
    r = run("dumpsys activity activities | grep -E 'mResumedActivity|mCurrentFocus' | head -3", shell=True, timeout=10)
    if r['success'] and r.get('stdout'):
        return r['stdout']
    r = run("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3", shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed'))


@mcp.tool()
async def app_usage_stats(days: int = 1) -> str:
    """Get app usage stats for recent days."""
    r = run(f'dumpsys usagestats {days} 2>/dev/null || dumpsys usagestats | head -300', shell=True, timeout=15)
    raw = r.get('stdout', '')
    if not raw or 'Error' in str(raw):
        return "Failed. Needs Shizuku/ADB or Usage Stats permission."

    entries = []
    current_pkg, current_time = None, 0
    for line in raw.split('\n'):
        ls = line.strip()
        if ls.startswith('package='):
            if current_pkg and current_time > 0:
                entries.append((current_pkg, current_time))
            current_pkg = ls.split('package=')[1].strip()
            current_time = 0
        elif 'totalTimeUse' in ls:
            m = _re.search(r'totalTimeUse:\s*(\d+)', ls)
            if m:
                current_time = int(m.group(1))
    if current_pkg and current_time > 0:
        entries.append((current_pkg, current_time))

    if not entries:
        return raw[:2000] + "\n\n(解析失败，显示原始输出)"

    entries.sort(key=lambda x: -x[1])
    lines = [f"📊 App Usage (last {days}d, top {min(len(entries), 30)}):\n"]
    for i, (pkg, ms) in enumerate(entries[:30], 1):
        mins = ms / 60_000
        label = pkg.split('.')[-1] if '.' in pkg else pkg
        bar = "█" * max(1, int(mins / max(1, entries[0][1] / 60_000) * 20))
        lines.append(f"  {i:2d}. {label:<25s} {mins:>8.1f} min  {bar}")
    total = sum(t for _, t in entries) / 60_000
    lines.append(f"\n  Total: {len(entries)} apps, {total:.0f} min ({total/60:.1f} h)")
    return "\n".join(lines)


@mcp.tool()
async def restart_android(reason: str = "手动触发") -> str:
    """Restart termux-mcp service (~2-3s downtime). Memory state is lost, file changes persist.

    Args:
        reason: Reason for restart (logged for debugging)
    """
    manager_path = str(MCP_MANAGER)
    if not os.path.isfile(manager_path):
        return f"❌ mcp-manager.sh not found at {manager_path}"

    subprocess.Popen(
        ['nohup', 'bash', '-c', f'sleep 1 && exec bash {manager_path} restart --android'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setpgrp, close_fds=True,
    )
    return f"🔄 重启中 (原因: {reason})，约 2~3 秒后恢复..."