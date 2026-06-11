"""Communication: SMS, contacts, clipboard, notifications."""

import time as _time
from termux_mcp.app import mcp
from termux_mcp.lib.utils import termux, format_json, run, adb_connected

_clipboard_fallback = ""
_clipboard_history: list[dict] = []
_MAX_CLIP_HISTORY = 50


@mcp.tool()
async def list_sms(limit: int = 10, msg_type: str = "inbox") -> str:
    """List SMS. Types: inbox/sent/draft/all."""
    return format_json(termux('termux-sms-list', ['-l', str(limit), '-t', msg_type]))


@mcp.tool()
async def send_sms(number: str, message: str) -> str:
    """Send SMS (incurs charges)."""
    return termux('termux-sms-send', ['-n', number, message])


@mcp.tool()
async def list_contacts() -> str:
    """List contacts (name, phone, email)."""
    return format_json(termux('termux-contact-list', timeout=30))


@mcp.tool()
async def clipboard(action: str = 'read', text: str = '') -> str:
    """📋 Read or write clipboard.

    Args:
        action: 'read' to get clipboard content, 'write' to set it
        text: Text to write (required when action='write')
    """
    global _clipboard_fallback, _clipboard_history

    if action == 'write':
        if not text:
            return '❌ 写入剪贴板时需要提供 text 参数'
        _clipboard_fallback = text
        if not _clipboard_history or _clipboard_history[0]['text'] != text[:200]:
            _clipboard_history.insert(0, {'text': text[:200], 'time': _time.strftime('%H:%M:%S'), 'chars': len(text)})
            if len(_clipboard_history) > _MAX_CLIP_HISTORY:
                _clipboard_history.pop()
        result = termux('termux-clipboard-set', [text])
        if result and 'Error' not in result:
            return f"✅ 剪贴板已写入 ({len(text)} chars)"
        if adb_connected():
            r = run(f'am broadcast -a clipper.set -e text "{text}"', shell=True, timeout=5)
            if r['success']:
                return f"✅ 剪贴板已写入 via ADB ({len(text)} chars)"
        return f"✅ 剪贴板已保存到内存 ({len(text)} chars)。安装 Termux:API 可写入系统剪贴板。"

    # Default: read
    raw = termux('termux-clipboard-get')
    if raw and 'Error' not in raw and raw.strip():
        return raw.strip()
    if _clipboard_fallback:
        return f"(memory) {_clipboard_fallback}"
    if adb_connected():
        r = run('am broadcast -a clipper.get', shell=True, timeout=5)
        if r['success'] and r.get('stdout'):
            return r['stdout']
    return "📋 剪贴板为空。安装 Termux:API 或先写入内容。"


@mcp.tool()
async def send_notification(title: str, content: str, id: str = "mcp", vibrate: bool = True) -> str:
    """Send a notification."""
    args = ['--title', title, '-c', content, '--id', id]
    if vibrate:
        args.extend(['--vibrate', '1'])
    return termux('termux-notification', args) or f"Notification sent: {title}"


@mcp.tool()
async def dismiss_notification(id: str) -> str:
    """Dismiss a notification by ID."""
    return termux('termux-notification-remove', [id]) or f"Dismissed: {id}"


@mcp.tool()
async def list_notifications() -> str:
    """List active notifications."""
    raw = termux('termux-notification-list')
    if raw and 'Error' not in raw and raw.strip():
        try:
            import json as _json
            items = _json.loads(raw)
            if not items:
                return "No active notifications."
            lines = [f"Notifications ({len(items)}):"]
            for n in items:
                lines.append(f"\n  📌 {n.get('title', '(no title)')}")
                if n.get('content'):
                    lines.append(f"     {n['content']}")
                lines.append(f"     [{n.get('packageName', '')}]")
            return "\n".join(lines)
        except Exception:
            pass
    r = run("dumpsys notification --v | grep -E 'NotificationRecord|android.title|android.text' | head -100",
            shell=True, timeout=10)
    return r.get('stdout', '').strip() or "Failed. Install Termux:API or enable ADB."


@mcp.tool()
async def show_toast(text: str, short: bool = True) -> str:
    """Show a toast message."""
    args = [text] if short else ['-s', text]
    return termux('termux-toast', args) or f"Toast: {text[:50]}"


@mcp.tool()
async def clipboard_history(limit: int = 10) -> str:
    """Show recent clipboard history (in-memory, lost on restart)."""
    if not _clipboard_history:
        return "No history. Use clipboard(action='write', text=...) to store."
    limit = min(limit, len(_clipboard_history))
    lines = [f"📋 Clipboard History (last {limit} of {len(_clipboard_history)}):"]
    for i, e in enumerate(_clipboard_history[:limit], 1):
        t = e['text'][:80] + ("…" if len(e['text']) > 80 else "")
        lines.append(f"\n  {i}. [{e['time']}] {t} ({e['chars']} chars)")
    return "".join(lines)


@mcp.tool()
async def clipboard_history_clear() -> str:
    """Clear clipboard history."""
    global _clipboard_history
    count = len(_clipboard_history)
    _clipboard_history.clear()
    return f"Cleared {count} entries."