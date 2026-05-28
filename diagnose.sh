#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────
#  android-mcp 环境诊断脚本
#  检查运行 Android MCP Server 所需的所有依赖
#  用法: bash diagnose.sh [--verbose]
# ──────────────────────────────────────────────────────────

set -euo pipefail

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'
D='\033[2m'; B='\033[1m'; C='\033[0;36m'; N='\033[0m'

ok()   { echo -e "  ${G}[✓]${N} $*"; }
err()  { echo -e "  ${R}[✗]${N} $*"; }
warn() { echo -e "  ${Y}[⚠]${N} $*"; }
inf()  { echo -e "  ${D}→${N} $*"; }

VERBOSE=false
[[ "${1:-}" == "--verbose" || "${1:-}" == "-v" ]] && VERBOSE=true

echo ""
echo -e "  ${B}╭──────────────────────────────────────────────╮${N}"
echo -e "  ${B}│${N}  🩺  ${B}Android MCP 环境诊断${N}                       ${B}│${N}"
echo -e "  ${B}╰──────────────────────────────────────────────╯${N}"
echo ""

# ── 1. 系统信息 ──
echo -e "  ${B}── 系统信息 ──${N}"
echo -e "  ${D}  系统:${N} $(uname -a 2>/dev/null || echo 'N/A')"
echo -e "  ${D}  Android:${N} $(getprop ro.build.version.release 2>/dev/null || echo 'N/A')"
echo -e "  ${D}  SDK:${N} $(getprop ro.build.version.sdk 2>/dev/null || echo 'N/A')"
echo -e "  ${D}  SELinux:${N} $(getenforce 2>/dev/null || echo 'N/A')"
echo ""

# ── 2. 用户和权限 ──
echo -e "  ${B}── 用户和权限 ──${N}"
echo -e "  ${D}  用户:${N} $(whoami 2>/dev/null || id -un 2>/dev/null || echo 'N/A')"
echo -e "  ${D}  UID:${N} $(id -u 2>/dev/null || echo 'N/A')"
echo -e "  ${D}  Shell:${N} $SHELL"
echo ""

# ── 3. Python 环境 ──
echo -e "  ${B}── Python 环境 ──${N}"
if command -v python3 &>/dev/null; then
    ok "python3: $(python3 --version 2>&1)"
else
    err "python3 未安装"
fi

# 检查依赖
if command -v pip3 &>/dev/null; then
    for pkg in mcp uvicorn httpx; do
        if pip3 show "$pkg" &>/dev/null; then
            $VERBOSE && ok "$pkg: $(pip3 show "$pkg" 2>/dev/null | grep Version | cut -d' ' -f2)"
        else
            warn "$pkg 未安装 (pip install $pkg)"
        fi
    done
fi
$VERBOSE || echo -e "  ${D}  (使用 -v 查看详细依赖信息)${N}"
echo ""

# ── 4. Termux:API ──
echo -e "  ${B}── Termux:API ──${N}"
if pm list packages 2>/dev/null | grep -q termux.api; then
    ok "Termux:API app 已安装"
else
    warn "Termux:API app 未安装"
fi
if dpkg -l 2>/dev/null | grep -q termux-api; then
    ok "termux-api package 已安装"
else
    warn "termux-api package 未安装 (pkg install termux-api)"
fi
echo ""

# ── 5. Shizuku / ADB ──
echo -e "  ${B}── 特权模式 ──${N}"
if [[ -f "$HOME/rish" ]]; then
    ok "rish 存在 ($HOME/rish)"
    timeout 5 "$HOME/rish" -c 'echo ok' &>/dev/null && ok "Shizuku 连接正常" || warn "Shizuku 未运行或无法连接"
else
    warn "rish 未找到 — Shizuku 不可用"
fi
if command -v adb &>/dev/null; then
    ok "adb 已安装"
    adb devices 2>/dev/null | grep -q "device\$" && ok "ADB 已连接" || warn "ADB 未连接设备"
else
    warn "adb 未安装 (pkg install android-tools)"
fi
echo ""

# ── 6. 核心命令 ──
echo -e "  ${B}── 核心命令 ──${N}"
for cmd in am input screencap dumpsys pm settings getprop; do
    if command -v "$cmd" &>/dev/null; then
        ok "$cmd 可用"
    else
        # Android 系统命令可能在 /system/bin
        if [[ -x "/system/bin/$cmd" ]]; then
            ok "$cmd (/system/bin)"
        else
            warn "$cmd 不可用"
        fi
    fi
done
echo ""

# ── 7. 端口冲突 ──
echo -e "  ${B}── 端口 3000 ──${N}"
if timeout 1 bash -c "echo > /dev/tcp/127.0.0.1/3000" 2>/dev/null; then
    local who_pid
    who_pid=$(ss -tlnp "sport = :3000" 2>/dev/null | grep -oP 'pid=\K\d+' | head -1)
    if [[ -n "$who_pid" ]]; then
        local cmdline
        cmdline=$(tr '\0' ' ' < "/proc/$who_pid/cmdline" 2>/dev/null || echo "?")
        warn "端口 3000 已被占用 (PID: $who_pid, 进程: ${cmdline:0:80})"
    else
        warn "端口 3000 已被占用 (未知进程)"
    fi
else
    ok "端口 3000 空闲"
fi

# ── 8. 日志 ──
echo -e "  ${B}── 日志 ──${N}"
local log_file="/data/data/com.termux/files/home/mcp-servers/logs/android_mcp.log"
if [[ -f "$log_file" ]]; then
    local size
    size=$(du -h "$log_file" | cut -f1)
    local lines
    lines=$(wc -l < "$log_file")
    ok "日志文件: $log_file (${size}, ${lines}行)"
    echo -e "  ${D}  最近 3 行:${N}"
    tail -3 "$log_file" 2>/dev/null | sed 's/^/    /'
else
    warn "日志文件不存在"
fi
echo ""

# ── 总结 ──
echo -e "  ${B}╭──────────────────────────────────────────────╮${N}"
echo -e "  ${B}│${N}  ${B}诊断完成${N}                                        ${B}│${N}"
echo -e "  ${B}│${N}                                                                 ${B}│${N}"
echo -e "  ${B}│${N}  启动服务: ${C}bash start.sh${N}                              ${B}│${N}"
echo -e "  ${B}│${N}  查看状态: ${C}bash start.sh status${N}                       ${B}│${N}"
echo -e "  ${B}│${N}  实时日志: ${C}bash start.sh log${N}                          ${B}│${N}"
echo -e "  ${B}╰──────────────────────────────────────────────╯${N}"
echo ""
