"""MCP Resources — declarative device state data sources."""

import json
import logging
from termux_mcp.app import mcp
from termux_mcp.lib.utils import async_termux, async_run, privileged_available, privileged_shell

logger = logging.getLogger('termux-mcp.resources')


@mcp.resource(uri="device://battery", name="Battery Status",
              description="Current battery state: level, temperature, charging, voltage 🔋",
              mime_type="application/json")
async def battery_resource() -> str:
    try:
        return json.dumps(json.loads(await async_termux('termux-battery-status', timeout=10)),
                          indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource(uri="device://info", name="Device Info",
              description="Device model, Android version, kernel, uptime 📱",
              mime_type="application/json")
async def device_info_resource() -> str:
    props = [('model', 'ro.product.model'), ('brand', 'ro.product.brand'),
             ('android_version', 'ro.build.version.release'), ('sdk_level', 'ro.build.version.sdk'),
             ('build_id', 'ro.build.display.id'), ('manufacturer', 'ro.product.manufacturer'),
             ('device', 'ro.product.device')]
    result = {}
    for key, prop in props:
        r = await async_run(f'getprop {prop}', shell=True, timeout=3)
        result[key] = r.get('stdout', '').strip() or None
    for key, cmd in [('kernel', 'uname -r'), ('arch', 'uname -m')]:
        r = await async_run(cmd, shell=True, timeout=3)
        result[key] = r.get('stdout', '').strip() or None
    r = await async_run('cat /proc/uptime', shell=True, timeout=3)
    up = (r.get('stdout', '') or '').strip().split()[0]
    if up:
        try:
            s = float(up)
            result['uptime'] = f"{int(s//86400)}d {int((s%86400)//3600)}h {int((s%3600)//60)}m"
        except: pass
    result['privileged'] = privileged_available()
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.resource(uri="device://network/wifi", name="WiFi Connection",
              description="Current WiFi: SSID, signal strength, link speed 📶",
              mime_type="application/json")
async def wifi_resource() -> str:
    try:
        d = json.loads(await async_termux('termux-wifi-connectioninfo', timeout=8))
        return json.dumps({'ssid': d.get('ssid'), 'bssid': d.get('bssid'),
                           'signal_dbm': d.get('signal_strength'), 'link_speed_mbps': d.get('link_speed'),
                           'frequency_mhz': d.get('frequency'), 'ip': d.get('ip'),
                           'connected': d.get('supplicant_state') == 'COMPLETED'},
                          indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource(uri="device://network/telephony", name="Telephony Info",
              description="Cellular: carrier, network type, SIM state 📡",
              mime_type="application/json")
async def telephony_resource() -> str:
    try:
        d = json.loads(await async_termux('termux-telephony-deviceinfo', timeout=8))
        return json.dumps({'carrier': d.get('operator_name') or d.get('sim_operator_name'),
                           'network_type': d.get('network_type'), 'sim_state': d.get('sim_state'),
                           'roaming': d.get('roaming'), 'phone_type': d.get('phone_type')},
                          indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource(uri="device://storage", name="Storage Status",
              description="Disk usage: total, used, available 💾",
              mime_type="application/json")
async def storage_resource() -> str:
    from termux_mcp.lib.constants import SDCARD
    result = {}
    try:
        r = await async_run(f'df -B1 {SDCARD}', shell=True, timeout=5)
        for line in r.get('stdout', '').strip().split('\n'):
            parts = line.split()
            if len(parts) >= 6 and SDCARD.name in line:
                d = {'total': int(parts[1]), 'used': int(parts[2]),
                     'available': int(parts[3]), 'use_percent': parts[4]}
                for k in ['total', 'used', 'available']:
                    v = d[k]; unit = 'B'
                    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
                        if v < 1024: unit = u; break
                        v /= 1024
                    d[f'{k}_human'] = f"{v:.1f}{unit}"
                result['sdcard'] = d
                break
    except: pass
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.resource(uri="device://health", name="Device Health Summary",
              description="Quick snapshot: battery + WiFi + storage 🩺",
              mime_type="application/json")
async def health_resource() -> str:
    from datetime import datetime
    from termux_mcp.lib.constants import SDCARD
    result = {'timestamp': datetime.now().isoformat()}
    try:
        b = json.loads(await async_termux('termux-battery-status', timeout=6))
        result['battery'] = {k: b.get(k) for k in ('percentage', 'temperature', 'status', 'health')}
    except: result['battery'] = None
    try:
        w = json.loads(await async_termux('termux-wifi-connectioninfo', timeout=5))
        result['wifi'] = {'ssid': w.get('ssid'), 'signal_dbm': w.get('signal_strength')}
    except: result['wifi'] = None
    try:
        r = await async_run(f'df -h {SDCARD}', shell=True, timeout=5)
        for line in r.get('stdout', '').split('\n'):
            if SDCARD.name in line:
                parts = line.split()
                if len(parts) >= 4:
                    result['storage'] = {'available': parts[3], 'use_pct': parts[4] if len(parts) > 4 else '?'}
                break
    except: pass
    result['privileged'] = privileged_available()
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.resource(uri="device://sensors", name="Sensor List",
              description="Available sensors 🎯", mime_type="application/json")
async def sensors_resource() -> str:
    try:
        data = json.loads(await async_termux('termux-sensor', ['-l'], timeout=8))
        sensors = data if isinstance(data, list) else [data]
        return json.dumps({'count': len(sensors), 'sensors': sensors}, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "count": 0})


@mcp.resource(uri="device://app/foreground", name="Foreground App",
              description="Currently focused app 📌", mime_type="application/json")
async def foreground_app_resource() -> str:
    import re
    try:
        if privileged_available():
            r = privileged_shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3", timeout=5)
            if r['success'] and r.get('stdout', '').strip():
                out = r['stdout'].strip()
                pkg = re.search(r'([a-zA-Z0-9.]+)/', out)
                act = re.search(r'/([a-zA-Z0-9._]+)}', out)
                return json.dumps({'package': pkg.group(1) if pkg else None,
                                   'activity': act.group(1) if act else None}, indent=2, ensure_ascii=False)
        from termux_mcp.tools.ui_smart import _dump_xml
        xml = _dump_xml()
        if xml:
            from xml.etree import ElementTree
            return json.dumps({'package': ElementTree.fromstring(xml).get('package', 'unknown')},
                              indent=2, ensure_ascii=False)
        return json.dumps({"package": None})
    except Exception as e:
        return json.dumps({"error": str(e)})