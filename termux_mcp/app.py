"""FastMCP instance. Tools loaded immediately on import."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("termux-control")

import termux_mcp.tools.device_info
import termux_mcp.tools.ui_smart
# import termux_mcp.tools.github  # 已迁移到独立 GitHub MCP (Go) :8082
import termux_mcp.tools.file_system  # 📝 read, search, edit, copy, move, delete, trash
import termux_mcp.tools.app_management
import termux_mcp.tools.communication
import termux_mcp.tools.system_control
import termux_mcp.tools.adb
import termux_mcp.tools.shizuku_window
import termux_mcp.tools.execute  # ⚡ execute_command with security assessment
import termux_mcp.resources
