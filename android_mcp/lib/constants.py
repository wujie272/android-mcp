"""Centralized paths and constants — change once, use everywhere."""

from pathlib import Path

HOME = Path('/data/data/com.termux/files/home')
MCP_SERVERS_DIR = HOME / 'mcp-servers'
LOG_DIR = MCP_SERVERS_DIR / 'logs'
RUN_DIR = MCP_SERVERS_DIR / 'run'

RISH = HOME / 'rish'
MCP_MANAGER = HOME / 'mcp-manager.sh'

PID_FILE = RUN_DIR / 'android-mcp.pid'
ANDROID_LOG = LOG_DIR / 'android_mcp.log'

SDCARD = Path('/storage/emulated/0')
SDCARD_SHORT = Path('/sdcard')
DCIM_CAMERA = SDCARD / 'DCIM/Camera'

TMP_SCREENSHOT = SDCARD / 'mcp_screenshot.png'
TMP_UI_DUMP = SDCARD / 'mcp_ui_dump.xml'
TMP_UI_TAP = SDCARD / 'mcp_ui_dump_tap.xml'
SCREENSHOT_DEFAULT = HOME / 'screenshot.png'
UI_DUMP_DEFAULT = HOME / 'ui_dump.xml'
PHOTO_DEFAULT = HOME / 'photo.jpg'

MCP_SERVER_DIR = Path('/data/data/com.termux/files/home/mcp-servers/android-mcp')

PHOTO_ALT_DIRS = [
    SDCARD / 'DCIM',
    SDCARD / 'Pictures',
    SDCARD_SHORT / 'DCIM/Camera',
    SDCARD_SHORT / 'DCIM',
    SDCARD_SHORT / 'Pictures',
]