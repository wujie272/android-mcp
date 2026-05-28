"""UI automation: screenshot, tap, swipe, input, keyevent, dump_ui, navigation."""

import base64
import json as _json
import shutil
import io
from pathlib import Path
from android_mcp.app import mcp
from android_mcp.lib.utils import run as sync_run, privileged_shell, privileged_available
from android_mcp.lib.utils import get_cached_ui_dump, set_ui_dump_cache, invalidate_ui_cache
from android_mcp.lib.constants import HOME, SDCARD, SDCARD_SHORT
from android_mcp.lib.constants import TMP_SCREENSHOT, TMP_UI_DUMP, TMP_UI_TAP
from android_mcp.lib.constants import SCREENSHOT_DEFAULT, UI_DUMP_DEFAULT

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def _resize_for_b64(image_path: Path, scale: float, max_dim: int = 1080):
    """Resize image with Pillow, return PNG bytes or None."""
    if not HAS_PILLOW or scale >= 1.0:
        return None
    try:
        img = Image.open(image_path)
        ow, oh = img.size
        nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
        if max(nw, nh) > max_dim:
            ratio = max_dim / max(nw, nh)
            nw, nh = max(1, int(nw * ratio)), max(1, int(nh * ratio))
        if nw >= ow and nh >= oh:
            return None
        buf = io.BytesIO()
        img.resize((nw, nh), Image.Resampling.LANCZOS).save(buf, format='PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None


# ── Screenshot ──

@mcp.tool()
async def take_screenshot(output_path: str = "", scale: float = 1.0) -> str:
    """Take screenshot. Returns base64 image data.

    scale (0.25~1.0): lower = fewer tokens. max_dim=1080 protects large screens.
    Full-resolution file always saved to disk regardless of scale.
    """
    if not output_path:
        output_path = str(SCREENSHOT_DEFAULT)
    scale = max(0.1, min(1.0, scale))

    try:
        tmp = str(TMP_SCREENSHOT)
        if privileged_available():
            r = privileged_shell(f'screencap -p {tmp}', timeout=10)
            if r['success']:
                try:
                    shutil.copy2(tmp, output_path)
                except Exception:
                    from android_mcp.lib.utils import adb_connected, adb_shell
                    if adb_connected():
                        sync_run(f'adb pull {tmp} {output_path}', shell=True, timeout=10)
        else:
            r = sync_run(f'screencap -p {output_path}', shell=True, timeout=10)
        if not r.get('success'):
            return f"Error: {r.get('error', r.get('stderr', 'Unknown'))}"
        path = Path(output_path)
        if not path.exists() or path.stat().st_size == 0:
            return "Error: Screenshot file empty"

        try:
            if scale < 1.0:
                scaled = _resize_for_b64(path, scale)
                if scaled is not None:
                    orig_sz = path.stat().st_size
                    data = base64.b64encode(scaled).decode('ascii')
                    saved = (1 - len(scaled) / orig_sz) * 100 if orig_sz else 0
                    info = (f"Screenshot: {output_path} (orig {orig_sz:,}B, "
                            f"scale {scale:.2f}x: {len(scaled):,}B, saved {saved:.0f}%)")
                else:
                    with open(path, 'rb') as f:
                        data = base64.b64encode(f.read()).decode('ascii')
                    info = f"Screenshot: {output_path} ({path.stat().st_size:,}B)"
            else:
                with open(path, 'rb') as f:
                    data = base64.b64encode(f.read()).decode('ascii')
                info = f"Screenshot: {output_path} ({path.stat().st_size:,}B)"
            if scale < 1.0:
                info += "\n💡 scale=1.0 for full resolution"
            return f"{info}\n\ndata:image/png;base64,{data}"
        except Exception as e:
            return f"Screenshot saved to {output_path} but encode failed: {e}"
    except Exception as e:
        return f"❌ {e}"


# ── Screen size ──

@mcp.tool()
async def get_screen_size() -> str:
    """Get screen resolution (width x height)."""
    if privileged_available():
        r = sync_run('wm size', shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out
        r = sync_run("dumpsys display | grep -E 'mDisplayWidth|mDisplayHeight' | head -5", shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out
    r_w = sync_run('getprop ro.sf.lcd_width', shell=True, timeout=3)
    r_h = sync_run('getprop ro.sf.lcd_height', shell=True, timeout=3)
    w, h = r_w.get('stdout', '').strip(), r_h.get('stdout', '').strip()
    if w and h:
        return f"Physical: {w}x{h} (from properties)"
    return "Need Shizuku or ADB to get screen size."


# ── Tap / Swipe / Long Press ──

@mcp.tool()
async def tap_screen(x: int, y: int) -> str:
    """Tap at (x, y). Use screenshot + dump_ui first to find coordinates."""
    try:
        r = sync_run(f'input tap {x} {y}', shell=True, timeout=5)
        invalidate_ui_cache()
        return f"Tapped ({x}, {y})" if r['success'] else f"Error: {r.get('error', 'Failed')}"
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def long_press(x: int, y: int, duration_ms: int = 1000) -> str:
    """Long press at (x, y) for duration_ms."""
    r = sync_run(f'input swipe {x} {y} {x} {y} {duration_ms}', shell=True, timeout=10)
    invalidate_ui_cache()
    return f"Long pressed ({x},{y}) {duration_ms}ms" if r['success'] else f"Error: {r.get('error', 'Failed')}"


@mcp.tool()
async def swipe_screen(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """Swipe from (x1,y1) to (x2,y2). duration_ms controls speed."""
    try:
        r = sync_run(f'input swipe {x1} {y1} {x2} {y2} {duration_ms}', shell=True, timeout=10)
        invalidate_ui_cache()
        return f"Swiped ({x1},{y1})→({x2},{y2}) {duration_ms}ms" if r['success'] else f"Error: {r.get('error', 'Failed')}"
    except Exception as e:
        return f"❌ {e}"


# ── Text Input ──

@mcp.tool()
async def input_text(text: str) -> str:
    """Type ASCII text into focused field. For Chinese, use set_clipboard + pasting."""
    try:
        r = sync_run(f'input text "{text.replace(" ", "%s")}"', shell=True, timeout=10)
        invalidate_ui_cache()
        return f"Typed: {text}" if r['success'] else f"Error: {r.get('error', 'Failed')}"
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def input_chinese_text(text: str) -> str:
    """Input Chinese/Unicode via clipboard paste."""
    from android_mcp.tools.communication import set_clipboard
    await set_clipboard(text)
    r = sync_run('input keyevent 279', shell=True, timeout=5)  # KEYCODE_PASTE
    invalidate_ui_cache()
    return f"Pasted: {text}" if r['success'] else f"Error: {r.get('error', 'Failed')}"


@mcp.tool()
async def input_keyevent(keycode: str) -> str:
    """Send key event (e.g. '3'=Home, '4'=Back, '26'=Power, '66'=Enter, '67'=Del, '187'=Recent)."""
    invalidate_ui_cache()
    r = sync_run(f'input keyevent {keycode}', shell=True, timeout=5)
    return f"Key {keycode} sent" if r['success'] else f"Error: {r.get('error', 'Failed')}"


# ── Navigation ──

@mcp.tool()
async def go_home() -> str:
    """Press Home button."""
    return await input_keyevent('3')


@mcp.tool()
async def go_back() -> str:
    """Press Back button."""
    return await input_keyevent('4')


@mcp.tool()
async def open_recent_apps() -> str:
    """Open recent apps switcher."""
    return await input_keyevent('187')


@mcp.tool()
async def screen_on() -> str:
    """Wake screen (turn on display)."""
    r = sync_run('input keyevent 26', shell=True, timeout=5)
    invalidate_ui_cache()
    return "Screen on" if r['success'] else f"Error: {r.get('error', 'Failed')}"


@mcp.tool()
async def screen_off() -> str:
    """Turn screen off (sleep)."""
    return await input_keyevent('26')  # Power toggles, so same key


@mcp.tool()
async def rotate_device(rotation: int) -> str:
    """Rotate screen: 0=portrait, 1=landscape, 2=reverse portrait, 3=reverse landscape."""
    try:
        r = sync_run(f'content insert --uri content://settings/system '
                     f'--bind name:s:user_rotation --bind value:i:{rotation}', shell=True, timeout=5)
        invalidate_ui_cache()
        if not r['success']:
            r = sync_run(f'settings put system user_rotation {rotation}', shell=True, timeout=5)
        return f"Rotation set to {rotation}" if r['success'] else f"Error: {r.get('error', 'Failed')}"
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def expand_notifications() -> str:
    """Pull down notification panel."""
    r = sync_run('cmd statusbar expand-notifications 2>/dev/null || '
                 'input swipe 500 0 500 500 200', shell=True, timeout=5)
    return "Notifications expanded" if r['success'] else f"Error: {r.get('error', 'Failed')}"


@mcp.tool()
async def expand_settings() -> str:
    """Pull down quick settings panel."""
    r = sync_run('cmd statusbar expand-settings 2>/dev/null || '
                 'input swipe 500 0 500 1000 300', shell=True, timeout=5)
    return "Settings expanded" if r['success'] else f"Error: {r.get('error', 'Failed')}"


@mcp.tool()
async def collapse_panels() -> str:
    """Collapse notification/settings panels."""
    r = sync_run('cmd statusbar collapse 2>/dev/null || '
                 'input swipe 500 1000 500 0 300', shell=True, timeout=5)
    invalidate_ui_cache()
    return "Panels collapsed" if r['success'] else f"Error: {r.get('error', 'Failed')}"


# ── UI Dump ──

def _dump_ui_xml(output: str) -> str | None:
    tmp = str(TMP_UI_DUMP)
    try:
        if privileged_available():
            r = privileged_shell(f'uiautomator dump {tmp}', timeout=15)
        else:
            r = sync_run(f'uiautomator dump {tmp}', shell=True, timeout=15)
        if not r.get('success'):
            return None
        path = Path(tmp)
        if not path.exists():
            return None
        content = path.read_text(encoding='utf-8')
        set_ui_dump_cache(content)
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return content
    except Exception as e:
        return None


def _parse_ui_summary(xml_content: str, max_nodes: int = 100) -> list[dict]:
    """Parse XML to list of clickable/interactive elements."""
    try:
        from xml.etree import ElementTree
        root = ElementTree.fromstring(xml_content)
    except Exception:
        return []

    nodes = []

    def walk(el):
        if len(nodes) >= max_nodes:
            return
        attrs = dict(el.attrib)
        clickable = attrs.get('clickable', 'false') == 'true'
        text = attrs.get('text', '') or attrs.get('content-desc', '') or ''
        bounds_str = attrs.get('bounds', '[0,0][0,0]')

        # Only include nodes with meaningful content or interactivity
        if text.strip() or clickable:
            try:
                parts = bounds_str.replace('[', '').replace(']', ',').split(',')
                x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                x, y = (x1 + x2) // 2, (y1 + y2) // 2
            except (ValueError, IndexError):
                x, y = 0, 0

            rid = attrs.get('resource-id', '')
            short_rid = rid.split('/')[-1] if '/' in rid else rid
            cls = attrs.get('class', '')
            short_cls = cls.rsplit('.', 1)[-1] if '.' in cls else cls

            nodes.append({
                'index': attrs.get('index', '0'),
                'text': text[:80],
                'resource_id': short_rid,
                'class': short_cls,
                'clickable': clickable,
                'x': x, 'y': y,
                'bounds': f'[{x1},{y1}][{x2},{y2}]',
                'focused': attrs.get('focused', 'false') == 'true',
                'checked': attrs.get('checked', 'false') == 'true',
                'selected': attrs.get('selected', 'false') == 'true',
            })

        for child in el:
            walk(child)

    walk(root)
    return nodes


@mcp.tool()
async def dump_ui(output_path: str = "", mode: str = "summary") -> str:
    """Dump UI hierarchy. mode: 'summary' (clickable elements, token-efficient),
    'full' (all details), 'json' (structured)."""
    if not output_path:
        output_path = str(UI_DUMP_DEFAULT)
    target = Path(output_path)

    # Check cache for summary mode
    if mode == "summary":
        cached = get_cached_ui_dump()
        if cached:
            nodes = _parse_ui_summary(cached)
            if nodes:
                return _format_summary(nodes)

    xml = _dump_ui_xml(str(target))
    if xml is None:
        return "❌ UI dump failed. Need Shizuku or ADB."

    if mode == "summary":
        nodes = _parse_ui_summary(xml)
        return _format_summary(nodes) if nodes else "No interactive elements found."
    elif mode == "json":
        nodes = _parse_ui_summary(xml, max_nodes=500)
        return _json.dumps(nodes, indent=2, ensure_ascii=False)
    else:
        return xml


def _format_summary(nodes: list[dict]) -> str:
    lines = [f"📱 UI Elements ({len(nodes)}):\n"]
    for i, n in enumerate(nodes):
        label = n['text'] or f"<{n['class']}>" or '(empty)'
        rid = f" [{n['resource_id']}]" if n['resource_id'] else ""
        click = "🖱️" if n['clickable'] else "  "
        focus = "📌" if n['focused'] else "  "
        lines.append(f"  [{i}] {click}{focus} \"{label}\" → ({n['x']}, {n['y']}){rid}")
    lines.append("\n💡 Use click_by_text() or tap_screen(x,y) to interact.")
    return "\n".join(lines)


# ── Dump UI with Screenshot ──

@mcp.tool()
async def dump_ui_with_screenshot(scale: float = 0.5) -> str:
    """Dump UI + annotated screenshot with element numbers.

    One call gets full UI state: numbered screenshot + element list with coordinates.
    """
    from PIL import ImageDraw, ImageFont
    import random

    scale = max(0.25, min(1.0, scale))
    xml = _dump_ui_xml(str(UI_DUMP_DEFAULT))
    if xml is None:
        return "❌ UI dump failed."

    nodes = _parse_ui_summary(xml, max_nodes=60)
    if not nodes:
        return "No interactive elements found."

    # Take screenshot with same scale
    ss_path = str(SCREENSHOT_DEFAULT)
    if privileged_available():
        privileged_shell(f'screencap -p {TMP_SCREENSHOT}', timeout=10)
        try:
            shutil.copy2(str(TMP_SCREENSHOT), ss_path)
        except Exception:
            pass
    else:
        sync_run(f'screencap -p {ss_path}', shell=True, timeout=10)

    # Annotate with Pillow
    annotated_b64 = ""
    if HAS_PILLOW:
        try:
            img = Image.open(ss_path)
            ow, oh = img.size
            nw = max(1, int(ow * scale))
            nh = max(1, int(oh * scale))
            if max(nw, nh) > 1080:
                ratio = 1080 / max(nw, nh)
                nw, nh = max(1, int(nw * ratio)), max(1, int(oh * ratio * scale))
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(img)

            # Color palette
            colors = ['#FF0000', '#00AA00', '#0000FF', '#FF8800', '#8800FF',
                      '#00AAAA', '#AA00AA', '#AAAA00', '#FF4488', '#4488FF']

            for i, n in enumerate(nodes[:60]):
                # Scale coordinates
                bx = [int(v) for v in n['bounds'].replace('[', ' ').replace(']', ' ').replace(',', ' ').split() if v.strip()]
                if len(bx) >= 4:
                    x1, y1, x2, y2 = bx
                    sx1, sy1 = int(x1 * nw / ow), int(y1 * nh / oh)
                    sx2, sy2 = int(x2 * nw / ow), int(y2 * nh / oh)
                    color = colors[i % len(colors)]
                    # Draw border
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            draw.rectangle([sx1+dx, sy1+dy, sx2+dx, sy2+dy], outline='#000000', width=1)
                    draw.rectangle([sx1, sy1, sx2, sy2], outline=color, width=2)
                    # Draw number
                    cx, cy = (sx1 + sx2) // 2, sy1 - 5
                    draw.text((cx - 5, max(0, cy - 10)), str(i), fill=color)

            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            annotated_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception as e:
            return f"❌ Annotation failed: {e}"

    # Build text summary
    lines = [f"📱 UI Elements ({len(nodes)} shown):\n"]
    for i, n in enumerate(nodes[:60]):
        label = n['text'] or f"<{n['class']}>" or '(empty)'
        rid = f" id:{n['resource_id']}" if n['resource_id'] else ""
        click = "🖱️" if n['clickable'] else "  "
        lines.append(f"  [{i}] {click} \"{label}\" → ({n['x']}, {n['y']}){rid}")
    lines.append("\n💡 Use click_by_text() or tap_screen(x,y) to interact.")

    text = "\n".join(lines)
    if annotated_b64:
        return f"{text}\n\ndata:image/png;base64,{annotated_b64}"
    return text