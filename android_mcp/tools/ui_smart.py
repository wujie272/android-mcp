"""Smart UI Element Finding — uiautomator2 风格智能元素定位。

无需 ADB 或 uiautomator2 驱动，基于 Shizuku 的 uiautomator dump 实现：
  - click_by_text / click_by_id / click_by_class — 按属性点击
  - find_element — 查找并返回元素信息（不点击）
  - wait_for_element — 轮询等待元素出现
  - get_foreground_app — 获取前台应用信息
  - get_ui_state — 结构化界面状态（含标注截图）
"""

import time as _time
import logging
from xml.etree import ElementTree
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import run as sync_run, privileged_shell, privileged_available
from android_mcp.lib.constants import HOME, TMP_UI_DUMP, TMP_SCREENSHOT

logger = logging.getLogger('android-mcp.ui_smart')


# ──────────────────────────────────────────────
# 内部工具：dump XML + 解析为元素树
# ──────────────────────────────────────────────

def _dump_xml() -> str | None:
    """Dump current UI XML. Returns XML string or None on failure."""
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
        # uiautomator dump wraps in <hierarchy>...</hierarchy>
        return content
    except Exception as e:
        logger.warning(f"dump XML failed: {e}")
        return None


def _parse_all_nodes(xml_content: str) -> list[dict]:
    """Parse UI XML into a flat list of all nodes with attributes."""
    try:
        root = ElementTree.fromstring(xml_content)
    except Exception:
        return []

    nodes = []

    def _walk(element):
        attrs = dict(element.attrib)
        node = {
            'text': attrs.get('text', ''),
            'resource_id': attrs.get('resource-id', ''),
            'class': attrs.get('class', ''),
            'content_desc': attrs.get('content-desc', ''),
            'package': attrs.get('package', ''),
            'clickable': attrs.get('clickable', 'false') == 'true',
            'long_clickable': attrs.get('long-clickable', 'false') == 'true',
            'checkable': attrs.get('checkable', 'false') == 'true',
            'checked': attrs.get('checked', 'false') == 'true',
            'focusable': attrs.get('focusable', 'false') == 'true',
            'focused': attrs.get('focused', 'false') == 'true',
            'selected': attrs.get('selected', 'false') == 'true',
            'scrollable': attrs.get('scrollable', 'false') == 'true',
            'enabled': attrs.get('enabled', 'true') == 'true',
            'password': attrs.get('password', 'false') == 'true',
            'index': int(attrs.get('index', 0)),
        }

        # Parse bounds
        bounds = attrs.get('bounds', '[0,0][0,0]')
        try:
            parts = bounds.replace('[', '').replace(']', ',').split(',')
            x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            node['bounds'] = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
            node['center'] = {'x': (x1 + x2) // 2, 'y': (y1 + y2) // 2}
        except (ValueError, IndexError):
            node['bounds'] = {'x1': 0, 'y1': 0, 'x2': 0, 'y2': 0}
            node['center'] = {'x': 0, 'y': 0}

        nodes.append(node)
        for child in element:
            _walk(child)

    _walk(root)
    return nodes


def _short_class(full_class: str) -> str:
    """Extract short class name from full Java class path."""
    if '.' in full_class:
        return full_class.rsplit('.', 1)[-1]
    return full_class


def _match_element(node: dict, **kwargs) -> bool:
    """Check if a node matches given criteria."""
    for key, value in kwargs.items():
        if value is None:
            continue
        node_val = node.get(key, '')
        if key == 'class':
            # Allow partial match on short class name
            short = _short_class(node_val)
            if value.lower() not in short.lower():
                return False
        elif key == 'text':
            if value.lower() not in node_val.lower():
                return False
        elif key == 'resource_id':
            # Allow partial match on resource ID
            if value not in node_val:
                return False
        elif key == 'content_desc':
            if value.lower() not in node_val.lower():
                return False
        elif key == 'clickable':
            if node_val != value:
                return False
        elif key == 'enabled':
            if node_val != value:
                return False
        else:
            if str(value).lower() != str(node_val).lower():
                return False
    return True


def _find_elements(xml_content: str, first_only: bool = True, **kwargs) -> list[dict]:
    """Find UI elements matching criteria.

    Args:
        xml_content: Raw UI XML
        first_only: If True, return first match only
        **kwargs: Search criteria (text, resource_id, class, content_desc, etc.)

    Returns:
        List of matching element dicts
    """
    all_nodes = _parse_all_nodes(xml_content)
    # Filter only enabled nodes, sorted by index
    enabled = [n for n in all_nodes if n['enabled']]

    matches = []
    for node in enabled:
        if _match_element(node, **kwargs):
            matches.append(node)
            if first_only:
                break

    return matches


# ──────────────────────────────────────────────
# 工具：查找元素
# ──────────────────────────────────────────────

@mcp.tool()
async def find_element(
    text: str | None = None,
    resource_id: str | None = None,
    class_name: str | None = None,
    content_desc: str | None = None,
    first_only: bool = True,
) -> str:
    """查找屏幕上的 UI 元素，返回位置和属性（不点击）。

    支持按文本 / 资源ID / 类名 / 内容描述 查找。
    返回元素的坐标、文本、类名、可点击状态等。
    使用此工具定位后，可用 tap_screen() 点击。

    Args:
        text: 元素的文本内容（部分匹配，不区分大小写）
        resource_id: 资源 ID（如 'com.example:id/btn_send'，部分匹配）
        class_name: 类名（如 'Button', 'EditText', 'TextView'，部分匹配）
        content_desc: 无障碍描述（部分匹配，不区分大小写）
        first_only: 是否只返回第一个匹配（default: True）
    """
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI 层次结构。需要 Shizuku 或 ADB 权限。"

    kwargs = {}
    if text is not None:
        kwargs['text'] = text
    if resource_id is not None:
        kwargs['resource_id'] = resource_id
    if class_name is not None:
        kwargs['class'] = class_name
    if content_desc is not None:
        kwargs['content_desc'] = content_desc

    if not kwargs:
        return "⚠️ 请至少指定一个搜索条件: text, resource_id, class_name, content_desc"

    matches = _find_elements(xml, first_only=first_only, **kwargs)

    if not matches:
        criteria = ' '.join(f'{k}="{v}"' for k, v in kwargs.items())
        return f"❌ 未找到匹配 \"{criteria}\" 的元素。可用 dump_ui() 查看当前屏幕布局。"

    lines = [f"✅ 找到 {len(matches)} 个匹配元素:\n"]
    for i, el in enumerate(matches):
        cx, cy = el['center']['x'], el['center']['y']
        rid = el['resource_id'].split('/')[-1] if '/' in el['resource_id'] else el['resource_id']
        lines.append(f"  [{i + 1}] \"{el['text'][:40] or el['content_desc'][:40] or '(空)'}\"")
        lines.append(f"       类: {_short_class(el['class'])}")
        lines.append(f"       ID: {rid or '(无)'}")
        lines.append(f"       位置: ({cx}, {cy})  |  范围: [{el['bounds']['x1']},{el['bounds']['y1']}] → [{el['bounds']['x2']},{el['bounds']['y2']}]")
        lines.append(f"       可点击: {'✅' if el['clickable'] else '❌'}  |  已聚焦: {'✅' if el['focused'] else '❌'}")
        lines.append("")

    lines.append("💡 用 tap_screen(x, y) 点击，或用 click_by_text() / click_by_id() 自动点击。")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 工具：按文本/ID/类名点击
# ──────────────────────────────────────────────

@mcp.tool()
async def click_by_text(text: str, index: int = 0) -> str:
    """按文本内容查找并点击 UI 元素。

    比 tap_screen(x, y) 更智能：不受布局变化影响，
    自动找到匹配的按钮/链接/菜单项并点击。

    Args:
        text: 元素的文本内容（部分匹配，不区分大小写）
        index: 如果有多个匹配，指定第几个（0=第一个, default: 0）
    """
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI 层次结构。"

    matches = _find_elements(xml, first_only=False, text=text)

    if not matches:
        return f"❌ 未找到包含文本 \"{text}\" 的元素。可用 dump_ui() 查看当前屏幕。"

    if index >= len(matches):
        return f"❌ 索引 {index} 超出范围（共 {len(matches)} 个匹配）。试试 index=0~{len(matches) - 1}。"

    el = matches[index]
    cx, cy = el['center']['x'], el['center']['y']
    label = el['text'][:50] or el['content_desc'][:50] or _short_class(el['class'])

    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    if r['success']:
        return f"✅ 点击 \"{label}\" → tap({cx}, {cy})（索引 {index}/{len(matches) - 1}）"
    return f"❌ 找到 \"{label}\" 但点击失败: {r.get('stderr', 'Unknown')}"


@mcp.tool()
async def click_by_id(resource_id: str, index: int = 0) -> str:
    """按资源 ID 查找并点击 UI 元素。

    适合点击有固定 ID 的控件（如悬浮按钮、菜单项等），
    不受文本变化或布局偏移影响。

    Args:
        resource_id: 资源 ID（如 'com.example:id/send'，部分匹配）
        index: 如果有多个匹配，指定第几个（default: 0）
    """
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI 层次结构。"

    matches = _find_elements(xml, first_only=False, resource_id=resource_id)

    if not matches:
        return f"❌ 未找到 ID 包含 \"{resource_id}\" 的元素。"

    if index >= len(matches):
        return f"❌ 索引 {index} 超出范围（共 {len(matches)} 个匹配）。"

    el = matches[index]
    cx, cy = el['center']['x'], el['center']['y']
    label = el['text'][:50] or el['content_desc'][:50] or el['resource_id']

    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    if r['success']:
        return f"✅ 点击 [{label}] → tap({cx}, {cy})"
    return f"❌ 找到 [{label}] 但点击失败: {r.get('stderr', 'Unknown')}"


@mcp.tool()
async def click_by_class(class_name: str, index: int = 0) -> str:
    """按类名查找并点击 UI 元素。

    适合点击特定类型的控件（如 Button, ImageButton, CheckBox 等），
    不关心具体文本或 ID。

    Args:
        class_name: 类名（如 'Button', 'ImageButton', 'Switch'，部分匹配）
        index: 如果有多个匹配，指定第几个（default: 0）
    """
    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI 层次结构。"

    matches = _find_elements(xml, first_only=False, class_name=class_name)

    if not matches:
        return f"❌ 未找到类名为 \"{class_name}\" 的元素。"

    if index >= len(matches):
        return f"❌ 索引 {index} 超出范围（共 {len(matches)} 个匹配）。"

    el = matches[index]
    cx, cy = el['center']['x'], el['center']['y']
    label = el['text'][:50] or el['content_desc'][:50] or f"({_short_class(el['class'])})"

    r = sync_run(f'input tap {cx} {cy}', shell=True, timeout=5)
    if r['success']:
        return f"✅ 点击 [{label}] → tap({cx}, {cy})（第 {index + 1}/{len(matches)} 个 {class_name}）"
    return f"❌ 找到 [{label}] 但点击失败: {r.get('stderr', 'Unknown')}"


# ──────────────────────────────────────────────
# 工具：等待元素出现
# ──────────────────────────────────────────────

@mcp.tool()
async def wait_for_element(
    text: str | None = None,
    resource_id: str | None = None,
    class_name: str | None = None,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> str:
    """等待 UI 元素出现在屏幕上。

    适合页面加载、动画过渡、异步内容刷新的场景。
    轮询检查，元素出现即返回，超时则报错。

    Args:
        text: 等待的文本内容（部分匹配）
        resource_id: 等待的资源 ID（部分匹配）
        class_name: 等待的类名（部分匹配）
        timeout: 最大等待秒数（default: 10.0）
        interval: 轮询间隔秒数（default: 0.5）
    """
    kwargs = {}
    if text is not None:
        kwargs['text'] = text
    if resource_id is not None:
        kwargs['resource_id'] = resource_id
    if class_name is not None:
        kwargs['class'] = class_name

    if not kwargs:
        return "⚠️ 请至少指定一个搜索条件: text, resource_id, class_name"

    criteria = ' '.join(f'{k}="{v}"' for k, v in kwargs.items())
    deadline = _time.time() + timeout

    while _time.time() < deadline:
        xml = _dump_xml()
        if xml is not None:
            matches = _find_elements(xml, first_only=True, **kwargs)
            if matches:
                el = matches[0]
                cx, cy = el['center']['x'], el['center']['y']
                label = el['text'][:50] or el['content_desc'][:50] or _short_class(el['class'])
                elapsed = timeout - (deadline - _time.time())
                return (
                    f"✅ 元素已出现 (等待 {elapsed:.1f}s)\n"
                    f"   文本: \"{label}\"\n"
                    f"   位置: ({cx}, {cy})\n"
                    f"   可点击: {'✅' if el['clickable'] else '❌'}\n"
                    f"💡 用 click_by_text(\"{text or label}\") 点击"
                )
        _time.sleep(interval)

    return f"❌ 等待超时 ({timeout}s)：未找到 \"{criteria}\""


# ──────────────────────────────────────────────
# 工具：获取当前应用
# ──────────────────────────────────────────────

@mcp.tool()
async def get_foreground_app() -> str:
    """获取当前前台应用信息（包 Activity返回信息，
    适合在操作前后确认应用状态。
    """
    try:
        # 方法1: dumpsys activity recents (最快)
        if privileged_available():
            r = privileged_shell(
                "dumpsys activity recents | grep 'RecentTasks' | head -3",
                timeout=5,
            )
            # 方法2: dumpsys window (更可靠)
            r2 = sync_run(
                "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp|mResumedActivity' | head -3",
                shell=True, timeout=5,
            )
            if r2['success'] and r2.get('stdout', '').strip():
                return f"📱 当前前台应用:\n{r2['stdout']}"

        # 方法3: 通过 UI dump 获取 package
        xml = _dump_xml()
        if xml:
            root = ElementTree.fromstring(xml)
            pkg = root.get('package', '')
            nodes = _parse_all_nodes(xml)
            focused = [n for n in nodes if n['focused']]
            info = [f"📱 当前前台应用:\n  包名: {pkg}"]
            if focused:
                info.append(f"  已聚焦元素: {focused[0]['text'][:50] or focused[0]['content_desc'][:50] or _short_class(focused[0]['class'])}")
            return "\n".join(info)

        return "❌ 无法获取前台应用信息。需要 Shizuku 或 ADB 权限。"
    except Exception as e:
        return f"❌ 获取前台应用失败: {e}"


# ──────────────────────────────────────────────
# 工具：获取结构化界面状态（含标注截图）
# ──────────────────────────────────────────────

@mcp.tool()
async def get_ui_state(
    scale: float = 0.5,
    include_screenshot: bool = True,
) -> str:
    """获取当前屏幕的结构化界面状态。

    类似 dump_ui_with_screenshot，但返回更丰富的元素属性：
    - 交互元素列表（含坐标、类名、文本、ID）
    - 可选标注截图
    - 当前应用信息

    适合 AI 在操作前全面理解界面状态。

    Args:
        scale: 截图缩放比例（0.25~1.0, default: 0.5）
        include_screenshot: 是否包含标注截图（default: True）
    """
    import base64
    from android_mcp.tools.ui_automation import (
        _annotate_screenshot,
        TMP_SCREENSHOT as SS,
    )

    scale = max(0.25, min(1.0, scale))

    xml = _dump_xml()
    if xml is None:
        return "❌ 无法获取 UI 状态。需要 Shizuku 或 ADB 权限。"

    all_nodes = _parse_all_nodes(xml)

    # Filter interactive elements
    interactive = [
        n for n in all_nodes
        if n['enabled'] and (
            n['clickable'] or n['long_clickable']
            or 'Button' in n['class'] or 'EditText' in n['class']
            or 'Switch' in n['class']
        )
    ]

    # Get package info
    root_pkg = ''
    try:
        root = ElementTree.fromstring(xml)
        root_pkg = root.get('package', '')
    except Exception:
        pass

    lines = [f"📱 界面状态 — {root_pkg}\n"]
    lines.append(f"  总节点: {len(all_nodes)}  |  可交互: {len(interactive)}\n")

    if interactive:
        lines.append("── 可交互元素 ──")
        for i, el in enumerate(interactive[:30]):  # 最多显示30个
            cx, cy = el['center']['x'], el['center']['y']
            label = el['text'][:50] or el['content_desc'][:50] or _short_class(el['class'])
            rid = el['resource_id'].split('/')[-1] if '/' in el['resource_id'] else ''
            rid_part = f" [{rid}]" if rid else ""
            click_icon = "🖱" if el['clickable'] else "  "
            lines.append(f"  {i + 1:>2}. {click_icon} \"{label}\"{rid_part}")
            lines.append(f"      → {_short_class(el['class'])} at ({cx}, {cy})")

        if len(interactive) > 30:
            lines.append(f"  ... 还有 {len(interactive) - 30} 个元素")

    # Screenshot
    if include_screenshot:
        try:
            ss_path = str(SS)
            if privileged_available():
                privileged_shell(f'screencap -p {ss_path}', timeout=10)
            else:
                sync_run(f'screencap -p {ss_path}', shell=True, timeout=10)

            # Build element list for annotation
            annotate_elements = []
            for i, el in enumerate(interactive[:30]):
                annotate_elements.append({
                    'label': el['text'][:60] or el['content_desc'][:60] or _short_class(el['class']),
                    'class': _short_class(el['class']),
                    'bounds': el['bounds'],
                    'center': el['center'],
                })

            annotated = _annotate_screenshot(Path(ss_path), annotate_elements, scale=scale)
            if annotated:
                data = base64.b64encode(annotated).decode('ascii')
                lines.append(f"\n📸 标注截图 (scale={scale}):")
                lines.append(f"data:image/png;base64,{data}")
        except Exception as e:
            lines.append(f"\n📸 截图生成失败: {e}")

    lines.append("\n💡 用 click_by_text() / click_by_id() 按属性点击，或 tap_screen(x, y) 按坐标点击。")
    return "\n".join(lines)
