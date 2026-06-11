"""System control: volume, torch, vibrate, TTS, brightness, fingerprint."""

from termux_mcp.app import mcp
from termux_mcp.lib.utils import termux, format_json, run, privileged_available, privileged_shell


@mcp.tool()
async def set_volume(stream: str, volume: int) -> str:
    """Set volume. stream: music/ring/alarm/notification/system/call. volume: 0-15."""
    return termux('termux-volume', [str(stream), str(volume)]) or f"Volume '{stream}' set to {volume}"


@mcp.tool()
async def get_volume() -> str:
    """Get current volume levels for all audio streams."""
    return format_json(termux('termux-volume'))


@mcp.tool()
async def toggle_torch(enabled: bool = True) -> str:
    """Toggle flashlight on/off."""
    return termux('termux-torch', ['on' if enabled else 'off']) or f"Torch {'on' if enabled else 'off'}"


@mcp.tool()
async def vibrate(duration_ms: int = 1000, force: bool = False) -> str:
    """Vibrate phone. force=True to vibrate in silent mode."""
    args = ['-d', str(duration_ms)]
    if force:
        args.append('-f')
    return termux('termux-vibrate', args) or f"Vibrated {duration_ms}ms"


@mcp.tool()
async def text_to_speech(text: str, language: str = "zh", rate: float = 1.0) -> str:
    """Speak text aloud via TTS."""
    return termux('termux-tts-speak', ['-l', language, '-r', str(rate), text], timeout=60) or f"Speaking: {text[:80]}"


@mcp.tool()
async def get_fingerprint() -> str:
    """Prompt for fingerprint authentication."""
    return format_json(termux('termux-fingerprint', timeout=30))


@mcp.tool()
async def get_screen_brightness() -> str:
    """Get screen brightness (requires Shizuku/ADB on Android 12+)."""
    if privileged_available():
        r = run('settings get system screen_brightness', shell=True, timeout=5)
        val = r.get('stdout', '').strip()
        if val:
            return f"Brightness: {val}/255"
        r = run("dumpsys display | grep -i brightness | head -5", shell=True, timeout=5)
        if r.get('stdout', '').strip():
            return r['stdout']
    r = run('getprop ro.sf.lcd_brightness', shell=True, timeout=3)
    val = r.get('stdout', '').strip()
    if val:
        return f"Brightness: {val} (getprop)"
    return ("无法获取亮度。需要 Shizuku 或 ADB 无线调试。\n"
            "💡 确保 Shizuku 已启动，或开启无线调试后 adb_connect。")


@mcp.tool()
async def set_screen_brightness(level: int) -> str:
    """Set screen brightness (0-255). Requires Shizuku/ADB."""
    level = max(0, min(255, level))
    if privileged_available():
        r = run(f'settings put system screen_brightness {level}', shell=True, timeout=5)
        if r['success']:
            return f"Brightness set to {level}/255"
        return f"Error: {r.get('stderr', 'Failed')}"
    return "无法设置亮度。需要 Shizuku 或 ADB。"