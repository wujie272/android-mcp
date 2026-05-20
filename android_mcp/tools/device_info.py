"""Device Information: battery, WiFi, telephony, location, storage, sensors, device info.

优化日志 v2.0:
  - 所有工具添加 try/except 异常保护（防止崩溃退出）
  - get_location 添加超时降级（GPS 超时自动切 passive）
  - 替换同步 run() 为 async_run() 避免阻塞事件循环
"""

from android_mcp.app import mcp
import json as _json
from android_mcp.lib.utils import async_termux, format_json, async_run, ok, err
import logging

logger = logging.getLogger('android-mcp.device_info')


# ── 安全执行 termux 命令的包装器 ──

async def _safe_termux(cmd: str, args: list[str] | None = None, timeout: int = 30,
                      fallback: str = "") -> str:
    """安全执行 termux 命令，失败返回 fallback 或错误信息（不会崩溃）"""
    try:
        result = await async_termux(cmd, args, timeout=timeout)
        return result
    except Exception as e:
        logger.warning(f"{cmd} 失败: {e}")
        return fallback if fallback else f"Error: {e}"


# ──────────────────────────────────────────────
# Battery
# ──────────────────────────────────────────────

@mcp.tool()
async def get_battery_status() -> str:
    """Get phone battery status including level, charging state, temperature, etc."""
    try:
        raw = await async_termux('termux-battery-status')
        return format_json(raw)
    except Exception as e:
        return err("获取电池状态失败", str(e))


# ──────────────────────────────────────────────
# WiFi
# ──────────────────────────────────────────────

@mcp.tool()
async def get_wifi_info() -> str:
    """Get current WiFi connection information (SSID, IP, signal strength, etc.)."""
    try:
        raw = await async_termux('termux-wifi-connectioninfo')
        return format_json(raw)
    except Exception as e:
        return err("获取 WiFi 信息失败", str(e))


@mcp.tool()
async def scan_wifi() -> str:
    """Scan for nearby WiFi networks."""
    try:
        raw = await async_termux('termux-wifi-scaninfo', timeout=20)
        return format_json(raw)
    except Exception as e:
        return err("WiFi 扫描失败", str(e))


# ──────────────────────────────────────────────
# Telephony
# ──────────────────────────────────────────────

@mcp.tool()
async def get_telephony_info() -> str:
    """Get telephony device info (carrier, phone type, SIM state, etc.)."""
    try:
        raw = await async_termux('termux-telephony-deviceinfo')
        return format_json(raw)
    except Exception as e:
        return err("获取设备信息失败", str(e))


@mcp.tool()
async def get_telephony_cell_info() -> str:
    """Get detailed cellular network information."""
    try:
        raw = await async_termux('termux-telephony-cellinfo')
        return format_json(raw)
    except Exception as e:
        return err("获取基站信息失败", str(e))


# ──────────────────────────────────────────────
# Location (GPS — 最易超时的工具)
# ──────────────────────────────────────────────

@mcp.tool()
async def get_location(provider: str = "gps", request: str = "once") -> str:
    """Get the phone's current GPS location.

    Args:
        provider: Location provider - 'gps', 'network', or 'passive' (default: gps)
        request: 'once' for single reading, 'last' for last known location, 'updates' for continuous
    """
    try:
        raw = await async_termux('termux-location', ['-p', provider, '-r', request], timeout=30)
        return format_json(raw)
    except Exception as e:
        logger.warning(f"GPS 定位失败 (provider={provider}): {e}")
        # GPS 超时时主动降级尝试其他 provider
        if provider == "gps":
            try:
                raw = await async_termux('termux-location', ['-p', 'passive', '-r', 'last'], timeout=10)
                return f"⚠️ GPS 定位超时，已自动降级到 passive/last:\n\n{format_json(raw)}"
            except Exception:
                pass
        return err(f"定位失败", f"provider={provider}, request={request}\n错误: {e}\n\n💡 提示: 确保已在手机设置中授予 Termux 位置权限")


# ──────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────

@mcp.tool()
async def get_storage_info() -> str:
    """Get phone storage usage information (disk space)."""
    try:
        r = await async_run('df -h /storage/emulated/0 /data 2>/dev/null || df -h', shell=True, timeout=10)
        return r.get('stdout', r.get('error', 'Failed'))
    except Exception as e:
        return err("获取存储信息失败", str(e))


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
        try:
            r = await async_run(cmd, shell=True, timeout=5)
            val = r.get('stdout', '').strip() or 'N/A'
        except Exception:
            val = 'N/A'
        lines.append(f"{label}: {val}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Sensors
# ──────────────────────────────────────────────

@mcp.tool()
async def get_sensor_list() -> str:
    """List all available sensors on the device."""
    try:
        raw = await async_termux('termux-sensor', ['-l'])
        return format_json(raw)
    except Exception as e:
        return err("获取传感器列表失败", str(e))


@mcp.tool()
async def read_sensor(sensor_name: str, count: int = 1) -> str:
    """Read data from a specific sensor.

    Args:
        sensor_name: Name of the sensor (use get_sensor_list to see available sensors)
        count: Number of readings to take (default: 1)
    """
    try:
        raw = await async_termux('termux-sensor', ['-s', sensor_name, '-n', str(count)], timeout=15)
        return format_json(raw)
    except Exception as e:
        return err(f"读取传感器 {sensor_name} 失败", str(e))


# ──────────────────────────────────────────────
# Battery Health
# ──────────────────────────────────────────────

@mcp.tool()
async def get_battery_health() -> str:
    """Get battery health info: cycle count, capacity, voltage, technology, etc.

    Uses dumpsys batterystats for detailed battery metrics.
    """
    from android_mcp.lib.utils import privileged_available, privileged_shell

    try:
        raw = await async_termux('termux-battery-status')
        basic = {}
        try:
            basic = _json.loads(raw)
        except Exception:
            pass

        lines = ["🔋 Battery Health Report:", ""]

        if basic:
            pct = basic.get('percentage', '?')
            temp = basic.get('temperature', '?')
            status = basic.get('status', '?')
            lines.append(f"  Level:       {pct}%")
            lines.append(f"  Temperature: {temp}°C")
            lines.append(f"  Status:      {status}")
            lines.append(f"  Health:      {basic.get('health', '?')}")
            lines.append(f"  Source:      {basic.get('source', '?')}")
            lines.append(f"  Voltage:     {basic.get('voltage', '?')}mV")
            lines.append(f"  Technology:  {basic.get('technology', '?')}")
            lines.append(f"  Current:     {basic.get('current', '?')}mA")

        if privileged_available():
            r = privileged_shell("dumpsys batterystats | grep -iE 'cycle|health|capacity' | head -10", timeout=10)
            if r['success'] and r.get('stdout'):
                lines.append("")
                lines.append("  ── Detailed Stats (rish/adb) ──")
                for line in r['stdout'].split('\n'):
                    lines.append(f"  {line.strip()}")

        return "\n".join(lines)
    except Exception as e:
        return err("获取电池健康信息失败", str(e))


# ──────────────────────────────────────────────
# WiFi QR Code
# ──────────────────────────────────────────────

@mcp.tool()
async def wifi_qr_code() -> str:
    """Generate a WiFi QR code string for the current network.

    Output is a WIFI:S:<SSID>;T:<WPA|WEP|nopass>;P:<password>;; string
    that can be scanned to join the network.
    Compatible with all QR code scanner apps.
    """
    try:
        raw = await async_termux('termux-wifi-connectioninfo')
        try:
            info = _json.loads(raw)
        except Exception:
            return err("无法解析 WiFi 信息", "Make sure WiFi is connected.")

        ssid = info.get('ssid', '')
        if not ssid:
            return err("未连接到 WiFi")

        # Try to get password from saved config
        r = await async_run(
            'cat /data/misc/wifi/WifiConfigStore.xml 2>/dev/null || '
            'cat /data/misc/wifi/wpa_supplicant.conf 2>/dev/null || '
            'echo "N/A"',
            shell=True, timeout=5
        )

        password = ""
        import re
        if r['success']:
            m = re.search(rf'{re.escape(ssid)}.*?PreSharedKey["\s=]*({{)?["\s]*([^}}"<\n]+)', r['stdout'], re.DOTALL)
            if m:
                password = m.group(2).strip()
            if not password:
                m = re.search(rf'ssid="{re.escape(ssid)}"\n\s*psk="([^"]+)"', r['stdout'])
                if m:
                    password = m.group(1).strip()

        sec_type = "WPA" if password else "nopass"
        qr_str = f"WIFI:S:{ssid};T:{sec_type};P:{password};;"

        lines = [
            f"📶 WiFi: {ssid}",
            f"🔒 Type: {sec_type}",
            f"🔑 Pass: {password or '(open network / need root)'}",
            "",
            "📱 Scan this QR code to connect:",
            qr_str,
            "",
            "💡 Tip: Use a QR scanner app or 'termux-qr' to display.",
        ]
        return "\n".join(lines)
    except Exception as e:
        return err("生成 WiFi QR 码失败", str(e))