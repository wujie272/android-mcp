"""Device info tools: battery, WiFi, telephony, location, storage, sensors."""

from android_mcp.app import mcp
import json as _json
from android_mcp.lib.utils import async_termux, format_json, async_run, ok, err
from android_mcp.lib.constants import SDCARD, PID_FILE, ANDROID_LOG
import logging

logger = logging.getLogger('android-mcp.device_info')


# ── Battery ──

@mcp.tool()
async def get_battery_status() -> str:
    """Get battery status: level, temperature, charging state, health, voltage, current.
    
    Returns JSON. Requires Termux:API. If error, try termux-setup-storage first."""
    try:
        return format_json(await async_termux('termux-battery-status'))
    except Exception as e:
        return err("获取电池状态失败", str(e))


@mcp.tool()
async def get_battery_health() -> str:
    """Get detailed battery metrics: cycle count, capacity, voltage, etc. via dumpsys."""
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
            for k in ('percentage', 'temperature', 'status', 'health', 'source', 'voltage', 'technology', 'current'):
                v = basic.get(k, '?')
                lines.append(f"  {k.replace('_',' ').title():15s} {v}")
        if privileged_available():
            r = privileged_shell("dumpsys batterystats | grep -iE 'cycle|health|capacity' | head -10", timeout=10)
            if r['success'] and r.get('stdout'):
                lines.extend(["", "  ── Detailed (dumpsys) ──"] + [f"  {l.strip()}" for l in r['stdout'].split('\n')])
        return "\n".join(lines)
    except Exception as e:
        return err("获取电池健康信息失败", str(e))


# ── WiFi ──

@mcp.tool()
async def get_wifi_info() -> str:
    """Get WiFi connection info: SSID, BSSID, IP, signal strength, link speed, frequency."""
    try:
        return format_json(await async_termux('termux-wifi-connectioninfo'))
    except Exception as e:
        return err("获取 WiFi 信息失败", str(e))


@mcp.tool()
async def scan_wifi() -> str:
    """Scan nearby WiFi networks (requires location permission)."""
    try:
        return format_json(await async_termux('termux-wifi-scaninfo', timeout=20))
    except Exception as e:
        return err("WiFi 扫描失败", str(e))


@mcp.tool()
async def wifi_qr_code() -> str:
    """Generate a WiFi QR code string (WIFI:S:<SSID>;T:<type>;P:<password>;;).

    Password extraction priority: cmd wifi → WifiConfigStore → wpa_supplicant."""
    import re as _re
    try:
        raw = await async_termux('termux-wifi-connectioninfo')
        try:
            info = _json.loads(raw)
        except Exception:
            return err("无法解析 WiFi 信息", "请确认已连接 WiFi")
        ssid = info.get('ssid', '')
        if not ssid:
            return err("未连接到 WiFi")

        password, source = "", ""
        from android_mcp.lib.utils import privileged_available, privileged_shell
        if privileged_available():
            r = privileged_shell(
                "cmd wifi get-wifi-config 2>/dev/null || cmd wifi list-networks 2>/dev/null", timeout=10)
            if r['success'] and r.get('stdout'):
                m = _re.search(rf'{_re.escape(ssid)}.*?preSharedKey[=:]\s*["\']?([^"\' \n]+)', r['stdout'])
                if m:
                    password, source = m.group(1).strip(), "cmd wifi"

        if not password and privileged_available():
            r = privileged_shell(
                "cat /data/misc/wifi/WifiConfigStore.xml 2>/dev/null || "
                "cat /data/misc/wifi/wpa_supplicant.conf 2>/dev/null", timeout=10)
            if r['success'] and r.get('stdout'):
                m = _re.search(rf'<string\s+name="PreSharedKey">\s*["\']?([^"\'<\n]+)["\']?\s*</string>', r['stdout'])
                if m:
                    password, source = m.group(1).strip().strip('"').strip("'"), "WifiConfigStore"
                else:
                    m = _re.search(rf'ssid="{_re.escape(ssid)}"\n\s*psk="([^"]+)"', r['stdout'])
                    if m:
                        password, source = m.group(1).strip(), "wpa_supplicant"

        sec = info.get('supplicant', '')
        if 'WPA' in sec or 'WEP' in sec:
            sec_type = 'WPA' if 'WEP' not in sec else 'WEP'
        else:
            sec_type = 'WPA' if password else 'nopass'

        lines = [f"📶 SSID: {ssid}", f"🔒 Type: {sec_type}"]
        if password:
            lines.append(f"🔑 Pass: {password}  ({source})")
        elif sec_type == "nopass":
            lines.append("🔑 (开放网络)")
        else:
            lines.append("🔑 (密码自动读取失败)")
            lines.append("💡 可手动在 设置→WiFi→当前网络→扫码分享")

        lines.extend(["", "📱 扫码连接:", f"WIFI:S:{ssid};T:{sec_type};P:{password};;"])
        return "\n".join(lines)
    except Exception as e:
        return err("生成 WiFi QR 码失败", str(e))


# ── Telephony ──

@mcp.tool()
async def get_telephony_info() -> str:
    """Get telephony device info: carrier, network type, SIM state, IMEI, etc."""
    try:
        return format_json(await async_termux('termux-telephony-deviceinfo'))
    except Exception as e:
        return err("获取设备信息失败", str(e))


@mcp.tool()
async def get_telephony_cell_info() -> str:
    """Get cellular cell info: CID, LAC, signal level, ARFCN."""
    try:
        return format_json(await async_termux('termux-telephony-cellinfo'))
    except Exception as e:
        return err("获取基站信息失败", str(e))


# ── Location ──

@mcp.tool()
async def get_location(provider: str = "gps", request: str = "once") -> str:
    """Get phone location.

    Args:
        provider: 'gps', 'network', or 'passive' (default: gps)
        request: 'once', 'last', or 'updates' (default: once)
    """
    try:
        return format_json(await async_termux('termux-location', ['-p', provider, '-r', request], timeout=30))
    except Exception as e:
        logger.warning(f"GPS fail (provider={provider}): {e}")
        if provider == "gps":
            try:
                raw = await async_termux('termux-location', ['-p', 'passive', '-r', 'last'], timeout=10)
                return f"⚠️ GPS 超时，降级到 passive/last:\n\n{format_json(raw)}"
            except Exception:
                pass
        return err("定位失败", f"provider={provider}\n{e}\n💡 检查 Termux 位置权限")


# ── Storage ──

@mcp.tool()
async def get_storage_info() -> str:
    """Get storage usage (disk space)."""
    try:
        r = await async_run(f'df -h {SDCARD} /data 2>/dev/null || df -h', shell=True, timeout=10)
        return r.get('stdout', r.get('error', 'Failed'))
    except Exception as e:
        return err("获取存储信息失败", str(e))


# ── Device Info ──

@mcp.tool()
async def get_device_info() -> str:
    """Get device model, Android version, kernel, architecture, uptime."""
    cmds = {'Model': 'getprop ro.product.model', 'Brand': 'getprop ro.product.brand',
            'Android': 'getprop ro.build.version.release', 'SDK': 'getprop ro.build.version.sdk',
            'Build': 'getprop ro.build.display.id', 'Kernel': 'uname -r',
            'Arch': 'uname -m', 'Uptime': 'uptime'}
    lines = []
    for label, cmd in cmds.items():
        try:
            r = await async_run(cmd, shell=True, timeout=5)
            val = r.get('stdout', '').strip() or 'N/A'
        except Exception:
            val = 'N/A'
        lines.append(f"{label}: {val}")
    return "\n".join(lines)


# ── Sensors ──

@mcp.tool()
async def get_sensor_list() -> str:
    """List all available sensors on the device."""
    try:
        return format_json(await async_termux('termux-sensor', ['-l']))
    except Exception as e:
        return err("获取传感器列表失败", str(e))


@mcp.tool()
async def read_sensor(sensor_name: str, count: int = 1) -> str:
    """Read data from a sensor.

    Args:
        sensor_name: Name from get_sensor_list()
        count: Number of readings (default: 1)
    """
    try:
        return format_json(await async_termux('termux-sensor', ['-s', sensor_name, '-n', str(count)], timeout=15))
    except Exception as e:
        return err(f"读取传感器 {sensor_name} 失败", str(e))


# ── ADB multi-device ──

@mcp.tool()
async def list_adb_devices() -> str:
    """List connected ADB devices (USB + WiFi) with serial, state, and model."""
    try:
        from android_mcp.lib.utils import run as _run
        r = _run('adb devices', shell=True, timeout=10)
        devices_raw = r.get('stdout', '').strip()
        if not devices_raw:
            return "ADB not found. Install android-tools."
        lines = devices_raw.split('\n')
        devices = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) == 2:
                serial, state = parts
                conn = "🌐 WiFi" if ":" in serial else "🔌 USB"
                devices.append((serial, state, conn))
        if not devices:
            return "📱 No ADB devices connected."

        result = [f"📱 ADB Devices ({len(devices)}):\n"]
        for serial, state, conn in devices:
            model = "?"
            if state == "device":
                r2 = _run(f'adb -s {serial} shell getprop ro.product.model', shell=True, timeout=3)
                model = r2.get('stdout', '').strip() or '?'
            icon = "✅" if state == "device" else "⚠️"
            result.append(f"  {conn} {icon} {serial}  (State: {state}  Model: {model})")
        return "\n".join(result)
    except Exception as e:
        return err("获取设备列表失败", str(e))


# ── Health check ──

@mcp.tool()
async def device_health_report() -> str:
    """Check android-mcp service health (uptime, PID, log size). For auto-recovery."""
    from android_mcp.lib.utils import get_uptime
    uptime_secs = get_uptime()
    h, m, s = int(uptime_secs // 3600), int((uptime_secs % 3600) // 60), int(uptime_secs % 60)
    pid_exists = PID_FILE.exists()
    pid_content = PID_FILE.read_text().strip() if pid_exists else 'N/A'
    log_size = ANDROID_LOG.stat().st_size if ANDROID_LOG.exists() else 0
    return (
        f"🩺 android-mcp 健康检查\n"
        f"  运行时间: {h}h {m}m {s}s  PID: {pid_content}\n"
        f"  PID文件: {'✅' if pid_exists else '❌'}  日志: {log_size:,} bytes\n"
        f"  版本: 0.4.0  Shizuku/ADB: 查看 adb_status()\n"
        f"  💡 重启: restart_android()"
    )