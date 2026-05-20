"""FastMCP application instance. Stratified loading for faster startup.

加载策略:
  🚀 第1层：核心工具  立即加载  → device_info, ui_automation
  ⏳ 第2层：常用工具  延迟3秒   → file_system, app_management, communication, system_control
  🐌 第3层：低频工具  延迟10秒  → media, adb, github
"""

from mcp.server.fastmcp import FastMCP
import threading

mcp = FastMCP("termux-control")

# ──────────────────────────────────────────────
# 🚀 第1层：核心工具（立即加载，每次对话都用）
# ──────────────────────────────────────────────
import android_mcp.tools.device_info       # noqa: F401 电池/WiFi/定位
import android_mcp.tools.ui_automation     # noqa: F401 截屏/点击/输入

# ──────────────────────────────────────────────
# ⏳ 第2层：常用工具（延迟3秒，避开启动内存峰值）
# ──────────────────────────────────────────────
def _load_layer2():
    """加载第2层工具模块"""
    import android_mcp.tools.file_system       # noqa: F401
    import android_mcp.tools.app_management    # noqa: F401
    import android_mcp.tools.communication     # noqa: F401
    import android_mcp.tools.system_control    # noqa: F401

threading.Timer(3.0, _load_layer2).start()

# ──────────────────────────────────────────────
# 🐌 第3层：低频工具（延迟10秒）
# ──────────────────────────────────────────────
def _load_layer3():
    """加载第3层工具模块"""
    import android_mcp.tools.media             # noqa: F401
    import android_mcp.tools.adb               # noqa: F401
    import android_mcp.tools.github            # noqa: F401

threading.Timer(10.0, _load_layer3).start()