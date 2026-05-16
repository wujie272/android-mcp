"""UI Automation: screenshot, tap, swipe, input, keyevent, dump_ui, navigation."""

import base64
import re
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import run, adb_connected, adb_shell, HOME


# ──────────────────────────────────────────────
# Screenshot
# ──────────────────────────────────────────────

@mcp.tool()
async def take_screenshot(output_path: str = "/data/data/com.termux/files/home/screenshot.png") -> str:
    """Take a screenshot of the current phone screen. Returns the screenshot as base64 image data.

    Args:
        output_path: Where to save the screenshot file
    """
    tmp_path = '/sdcard/mcp_screenshot.png'
    if adb_connected():
        r = adb_shell(f'screencap -p {tmp_path}', timeout=10)
        if r['success']:
            import shutil
            sdcard_real = '/storage/emulated/0/mcp_screenshot.png'
            try:
                shutil.copy2(sdcard_real, output_path)
            except Exception:
                run(f'adb pull {tmp_path} {output_path}', shell=True, timeout=10)
    else:
        r = run(f'screencap -p {output_path}', shell=True, timeout=10)

    if not r.get('success'):
        return f"Error taking screenshot: {r.get('error', r.get('stderr', 'Unknown'))}"

    path = Path(output_path)
    if not path.exists() or path.stat().st_size == 0:
        return "Error: Screenshot file was not created or is empty"

    try:
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"Screenshot saved to {output_path} ({path.stat().st_size:,} bytes)\n\ndata:image/png;base64,{data}"
    except Exception as e:
        return f"Screenshot saved to {output_path} but failed to encode: {e}"


# ──────────────────────────────────────────────
# Screen info — graceful fallback
# ──────────────────────────────────────────────

@mcp.tool()
async def get_screen_size() -> str:
    """Get the phone screen resolution (width x height in pixels).

    Returns known dimensions from device properties if ADB is not connected.
    """
    # Try via ADB first
    if adb_connected():
        r = run('wm size', shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out

    # Fallback: try dumpsys
    if adb_connected():
        r = run("dumpsys display | grep -E 'mDisplayWidth|mDisplayHeight|displayWidth|displayHeight' | head -5",
                shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out

    # Fallback: device properties
    r_w = run('getprop ro.sf.lcd_width', shell=True, timeout=3)
    r_h = run('getprop ro.sf.lcd_height', shell=True, timeout=3)
    w = r_w.get('stdout', '').strip()
    h = r_h.get('stdout', '').strip()
    if w and h:
        return f"Physical size: {w}x{h} (from device properties)"

    r_dpi = run('getprop ro.sf.lcd_density', shell=True, timeout=3)
    dpi = r_dpi.get('stdout', '').strip()

    return (f"Screen size unavailable.\n"
            f"需要 ADB 无线调试才能获取精确分辨率。\n"
            f"{f'DPI: {dpi}' if dpi else ''}"
            f"\n设置 → 开发者选项 → 无线调试 → 开启"
            f"\n然后用 adb_connect 工具连接。")


# ──────────────────────────────────────────────
# Tap / Swipe / Long Press
# ──────────────────────────────────────────────

@mcp.tool()
async def tap_screen(x: int, y: int) -> str:
    """Tap the screen at specific coordinates.

    Use take_screenshot + dump_ui first to find the right coordinates.

    Args:
        x: X coordinate (pixels from left)
        y: Y coordinate (pixels from top)
    """
    r = run(f'input tap {x} {y}', shell=True, timeout=5)
    if r['success']:
        return f"Tapped at ({x}, {y})"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


@mcp.tool()
async def long_press(x: int, y: int, duration_ms: int = 1000) -> str:
    """Long press at specific screen coordinates.

    Args:
        x: X coordinate
        y: Y coordinate
        duration_ms: Press duration in milliseconds (default: 1000)
    """
    r = run(f'input swipe {x} {y} {x} {y} {duration_ms}', shell=True, timeout=10)
    if r['success']:
        return f"Long pressed at ({x}, {y}) for {duration_ms}ms"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


@mcp.tool()
async def swipe_screen(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """Swipe on the screen from one point to another.

    Args:
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
        duration_ms: Swipe duration in milliseconds (default: 300)
    """
    r = run(f'input swipe {x1} {y1} {x2} {y2} {duration_ms}', shell=True, timeout=10)
    if r['success']:
        return f"Swiped from ({x1},{y1}) to ({x2},{y2}) in {duration_ms}ms"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


# ──────────────────────────────────────────────
# Text Input
# ──────────────────────────────────────────────

@mcp.tool()
async def input_text(text: str) -> str:
    """Type text into the currently focused input field.

    Note: This works best with ASCII text. For Chinese/Unicode text,
    use set_clipboard + input_keyevent(keycode='279') (paste) instead.

    Args:
        text: Text to type (spaces are supported)
    """
    escaped = text.replace(' ', '%s')
    r = run(f'input text "{escaped}"', shell=True, timeout=10)
    if r['success']:
        return f"Typed: {text}"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


@mcp.tool()
async def input_chinese_text(text: str) -> str:
    """Input Chinese/Unicode text by copying to clipboard and pasting.

    Args:
        text: The text to input (any language)
    """
    from android_mcp.lib.utils import run as _run
    # Use in-memory clipboard fallback (via set_clipboard which has fallback)
    from android_mcp.tools.communication import set_clipboard as _set_clip
    await _set_clip(text)
    # Now paste
    r = _run('input keyevent 279', shell=True, timeout=5)
    if r['success']:
        return f"Pasted text: {text}"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


@mcp.tool()
async def input_keyevent(keycode: str) -> str:
    """Send a key event to the phone.

    Args:
        keycode: Android keycode name or number. Common ones:
            - '3' / 'KEYCODE_HOME' = Home
            - '4' / 'KEYCODE_BACK' = Back
            - '26' / 'KEYCODE_POWER' = Power
            - '66' / 'KEYCODE_ENTER' = Enter
            - '67' / 'KEYCODE_DEL' = Backspace
            - '61' / 'KEYCODE_TAB' = Tab
            - '187' / 'KEYCODE_APP_SWITCH' = Recent apps
            - '279' / 'KEYCODE_PASTE' = Paste
            - '84' / 'KEYCODE_SEARCH' = Search
    """
    r = run(f'input keyevent {keycode}', shell=True, timeout=5)
    if r['success']:
        return f"Sent keyevent: {keycode}"
    return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"


# ──────────────────────────────────────────────
# UI Dump — 3 output modes
# ──────────────────────────────────────────────

def _parse_ui_xml(content: str) -> list[dict]:
    """Parse UI XML into structured element list."""
    patterns = [
        r'text="([^"]*)"[^>]*?resource-id="([^"]*)"[^>]*?class="([^"]*)"[^>]*?content-desc="([^"]*)"[^>]*?clickable="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'text="([^"]*)".*?resource-id="([^"]*)".*?class="([^"]*)".*?content-desc="([^"]*)".*?clickable="([^"]*)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            elements = []
            for text, res_id, cls, desc, clickable, x1, y1, x2, y2 in matches:
                elements.append({
                    'text': text,
                    'resource_id': res_id,
                    'class': cls.split('.')[-1] if '.' in cls else cls,
                    'content_desc': desc,
                    'clickable': clickable == 'true',
                    'bounds': {
                        'x1': int(x1), 'y1': int(y1),
                        'x2': int(x2), 'y2': int(y2),
                    },
                    'center': {
                        'x': (int(x1) + int(x2)) // 2,
                        'y': (int(y1) + int(y2)) // 2,
                    },
                })
            return elements
    return []


def _dump_ui_xml(output_path: str) -> str | None:
    """Dump UI XML, supply raw XML or None on error."""
    tmp_dump = '/sdcard/mcp_ui_dump.xml'
    sdcard_real = '/storage/emulated/0/mcp_ui_dump.xml'

    if adb_connected():
        r = adb_shell(f'uiautomator dump {tmp_dump}', timeout=15)
        if r['success']:
            import shutil
            try:
                shutil.copy2(sdcard_real, output_path)
            except Exception:
                run(f'adb pull {tmp_dump} {output_path}', shell=True, timeout=10)
    else:
        r = run(f'uiautomator dump {output_path}', shell=True, timeout=15)

    if not r.get('success'):
        return None

    path = Path(output_path)
    if not path.exists():
        return None

    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return None


@mcp.tool()
async def dump_ui(
    output_path: str = "/data/data/com.termux/files/home/ui_dump.xml",
    mode: str = "summary",
) -> str:
    """Dump the current UI hierarchy. Three output modes for different needs.

    Args:
        output_path: Where to save the full XML
        mode: Output format:
            'summary' — Only clickable/interactive elements with coordinates (token-efficient, default)
            'full'    — All UI elements with full details
            'json'    — Structured JSON for programmatic processing
    """
    content = _dump_ui_xml(output_path)
    if content is None:
        return "Error: Failed to dump UI hierarchy. Make sure ADB is connected."

    if mode == 'full':
        return f"Full UI XML saved to {output_path}\n\nFile size: {len(content):,} chars\nUse mode='summary' for a compact view."

    elements = _parse_ui_xml(content)

    if mode == 'json':
        import json as _json
        clean = []
        for el in elements:
            clean.append({
                'text': el['text'],
                'class': el['class'],
                'desc': el['content_desc'],
                'clickable': el['clickable'],
                'center': el['center'],
                'bounds': el['bounds'],
            })
        return _json.dumps(clean, indent=2, ensure_ascii=False)

    # summary mode
    interactive = [el for el in elements if el['clickable']]
    text_inputs = [el for el in elements if 'EditText' in el['class']]

    lines = [f"📱 Screen elements ({len(elements)} total, {len(interactive)} interactive):\n"]

    if interactive:
        lines.append("── Clickable ──")
        for el in interactive:
            label = el['text'] or el['content_desc'] or f"({el['class']})"
            cx, cy = el['center']['x'], el['center']['y']
            lines.append(f"  • \"{label[:50]}\" → tap({cx}, {cy})")

    if text_inputs:
        lines.append("\n── Text Inputs ──")
        for el in text_inputs:
            hint = el['text'] or el['content_desc'] or 'input field'
            cx, cy = el['center']['x'], el['center']['y']
            lines.append(f"  • \"{hint[:40]}\" → tap({cx}, {cy}) to focus")

    lines.append(f"\n💡 Tip: Use mode='full' for raw XML, mode='json' for structured data.")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Find & Tap
# ──────────────────────────────────────────────

@mcp.tool()
async def find_and_tap(text: str) -> str:
    """Find a UI element by its text and tap on it.

    Combines dump_ui + tap_screen: dumps the UI hierarchy, finds an element
    matching the given text, and taps its center.

    Args:
        text: Text to search for in UI elements (partial match, case-insensitive)
    """
    dump_path = f"{HOME}/ui_dump_tap.xml"
    tmp_dump = '/sdcard/mcp_ui_dump_tap.xml'
    sdcard_real = '/storage/emulated/0/mcp_ui_dump_tap.xml'

    if adb_connected():
        r = adb_shell(f'uiautomator dump {tmp_dump}', timeout=15)
        if r.get('success'):
            import shutil
            try:
                shutil.copy2(sdcard_real, dump_path)
            except Exception:
                run(f'adb pull {tmp_dump} {dump_path}', shell=True, timeout=10)
    else:
        r = run(f'uiautomator dump {dump_path}', shell=True, timeout=15)

    if not r.get('success'):
        return f"Error dumping UI: {r.get('error', r.get('stderr', 'Unknown'))}"

    path = Path(dump_path)
    if not path.exists():
        return "Error: UI dump file was not created"

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading dump: {e}"

    pattern = r'text="([^"]*)".*?content-desc="([^"]*)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    matches = re.findall(pattern, content)

    text_lower = text.lower()
    for node_text, desc, x1, y1, x2, y2 in matches:
        if text_lower in node_text.lower() or text_lower in desc.lower():
            cx = (int(x1) + int(x2)) // 2
            cy = (int(y1) + int(y2)) // 2
            r = run(f'input tap {cx} {cy}', shell=True, timeout=5)
            found_label = node_text or desc
            return f"Found \"{found_label}\" → tapped at ({cx}, {cy})"

    return f"No UI element found matching \"{text}\". Use dump_ui() to see what's on screen."


# ──────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────

@mcp.tool()
async def go_home() -> str:
    """Press the Home button to go to the home screen."""
    r = run('input keyevent 3', shell=True, timeout=5)
    return "Home button pressed" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"


@mcp.tool()
async def go_back() -> str:
    """Press the Back button."""
    r = run('input keyevent 4', shell=True, timeout=5)
    return "Back button pressed" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"


@mcp.tool()
async def open_recent_apps() -> str:
    """Open the recent apps / app switcher."""
    r = run('input keyevent 187', shell=True, timeout=5)
    return "Recent apps opened" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"
