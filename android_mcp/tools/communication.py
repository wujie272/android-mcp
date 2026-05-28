"""Communication: SMS, contacts, clipboard, notifications."""

import time as _time
from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run, adb_connected


# ──────────────────────────────────────────────
# SMS
# ──────────────────────────────────────────────

@mcp.tool()
async def list_sms(limit: int = 10, msg_type: str = "inbox") -> str:
    """List SMS messages on the phone.

    获取短信列表。默认返回收件箱最新 10 条。
    每条包含: sender(发件人), body(内容), received_time(时间).

    Args:
        limit: Number of messages to retrieve (default: 10, max: 100)
        msg_type: Message type - 'inbox' (收件箱), 'sent' (已发送),
                  'draft' (草稿), 'all' (全部) (default: inbox)
    """
    return format_json(termux('termux-sms-list', ['-l', str(limit), '-t', msg_type]))


@mcp.tool()
async def send_sms(number: str, message: str) -> str:
    """Send an SMS message to a phone number.

    发送短信。需要已授予 Termux 短信权限。
    注意：发送短信会产生费用。

    Args:
        number: Phone number to send to (e.g. '13800138000')
        message: Message text content
    """
    return termux('termux-sms-send', ['-n', number, message])


# ──────────────────────────────────────────────
# Contacts
# ──────────────────────────────────────────────

@mcp.tool()
async def list_contacts() -> str:
    """List all contacts from the phone book.

    返回联系人列表: name(姓名), phone(电话号码),
    email(邮箱, 如果有). 需要已授予联系人权限。
    """
    return format_json(termux('termux-contact-list', timeout=30))


# ──────────────────────────────────────────────
# Clipboard (with memory fallback)
# ──────────────────────────────────────────────

_clipboard_fallback: str = ""
_clipboard_history: list[dict] = []
_MAX_CLIP_HISTORY = 50


@mcp.tool()
async def get_clipboard() -> str:
    """Get the current clipboard content.

    Uses termux-clipboard-get.
    If Termux:API is unavailable, returns the last set clipboard value (in-memory fallback).
    """
    raw = termux('termux-clipboard-get')
    if raw and 'Error' not in raw and raw.strip():
        return raw.strip()
    if _clipboard_fallback:
        return f"(memory fallback) {_clipboard_fallback}"
    # Try ADB route
    if adb_connected():
        r = run('am broadcast -a clipper.get', shell=True, timeout=5)
        if r['success'] and r.get('stdout'):
            return r['stdout']
    return "Clipboard empty. Install Termux:API from F-Droid for clipboard access.\nUse set_clipboard() to set clipboard content (saved in-memory as fallback)."


@mcp.tool()
async def set_clipboard(text: str) -> str:
    """Set the clipboard content.

    Saves to memory as fallback for environments without Termux:API.

    Args:
        text: Text to copy to clipboard
    """
    global _clipboard_fallback, _clipboard_history
    _clipboard_fallback = text

    # Record in history (skip duplicates)
    if not _clipboard_history or _clipboard_history[0]['text'] != text[:200]:
        _clipboard_history.insert(0, {
            'text': text[:200],
            'time': _time.strftime('%H:%M:%S'),
            'chars': len(text),
        })
        if len(_clipboard_history) > _MAX_CLIP_HISTORY:
            _clipboard_history.pop()

    result = termux('termux-clipboard-set', [text])
    if result and 'Error' not in result:
        return f"Clipboard set ({len(text)} chars)"

    # Try ADB route
    if adb_connected():
        r = run(f'am broadcast -a clipper.set -e text "{text}"', shell=True, timeout=5)
        if r['success']:
            return f"Clipboard set via ADB ({len(text)} chars)"

    return f"Clipboard saved in-memory ({len(text)} chars). Install Termux:API from F-Droid for persistent clipboard access.\nTip: input_chinese_text() also uses clipboard paste."


# ──────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────

@mcp.tool()
async def send_notification(title: str, content: str, id: str = "mcp", vibrate: bool = True) -> str:
    """Send a notification to the phone.

    Args:
        title: Notification title
        content: Notification body text
        id: Notification ID for updates/removal
        vibrate: Whether to vibrate (default: True)
    """
    args = ['--title', title, '-c', content, '--id', id]
    if vibrate:
        args.extend(['--vibrate', '1'])
    result = termux('termux-notification', args)
    if result and 'Error' not in result:
        return f"Notification sent: {title}"
    # Fallback: use ADB
    if adb_connected():
        r = run(f'am broadcast -a android.intent.action.SHOW_NOTIFICATION --es title "{title}" --es content "{content}"', shell=True, timeout=5)
    return result or f"Notification sent: {title}"


@mcp.tool()
async def dismiss_notification(id: str) -> str:
    """Dismiss/remove a notification by its ID.

    Args:
        id: Notification ID to dismiss
    """
    return termux('termux-notification-remove', [id]) or f"Notification '{id}' dismissed"


@mcp.tool()
async def list_notifications() -> str:
    """List all active notifications from the notification bar.

    Uses termux-notification-list (Termux:API). Falls back to dumpsys if available.
    """
    # Try Termux:API first (works without ADB)
    raw = termux('termux-notification-list')
    if raw and 'Error' not in raw and raw.strip():
        try:
            import json as _json
            items = _json.loads(raw)
            if not items:
                return "No active notifications."
            lines = [f"Notifications ({len(items)}):\n"]
            for n in items:
                title = n.get('title', '') or '(no title)'
                content = n.get('content', '') or ''
                pkg = n.get('packageName', '')
                when = n.get('when', '')
                lines.append(f"  📌 {title}")
                if content:
                    lines.append(f"     {content}")
                lines.append(f"     [{pkg}]  {when}")
            return "\n".join(lines)
        except Exception:
            pass

    # Fallback: dumpsys (needs ADB on Android 12+)
    r = run("dumpsys notification --v | grep -E 'NotificationRecord|tickerText|android.title|android.text|key=' | head -100",
            shell=True, timeout=10)
    out = r.get('stdout', '').strip()
    if out:
        return out

    return "Failed to list notifications.\nInstall Termux:API from F-Droid for notification access.\nOr enable Wireless Debugging for ADB access."


@mcp.tool()
async def show_toast(text: str, short: bool = True) -> str:
    """Show a toast message on the phone screen.

    Args:
        text: Text to show
        short: True for short display, False for long (default: True)
    """
    args = [text]
    if not short:
        args = ['-s'] + args
    result = termux('termux-toast', args)
    if result and 'Error' not in result:
        return f"Toast shown: {text[:50]}"
    # Fallback
    if adb_connected():
        run(f'am broadcast -a clipper.toast --es text "{text}"', shell=True, timeout=5)
    return f"Toast shown: {text[:50]}"


# ──────────────────────────────────────────────
# Clipboard History
# ──────────────────────────────────────────────

@mcp.tool()
async def clipboard_history(limit: int = 10) -> str:
    """Show recent clipboard history entries.

    Tracks text set via set_clipboard() during this session.
    History is in-memory and lost when the server restarts.

    Args:
        limit: Number of recent entries to show (default: 10)
    """
    if not _clipboard_history:
        return "No clipboard history yet. Use set_clipboard() to store text."

    limit = min(limit, len(_clipboard_history))
    lines = [f"📋 Clipboard History (last {limit} of {len(_clipboard_history)}):\n"]
    for i, entry in enumerate(_clipboard_history[:limit]):
        text = entry['text'][:80]
        suffix = "…" if len(entry['text']) > 80 else ""
        lines.append(f"  {i+1}. [{entry['time']}] {text}{suffix} ({entry['chars']} chars)")
    return "\n".join(lines)


@mcp.tool()
async def clipboard_history_clear() -> str:
    """Clear the clipboard history."""
    global _clipboard_history
    count = len(_clipboard_history)
    _clipboard_history.clear()
    return f"Cleared {count} clipboard history entries."
