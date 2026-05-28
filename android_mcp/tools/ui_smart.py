"""Smart UI element finding: click_by_text, click_by_id, find_element, wait_for_element, get_ui_state.

Based on Shizuku uiautomator dump — no uiautomator2 driver needed."""

import time as _time
import logging
from xml.etree import ElementTree
from pathlib import Path
from android_mcp.app import mcp
from android_mcp.lib.utils import run as sync_run, privileged_shell, privileged_available
from android_mcp.lib.utils import get_cached_ui_dump, set_ui_dump_cache, invalidate_ui_cache
from android_mcp.lib.constants import HOME, TMP_UI_DUMP, TMP_SCREENSHOT

logger = logging.getLogger('android-mcp.ui_smart')


def _dump_xml() -> str | None:
    """Dump UI XML. Uses 300ms TTL cache — repeated calls skip dump."""
    cached = get_cached_ui_dump()
    if cached is not None:
        return cached

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
        return content
    except Exception as e:
        logger.warning(f"dump XML: {e}")
        return None


def _parse_nodes(xml: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(xml)
    except Exception:
        return []
    nodes = []

    def walk(el):
        a = dict(el.attrib)
        bounds = a.get('bounds', '[0,0][0,0]')
        try:
            parts = bounds.replace('[', '').replace(']', ',').split(',')
            x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        except (ValueError, IndexError):
            x1 = y1 = x2 = y2 = 0

        node = {
            'text': a.get('text', ''),
            'resource_id': a.get('resource-id', ''),
            'class': a.get('class', ''),
            'content_desc': a.get('content-desc', ''),
            'package': a.get('package', ''),
            'clickable': a.get('clickable', 'false') == 'true',
            'enabled': a.get('enabled', 'true') == 'true',
            'focused': a.get('focused', 'false') == 'true',
            'selected': a.get('selected', 'false') == 'true',
            'scrollable': a.get('scrollable', 'false') == 'true',
            'password': a.get('password', 'false') == 'true',
            'index': int(a.get('index', 0)),
            'bounds': (x1, y1, x2, y2),
            'center': ((x1 + x2) // 2, (y1 + y2) // 2),
        }
        nodes.append(node)
        for child in el:
            walk(child)

    walk(root)
    return nodes


def _short_class(full: str) -> str:
    return full.rsplit('.', 1)[-1] if '.' in full else full


def _match(node: dict, **kwargs) -> bool:
    for key, val in kwargs.items():
        if val is None:
            continue
        nv = node.get(key, '')
        if key == 'class':
            if val.lower() not in _short_class(nv).lower():
                return False
        elif key in ('text', 'content_desc'):
            if val.lower() not in nv.lower():
                return False
        elif key == 'resource_id':
            if val not in nv:
                return False
        elif key in ('clickable', 'enabled'):
            if nv != val:
                return False
        else:
            if str(val).lower() != str(nv).lower():
                return False
    return True


def _find(xml: str, first_only: bool = True, **kwargs) -> list[dict]:
    all_nodes = _parse_nodes(xml)
    enabled = [n for n in all_nodes if n['enabled']]
    matches = []
    for node in enabled:
        if _match(node, **kwargs):
            matches.append(node)
            if first_only:
                break
    return matches


# ── Tools ──

@mcp.tool()
async def find_element(text: str | None = None, resource_id: str | None = None,
                       class_name: str | None = None, content_desc: str | None = None,
                       first_only: bool = True) -> str:
    """Find UI element by text/resource_id/class/content_desc. Returns position (no tap)."""
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI。需要 Shizuku 或 ADB。"

    kwargs = {}
    if text is not None: kwargs['text'] = text
    if resource_id is not None: kwargs['resource_id'] = resource_id
    if class_name is not None: kwargs['class'] = class_name
    if content_desc is not None: kwargs['content_desc'] = content_desc
    if not kwargs:
        return "⚠️ 指定至少一个条件: text/resource_id/class_name/content_desc"

    matches = _find(xml, first_only=first_only, **kwargs)
    if not matches:
        return f"❌ 未匹配。用 dump_ui() 查看当前布局。"

    lines = [f"✅ {len(matches)} 个匹配:\n"]
    for i, el in enumerate(matches):
        cx, cy = el['center']
        rid = el['resource_id'].split('/')[-1] if '/' in el['resource_id'] else el['resource_id']
        label = el['text'][:40] or el['content_desc'][:40] or '(空)'
        lines.append(f"  [{i}] \"{label}\"  ({cx},{cy})  [{rid}]  {_short_class(el['class'])}")
        lines.append(f"       可点击:{'✅' if el['clickable'] else '❌'}  bounds:{el['bounds']}")
    lines.append("\n💡 用 tap_screen() 点击或 click_by_text() 自动点击。")
    return "\n".join(lines)


@mcp.tool()
async def click_by_text(text: str, index: int = 0) -> str:
    """Find element by text and tap it. More robust than manual tap_screen."""
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI。"

    matches = _find(xml, first_only=False, text=text)
    if not matches:
        return f"❌ 未找到 \"{text}\""
    if index >= len(matches):
        return f"❌ 索引 {index} 超范围 (共 {len(matches)})"

    el = matches[index]
    cx, cy = el['center']
    label = el['text'][:50] or el['content_desc'][:50] or _short_class(el['class'])

    invalidate_ui_cache()
    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    return f"✅ 点击 \"{label}\" → ({cx},{cy})" if r['success'] else f"❌ 找到但点击失败: {r.get('stderr', '?')}"


@mcp.tool()
async def click_by_id(resource_id: str, index: int = 0) -> str:
    """Find element by resource ID and tap it."""
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI。"

    matches = _find(xml, first_only=False, resource_id=resource_id)
    if not matches:
        return f"❌ 未找到 ID \"{resource_id}\""
    if index >= len(matches):
        return f"❌ 索引 {index} 超范围 (共 {len(matches)})"

    el = matches[index]
    cx, cy = el['center']
    invalidate_ui_cache()
    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    return f"✅ 点击 {resource_id} → ({cx},{cy})" if r['success'] else f"❌ 点击失败: {r.get('stderr', '?')}"


@mcp.tool()
async def click_by_class(class_name: str, index: int = 0) -> str:
    """Find element by class name and tap it."""
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI。"

    matches = _find(xml, first_only=False, **{'class': class_name})
    if not matches:
        return f"❌ 未找到类 \"{class_name}\""
    if index >= len(matches):
        return f"❌ 索引 {index} 超范围 (共 {len(matches)})"

    el = matches[index]
    cx, cy = el['center']
    invalidate_ui_cache()
    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    return f"✅ 点击 {_short_class(el['class'])}[{index}] → ({cx},{cy})" if r['success'] else f"❌ 点击失败: {r.get('stderr', '?')}"


@mcp.tool()
async def wait_for_element(text: str | None = None, resource_id: str | None = None,
                           class_name: str | None = None,
                           timeout: float = 10.0, interval: float = 0.5) -> str:
    """Wait for element to appear (polling). Returns element info or timeout error."""
    kwargs = {}
    if text is not None: kwargs['text'] = text
    if resource_id is not None: kwargs['resource_id'] = resource_id
    if class_name is not None: kwargs['class'] = class_name

    start = _time.time()
    while _time.time() - start < timeout:
        xml = _dump_xml()
        if xml:
            matches = _find(xml, first_only=True, **kwargs)
            if matches:
                el = matches[0]
                cx, cy = el['center']
                return f"✅ 元素出现 ({_time.time() - start:.1f}s): \"{el['text'][:40]}\" → ({cx},{cy})"
        _time.sleep(interval)

    return f"❌ 超时 {timeout}s: 元素未出现"


@mcp.tool()
async def get_foreground_app() -> str:
    """Get foreground app info (package + activity)."""
    try:
        if privileged_available():
            r = privileged_shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3", timeout=5)
            if r['success'] and r.get('stdout', '').strip():
                return f"📌 前台应用:\n{r['stdout'].strip()}"
        xml = _dump_xml()
        if xml:
            pkg = ElementTree.fromstring(xml).get('package', 'unknown')
            return f"📌 前台应用: {pkg}"
        return "📌 前台: 无法获取"
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def get_ui_state(scale: float = 0.5, include_screenshot: bool = True) -> str:
    """Get structured UI state: interactive elements list + optional annotated screenshot."""
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI。"

    nodes = _parse_nodes(xml)
    # Filter interactive elements
    interactive = [n for n in nodes if (n['text'] or n['resource_id'] or n['content_desc']) and n['enabled']]

    app_pkg = ElementTree.fromstring(xml).get('package', 'unknown') if xml else '?'

    lines = [f"📱 {app_pkg} — {len(interactive)} 个交互元素:\n"]
    for i, el in enumerate(interactive[:80]):
        cx, cy = el['center']
        rid = el['resource_id'].split('/')[-1] if '/' in el['resource_id'] else el['resource_id']
        label = el['text'][:40] or el['content_desc'][:40] or rid or _short_class(el['class'])
        click = "🖱️" if el['clickable'] else "  "
        lines.append(f"  [{i}] {click} \"{label}\" ({cx},{cy})")

    text = "\n".join(lines)

    if include_screenshot:
        try:
            from android_mcp.tools.ui_automation import take_screenshot
            ss = await take_screenshot(scale=scale)
            if 'data:image/png;base64,' in ss:
                b64 = ss.split('data:image/png;base64,')[-1]
                text += f"\n\ndata:image/png;base64,{b64}"
            else:
                text += f"\n{ss}"
        except Exception:
            pass

    return text