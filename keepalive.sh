#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────
#  android-mcp 保活监控脚本 v2.0
#  用途：
#    每 30 秒检查一次服务，挂了就自动拉起
#    配合 http_termux_server.py 的内部重启形成「双层保险」
#  用法：
#    bash keepalive.sh {start|stop|status|restart}
#    bash keepalive.sh daemon          # 启动保活循环（后台）
# ──────────────────────────────────────────────────────────

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$BASE_DIR/keepalive.pid"
LOG_FILE="$BASE_DIR/keepalive.log"
START_SCRIPT="$BASE_DIR/start.sh"
CHECK_INTERVAL=30

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; D='\033[2m'; N='\033[0m'
ok()   { echo -e "  ${G}[✓]${N} $*"; }
err()  { echo -e "  ${R}[✗]${N} $*"; }
warn() { echo -e "  ${Y}[⚠]${N} $*"; }

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }
info() { echo -e "  ${D}→${N} $*"; }

# ── 核心检查逻辑 ──
check_and_restart() {
    # 通过 start.sh status 检查状态
    if bash "$START_SCRIPT" status > /dev/null 2>&1; then
        return 0  # 正常运行
    fi

    # 挂了 → 重启
    log "⚠️ 检测到服务未运行，正在重启..."
    if bash "$START_SCRIPT" start >> "$LOG_FILE" 2>&1; then
        log "✅ 重启成功"
    else
        log "❌ 重启失败"
    fi
}

# ── 守护循环 ──
daemon_loop() {
    echo "$$" > "$PID_FILE"
    log "📡 android-mcp 保活监控已启动 (PID: $$, 间隔: ${CHECK_INTERVAL}s)"

    while true; do
        check_and_restart
        sleep "$CHECK_INTERVAL"
    done
}

# ── 命令: start (前台) ──
cmd_start() {
    # 检查是否已有实例
    if [[ -f "$PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
            warn "保活守护已在运行 (PID: $old_pid)"
            return 0
        fi
        rm -f "$PID_FILE"
    fi

    daemon_loop &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    ok "保活守护已启动 (PID: $pid)"
}

# ── 命令: stop ──
cmd_stop() {
    if [[ ! -f "$PID_FILE" ]]; then
        warn "保活守护未运行"
        return 0
    fi

    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [[ -z "$pid" ]]; then
        rm -f "$PID_FILE"
        warn "保活守护未运行"
        return 0
    fi

    info "停止保活守护 (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    local i=0
    while kill -0 "$pid" 2>/dev/null && [[ $i -lt 5 ]]; do
        sleep 1; i=$((i + 1))
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true

    rm -f "$PID_FILE"
    ok "保活守护已停止"
}

# ── 命令: status ──
cmd_status() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            ok "保活守护运行中 (PID: $pid)"
            echo -e "  ${D}  最近日志:${N}"
            tail -3 "$LOG_FILE" 2>/dev/null | sed 's/^/    /'
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    warn "保活守护未运行"
}

# ── 命令: restart ──
cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

# ── 主入口 ──
case "${1:-status}" in
    daemon|start)    cmd_start ;;
    stop)            cmd_stop ;;
    status|st)       cmd_status ;;
    restart|re)      cmd_restart ;;
    *)
        echo "用法: bash keepalive.sh {start|stop|status|restart}"
        echo ""
        echo "  命令:"
        echo "    start    启动保活守护（后台）"
        echo "    stop     停止保活守护"
        echo "    status   查看运行状态"
        echo "    restart  重启保活守护"
        echo ""
        echo "  示例:"
        echo "    bash keepalive.sh start     # 启动保活"
        echo "    bash keepalive.sh status    # 查看状态"
        ;;
esac
