"""ADB tools: status, connect."""

from android_mcp.app import mcp
from android_mcp.lib.adb import check_setup_status as _check, connect as _connect


@mcp.tool()
async def adb_status() -> str:
    """Check ADB/Shizuku installation and connection status."""
    return await _check()


@mcp.tool()
async def adb_connect(pair_code: str = "", pair_port: str = "", connect_port: str = "") -> str:
    """Connect ADB wirelessly (Android 12+). Get pairing code from Wireless Debugging settings."""
    return await _connect(pair_code, pair_port, connect_port)