#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────
#  android-mcp Shizuku Watchdog v1.0
#  用途：
#    通过 rish (Shizuku) 运行，Termux 被 OOM 杀掉后仍能存活。
#    每 60s 检测 MCP 状态，挂了就自动拉起。
#  安装（后台运行）：
#    nohup bash watchdog.sh > watchdog.log 2>&1 &
#  停止：
#    kill $(cat watchdog.pid)
# ──────────────────────────────────────────────────────────

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$BASE_DIR/watchdog.pid"
LOG_FILE="$BASE_DIR/watchdog.log"
FLAG_FILE="$HOME/.mcp_autostart"
CHECK_INTERVAL=30
RISH="$HOME/rish"
MCP_SCRIPT="$BASE_DIR/start.sh"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

# ── 检查 MCP 是否存活 ──
mcp_alive() {
    # 方法1: PID 文件检查
    if [[ -f "$BASE_DIR/run.pid" ]]; then
        local pid
        pid=$(cat "$BASE_DIR/run.pid" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            # 校验是 MCP 进程
            local cmdline
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || echo "")
            if [[ "$cmdline" == *"http_termux_server"* ]]; then
                return 0
            fi
        fi
    fi
    # 方法2: pgrep 兜底
    pgrep -f "http_termux_server" >/dev/null 2>&1 && return 0
    return 1
}

# ── 启动 MCP ──
start_mcp() {
    log "⚠️  MCP 未运行，尝试启动..."

    # 写入标记文件，让 Termux 启动时自动拉起
    echo "autostart" > "$FLAG_FILE"
    log "📝 写入标记文件: $FLAG_FILE"

    # 启动 Termux App（通过 rish）
    if command -v "$RISH" &>/dev/null; then
        # 先尝试直接启动 MCP（如果 Termux 进程在）
        if pgrep -u "$(whoami)" -f "com.termux" >/dev/null 2>&1; then
            # Termux 进程活着 → 直接调 am
            "$RISH" -c "am start -n com.termux/.app --activity-new-task" 2>/dev/null || true
        else
            # Termux 被杀透了 → 启动 App
            "$RISH" -c "am start -n com.termux/.app --activity-new-task --activity-clear-task" 2>/dev/null || true
        fi
    fi

    log "✅ 拉起请求已发送"
}

# ── 主循环 ──
main() {
    echo "$$" > "$PID_FILE"
    log "🚀 Shizuku Watchdog 启动 (PID: $$, 间隔: ${CHECK_INTERVAL}s)"
    log "📌 标记文件: $FLAG_FILE"
    log "📌 MCP 脚本: $MCP_SCRIPT"

    while true; do
        if ! mcp_alive; then
            start_mcp
        fi
        sleep "$CHECK_INTERVAL"
    done
}

main
