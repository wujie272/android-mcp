"""Communication: SMS, contacts, clipboard, notifications."""

from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run


# ──────────────────────────────────────────────
# SMS
# ──────────────────────────────────────────────

@mcp.tool()
async def list_sms(limit: int = 10, type: str = "inbox") -> str:
    """List SMS messages.

    Args:
        limit: Number of messages to retrieve (default: 10)
        type: Message type - 'inbox', 'sent', 'draft', 'all' (default: inbox)
    """
    return format_json(termux('termux-sms-list', ['-l', str(limit), '-t', type]))


@mcp.tool()
async def send_sms(number: str, message: str) -> str:
    """Send an SMS message.

    Args:
        number: Phone number to send to
        message: Message text
    """
    return termux('termux-sms-send', ['-n', number, message])


# ──────────────────────────────────────────────
# Contacts
# ──────────────────────────────────────────────

@mcp.tool()
async def list_contacts() -> str:
    """List all contacts from the phone."""
    return format_json(termux('termux-contact-list', timeout=30))


# ──────────────────────────────────────────────
# Clipboard
# ──────────────────────────────────────────────

@mcp.tool()
async def get_clipboard() -> str:
    """Get the current clipboard content."""
    return termux('termux-clipboard-get')


@mcp.tool()
async def set_clipboard(text: str) -> str:
    """Set the clipboard content.

    Args:
        text: Text to copy to clipboard
    """
    result = termux('termux-clipboard-set', [text])
    return result or f"Clipboard set to: {text[:100]}{'...' if len(text) > 100 else ''}"


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
        args.append('--vibrate')
    return termux('termux-notification', args) or f"Notification sent: {title}"


@mcp.tool()
async def dismiss_notification(id: str) -> str:
    """Dismiss/remove a notification by its ID.

    Args:
        id: Notification ID to dismiss
    """
    return termux('termux-notification-remove', [id]) or f"Notification '{id}' dismissed"


@mcp.tool()
async def list_notifications() -> str:
    """List all active notifications from the notification bar."""
    r = run("dumpsys notification --v | grep -E 'NotificationRecord|tickerText|android.title|android.text|key=' | head -100",
            shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed to list notifications'))


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
    return termux('termux-toast', args) or f"Toast shown: {text}"
