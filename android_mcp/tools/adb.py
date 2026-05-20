"""ADB connection management tools."""

from android_mcp.app import mcp
from android_mcp.lib.adb import check_setup_status as _check, connect as _connect


@mcp.tool()
async def adb_status() -> str:
    """Check ADB installation and connection status.

    Returns whether ADB is installed and whether there's an active
    wireless debugging connection to the device.
    """
    return await _check()


@mcp.tool()
async def adb_connect(pair_code: str = "", pair_port: str = "", connect_port: str = "") -> str:
    """Connect ADB to this device wirelessly. Required on Android 12+.

    Args:
        pair_code: Pairing code from wireless debugging settings
        pair_port: Pairing port (e.g. '37123')
        connect_port: Connection port from the main wireless debugging page (e.g. '5555')
    """
    return await _connect(pair_code, pair_port, connect_port)
