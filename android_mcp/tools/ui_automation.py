"""UI Automation: screenshot, tap, swipe, input, keyevent, dump_ui, navigation.

优化日志 v3.1:
  - 新增 screen_on / screen_off / rotate_device / expand_notifications / expand_settings / collapse_panels
  - 新增 annotated_screenshot / dump_ui_with_screenshot（标注截图+交互元素列表）
  - take_screenshot 新增 scale 参数（0.25~1.0），支持截图劣化减少 Token
  - 使用 Pillow 高质量缩放 (LANCZOS)，文件保留全分辨率，仅返回缩略图
  - 所有工具添加 try/except 异常保护（防止崩溃退出）
"""

import base64
import json as _json
import re
import shutil
import io
import random
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import run as sync_run, privileged_shell, privileged_available
from android_mcp.lib.constants import (
    HOME, SDCARD, SDCARD_SHORT,
    TMP_SCREENSHOT, TMP_UI_DUMP, TMP_UI_TAP,
    SCREENSHOT_DEFAULT, UI_DUMP_DEFAULT,
)

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    ImageDraw = None
    ImageFont = None


# ──────────────────────────────────────────────
# Screenshot
# ──────────────────────────────────────────────

def _resize_image_for_base64(image_path: Path, scale: float, max_dim: int = 1080) -> bytes | None:
    """Resize image using Pillow and return as PNG bytes.

    双重约束：
      1. scale 因子缩小（如 scale=0.5 → 50% 尺寸）
      2. max_dim 上限（防止大屏设备 scale=1.0 时仍然超大）

    返回 PNG bytes，失败时返回 None（降级到原图）。
    """
    if not HAS_PILLOW or scale >= 1.0:
        return None

    try:
        img = Image.open(image_path)

        ow, oh = img.size
        nw = max(1, int(ow * scale))
        nh = max(1, int(oh * scale))

        # 同时受 max_dim 约束（取较小值）
        if max(nw, nh) > max_dim:
            ratio = max_dim / max(nw, nh)
            nw = max(1, int(nw * ratio))
            nh = max(1, int(nh * ratio))

        # 只在确实缩小了才 resize（避免不必要的解码）
        if nw >= ow and nh >= oh:
            return None

        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        resized.save(buf, format='PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None


@mcp.tool()
async def take_screenshot(output_path: str = "", scale: float = 1.0) -> str:
    """Take a screenshot of the current phone screen. Returns the screenshot as base64 image data.

    截图劣化：配合 scale 参数（0.25~1.0）可大幅减少 Token 消耗。
    - scale=1.0: 原始分辨率（Token 消耗最大，细节最清晰）
    - scale=0.5:  半尺寸（Token 约 1/4，适合布局识别）
    - scale=0.25: 四分之一尺寸（Token 约 1/16，适合快速预览）
    - 还有 max_dim=1080 上限保护，大屏设备 scale=1.0 也不会爆炸

    Args:
        output_path: Where to save the screenshot file (default: ~/screenshot.png)
        scale: Image scale factor for the returned base64 data (0.1~1.0, default: 1.0).
               Full-resolution file is always saved to disk regardless of this value.
    """
    if not output_path:
        output_path = str(SCREENSHOT_DEFAULT)
    scale = max(0.1, min(1.0, scale))

    try:
        tmp_path = str(TMP_SCREENSHOT)
        sdcard_real = str(TMP_SCREENSHOT)

        if privileged_available():
            r = privileged_shell(f'screencap -p {tmp_path}', timeout=10)
            if r['success']:
                try:
                    shutil.copy2(sdcard_real, output_path)
                except Exception:
                    from android_mcp.lib.utils import adb_connected, adb_shell
                    if adb_connected():
                        sync_run(f'adb pull {tmp_path} {output_path}', shell=True, timeout=10)
        else:
            r = sync_run(f'screencap -p {output_path}', shell=True, timeout=10)

        if not r.get('success'):
            return f"Error taking screenshot: {r.get('error', r.get('stderr', 'Unknown'))}"

        path = Path(output_path)
        if not path.exists() or path.stat().st_size == 0:
            return "Error: Screenshot file was not created or is empty"

        # 生成 base64 数据（支持劣化）
        try:
            if scale < 1.0:
                scaled_bytes = _resize_image_for_base64(path, scale)
                if scaled_bytes is not None:
                    original_size = path.stat().st_size
                    data = base64.b64encode(scaled_bytes).decode('ascii')
                    scaled_size = len(scaled_bytes)
                    ratio = (1 - scaled_size / original_size) * 100 if original_size > 0 else 0
                    size_info = (f"Screenshot saved to {output_path} "
                                 f"(original: {original_size:,} bytes, "
                                 f"scaled {scale:.2f}x: {scaled_size:,} bytes, "
                                 f"saved {ratio:.0f}%)")
                else:
                    # 劣化失败/不需要，回退原图
                    with open(path, 'rb') as f:
                        data = base64.b64encode(f.read()).decode('ascii')
                    size_info = f"Screenshot saved to {output_path} ({path.stat().st_size:,} bytes)"
            else:
                with open(path, 'rb') as f:
                    data = base64.b64encode(f.read()).decode('ascii')
                size_info = f"Screenshot saved to {output_path} ({path.stat().st_size:,} bytes)"

            # 附加劣化提示
            if scale < 1.0:
                size_info += f"\n💡 当前 scale={scale}，如需更高清晰度请用 scale=1.0"

            return f"{size_info}\n\ndata:image/png;base64,{data}"
        except Exception as e:
            return f"Screenshot saved to {output_path} but failed to encode: {e}"
    except Exception as e:
        return f"❌ 截图失败: {e}"


# ──────────────────────────────────────────────
# Screen info — graceful fallback
# ──────────────────────────────────────────────

@mcp.tool()
async def get_screen_size() -> str:
    """Get the phone screen resolution (width x height in pixels).

    Returns known dimensions from device properties if ADB is not connected.
    """
    # Try via privileged shell (rish/adb) first
    if privileged_available():
        r = sync_run('wm size', shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out

    # Fallback: try dumpsys
    if privileged_available():
        r = sync_run("dumpsys display | grep -E 'mDisplayWidth|mDisplayHeight|displayWidth|displayHeight' | head -5",
                shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out

    # Fallback: device properties
    r_w = sync_run('getprop ro.sf.lcd_width', shell=True, timeout=3)
    r_h = sync_run('getprop ro.sf.lcd_height', shell=True, timeout=3)
    w = r_w.get('stdout', '').strip()
    h = r_h.get('stdout', '').strip()
    if w and h:
        return f"Physical size: {w}x{h} (from device properties)"

    r_dpi = sync_run('getprop ro.sf.lcd_density', shell=True, timeout=3)
    dpi = r_dpi.get('stdout', '').strip()

    return (f"Screen size unavailable.\n"
            f"需要 Shizuku 或 ADB 无线调试才能获取精确分辨率。\n"
            f"{f'DPI: {dpi}' if dpi else ''}"
            f"\n💡 推荐用 Shizuku（已在运行），或："
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
    try:
        r = sync_run(f'input tap {x} {y}', shell=True, timeout=5)
        if r['success']:
            return f"Tapped at ({x}, {y})"
        return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"
    except Exception as e:
        return f"❌ 点击失败: {e}"


@mcp.tool()
async def long_press(x: int, y: int, duration_ms: int = 1000) -> str:
    """Long press at specific screen coordinates.

    Args:
        x: X coordinate
        y: Y coordinate
        duration_ms: Press duration in milliseconds (default: 1000)
    """
    r = sync_run(f'input swipe {x} {y} {x} {y} {duration_ms}', shell=True, timeout=10)
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
    try:
        r = sync_run(f'input swipe {x1} {y1} {x2} {y2} {duration_ms}', shell=True, timeout=10)
        if r['success']:
            return f"Swiped from ({x1},{y1}) to ({x2},{y2}) in {duration_ms}ms"
        return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"
    except Exception as e:
        return f"❌ 滑动失败: {e}"


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
    try:
        escaped = text.replace(' ', '%s')
        r = sync_run(f'input text "{escaped}"', shell=True, timeout=10)
        if r['success']:
            return f"Typed: {text}"
        return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"
    except Exception as e:
        return f"❌ 输入失败: {e}"


@mcp.tool()
async def input_chinese_text(text: str) -> str:
    """Input Chinese/Unicode text by copying to clipboard and pasting.

    Args:
        text: The text to input (any language)
    """
    try:
        from android_mcp.lib.utils import run as _run
        from android_mcp.tools.communication import set_clipboard as _set_clip
        await _set_clip(text)
        # Now paste
        r = _run('input keyevent 279', shell=True, timeout=5)
        if r['success']:
            return f"Pasted text: {text}"
        return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"
    except Exception as e:
        return f"❌ 粘贴失败: {e}"


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
    try:
        r = sync_run(f'input keyevent {keycode}', shell=True, timeout=5)
        if r['success']:
            return f"Sent keyevent: {keycode}"
        return f"Error: {r.get('error', r.get('stderr', 'Failed'))}"
    except Exception as e:
        return f"❌ 按键失败: {e}"


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
    tmp_dump = str(TMP_UI_DUMP)
    sdcard_real = str(TMP_UI_DUMP)

    if privileged_available():
        r = privileged_shell(f'uiautomator dump {tmp_dump}', timeout=15)
        if r['success']:
            import shutil
            try:
                shutil.copy2(sdcard_real, output_path)
            except Exception:
                from android_mcp.lib.utils import adb_connected
                if adb_connected():
                    sync_run(f'adb pull {tmp_dump} {output_path}', shell=True, timeout=10)
    else:
        r = sync_run(f'uiautomator dump {output_path}', shell=True, timeout=15)

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
    output_path: str = "",
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
    if not output_path:
        output_path = str(UI_DUMP_DEFAULT)
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
    try:
        dump_path = str(HOME / 'ui_dump_tap.xml')
        tmp_dump = str(TMP_UI_TAP)
        sdcard_real = str(TMP_UI_TAP)

        if privileged_available():
            r = privileged_shell(f'uiautomator dump {tmp_dump}', timeout=15)
            if r.get('success'):
                import shutil
                try:
                    shutil.copy2(sdcard_real, dump_path)
                except Exception:
                    from android_mcp.lib.utils import adb_connected
                    if adb_connected():
                        sync_run(f'adb pull {tmp_dump} {dump_path}', shell=True, timeout=10)
        else:
            r = sync_run(f'uiautomator dump {dump_path}', shell=True, timeout=15)

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
                r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
                found_label = node_text or desc
                return f"Found \"{found_label}\" → tapped at ({cx}, {cy})"

        return f"No UI element found matching \"{text}\". Use dump_ui() to see what's on screen."
    except Exception as e:
        return f"❌ 查找点击失败: {e}"


# ──────────────────────────────────────────────
# Screen Control (亮屏/息屏/旋转/通知栏)
# ──────────────────────────────────────────────

@mcp.tool()
async def screen_on() -> str:
    """Wake the device screen (turn on display).

    如果屏幕已亮，不会产生副作用。适用于设备休眠后先唤醒再操作。
    """
    try:
        # KEYCODE_WAKEUP (224) / KEYCODE_POWER (26)
        r = sync_run('input keyevent 224', shell=True, timeout=5)
        if not r['success']:
            r = sync_run('input keyevent 26', shell=True, timeout=5)
        if r['success']:
            return "✅ 屏幕已唤醒"
        return f"❌ 唤醒失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 唤醒失败: {e}"


@mcp.tool()
async def screen_off() -> str:
    """Turn the device screen off (sleep).

    通过按 Power 键息屏。
    """
    try:
        r = sync_run('input keyevent 26', shell=True, timeout=5)
        if r['success']:
            return "✅ 屏幕已关闭"
        return f"❌ 息屏失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 息屏失败: {e}"


@mcp.tool()
async def rotate_device(rotation: int = 1) -> str:
    """Rotate the screen orientation.

    Args:
        rotation: Rotation value:
            - 0: 竖屏 (Portrait)
            - 1: 横屏 (Landscape)
            - 2: 倒置竖屏 (Reverse Portrait)
            - 3: 倒置横屏 (Reverse Landscape)
    """
    try:
        rotation = max(0, min(3, rotation))
        r = sync_run(f'settings put system user_rotation {rotation}', shell=True, timeout=5)
        if r['success']:
            labels = {0: "竖屏", 1: "横屏", 2: "倒置竖屏", 3: "倒置横屏"}
            return f"✅ 已旋转至: {labels.get(rotation, f'rotation={rotation}')}"
        return f"❌ 旋转失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 旋转失败: {e}"


@mcp.tool()
async def expand_notifications() -> str:
    """Pull down the notification panel (显示通知栏).

    适用于查看通知、点击通知快捷按钮。
    """
    try:
        r = sync_run('cmd statusbar expand-notifications', shell=True, timeout=5)
        if r['success']:
            return "✅ 通知栏已展开"
        # 降级方案：用 swipe 模拟下拉
        r2 = sync_run('input swipe 500 0 500 500 200', shell=True, timeout=5)
        if r2['success']:
            return "✅ 通知栏已展开 (swipe 降级)"
        return f"❌ 展开通知栏失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 展开通知栏失败: {e}"


@mcp.tool()
async def expand_settings() -> str:
    """Pull down the quick settings panel (展开快捷设置).

    从通知栏继续下拉可展开快捷开关面板（WiFi、蓝牙、手电筒等）。
    """
    try:
        r = sync_run('cmd statusbar expand-settings', shell=True, timeout=5)
        if r['success']:
            return "✅ 快捷设置面板已展开"
        # 降级：两次下拉
        sync_run('input swipe 500 0 500 800 400', shell=True, timeout=3)
        r2 = sync_run('input swipe 500 100 500 800 400', shell=True, timeout=3)
        if r2['success']:
            return "✅ 快捷设置已展开 (swipe 降级)"
        return f"❌ 展开快捷设置失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 展开快捷设置失败: {e}"


@mcp.tool()
async def collapse_panels() -> str:
    """Collapse notification/settings panels (收起通知栏/快捷设置).

    执行操作后通常需要收起面板才能继续操作屏幕内容。
    """
    try:
        r = sync_run('cmd statusbar collapse', shell=True, timeout=5)
        if r['success']:
            return "✅ 面板已收起"
        # 降级：从顶部往上滑
        r2 = sync_run('input swipe 500 500 500 0 200', shell=True, timeout=5)
        if r2['success']:
            return "✅ 面板已收起 (swipe 降级)"
        return f"❌ 收起面板失败: {r.get('stderr', 'Unknown')}"
    except Exception as e:
        return f"❌ 收起面板失败: {e}"


# ──────────────────────────────────────────────
# Annotated Screenshot（标注截图 + 交互元素列表）
# ──────────────────────────────────────────────

def _parse_interactive_elements(content: str) -> list[dict]:
    """Parse UI XML and return clickable/interactive elements with coordinates."""
    pattern = (
        r'<node[^>]*?text="([^"]*)"'
        r'[^>]*?resource-id="([^"]*)"'
        r'[^>]*?class="([^"]*)"'
        r'[^>]*?content-desc="([^"]*)"'
        r'[^>]*?clickable="([^"]*)"'
        r'[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    )
    matches = re.findall(pattern, content)

    elements = []
    for text, res_id, cls, desc, clickable, x1, y1, x2, y2 in matches:
        is_interactive = clickable == 'true' or 'Button' in cls or 'EditText' in cls
        if not is_interactive:
            continue
        label = text or desc or cls.split('.')[-1]
        if not label:
            continue
        elements.append({
            'label': label[:60],
            'class': cls.split('.')[-1] if '.' in cls else cls,
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


def _annotate_screenshot(
    screenshot_path: Path,
    elements: list[dict],
    scale: float = 0.7,
) -> bytes | None:
    """Draw bounding boxes + numbers on screenshot.

    返回标注后的 PNG bytes，失败时返回 None。
    """
    if not HAS_PILLOW:
        return None
    try:
        img = Image.open(screenshot_path)
        ow, oh = img.size

        # 缩小到指定 scale 用于标注
        nw = max(1, int(ow * scale))
        nh = max(1, int(oh * scale))
        if nw < ow:
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype('/system/fonts/DroidSans.ttf', 14)
        except (IOError, OSError):
            try:
                font = ImageFont.truetype('NotoSansSC-Regular', 14)
            except (IOError, OSError):
                font = ImageFont.load_default()

        for i, el in enumerate(elements):
            b = el['bounds']
            color = f"#{random.randint(0x33, 0xFF):02x}{random.randint(0x33, 0xFF):02x}{random.randint(0x33, 0xFF):02x}"

            # 缩放坐标
            sx1 = int(b['x1'] * scale)
            sy1 = int(b['y1'] * scale)
            sx2 = int(b['x2'] * scale)
            sy2 = int(b['y2'] * scale)

            # 画边框
            draw.rectangle([sx1, sy1, sx2, sy2], outline=color, width=2)

            # 画编号背景
            num = i + 1
            num_text = str(num)
            bbox = draw.textbbox((0, 0), num_text, font=font)
            tw = bbox[2] - bbox[0] + 6
            th = bbox[3] - bbox[1] + 4
            draw.rectangle([sx1, sy1 - th, sx1 + tw, sy1], fill=color)
            draw.text((sx1 + 3, sy1 - th + 2), num_text, fill='white', font=font)

        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None


@mcp.tool()
async def dump_ui_with_screenshot(
    scale: float = 0.5,
) -> str:
    """Dump UI hierarchy, annotate screenshot with element numbers, and return both.

    一次调用获取完整 UI 状态：
      - 截屏并标注所有可交互元素（带编号边框）
      - 列出元素编号 → 文本 → 坐标映射
      - 适合 LLM 理解屏幕布局后精确操作

    Args:
        scale: Screenshot scale for base64 output (0.25~1.0, default: 0.5).
               越小 Token 消耗越少，但标注文字可能模糊。
    """
    scale = max(0.25, min(1.0, scale))

    try:
        # 1. 截图
        ss_path = str(TMP_SCREENSHOT)
        if privileged_available():
            r = privileged_shell(f'screencap -p {ss_path}', timeout=10)
        else:
            r = sync_run(f'screencap -p {ss_path}', shell=True, timeout=10)
        if not r.get('success'):
            return f"❌ 截图失败: {r.get('error', 'Unknown')}"

        # 2. Dump UI
        dump_path = str(TMP_UI_DUMP)
        if privileged_available():
            r2 = privileged_shell(f'uiautomator dump {dump_path}', timeout=15)
        else:
            r2 = sync_run(f'uiautomator dump {dump_path}', shell=True, timeout=15)
        if not r2.get('success'):
            return f"❌ UI dump 失败: {r2.get('error', 'Unknown')}"

        # 3. 解析元素
        content = Path(UI_DUMP_DEFAULT if dump_path == str(UI_DUMP_DEFAULT) else dump_path)
        if not content.exists():
            # 尝试从 sdcard 临时文件读
            content = Path(ss_path.replace('screenshot', 'ui_dump').replace('.png', '.xml'))
            if not content.exists():
                return "❌ 无法读取 UI dump 文件"

        xml_content = content.read_text(encoding='utf-8')
        elements = _parse_interactive_elements(xml_content)

        # 4. 生成标注截图
        annotated_bytes = _annotate_screenshot(Path(ss_path), elements, scale=scale)

        if annotated_bytes is None:
            return "❌ 标注截图失败（Pillow 不可用？）"

        data = base64.b64encode(annotated_bytes).decode('ascii')

        # 5. 格式化元素列表
        lines = [f"📱 共 {len(elements)} 个可交互元素:\n"]
        for i, el in enumerate(elements):
            num = i + 1
            cx, cy = el['center']['x'], el['center']['y']
            lines.append(f"  {num:>2}. [{el['class']}] \"{el['label']}\" → tap({cx}, {cy})")

        lines.append("\n💡 截图上每个元素已标注编号，按照编号点击即可。")
        lines.append("📌 点击用 tap_screen(x, y) 工具。")

        return (
            f"{chr(10).join(lines)}\n\n"
            f"data:image/png;base64,{data}"
        )
    except Exception as e:
        return f"❌ 标注截图失败: {e}"


# ──────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────

@mcp.tool()
async def go_home() -> str:
    """Press the Home button to go to the home screen."""
    try:
        r = sync_run('input keyevent 3', shell=True, timeout=5)
        return "Home button pressed" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"
    except Exception as e:
        return f"❌ 返回桌面失败: {e}"


@mcp.tool()
async def go_back() -> str:
    """Press the Back button."""
    try:
        r = sync_run('input keyevent 4', shell=True, timeout=5)
        return "Back button pressed" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"
    except Exception as e:
        return f"❌ 返回失败: {e}"


@mcp.tool()
async def open_recent_apps() -> str:
    """Open the recent apps / app switcher."""
    try:
        r = sync_run('input keyevent 187', shell=True, timeout=5)
        return "Recent apps opened" if r['success'] else f"Error: {r.get('stderr', 'Failed')}"
    except Exception as e:
        return f"❌ 打开最近应用失败: {e}"
