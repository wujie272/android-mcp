"""Shizuku 小窗管理：隐藏/显示/移动/重启 Shizuku App 窗口。

Shizuku 的 shizuku_server 是独立守护进程（oom_adj=-17），
App UI 窗口关闭后不影响 rish 调用。本模块用于管理 App 窗口。
"""

import re

from android_mcp.app import mcp
from android_mcp.lib.utils import privileged_shell, run

SHIZUKU_PKG = "moe.shizuku.privileged.api"
SHIZUKU_ACTIVITY = "moe.shizuku.privileged.api/moe.shizuku.manager.MainActivity"


def _get_task_id() -> str | None:
    """通过 dumpsys activity activities 查找 Shizuku 的 taskId。

    兼容 Android 15 (taskId=296) 和 Android 16 (#2502) 两种格式。
    """
    r = privileged_shell(
        "dumpsys activity activities 2>/dev/null | grep 'moe.shizuku.privileged.api' | head -1"
    )
    if not r.get('success') or not r.get('stdout', '').strip():
        # Fallback: 尝试旧版 dumpsys window 路径
        r = privileged_shell(
            "dumpsys window windows 2>/dev/null | grep 'moe.shizuku' | head -1"
        )
    out = r.get('stdout', '').strip()
    if not out:
        return None

    # Android 16:  Task{xxx #2502 ...}
    m = re.search(r'#(\d+)', out)
    if m:
        return m.group(1)
    # Android 15:  taskId=296
    m = re.search(r'taskId=(\d+)', out)
    return m.group(1) if m else None


def _is_shizuku_running() -> bool:
    """检查 Shizuku App 进程是否在运行。"""
    r = privileged_shell(f"pgrep -f '{SHIZUKU_PKG}' | head -1")
    return bool(r.get('stdout', '').strip())


def _rish_available() -> bool:
    """检查 rish 是否可用（直接在 Termux 下调 rish，避免递归）。"""
    r = run("~/rish -c 'echo ok' 2>&1", timeout=10, shell=True)
    return r.get('success', False) and 'ok' in r.get('stdout', '')


@mcp.tool()
async def shizuku_hide() -> str:
    """隐藏 Shizuku 小窗（缩到右上角极小尺寸 + force-stop App UI）。

    shizuku_server 守护进程不受影响，rish 调用继续可用。
    需要恢复时用 shizuku_show()。
    """
    task_id = _get_task_id()
    if not task_id:
        return "⚠️ 未找到 Shizuku 小窗（可能已隐藏）"

    # 先缩到右上角极小尺寸（18×13px），再 force-stop
    r = privileged_shell(
        f"am task resize {task_id} 1040 10 1070 30 && "
        f"sleep 0.5 && "
        f"am force-stop {SHIZUKU_PKG}"
    )
    if r.get('success'):
        return (
            "✅ Shizuku 小窗已隐藏\n"
            "  · App UI 已关闭\n"
            "  · shizuku_server 守护进程继续运行 ✓\n"
            "  · rish 调用不受影响 ✓\n"
            "  · 需要恢复请用 shizuku_show()"
        )
    return f"⚠️ 隐藏失败：{r.get('stderr', r.get('error', '未知错误'))}"


@mcp.tool()
async def shizuku_show() -> str:
    """显示/启动 Shizuku App 窗口。

    如果 App 已关闭则重新打开，如果已在运行则移到屏幕中央。
    """
    if _is_shizuku_running():
        # 已有进程，移到屏幕中央
        task_id = _get_task_id()
        if task_id:
            r = privileged_shell(f"am task resize {task_id} 200 500 880 1400")
            if r.get('success'):
                return "✅ Shizuku 窗口已移到屏幕中央"
        # 即使 resize 失败，也尝试 bring-to-front
        privileged_shell(f"am start -n {SHIZUKU_ACTIVITY}")
        return "✅ Shizuku 已切换到前台"
    else:
        # 启动 App
        r = privileged_shell(f"am start -n {SHIZUKU_ACTIVITY}")
        if r.get('success'):
            return "✅ Shizuku App 已启动"
        return f"⚠️ 启动失败：{r.get('stderr', r.get('error', '未知错误'))}"


@mcp.tool()
async def shizuku_resize(left: int = 100, top: int = 100, right: int = 500, bottom: int = 500) -> str:
    """调整 Shizuku 小窗的位置和大小。

    Args:
        left: 左边缘 x 坐标（默认 100）
        top: 上边缘 y 坐标（默认 100）
        right: 右边缘 x 坐标（默认 500）
        bottom: 下边缘 y 坐标（默认 500）

    屏幕尺寸 1080×2400，坐标示例：
        · 右上角小点:  1040, 10, 1070, 30
        · 右下角小点:  1040, 2350, 1070, 2380
        · 屏幕中央:    200, 500, 880, 1400
        · 全屏:        0, 0, 1080, 2400
    """
    task_id = _get_task_id()
    if not task_id:
        return "⚠️ 未找到 Shizuku 小窗，请先用 shizuku_show() 打开"

    r = privileged_shell(f"am task resize {task_id} {left} {top} {right} {bottom}")
    if r.get('success'):
        w = right - left
        h = bottom - top
        return f"✅ Shizuku 窗口已调整到 ({left},{top}) → ({right},{bottom})，尺寸 {w}×{h}px"
    return f"⚠️ 调整失败：{r.get('stderr', r.get('error', '未知错误'))}"


@mcp.tool()
async def shizuku_status() -> str:
    """查看 Shizuku 的运行状态：App 进程、shizuku_server 守护进程、rish 可用性。

    返回：
        · App UI 是否运行
        · shizuku_server 守护进程状态
        · rish 是否可用
        · 小窗位置（如果可见）
    """
    lines = []

    # 1. App 进程
    r = privileged_shell(f"pgrep -f '{SHIZUKU_PKG}' | head -1")
    app_pid = r.get('stdout', '').strip()
    if app_pid:
        lines.append(f"✅ App UI 进程: PID {app_pid}")
    else:
        lines.append("⏹️  App UI 进程: 未运行")

    # 2. shizuku_server 守护进程
    r = privileged_shell("pgrep -x shizuku_server | head -1")
    srv_pid = r.get('stdout', '').strip()
    if srv_pid:
        r2 = privileged_shell(f"cat /proc/{srv_pid}/oom_adj 2>/dev/null || echo '?'")
        oom = r2.get('stdout', '').strip()
        lines.append(f"✅ shizuku_server 守护进程: PID {srv_pid} (oom_adj={oom})")
    else:
        lines.append("❌ shizuku_server 守护进程: 未运行 — 请在 Shizuku App 中启动")

    # 3. rish 可用性（直接用 Termux 调 rish，不走 privileged_shell 递归）
    if _rish_available():
        lines.append("✅ rish 可用")
    else:
        lines.append("❌ rish 不可用")

    # 4. 小窗位置（取 activity 中的 visible/freeform 信息）
    r = privileged_shell(
        "dumpsys activity activities 2>/dev/null | grep 'moe.shizuku' | head -3"
    )
    task_line = r.get('stdout', '').strip()
    if task_line:
        # 提取 mode、visible 等信息
        mode_m = re.search(r'mode=(\w+)', task_line)
        vis_m = re.search(r'visible=(\w+)', task_line)
        mode = mode_m.group(1) if mode_m else '?'
        vis = vis_m.group(1) if vis_m else '?'
        wtask_m = re.search(r'#(\d+)', task_line)
        tid = wtask_m.group(1) if wtask_m else '?'
        lines.append(f"🪟 task #{tid} | mode={mode} | visible={vis}")
    else:
        lines.append("🪟 小窗: 不可见（已隐藏或未启动）")

    return "\n".join(lines)


@mcp.tool()
async def shizuku_restart() -> str:
    """重启 Shizuku App（先 force-stop 再重新打开）。

    用于 Shizuku 卡死或异常时恢复。
    shizuku_server 守护进程不受 force-stop 影响。
    """
    r = privileged_shell(f"am force-stop {SHIZUKU_PKG} && sleep 1 && am start -n {SHIZUKU_ACTIVITY}")
    if r.get('success'):
        return "✅ Shizuku App 已重启"
    return f"⚠️ 重启失败：{r.get('stderr', r.get('error', '未知错误'))}"


# ══════════════════════════════════════════════════════════════
#  Shizuku Watchdog — Termux 被杀能自启
# ══════════════════════════════════════════════════════════════

WATCHDOG_BASE = "$HOME/mcp-servers/android-mcp/watchdog"
WATCHDOG_SCRIPT = WATCHDOG_BASE + ".sh"
WATCHDOG_PID_FILE = WATCHDOG_BASE + ".pid"
WATCHDOG_LOG = WATCHDOG_BASE + ".log"


def _get_watchdog_pid() -> str | None:
    """获取 Watchdog 进程 PID，避免 pgrep 自匹配。"""
    pid = None
    # 从 PID 文件读
    r = run("cat " + WATCHDOG_PID_FILE + " 2>/dev/null", timeout=5, shell=True)
    candidate = r.get('stdout', '').strip()
    if candidate and candidate.isdigit():
        r2 = run("kill -0 " + candidate + " 2>/dev/null && echo alive", timeout=5, shell=True)
        if r2.get('stdout', '').strip() == 'alive':
            pid = candidate
    if pid:
        return pid
    # ps aux 兜底（[w]atchdog 避免自匹配，awk 取 PID）
    r = run("ps aux 2>/dev/null | grep -E '[w]atchdog\\.sh' | awk '{print $2}' | head -1", timeout=5, shell=True)
    return r.get('stdout', '').strip() or None


@mcp.tool()
async def watchdog_start() -> str:
    """🛡️ 启动 Shizuku Watchdog 守护（Termux 被杀后自动拉起 MCP）。

    Watchdog 通过 rish (Shizuku) 运行，独立于 Termux 进程。
    即使 Termux 被系统 OOM 杀掉，Watchdog 仍能存活并自动恢复。
    """
    existing = _get_watchdog_pid()
    if existing:
        return "⚠️ Watchdog 已在运行 (PID: " + existing + ")"

    r = run("test -f " + WATCHDOG_SCRIPT + " && echo exists", timeout=5, shell=True)
    if r.get('stdout', '').strip() != 'exists':
        return "❌ watchdog.sh 不存在，请先部署脚本"

    if not _rish_available():
        return "❌ rish 不可用，Watchdog 需要 Shizuku 环境"

    r = run("nohup bash " + WATCHDOG_SCRIPT + " > " + WATCHDOG_LOG + " 2>&1 &", timeout=10, shell=True)
    if not r.get('success', False):
        return "❌ 启动失败: " + r.get('stderr', r.get('error', '未知错误'))

    import asyncio
    await asyncio.sleep(2)
    pid = _get_watchdog_pid()
    if pid:
        return (
            "✅ Watchdog 已启动 (PID: " + pid + ")\n"
            "  · 每 30s 检查 MCP 状态\n"
            "  · MCP 挂了自动拉起 Termux + start.sh\n"
            "  · Termux 被 OOM 杀后仍能恢复\n"
            "  · 日志: " + WATCHDOG_LOG
        )
    return "⚠️ Watchdog 似乎启动失败，请查看日志: " + WATCHDOG_LOG


@mcp.tool()
async def watchdog_stop() -> str:
    """⏹️ 停止 Shizuku Watchdog 守护。"""
    pid = _get_watchdog_pid()
    if not pid:
        return "⚠️ Watchdog 未运行"

    run("kill " + pid + " 2>/dev/null", timeout=5, shell=True)
    import asyncio
    await asyncio.sleep(1)

    r = run("kill -0 " + pid + " 2>/dev/null && echo alive", timeout=5, shell=True)
    if r.get('stdout', '').strip() == 'alive':
        run("kill -9 " + pid + " 2>/dev/null", timeout=5, shell=True)
        await asyncio.sleep(0.5)

    run("rm -f " + WATCHDOG_PID_FILE, timeout=5, shell=True)
    return "✅ Watchdog 已停止 (PID: " + pid + ")"


@mcp.tool()
async def watchdog_status() -> str:
    """📊 查看 Shizuku Watchdog 运行状态。"""
    lines = []

    pid = _get_watchdog_pid()
    if pid:
        lines.append("🟢 Watchdog 运行中 (PID: " + pid + ")")

        r = run("ps -o etimes= -p " + pid + " 2>/dev/null", timeout=5, shell=True)
        etimes = r.get('stdout', '').strip()
        if etimes and etimes.isdigit():
            hours = int(etimes) // 3600
            mins = (int(etimes) % 3600) // 60
            lines.append("  运行: " + str(hours) + "h " + str(mins) + "m")

        r = run("tail -3 " + WATCHDOG_LOG + " 2>/dev/null", timeout=5, shell=True)
        log_tail = r.get('stdout', '').strip()
        if log_tail:
            lines.append("  最近日志:")
            for line in log_tail.split('\n'):
                lines.append("    " + line)
    else:
        lines.append("🔴 Watchdog 未运行")

    r = run("pgrep -f 'http_termux_server' | head -1", timeout=5, shell=True)
    mcp_pid = r.get('stdout', '').strip()
    lines.append("  MCP 服务: " + ("🟢 运行中 (PID: " + mcp_pid + ")" if mcp_pid else "🔴 未运行"))

    r = run("test -f $HOME/.mcp_autostart && echo exists", timeout=5, shell=True)
    if r.get('stdout', '').strip() == 'exists':
        lines.append("  📝 autostart 标记: 存在（待拉起）")

    lines.append("  rish: " + ("✅ 可用" if _rish_available() else "❌ 不可用"))

    r = run("grep -q 'mcp_autostart' ~/.bashrc && echo installed", timeout=5, shell=True)
    lines.append("  .bashrc 钩子: " + ("✅ 已安装" if r.get('stdout','').strip() else "❌ 未安装"))

    return "\n".join(lines)
