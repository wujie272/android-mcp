#!/system/bin/sh
# ──────────────────────────────────────────────────────────
#  android-mcp 保活监控脚本
#  用途：每 30 秒检查一次服务，挂了就自动拉起
#  配合 http_termux_server.py 的内部重启形成「双层保险」
# ──────────────────────────────────────────────────────────

BASE_DIR="/data/data/com.termux/files/home/mcp-servers"
PID_FILE="$BASE_DIR/run/android-mcp.pid"
LOG_FILE="$BASE_DIR/logs/keepalive.log"

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

log() {
    echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"
}

check_and_restart() {
    local pid=""
    local running=false

    # 1. 先检查 PID 文件
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            running=true
        fi
    fi

    # 2. 再检查进程列表（兜底）
    if ! $running; then
        local pgid
        pgid=$(pgrep -f "http_termux_server.py" 2>/dev/null | head -1)
        if [ -n "$pgid" ] && kill -0 "$pgid" 2>/dev/null; then
            running=true
            pid=$pgid
            echo "$pid" > "$PID_FILE"
        fi
    fi

    # 3. 还活着 → 无事发生
    if $running; then
        return 0
    fi

    # 4. 挂了 → 重启
    log "⚠️ 检测到服务未运行，正在重启..."
    cd "$BASE_DIR/android-mcp" || return 1
    nohup python3 http_termux_server.py > /dev/null 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"
    log "✅ 已重启 (PID: $new_pid)"
}

# ── 主循环 ──
log "📡 android-mcp 保活监控已启动 (间隔30s)"

while true; do
    check_and_restart
    sleep 30
done
