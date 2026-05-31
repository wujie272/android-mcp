"""FastMCP instance. Tools loaded immediately on import."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("termux-control")

import android_mcp.tools.device_info
import android_mcp.tools.ui_automation
import android_mcp.tools.ui_smart
import android_mcp.tools.github
import android_mcp.tools.aggregation
import android_mcp.tools.file_system
import android_mcp.tools.app_management
import android_mcp.tools.communication
import android_mcp.tools.system_control
import android_mcp.tools.media
import android_mcp.tools.adb
import android_mcp.tools.shizuku_window
import android_mcp.tools.weather  # 🌤️ weather tools (wttr.in + ip-api + WAQI)
import android_mcp.tools.execute  # ⚡ execute_command with security assessment
import android_mcp.resources