"""MCP Resources — 设备状态数据源。

Resources 是可读的、可订阅的数据源，与 Tools（执行操作）不同：
  - Tools 做事情（命令式）
  - Resources 提供数据（声明式）

URI 设计:
  device://battery          → 电池状态
  device://info             → 设备基本信息
  device://network/wifi     → WiFi 连接信息
  device://network/telephony → 蜂窝网络信息
  device://storage          → 存储使用情况
  device://health           → 健康状态摘要
  device://sensors          → 传感器列表
  device://app/foreground   → 前台应用信息
"""

import json
import logging

from android_mcp.app import mcp
from android_mcp.lib.utils import (
    async_termux, async_run,
    privileged_available, privileged_shell,
)

logger = logging.getLogger('android-mcp.resources')


# ══════════════════════════════════════════════
# Resource: 电池状态
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://battery",
    name="Battery Status",
    description="当前电池状态：电量、温度、充电状态、电压、电流等 🔋",
    mime_type="application/json",
)
async def battery_resource() -> str:
    try:
        raw = await async_termux('termux-battery-status', timeout=10)
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ══════════════════════════════════════════════
# Resource: 设备信息
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://info",
    name="Device Info",
    description="设备基本信息：型号、品牌、Android 版本、内核等 📱",
    mime_type="application/json",
)
async def device_info_resource() -> str:
    props = [
        ('model', 'ro.product.model'),
        ('brand', 'ro.product.brand'),
        ('android_version', 'ro.build.version.release'),
        ('sdk_level', 'ro.build.version.sdk'),
        ('build_id', 'ro.build.display.id'),
        ('manufacturer', 'ro.product.manufacturer'),
        ('device', 'ro.product.device'),
    ]
    result = {}
    for key, prop in props:
        r = await async_run(f'getprop {prop}', shell=True, timeout=3)
        result[key] = r.get('stdout', '').strip() or None

    r = await async_run('uname -r', shell=True, timeout=3)
    result['kernel'] = r.get('stdout', '').strip() or None

    r = await async_run('uname -m', shell=True, timeout=3)
    result['architecture'] = r.get('stdout', '').strip() or None

    # uptime
    r = await async_run('cat /proc/uptime', shell=True, timeout=3)
    uptime_str = r.get('stdout', '').strip().split()[0] if r.get('stdout') else None
    if uptime_str:
        try:
            seconds = float(uptime_str)
            result['uptime'] = f"{int(seconds//86400)}d {int((seconds%86400)//3600)}h {int((seconds%3600)//60)}m"
        except ValueError:
            result['uptime'] = uptime_str

    result['privileged'] = privileged_available()
    return json.dumps(result, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════
# Resource: WiFi 网络
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://network/wifi",
    name="WiFi Connection",
    description="当前 WiFi 连接：SSID、信号强度、速率、频段等 📶",
    mime_type="application/json",
)
async def wifi_resource() -> str:
    try:
        raw = await async_termux('termux-wifi-connectioninfo', timeout=8)
        data = json.loads(raw)
        summary = {
            'ssid': data.get('ssid'),
            'bssid': data.get('bssid'),
            'signal_strength_dbm': data.get('signal_strength'),
            'link_speed_mbps': data.get('link_speed'),
            'frequency_mhz': data.get('frequency'),
            'ip_address': data.get('ip'),
            'is_connected': data.get('supplicant_state') == 'COMPLETED',
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ══════════════════════════════════════════════
# Resource: 蜂窝网络
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://network/telephony",
    name="Telephony Info",
    description="蜂窝网络：运营商、网络类型、SIM 状态等 📡",
    mime_type="application/json",
)
async def telephony_resource() -> str:
    try:
        raw = await async_termux('termux-telephony-deviceinfo', timeout=8)
        data = json.loads(raw)
        summary = {
            'carrier': data.get('operator_name') or data.get('sim_operator_name'),
            'network_type': data.get('network_type') or data.get('data_network_type'),
            'sim_state': data.get('sim_state'),
            'sim_count': data.get('sim_count'),
            'roaming': data.get('roaming'),
            'phone_type': data.get('phone_type'),
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ══════════════════════════════════════════════
# Resource: 存储状态
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://storage",
    name="Storage Status",
    description="存储使用情况：总量、已用、剩余 💾",
    mime_type="application/json",
)
async def storage_resource() -> str:
    from android_mcp.lib.constants import SDCARD
    result = {}
    try:
        r = await async_run(f'df -B1 {SDCARD}', shell=True, timeout=5)
        for line in r.get('stdout', '').strip().split('\n'):
            parts = line.split()
            if len(parts) >= 6 and SDCARD.name in line:
                d = {'total': int(parts[1]), 'used': int(parts[2]),
                     'available': int(parts[3]), 'use_percent': parts[4]}
                for k in ['total', 'used', 'available']:
                    v = d[k]
                    for u in ['B','KB','MB','GB','TB']:
                        if v < 1024: d[f'{k}_human'] = f"{v:.1f}{u}"; break
                        v /= 1024
                result['sdcard'] = d
                break
    except Exception:
        pass
    return json.dumps(result, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════
# Resource: 健康摘要
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://health",
    name="Device Health Summary",
    description="设备健康摘要：电池+WiFi+存储一键快照 🩺",
    mime_type="application/json",
)
async def health_resource() -> str:
    from datetime import datetime
    from android_mcp.lib.constants import SDCARD
    result = {'timestamp': datetime.now().isoformat()}

    try:
        raw = await async_termux('termux-battery-status', timeout=6)
        bat = json.loads(raw)
        result['battery'] = {k: bat.get(k) for k in ('percentage','temperature','status','health')}
    except Exception:
        result['battery'] = None

    try:
        raw = await async_termux('termux-wifi-connectioninfo', timeout=5)
        wifi = json.loads(raw)
        result['wifi'] = {'ssid': wifi.get('ssid'), 'signal_dbm': wifi.get('signal_strength')}
    except Exception:
        result['wifi'] = None

    try:
        r = await async_run(f'df -h {SDCARD}', shell=True, timeout=5)
        for line in r.get('stdout','').split('\n'):
            if SDCARD.name in line:
                parts = line.split()
                if len(parts) >= 4:
                    result['storage'] = {'available': parts[3], 'use_percent': parts[4] if len(parts)>4 else '?'}
                break
    except Exception:
        pass

    result['privileged'] = privileged_available()
    return json.dumps(result, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════
# Resource: 传感器列表
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://sensors",
    name="Sensor List",
    description="设备可用传感器列表 🎯",
    mime_type="application/json",
)
async def sensors_resource() -> str:
    try:
        raw = await async_termux('termux-sensor', ['-l'], timeout=8)
        data = json.loads(raw)
        sensors = data if isinstance(data, list) else [data]
        return json.dumps({'count': len(sensors), 'sensors': sensors}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "count": 0}, indent=2)


# ══════════════════════════════════════════════
# Resource: 前台应用
# ══════════════════════════════════════════════

@mcp.resource(
    uri="device://app/foreground",
    name="Foreground App",
    description="当前前台运行的 App 📌",
    mime_type="application/json",
)
async def foreground_app_resource() -> str:
    import re
    try:
        if privileged_available():
            r = privileged_shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3", timeout=5)
            if r['success'] and r.get('stdout','').strip():
                out = r['stdout'].strip()
                pkg_m = re.search(r'([a-zA-Z0-9.]+)/', out)
                act_m = re.search(r'/([a-zA-Z0-9._]+)}', out)
                return json.dumps({
                    'package': pkg_m.group(1) if pkg_m else None,
                    'activity': act_m.group(1) if act_m else None,
                    'source': 'dumpsys window',
                }, indent=2, ensure_ascii=False)

        from android_mcp.tools.ui_smart import _dump_xml
        xml = _dump_xml()
        if xml:
            from xml.etree import ElementTree
            pkg = ElementTree.fromstring(xml).get('package', 'unknown')
            return json.dumps({'package': pkg, 'source': 'uiautomator'}, indent=2, ensure_ascii=False)

        return json.dumps({"package": None, "note": "无法获取"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)