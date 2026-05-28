"""Device Information: battery, WiFi, telephony, location, storage, sensors, device info.

优化日志 v2.0:
  - 所有工具添加 try/except 异常保护（防止崩溃退出）
  - get_location 添加超时降级（GPS 超时自动切 passive）
  - 替换同步 run() 为 async_run() 避免阻塞事件循环
"""

from android_mcp.app import mcp
import json as _json
from android_mcp.lib.utils import async_termux, format_json, async_run, ok, err
from android_mcp.lib.constants import SDCARD, PID_FILE, ANDROID_LOG
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
    """Get phone battery status including level, charging state, temperature, etc.

    返回 JSON 包含: percentage(电量%), temperature(温度°C),
    status(充电状态: CHARGING/DISCHARGING), health(健康度), source(电源来源),
    voltage(电压mV), current(电流mA), technology(电池类型).

    需要安装 Termux:API。如果返回错误，可尝试先运行 termux-setup-storage。
    """
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
    """Get current WiFi connection information.

    返回: SSID(网络名), BSSID(路由器MAC), IP地址,
    signal_strength(信号强度, 负值/dBm), link_speed(Mbps),
    frequency(频段Hz), supplicant_state(认证状态).
    需要已连接 WiFi 且安装了 Termux:API。
    """
    try:
        raw = await async_termux('termux-wifi-connectioninfo')
        return format_json(raw)
    except Exception as e:
        return err("获取 WiFi 信息失败", str(e))


@mcp.tool()
async def scan_wifi() -> str:
    """Scan for nearby WiFi networks.

    返回附近所有 WiFi 热点的列表，包含 SSID、BSSID、
    信号强度、加密类型、频段等信息。
    需要安装 Termux:API 并授予位置权限。
    """
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
    """Get telephony/network device info.

    返回: carrier(运营商), network_type(4G/5G),
    sim_state(SIM卡状态), phone_type(GSM/CDMA),
    roaming(是否漫游), imei(设备标识), etc.
    需要安装 Termux:API 并授予电话权限。
    """
    try:
        raw = await async_termux('termux-telephony-deviceinfo')
        return format_json(raw)
    except Exception as e:
        return err("获取设备信息失败", str(e))


@mcp.tool()
async def get_telephony_cell_info() -> str:
    """Get detailed cellular network information.

    返回基站信息: CID(小区ID), LAC(位置区码),
    PSC(主扰码), signal_level(信号强度, dBm),
    arfcn(绝对无线频道号) 等。
    需要安装 Termux:API 并授予电话权限。
    """
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
        r = await async_run(f'df -h {SDCARD} /data 2>/dev/null || df -h', shell=True, timeout=10)
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

    密码提取策略（按优先级）:
      1. cmd wifi (Android 12+, 需 Shizuku/ADB)
      2. WifiConfigStore.xml (Android 11-, 需 root 或 Shizuku)
      3. wpa_supplicant.conf (旧版 Android)
    """
    try:
        raw = await async_termux('termux-wifi-connectioninfo')
        try:
            info = _json.loads(raw)
        except Exception:
            return err("无法解析 WiFi 信息", "请确保已连接 WiFi")

        ssid = info.get('ssid', '')
        if not ssid:
            return err("未连接到 WiFi")

        password = ""
        source = ""

        # ── 策略 1: cmd wifi (Android 12+, 推荐) ──
        from android_mcp.lib.utils import privileged_available, privileged_shell
        if privileged_available():
            r = privileged_shell("cmd wifi get-wifi-config 2>/dev/null || "
                                 "cmd wifi list-networks 2>/dev/null", timeout=10)
            if r['success'] and r.get('stdout'):
                # Parse network config
                m = _re.search(rf'{_re.escape(ssid)}.*?preSharedKey[=:]\s*["\']?([^"\' \n]+)', r['stdout'])
                if m:
                    password = m.group(1).strip()
                    source = "cmd wifi"

        # ── 策略 2: WifiConfigStore.xml ──
        if not password and privileged_available():
            r = privileged_shell(
                "cat /data/misc/wifi/WifiConfigStore.xml 2>/dev/null || "
                "cat /data/misc/wifi/wpa_supplicant.conf 2>/dev/null",
                timeout=10
            )
            if r['success'] and r.get('stdout'):
                # Try WifiConfigStore XML format
                m = _re.search(
                    rf'<string\s+name="PreSharedKey">\s*({_re.escape(ssid)}\s*)?'
                    rf'["\']?([^"\'<\n]+)["\']?\s*</string>',
                    r['stdout']
                )
                if m:
                    password = m.group(2) or m.group(1)
                    password = password.strip().strip('"').strip("'")
                    source = "WifiConfigStore.xml"
                else:
                    # Try wpa_supplicant format
                    m = _re.search(
                        rf'ssid="{_re.escape(ssid)}"\n\s*psk="([^"]+)"',
                        r['stdout']
                    )
                    if m:
                        password = m.group(1).strip()
                        source = "wpa_supplicant.conf"

        # ── 判断加密类型 ──
        sec_type = info.get('supplicant', '')
        encryption_type = info.get('encryption_type', '')
        if 'WPA3' in sec_type or 'WPA3' in encryption_type:
            sec_type = 'WPA'
        elif 'WPA2' in sec_type or 'WPA' in sec_type:
            sec_type = 'WPA'
        elif 'WEP' in sec_type:
            sec_type = 'WEP'
        else:
            sec_type = 'WPA' if password else 'nopass'

        qr_str = f"WIFI:S:{ssid};T:{sec_type};P:{password};;"

        lines = [
            f"📶 SSID:  {ssid}",
            f"🔒 Type:  {sec_type}",
        ]
        if password:
            lines.append(f"🔑 Pass:  {password}")
            if source:
                lines.append(f"📎 Source: {source}")
        elif sec_type == "nopass":
            lines.append(f"🔑 Pass:  (开放网络，无需密码)")
        else:
            lines.append(f"🔑 Pass:  (无法自动读取)")
            lines.append(f"")
            lines.append(f"⚠️  Android 12+ 限制了 WiFi 密码读取。可能的原因：")
            lines.append(f"   • Shizuku 未运行或未授权")
            lines.append(f"   • 系统限制了配置读取权限")
            lines.append(f"💡 可手动在 设置 → WiFi → 点击当前网络 → 扫码 用二维码分享")

        lines.extend([
            "",
            "📱 扫码连接字符串:",
            qr_str,
        ])
        return "\n".join(lines)

    except Exception as e:
        return err("生成 WiFi QR 码失败", str(e))


# ──────────────────────────────────────────────
# Multi-Device List
# ──────────────────────────────────────────────


@mcp.tool()
async def list_adb_devices() -> str:
    """List all connected ADB devices (USB + WiFi) with serial, state, and model info.

    当你有多个设备时，可先用此工具查看所有设备，
    然后通过 adb_connect() / adb_status() 连接到指定设备。
    """
    try:
        from android_mcp.lib.utils import run as _run

        # 1. adb devices
        r = _run('adb devices', shell=True, timeout=10)
        devices_raw = r.get('stdout', '').strip()
        if not devices_raw:
            return "未找到 ADB 命令。需要安装 android-tools。"

        lines = devices_raw.split('\n')
        device_list = []
        for line in lines[1:]:  # 跳过 "List of devices attached"
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) == 2:
                serial, state = parts
                conn_type = "🌐 WiFi" if ":" in serial else "🔌 USB"
                device_list.append((serial, state, conn_type))

        if not device_list:
            return "📱 没有连接的 ADB 设备。\n   • USB: 用数据线连接并开启 USB 调试\n   • WiFi: 用 adb_connect() 工具连接"

        # 2. 尝试获取每个设备的型号
        result = [f"📱 ADB Devices ({len(device_list)}):\n"]
        for serial, state, conn_type in device_list:
            model = "?"
            if state == "device":
                r2 = _run(f'adb -s {serial} shell getprop ro.product.model', shell=True, timeout=3)
                model = r2.get('stdout', '').strip() or '?'

            state_icon = "✅" if state == "device" else "⚠️"
            result.append(f"  {conn_type} {state_icon} {serial}")
            result.append(f"     State: {state}   Model: {model}")

        result.append(f"\n💡 本机使用的设备: 查看 adb_status() 获取当前连接方式")
        return "\n".join(result)
    except Exception as e:
        return err("获取设备列表失败", str(e))


# ──────────────────────────────────────────────
# Health Check（服务自愈）
# ──────────────────────────────────────────────

@mcp.tool()
async def device_health_report() -> str:
    """检查 android-mcp 服务健康状态。

    返回服务运行时长、工具加载状态、PID 等信息。
    供 mcp-manager 轮询实现自动重启（服务自愈）。
    """
    from android_mcp.lib.utils import get_uptime

    uptime_secs = get_uptime()
    hours = int(uptime_secs // 3600)
    minutes = int((uptime_secs % 3600) // 60)
    seconds = int(uptime_secs % 60)

    pid_exists = PID_FILE.exists()
    pid_content = PID_FILE.read_text().strip() if pid_exists else 'N/A'
    log_size = ANDROID_LOG.stat().st_size if ANDROID_LOG.exists() else 0

    lines = [
        "🩺 android-mcp 健康检查",
        "",
        f"  运行时间:  {hours}h {minutes}m {seconds}s",
        f"  进程 PID:  {pid_content}",
        f"  PID 文件:  {'✅ 存在' if pid_exists else '❌ 不存在'}",
        f"  日志大小:  {log_size:,} bytes",
        f"  服务版本:  0.2.0",
        f"  Shizuku:   查看 adb_status()",
        "",
        "💡 提示:",
        "  • HTTP 服务也提供 /health 端点（JSON 格式）",
        f"  • 日志文件: {ANDROID_LOG}",
        "  • 重启服务: restart_android()",
    ]
    return "\n".join(lines)