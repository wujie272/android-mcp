"""System Control: volume, torch, vibrate, TTS, brightness, fingerprint."""

from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run, adb_connected


@mcp.tool()
async def set_volume(stream: str, volume: int) -> str:
    """Set a volume level on the phone.

    Args:
        stream: Volume stream - 'music', 'ring', 'alarm', 'notification', 'system', 'call'
        volume: Volume level (0-15 typical range, depends on device)
    """
    return termux('termux-volume', [stream, str(volume)]) or f"Volume '{stream}' set to {volume}"


@mcp.tool()
async def get_volume() -> str:
    """Get current volume levels for all audio streams."""
    return format_json(termux('termux-volume'))


@mcp.tool()
async def toggle_torch(enabled: bool = True) -> str:
    """Turn the flashlight (torch) on or off.

    Args:
        enabled: True to turn on, False to turn off
    """
    return termux('termux-torch', ['on' if enabled else 'off']) or f"Torch {'on' if enabled else 'off'}"


@mcp.tool()
async def vibrate(duration_ms: int = 1000, force: bool = False) -> str:
    """Vibrate the phone.

    Args:
        duration_ms: Vibration duration in milliseconds (default: 1000)
        force: Vibrate even in silent mode (default: False)
    """
    args = ['-d', str(duration_ms)]
    if force:
        args.append('-f')
    return termux('termux-vibrate', args) or f"Vibrated for {duration_ms}ms"


@mcp.tool()
async def text_to_speech(text: str, language: str = "zh", rate: float = 1.0) -> str:
    """Speak text aloud using text-to-speech.

    Args:
        text: Text to speak
        language: Language code (e.g. 'en', 'zh', 'ja') (default: zh)
        rate: Speech rate, 1.0 is normal (default: 1.0)
    """
    args = ['-l', language, '-r', str(rate), text]
    return termux('termux-tts-speak', args, timeout=60) or f"Speaking: {text[:80]}"


@mcp.tool()
async def get_fingerprint() -> str:
    """Prompt for fingerprint authentication on the device."""
    return format_json(termux('termux-fingerprint', timeout=30))


@mcp.tool()
async def get_screen_brightness() -> str:
    """Get current screen brightness level.

    Requires ADB wireless debugging enabled on Android 12+.
    """
    # Try via ADB if connected (settings command needs system permissions)
    if adb_connected():
        r = run('settings get system screen_brightness', shell=True, timeout=5)
        val = r.get('stdout', '').strip()
        if val:
            return f"Screen brightness: {val}/255"
        # Try dumpsys as fallback
        r = run("dumpsys display | grep -i brightness | head -5", shell=True, timeout=5)
        if r.get('stdout', '').strip():
            return r['stdout']

    # Try getprop (works without ADB on some ROMs)
    r = run('getprop ro.sf.lcd_brightness', shell=True, timeout=3)
    val = r.get('stdout', '').strip()
    if val:
        return f"Screen brightness: {val} (from getprop)"

    return ("Screen brightness: unknown.\n"
            "Wireless Debugging 未启用。需要 ADB 连接才能查询亮度。\n"
            "设置 → 开发者选项 → 无线调试 → 开启\n"
            "然后用 adb_connect 工具连接。")


@mcp.tool()
async def set_screen_brightness(level: int) -> str:
    """Set screen brightness level.

    Requires ADB wireless debugging enabled on Android 12+.

    Args:
        level: Brightness level 0-255
    """
    level = max(0, min(255, level))
    if adb_connected():
        r = run(f'settings put system screen_brightness {level}', shell=True, timeout=5)
        if r['success']:
            return f"Brightness set to {level}/255"
        return f"Error: {r.get('stderr', 'ADB command failed')}"
    return ("无法设置亮度：需要 ADB 无线调试。\n"
            "设置 → 开发者选项 → 无线调试 → 开启\n"
            "然后用 adb_connect 工具连接。")
