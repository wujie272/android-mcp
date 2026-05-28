"""Centralized path and configuration constants for android-mcp.

所有硬编码路径集中管理，一处修改全局生效。
引用方式：from android_mcp.lib.constants import HOME, LOG_DIR, ...
"""

from pathlib import Path


# ══════════════════════════════════════════════
#  Base Paths
# ══════════════════════════════════════════════

HOME = Path('/data/data/com.termux/files/home')
MCP_SERVERS_DIR = HOME / 'mcp-servers'
LOG_DIR = MCP_SERVERS_DIR / 'logs'
RUN_DIR = MCP_SERVERS_DIR / 'run'

# ══════════════════════════════════════════════
#  Binary & Script Paths
# ══════════════════════════════════════════════

RISH = HOME / 'rish'
MCP_MANAGER = HOME / 'mcp-manager.sh'

# ══════════════════════════════════════════════
#  Runtime Files
# ══════════════════════════════════════════════

PID_FILE = RUN_DIR / 'android-mcp.pid'
ANDROID_LOG = LOG_DIR / 'android_mcp.log'

# ══════════════════════════════════════════════
#  SD Card 路径（外部存储）
# ══════════════════════════════════════════════

SDCARD = Path('/storage/emulated/0')
SDCARD_SHORT = Path('/sdcard')
DCIM_CAMERA = SDCARD / 'DCIM/Camera'

# ══════════════════════════════════════════════
#  临时文件（UI自动化用）
# ══════════════════════════════════════════════

TMP_SCREENSHOT = SDCARD / 'mcp_screenshot.png'
TMP_UI_DUMP = SDCARD / 'mcp_ui_dump.xml'
TMP_UI_TAP = SDCARD / 'mcp_ui_dump_tap.xml'
SCREENSHOT_DEFAULT = HOME / 'screenshot.png'
UI_DUMP_DEFAULT = HOME / 'ui_dump.xml'
PHOTO_DEFAULT = HOME / 'photo.jpg'

# ══════════════════════════════════════════════
#  MCP Server 自身路径
# ══════════════════════════════════════════════

MCP_SERVER_DIR = Path('/data/data/com.termux/files/home/mcp-servers/android-mcp')

# ══════════════════════════════════════════════
#  照片备选目录
# ══════════════════════════════════════════════

PHOTO_ALT_DIRS = [
    SDCARD / 'DCIM',
    SDCARD / 'Pictures',
    SDCARD_SHORT / 'DCIM/Camera',
    SDCARD_SHORT / 'DCIM',
    SDCARD_SHORT / 'Pictures',
]
