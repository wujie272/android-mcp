"""FastMCP application instance. Importing this module registers all tools."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("termux-control")

# ── Register all tool modules (order doesn't matter) ──
import android_mcp.tools.device_info       # noqa: F401
import android_mcp.tools.ui_automation     # noqa: F401
import android_mcp.tools.file_system       # noqa: F401
import android_mcp.tools.app_management    # noqa: F401
import android_mcp.tools.communication     # noqa: F401
import android_mcp.tools.system_control    # noqa: F401
import android_mcp.tools.media             # noqa: F401
