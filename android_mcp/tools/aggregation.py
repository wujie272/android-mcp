"""Aggregation tools: device_health, analyze_app, quick_status, screen_diagnostics."""

import json
import asyncio
import logging
from android_mcp.app import mcp
from android_mcp.lib.utils import async_termux, async_run, format_json, ok, err, privileged_available, privileged_shell
from android_mcp.lib.constants import SDCARD

logger = logging.getLogger('android-mcp.aggregation')


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

    try:
        from android_mcp.tools.ui_smart import get_foreground_app
        fg = await get_foreground_app()
        if fg and '前台' in fg:
            sections.append(f"📌 **前台** | {fg.split(chr(10))[1].strip() if chr(10) in fg else fg}")
    except: pass

    lines = ["━━━ 📊 设备健康总览 ━━━\n"]
    lines.extend(sections)
    if issues:
        lines.extend(["", "── ⚠️ 注意事项 ──"] + issues)
    score = max(0, 100 - len(issues) * 15)
    lines.append(f"\n{'🏆' if score >= 80 else '⚠️' if score >= 50 else '🔴'} **健康评分: {score}/100**"
                 f"{' — 状态良好' if score >= 80 else ' — 建议关注' if score >= 50 else ' — 需要处理'}")
    return "\n".join(lines)


@mcp.tool()
async def analyze_app(package: str) -> str:
    """Deep app analysis: info + permissions + memory + data + activities."""
    if not package or '.' not in package:
        return "❌ 提供有效包名，如 'com.android.chrome'"

    sections = []

    def _add(title, content):
        sections.append(f"── {title} ──\n{content}\n")

    if privileged_available():
        r = privileged_shell(
            f"dumpsys package {package} | grep -E 'versionName|versionCode|firstInstallTime|"
            f"lastUpdateTime|installerPackageName|uid' | head -10", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            _add("包信息", r['stdout'].strip())

        r = privileged_shell(
            f"dumpsys package {package} | grep -i 'permission:' | "
            f"grep -E 'dangerous|signature|system' | head -30", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            perms = r['stdout'].strip()
            flagged = [l for l in perms.split('\n') if any(x in l.lower() for x in
                       ['location', 'camera', 'contacts', 'microphone', 'sms', 'phone', 'storage'])]
            _add("权限", perms[:2000] + ("\n\n⚠️ 敏感权限: " + "\n".join(flagged[:10]) if flagged else ""))

        r = privileged_shell(f"dumpsys meminfo {package} | head -40", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            _add("内存", r['stdout'].strip()[:1500])

        r = privileged_shell(f"dumpsys package {package} | grep -E 'dataDir|codePath|nativeLibraryPath'", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            _add("路径", r['stdout'].strip())

    r = privileged_shell(f"dumpsys package {package} | grep -A 5 'android.intent.action.MAIN' | head -20", timeout=10) \
        if privileged_available() else await async_run(f"pm dump {package} 2>/dev/null | grep -A 5 'MAIN' | head -20",
                                                        shell=True, timeout=10)
    if r.get('stdout', '').strip():
        _add("Activity", r['stdout'].strip())

    if not sections:
        return f"无法获取 {package} 信息。需要 Shizuku/ADB 权限。"

    return f"🔍 {package} 分析:\n\n" + "\n".join(sections)


@mcp.tool()
async def quick_status() -> str:
    """Desktop-widget style quick overview: battery + WiFi + storage + time."""
    (bat_raw, wifi_raw, df_result, time_raw) = await asyncio.gather(
        async_termux('termux-battery-status', timeout=8),
        async_termux('termux-wifi-connectioninfo', timeout=5),
        async_run(f'df -h {SDCARD} | tail -1', shell=True, timeout=5),
        async_run('date "+%H:%M"', shell=True, timeout=3),
        return_exceptions=True,
    )

    lines = []
    if not isinstance(bat_raw, Exception):
        try:
            b = json.loads(bat_raw)
            pct, temp, status = b.get('percentage', '?'), b.get('temperature', '?'), b.get('status', '?')
            icon = "🟢" if (isinstance(pct, (int, float)) and pct > 20 and isinstance(temp, (int, float)) and temp < 40) else "🟡"
            lines.append(f"{icon} 🔋{pct}%  {temp}°C  {status}")
        except: pass

    if not isinstance(wifi_raw, Exception):
        try:
            w = json.loads(wifi_raw)
            ssid = w.get('ssid', '-')
            sig = w.get('signal_strength', '?')
            lines.append(f"📶 {ssid}  {sig}dBm")
        except: pass

    if not isinstance(df_result, Exception):
        parts = df_result.get('stdout', '').strip().split()
        if len(parts) >= 4:
            lines.append(f"💾 剩余 {parts[3]}")
    else:
        lines.append("💾 ?")

    if not isinstance(time_raw, Exception):
        lines.append(f"🕐 {time_raw.get('stdout', '').strip()}")

    return " | ".join(lines) or "❌ 状态获取失败"


@mcp.tool()
async def screen_diagnostics() -> str:
    """Screen diagnostics: resolution, orientation, brightness, foreground app."""
    from android_mcp.lib.utils import run as sync_run

    res = sync_run('wm size', shell=True, timeout=5).get('stdout', '').strip() if privileged_available() else "?"
    orient = sync_run('dumpsys input | grep "SurfaceOrientation" | head -1', shell=True, timeout=5).get('stdout', '').strip() \
        if privileged_available() else "?"
    lines = [f"📺 Screen: {res}", f"🔄 Orientation: {orient}"]

    if privileged_available():
        brightness = sync_run('settings get system screen_brightness', shell=True, timeout=5).get('stdout', '').strip()
        if brightness:
            lines.append(f"☀️ Brightness: {brightness}/255")

    fg = sync_run("dumpsys window | grep -E 'mCurrentFocus' | head -1", shell=True, timeout=5).get('stdout', '').strip()
    if fg:
        lines.append(f"📌 Focus: {fg}")

    return "\n".join(lines) if lines else "Screen diag: 需要 Shizuku 或 ADB"