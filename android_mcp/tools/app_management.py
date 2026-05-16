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
