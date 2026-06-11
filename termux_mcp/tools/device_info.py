"""Device info tools: battery, WiFi, telephony, location, storage, sensors."""

from termux_mcp.app import mcp
import json as _json
from termux_mcp.lib.utils import async_termux, format_json, async_run, ok, err
from termux_mcp.lib.constants import SDCARD, PID_FILE, ANDROID_LOG
from termux_mcp.lib.utils import run as sync_run, privileged_available, privileged_shell
import asyncio


# ── Screen Size ──

@mcp.tool()
async def get_screen_size() -> str:
    """Get screen resolution (width x height)."""
    if privileged_available():
        r = sync_run('wm size', shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out
        r = sync_run("dumpsys display | grep -E 'mDisplayWidth|mDisplayHeight' | head -5", shell=True, timeout=5)
        out = r.get('stdout', '').strip()
        if out:
            return out
    r_w = sync_run('getprop ro.sf.lcd_width', shell=True, timeout=3)
    r_h = sync_run('getprop ro.sf.lcd_height', shell=True, timeout=3)
    w, h = r_w.get('stdout', '').strip(), r_h.get('stdout', '').strip()
    if w and h:
        return f"Physical: {w}x{h} (from properties)"
    return "Need Shizuku or ADB to get screen size."


import logging

logger = logging.getLogger('termux-mcp.device_info')


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
    from termux_mcp.lib.utils import privileged_available, privileged_shell
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
        from termux_mcp.lib.utils import privileged_available, privileged_shell
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
        from termux_mcp.lib.utils import run as _run
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
    """Check termux-mcp service health (uptime, PID, log size). For auto-recovery."""
    from termux_mcp.lib.utils import get_uptime
    uptime_secs = get_uptime()
    h, m, s = int(uptime_secs // 3600), int((uptime_secs % 3600) // 60), int(uptime_secs % 60)
    pid_exists = PID_FILE.exists()
    pid_content = PID_FILE.read_text().strip() if pid_exists else 'N/A'
    log_size = ANDROID_LOG.stat().st_size if ANDROID_LOG.exists() else 0
    return (
        f"🩺 termux-mcp 健康检查\n"
        f"  运行时间: {h}h {m}m {s}s  PID: {pid_content}\n"
        f"  PID文件: {'✅' if pid_exists else '❌'}  日志: {log_size:,} bytes\n"
        f"  版本: 0.4.0  Shizuku/ADB: 查看 adb_status()\n"
        f"  💡 重启: restart_android()"
    )


# ── Device Health (merged from aggregation) ──

@mcp.tool()
async def device_health() -> str:
    """One-shot device health: battery + storage + memory + WiFi + CPU + processes.

    ⚡ 7 parallel data sources via asyncio.gather. Read-only.
    """
    (bat_raw, df_result, mem_result, wifi_raw,
     model_result, android_result, uptime_result) = await asyncio.gather(
        async_termux('termux-battery-status', timeout=10),
        async_run(f'df -h {SDCARD}', shell=True, timeout=10),
        async_run("cat /proc/meminfo | grep -E 'MemTotal|MemAvailable|MemFree'", shell=True, timeout=5),
        async_termux('termux-wifi-connectioninfo', timeout=8),
        async_run('getprop ro.product.model', shell=True, timeout=3),
        async_run('getprop ro.build.version.release', shell=True, timeout=3),
        async_run('uptime', shell=True, timeout=3),
        return_exceptions=True,
    )

    sections, issues = [], []

    if not isinstance(bat_raw, Exception):
        try:
            b = json.loads(bat_raw)
            pct, temp = b.get('percentage', '?'), b.get('temperature', '?')
            tn, pn = float(temp) if temp != '?' else 0, float(pct) if pct != '?' else 0
            icon = "🟢" if pn > 20 and tn < 40 else ("🟡" if pn > 10 else "🔴")
            sections.append(f"{icon} **电池** | {pct}% | {temp}°C | {b.get('status','?')} | 健康: {b.get('health','?')}")
            if pn <= 10: issues.append("🔴 电量极低(≤10%)")
            elif pn <= 20: issues.append("🟡 电量偏低(≤20%)")
            if tn >= 40: issues.append("🔴 温度过高(≥40°C)")
            elif tn >= 37: issues.append("🟡 温度偏高(≥37°C)")
        except Exception as e:
            sections.append(f"⚪ **电池** | 解析失败")
    else:
        sections.append(f"⚪ **电池** | 获取失败")

    if not isinstance(df_result, Exception) and df_result.get('success'):
        try:
            for line in df_result.get('stdout', '').strip().split('\n'):
                if '/storage' in line or SDCARD.name in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pct_str = parts[4].replace('%', '')
                        sections.append(f"💾 **存储** | 总量:{parts[1]} 已用:{parts[2]} 剩余:{parts[3]} 使用率:{parts[4]}")
                        try:
                            pv = float(pct_str)
                            if pv >= 90: issues.append(f"🔴 存储即将耗尽({parts[4]})")
                            elif pv >= 80: issues.append(f"🟡 存储不足({parts[4]})")
                        except: pass
                        break
        except: pass
    else:
        sections.append("⚪ **存储** | 获取失败")

    if not isinstance(mem_result, Exception) and mem_result.get('success'):
        try:
            info = mem_result.get('stdout', '')
            total = next((l.split(':')[1].strip() for l in info.split('\n') if 'MemTotal' in l), '')
            avail = next((l.split(':')[1].strip() for l in info.split('\n') if 'MemAvailable' in l), '')
            if total and avail:
                tk = int(total.replace('kB', '').strip())
                ak = int(avail.replace('kB', '').strip())
                up = (tk - ak) / tk * 100
                icon = "🟢" if up < 70 else ("🟡" if up < 85 else "🔴")
                sections.append(f"{icon} **内存** | 总量:{total} 可用:{avail} 使用率:{up:.0f}%")
                if up >= 85: issues.append(f"🔴 内存使用率过高({up:.0f}%)")
                elif up >= 70: issues.append(f"🟡 内存偏高({up:.0f}%)")
            else:
                sections.append(f"💾 **内存** | {total} 总量 | {avail} 可用")
        except: pass
    else:
        sections.append("⚪ **内存** | 获取失败")

    if not isinstance(wifi_raw, Exception):
        try:
            w = json.loads(wifi_raw)
            ssid, sig = w.get('ssid', '未连接'), w.get('signal_strength', '?')
            si = "🟢"
            if sig != '?':
                try:
                    sv = int(sig)
                    if sv < -80: si = "🔴"; issues.append(f"🔴 WiFi 信号极弱({sv}dBm)")
                    elif sv < -65: si = "🟡"
                except: pass
            sections.append(f"{si} **网络** | {ssid} | 信号:{sig}dBm | 速率:{w.get('link_speed','?')}Mbps")
        except: pass
    else:
        sections.append("⚪ **网络** | 获取失败")

    model = model_result.get('stdout', '').strip() if not isinstance(model_result, Exception) else '?'
    android = android_result.get('stdout', '').strip() if not isinstance(android_result, Exception) else '?'
    sections.append(f"📱 **设备** | {model} | Android {android}")

    if not isinstance(uptime_result, Exception):
        up = uptime_result.get('stdout', '').strip()
        if up:
            parts = up.split('load average:')
            sections.append(f"⏱ **运行** | {parts[0].strip()}" + (f" | 负载:{parts[1].strip()}" if len(parts) > 1 else ""))

    lines = ["━━━ 📊 设备健康总览 ━━━\n"]
    lines.extend(sections)
    if issues:
        lines.extend(["", "── ⚠️ 注意事项 ──"] + issues)
    score = max(0, 100 - len(issues) * 15)
    lines.append(f"\n{'🏆' if score >= 80 else '⚠️' if score >= 50 else '🔴'} **健康评分: {score}/100**"
                 f"{' — 状态良好' if score >= 80 else ' — 建议关注' if score >= 50 else ' — 需要处理'}")
    return "\n".join(lines)

