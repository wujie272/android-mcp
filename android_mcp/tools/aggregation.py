"""Aggregation Tools — 聚合多个维度数据，一次返回全景信息。

解决了"AI 需要多次调用才能拼出完整图景"的问题。

包含：
  - device_health()      → 电池 + 存储 + 内存 + 网络 + 进程（一站式）
  - analyze_app()        → 应用信息 + 权限 + 内存 + 数据（深度分析）
  - quick_status()       → 桌面 Widget 风格的极速概览
  - screen_diagnostics() → 针对视觉任务的屏幕诊断
"""

import json
import logging
from android_mcp.app import mcp
from android_mcp.lib.utils import (
    async_termux, async_run, format_json, ok, err, warn,
    privileged_available, privileged_shell,
    check_write_permission, check_readonly,
    DANGER_READONLY, DANGER_LOW, DANGER_MEDIUM, DANGER_HIGH,
)
from android_mcp.lib.constants import SDCARD

logger = logging.getLogger('android-mcp.aggregation')


# ══════════════════════════════════════════════
# 工具：设备健康全景
# ══════════════════════════════════════════════

@mcp.tool()
async def device_health() -> str:
    """🔥 一站式设备健康检查 — 电池 + 存储 + 内存 + 网络 + CPU + 进程。

    聚合 6 个维度的数据，一次调用获取设备全景状态。
    适合：
      - 运行自动化任务前的环境检查
      - 设备卡顿/发热时的快速诊断
      - 定期健康巡检

    安全等级: 🔒 只读（不会产生副作用）
    """
    sections = []
    issues = []

    # ── 1. 电池 ──
    try:
        raw = await async_termux('termux-battery-status', timeout=10)
        bat = json.loads(raw)
        pct = bat.get('percentage', '?')
        temp = bat.get('temperature', '?')
        status = bat.get('status', '?')
        health = bat.get('health', '?')
        source = bat.get('source', '?')

        temp_num = float(temp) if temp != '?' else 0
        pct_num = float(pct) if pct != '?' else 0

        bat_icon = "🟢" if pct_num > 20 and temp_num < 40 else "🟡" if pct_num > 10 else "🔴"
        sections.append(f"{bat_icon} **电池** | {pct}% | {temp}°C | {status} | 健康: {health} | 电源: {source}")

        if pct_num <= 10:
            issues.append("🔴 电池电量极低（≤10%），建议立即充电")
        elif pct_num <= 20:
            issues.append("🟡 电池电量偏低（≤20%）")
        if temp_num >= 40:
            issues.append("🔴 电池温度过高（≥40°C），建议停止高强度操作")
        elif temp_num >= 37:
            issues.append("🟡 电池温度偏高（≥37°C）")
    except Exception as e:
        sections.append(f"⚪ **电池** | 获取失败: {e}")

    # ── 2. 存储 ──
    try:
        r = await async_run(f'df -h {SDCARD}', shell=True, timeout=10)
        df_out = r.get('stdout', '')
        for line in df_out.strip().split('\n'):
            if '/storage' in line or '/sdcard' in line or SDCARD.name in line:
                parts = line.split()
                if len(parts) >= 5:
                    total = parts[1]
                    used = parts[2]
                    avail = parts[3]
                    use_pct = parts[4]
                    sections.append(f"💾 **存储** | 总量: {total} | 已用: {used} | 剩余: {avail} | 使用率: {use_pct}")

                    # 解析使用率
                    pct_str = use_pct.replace('%', '')
                    try:
                        pct_val = float(pct_str)
                        if pct_val >= 90:
                            issues.append(f"🔴 存储空间即将耗尽（{use_pct}），请立即清理")
                        elif pct_val >= 80:
                            issues.append(f"🟡 存储空间不足（{use_pct}）")
                    except ValueError:
                        pass
                    break
    except Exception as e:
        sections.append(f"⚪ **存储** | 获取失败: {e}")

    # ── 3. 内存 (通过 /proc/meminfo) ──
    try:
        r = await async_run("cat /proc/meminfo | grep -E 'MemTotal|MemAvailable|MemFree'", shell=True, timeout=5)
        mem_info = r.get('stdout', '')
        mem_total = ""
        mem_avail = ""
        for line in mem_info.strip().split('\n'):
            if 'MemTotal' in line:
                mem_total = line.split(':')[1].strip()
            elif 'MemAvailable' in line:
                mem_avail = line.split(':')[1].strip()

        if mem_total and mem_avail:
            # 估算使用率
            try:
                total_kb = int(mem_total.replace('kB', '').strip())
                avail_kb = int(mem_avail.replace('kB', '').strip())
                used_pct = (total_kb - avail_kb) / total_kb * 100
                mem_icon = "🟢" if used_pct < 70 else "🟡" if used_pct < 85 else "🔴"
                sections.append(f"{mem_icon} **内存** | 总量: {mem_total} | 可用: {mem_avail} | 使用率: {used_pct:.0f}%")

                if used_pct >= 85:
                    issues.append(f"🔴 内存使用率过高（{used_pct:.0f}%），建议关闭后台应用")
                elif used_pct >= 70:
                    issues.append(f"🟡 内存使用率偏高（{used_pct:.0f}%）")
            except (ValueError, IndexError):
                sections.append(f"💾 **内存** | {mem_total} 总量 | {mem_avail} 可用")
        else:
            sections.append(f"💾 **内存** | 读取失败，试试使用 ADB/Shizuku")
    except Exception as e:
        sections.append(f"⚪ **内存** | 获取失败: {e}")

    # ── 4. 网络 ──
    try:
        raw = await async_termux('termux-wifi-connectioninfo', timeout=8)
        wifi = json.loads(raw)
        ssid = wifi.get('ssid', '未连接')
        sig = wifi.get('signal_strength', '?')
        link_speed = wifi.get('link_speed', '?')
        freq = wifi.get('frequency', '?')

        # 信号强度评估（负值 dBm，越接近 0 越好）
        sig_icon = "🟢"
        if sig != '?':
            try:
                sig_val = int(sig)
                if sig_val < -80:
                    sig_icon = "🔴"
                    issues.append(f"🔴 WiFi 信号极弱（{sig_val}dBm），建议靠近路由器")
                elif sig_val < -65:
                    sig_icon = "🟡"
            except ValueError:
                pass

        sections.append(f"{sig_icon} **网络** | {ssid} | 信号: {sig}dBm | 速率: {link_speed}Mbps | 频段: {freq}")
    except Exception:
        sections.append(f"⚪ **网络** | 未连接 WiFi 或获取失败")

    # ── 5. 设备基础信息 ──
    try:
        model = (await async_run('getprop ro.product.model', shell=True, timeout=3)).get('stdout', '').strip()
        android = (await async_run('getprop ro.build.version.release', shell=True, timeout=3)).get('stdout', '').strip()
        uptime_r = await async_run('uptime', shell=True, timeout=3)
        uptime_str = uptime_r.get('stdout', '').strip()

        sections.append(f"📱 **设备** | {model} | Android {android}")
        if uptime_str:
            # 截取 uptime 的负载部分
            parts = uptime_str.split('load average:')
            uptime_clean = parts[0].strip() if parts else uptime_str
            load = f"负载: {parts[1].strip()}" if len(parts) > 1 else ""
            sections.append(f"⏱ **运行** | {uptime_clean} | {load}")
    except Exception:
        pass

    # ── 6. 前台应用 ──
    try:
        from android_mcp.tools.ui_smart import get_foreground_app
        fg = await get_foreground_app()
        if fg and '前台' in fg:
            sections.append(f"📌 **前台** | {fg.split(chr(10))[1].strip() if chr(10) in fg else fg}")
    except Exception:
        pass

    # ── 汇总 ──
    lines = [
        "━━━ 📊 设备健康总览 ━━━",
        "",
    ]
    lines.extend(sections)
    lines.append("")

    if issues:
        lines.append("── ⚠️ 注意事项 ──")
        lines.extend(issues)
        lines.append("")

    # 总体评分（简易版）
    score = max(0, 100 - len(issues) * 15)
    if score >= 80:
        lines.append(f"🏆 **健康评分: {score}/100** — 状态良好")
    elif score >= 50:
        lines.append(f"⚠️ **健康评分: {score}/100** — 建议关注问题项")
    else:
        lines.append(f"🔴 **健康评分: {score}/100** — 需要处理")

    lines.append("\n💡 用 device_health_check prompt 获取更详细的诊断指导。")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# 工具：应用深度分析
# ══════════════════════════════════════════════

@mcp.tool()
async def analyze_app(package: str) -> str:
    """🔍 深度分析指定 App — 包信息 + 权限 + 内存 + 数据 + Activity。

    一次调用获取 App 全维度信息，适合：
      - 审计第三方应用的安全性
      - 分析 App 内存/性能问题
      - 了解 App 的 Activity 结构

    Args:
        package: App 包名（如 'com.tencent.mm'）

    安全等级: 🔒 只读（不会修改任何数据）
    """
    if not package or '.' not in package:
        return "❌ 请提供有效的包名（如 'com.android.chrome'）"

    sections = []
    issues = []

    def _add(title: str, content: str):
        sections.append(f"── {title} ──\n{content}\n")

    # ── 1. 包基本信息 ──
    if privileged_available():
        r = privileged_shell(f"dumpsys package {package} | grep -E 'versionName|versionCode|firstInstallTime|lastUpdateTime|installerPackageName|uid' | head -10", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            _add("📦 包信息", r['stdout'])

    # ── 2. 安装来源 ──
    r = privileged_shell(f"pm list packages -f --show-versioncode 2>/dev/null | grep {package}", timeout=5)
    if r['success'] and r.get('stdout', '').strip():
        _add("📋 安装信息", r['stdout'])

    # ── 3. 权限 ──
    if privileged_available():
        r = privileged_shell(f"dumpsys package {package} | grep -A 200 'requested permissions:' | grep -m 50 'android.permission.'", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            perm_lines = r['stdout'].strip().split('\n')
            granted = []
            denied = []
            for line in perm_lines:
                if 'granted=true' in line or ': granted=true' in line:
                    granted.append(line.strip())
                elif 'granted=false' in line or ': granted=false' in line:
                    denied.append(line.strip())

            dangerous_keywords = ['location', 'camera', 'contacts', 'microphone',
                                  'sms', 'phone', 'storage', 'calendar',
                                  'activity_recognition', 'body_sensors']

            dangerous = [p for p in granted if any(k in p.lower() for k in dangerous_keywords)]
            safe = [p for p in granted if p not in dangerous]

            perm_report = []
            if dangerous:
                perm_report.append(f"  🚨 **危险权限（{len(dangerous)} 项）**:")
                for p in dangerous:
                    perm_report.append(f"    • {p.split('.')[-1]}")
            if safe:
                perm_report.append(f"  🔵 **普通权限（{len(safe)} 项）**")
            if denied:
                perm_report.append(f"  ⚪ **已拒绝（{len(denied)} 项）**")

            if perm_report:
                _add("🔐 权限", "\n".join(perm_report))

            if dangerous:
                issues.append(f"🟡 该 App 持有 {len(dangerous)} 项敏感权限")
        else:
            # 降级：尝试直接 pm list permissions
            r2 = privileged_shell(f"pm list permissions -g 2>/dev/null | grep -i {package.split('.')[0]} | head -10", timeout=5)
            if r2['success'] and r2.get('stdout', '').strip():
                _add("🔐 权限", r2['stdout'])

    # ── 4. 内存 ──
    if privileged_available():
        r = privileged_shell(f"dumpsys meminfo {package} 2>/dev/null | head -30", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            # 提取关键信息
            mem_lines = []
            for line in r['stdout'].strip().split('\n'):
                line_s = line.strip()
                if any(k in line_s for k in ['TOTAL', 'Native Heap', 'Dalvik Heap', 'Heap Alloc',
                                              'PSS Total', 'Java Heap']):
                    mem_lines.append(f"  {line_s}")
            if mem_lines:
                _add("💾 内存", "\n".join(mem_lines))
            else:
                _add("💾 内存（完整）", r['stdout'])

    # ── 5. Activity 信息 ──
    if privileged_available():
        r = privileged_shell(f"dumpsys package {package} | grep -E 'MAIN|LAUNCHER|activity=' | head -10", timeout=10)
        if r['success'] and r.get('stdout', '').strip():
            _add("🎯 Activity/Launcher", r['stdout'])

    # ── 6. App 前台/后台进程 ──
    r = privileged_shell(f"ps -ef 2>/dev/null | grep {package} | head -10", timeout=5)
    if r['success'] and r.get('stdout', '').strip():
        process_count = len(r['stdout'].strip().split('\n'))
        _add(f"🧵 进程（{process_count} 个）", r['stdout'])

    # ── 构建报告 ──
    if not sections:
        # 降级：用 pm path 确认包是否存在
        r = privileged_shell(f"pm path {package} 2>/dev/null", timeout=5)
        if r['success'] and r.get('stdout', '').strip():
            sections.append(f"📦 App 已安装\n  {r['stdout'].strip()}")
            sections.append("\n💡 要获取更详细信息，请确保 Shizuku 或 ADB 已连接。")
        else:
            return f"❌ 未找到包 \"{package}\"，请确认包名是否正确。\n💡 试试 pm list packages | grep <关键字> 查找。"

    lines = [
        f"━━━ 🔍 应用分析: {package} ━━━",
        "",
    ]
    lines.extend(sections)
    lines.append("")

    if issues:
        lines.append("── ⚠️ 注意事项 ──")
        lines.extend(issues)
        lines.append("")

    lines.append("💡 用 app_forensic_audit prompt 获得更详细的分析指导。")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# 工具：极速概览
# ══════════════════════════════════════════════

@mcp.tool()
async def quick_status() -> str:
    """⚡ 桌面 Widget 风格极速概览 — 一行一个核心指标。

    比 device_health() 更快更轻量，适合：
      - 快速查看当前状态
      - 对话开始前的环境确认
      - 仪表盘式监控

    安全等级: 🔒 只读
    """
    lines = ["━━━ ⚡ 快速状态 ━━━"]

    # 电池
    try:
        raw = await async_termux('termux-battery-status', timeout=6)
        bat = json.loads(raw)
        pct = bat.get('percentage', '?')
        temp = bat.get('temperature', '?')
        status = bat.get('status', '?')
        icon = "🔋" if 'CHARG' in str(status) else "🪫"
        lines.append(f"{icon} {pct}% | {temp}°C | {status}")
    except Exception:
        lines.append(f"🔋 电池: N/A")

    # WiFi
    try:
        raw = await async_termux('termux-wifi-connectioninfo', timeout=5)
        wifi = json.loads(raw)
        ssid = wifi.get('ssid', '未连接')
        sig = wifi.get('signal_strength', '')
        lines.append(f"📶 {ssid} | {sig}dBm")
    except Exception:
        lines.append(f"📶 WiFi: N/A")

    # 存储
    try:
        r = await async_run(f'df -h {SDCARD}', shell=True, timeout=5)
        for line in r.get('stdout', '').strip().split('\n'):
            if SDCARD.name in line:
                parts = line.split()
                if len(parts) >= 4:
                    lines.append(f"💾 剩余 {parts[3]}")
                break
    except Exception:
        pass

    # 设备
    try:
        model = (await async_run('getprop ro.product.model', shell=True, timeout=3)).get('stdout', '').strip()
        android = (await async_run('getprop ro.build.version.release', shell=True, timeout=3)).get('stdout', '').strip()
        lines.append(f"📱 {model} | Android {android}")
    except Exception:
        pass

    # 特权状态
    priv = "✅ Shizuku" if privileged_available() else "❌ 无特权"
    lines.append(f"🛡️  {priv}")

    lines.append("\n💡 查看全面健康报告: device_health()")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# 工具：屏幕诊断
# ══════════════════════════════════════════════

@mcp.tool()
async def screen_diagnostics() -> str:
    """📺 屏幕诊断 — 分辨率 + 方向 + 亮度 + 屏幕状态 + 前台应用。

    适合在视觉操作（截图/点击）前了解屏幕配置。

    安全等级: 🔒 只读
    """
    lines = ["━━━ 📺 屏幕诊断 ━━━"]

    # 分辨率
    if privileged_available():
        r = await async_run('wm size', shell=True, timeout=5)
        size = r.get('stdout', '').strip()
        if size:
            lines.append(f"📐 分辨率: {size}")

    # 方向
    try:
        r = await async_run('settings get system user_rotation', shell=True, timeout=3)
        rot = r.get('stdout', '').strip()
        rot_labels = {'0': '竖屏 🔄', '1': '横屏 🔄', '2': '倒竖 🔄', '3': '倒横 🔄'}
        lines.append(f"🧭 方向: {rot_labels.get(rot, f'rotation={rot}')}")
    except Exception:
        pass

    # 亮度
    try:
        r = await async_run('settings get system screen_brightness', shell=True, timeout=3)
        bright = r.get('stdout', '').strip()
        if bright and bright != 'null':
            try:
                b_val = int(bright)
                pct = round(b_val / 255 * 100)
                lines.append(f"☀️ 亮度: {pct}% ({b_val}/255)")
            except ValueError:
                lines.append(f"☀️ 亮度: {bright}")
    except Exception:
        pass

    # 前台应用
    try:
        from android_mcp.tools.ui_smart import get_foreground_app
        fg = await get_foreground_app()
        if fg:
            for line in fg.split('\n'):
                if '包名' in line or '前台' in line:
                    lines.append(f"📌 {line.strip()}")
                    break
    except Exception:
        pass

    # UI 元素数量（如果可能）
    from android_mcp.tools.ui_smart import _dump_xml, _parse_all_nodes
    try:
        xml = _dump_xml()
        if xml:
            nodes = _parse_all_nodes(xml)
            interactive = [n for n in nodes if n['enabled'] and (n['clickable'] or 'Button' in n['class'])]
            lines.append(f"🖱 当前屏幕: {len(nodes)} 节点 / {len(interactive)} 可交互")
    except Exception:
        pass

    lines.append("\n💡 视觉操作推荐: dump_ui_with_screenshot(scale=0.5)")
    return "\n".join(lines)
