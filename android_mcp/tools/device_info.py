"""Device Information: battery, WiFi, telephony, location, storage, sensors, device info."""

from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run, format_json


# ──────────────────────────────────────────────
# Battery
# ──────────────────────────────────────────────

@mcp.tool()
async def get_battery_status() -> str:
    """Get phone battery status including level, charging state, temperature, etc."""
    return format_json(termux('termux-battery-status'))


# ──────────────────────────────────────────────
# WiFi
# ──────────────────────────────────────────────

@mcp.tool()
async def get_wifi_info() -> str:
    """Get current WiFi connection information (SSID, IP, signal strength, etc.)."""
    return format_json(termux('termux-wifi-connectioninfo'))


@mcp.tool()
async def scan_wifi() -> str:
    """Scan for nearby WiFi networks."""
    return format_json(termux('termux-wifi-scaninfo', timeout=15))


# ──────────────────────────────────────────────
# Telephony
# ──────────────────────────────────────────────

@mcp.tool()
async def get_telephony_info() -> str:
    """Get telephony device info (carrier, phone type, SIM state, etc.)."""
    return format_json(termux('termux-telephony-deviceinfo'))


@mcp.tool()
async def get_telephony_cell_info() -> str:
    """Get detailed cellular network information."""
    return format_json(termux('termux-telephony-cellinfo'))


# ──────────────────────────────────────────────
# Location
# ──────────────────────────────────────────────

@mcp.tool()
async def get_location(provider: str = "gps", request: str = "once") -> str:
    """Get the phone's current GPS location.

    Args:
        provider: Location provider - 'gps', 'network', or 'passive' (default: gps)
        request: 'once' for single reading, 'last' for last known location, 'updates' for continuous
    """
    return format_json(termux('termux-location', ['-p', provider, '-r', request], timeout=60))


# ──────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────

@mcp.tool()
async def get_storage_info() -> str:
    """Get phone storage usage information (disk space)."""
    r = run('df -h /storage/emulated/0 /data 2>/dev/null || df -h', shell=True, timeout=10)
    return r.get('stdout', r.get('error', 'Failed'))


# ──────────────────────────────────────────────
# Device Info
# ──────────────────────────────────────────────

@mcp.tool()
async def get_device_info() -> str:
    """Get comprehensive device information (model, Android version, etc.)."""
    commands = {
        'Model': 'getprop ro.product.model',
        'Brand': 'getprop ro.product.brand',
        'Android Version': 'getprop ro.build.version.release',
        'SDK Level': 'getprop ro.build.version.sdk',
        'Build': 'getprop ro.build.display.id',
        'Kernel': 'uname -r',
        'Architecture': 'uname -m',
        'Uptime': 'uptime',
    }
    lines = []
    for label, cmd in commands.items():
        r = run(cmd, shell=True, timeout=5)
        val = r.get('stdout', '').strip() or 'N/A'
        lines.append(f"{label}: {val}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Sensors
# ──────────────────────────────────────────────

@mcp.tool()
async def get_sensor_list() -> str:
    """List all available sensors on the device."""
    return format_json(termux('termux-sensor', ['-l']))


@mcp.tool()
async def read_sensor(sensor_name: str, count: int = 1) -> str:
    """Read data from a specific sensor.

    Args:
        sensor_name: Name of the sensor (use get_sensor_list to see available sensors)
        count: Number of readings to take (default: 1)
    """
    return format_json(termux('termux-sensor', ['-s', sensor_name, '-n', str(count)], timeout=15))
