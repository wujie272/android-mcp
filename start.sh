#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────
#  Android MCP Server 管理脚本
#  统一管理 start / stop / status / restart / log
#  用法: bash start.sh {start|stop|status|restart|log|diagnose}
# ──────────────────────────────────────────────────────────

set -euo pipefail

# ── 路径配置 ──
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$BASE_DIR/run.pid"
LOG_FILE="$BASE_DIR/run.log"
RUN_DIR="/data/data/com.termux/files/home/mcp-servers/run"
PID_LINK="$RUN_DIR/android-mcp.pid"

PORT="${PORT:-3000}"
HOST="${HOST:-0.0.0.0}"
PYTHON="python3"

# ── 颜色 ──
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'
C='\033[0;36m'; D='\033[2m'; B='\033[1m'; N='\033[0m'

ok()   { echo -e "  ${G}[✓]${N} $*"; }
err()  { echo -e "  ${R}[✗]${N} $*"; }
warn() { echo -e "  ${Y}[⚠]${N} $*"; }
inf()  { echo -e "  ${D}→${N} $*"; }

# ── 工具函数 ──
port_busy() { local p="${1:-$PORT}"; timeout 1 bash -c "echo > /dev/tcp/127.0.0.1/$p" 2>/dev/null; }

get_pid() {
    local pid
    # 从 PID 文件读取
    if [[ -f "$PID_FILE" ]]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            # 验证进程确实是我们的
            local cmdline
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || echo "")
            if [[ "$cmdline" == *"http_termux_server"* || "$cmdline" == *"android-mcp"* ]]; then
                echo "$pid"
                return 0
            fi
        fi
    fi
    # 从端口反查（兜底）
    local port_pid
    port_pid=$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K\d+' | head -1)
    if [[ -n "$port_pid" ]]; then
        echo "$port_pid"
        return 0
    fi
    # pgrep 兜底
    pgrep -f "http_termux_server" 2>/dev/null | head -1 || return 1
}

wait_port() {
    local timeout="${1:-15}"
    local i=0
    while [[ $i -lt $timeout ]]; do
        if port_busy "$PORT"; then return 0; fi
        sleep 1; i=$((i + 1))
    done
    return 1
}

rotate_log() {
    [[ -f "$LOG_FILE" ]] || return 0
    local size
    size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    [[ $size -le 5242880 ]] && return 0  # 5MB 轮转
    mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S).bak" 2>/dev/null || true
    # 清理旧备份（保留最近 5 个）
    ls -1t "${LOG_FILE}".*.bak 2>/dev/null | tail -n +6 | xargs -r rm -f
}

# ── 加载配置文件 ──
load_config() {
    local config_file="$BASE_DIR/config.json"
    if [[ ! -f "$config_file" ]]; then
        return 0  # 没有配置文件不报错
    fi

    # 用 python3 解析 JSON，比 jq/sed 更可靠
    local cfg
    cfg=$("$PYTHON" -c "
import json, sys
with open('$config_file') as f:
    cfg = json.load(f)
for k, v in cfg.items():
    if v:
        print(f'{k}={v}')
" 2>/dev/null) || return 0

    while IFS='=' read -r key value; do
        [[ -z "$key" || -z "$value" ]] && continue
        export "${key^^}"="$value"
        inf "配置: ${key^^}=${value:0:8}..."
    done <<< "$cfg"
}
# ── 命令: start ──
cmd_start() {
    # 已在运行？
    local existing_pid
    existing_pid=$(get_pid) || true
    if [[ -n "$existing_pid" ]] && port_busy; then
        warn "服务已在运行 (PID: $existing_pid, 端口: $PORT)"
        return 0
    fi

    # 清理残留 PID 文件
    [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"

    # 检查启动文件
    local server_script="$BASE_DIR/http_termux_server.py"
    if [[ ! -f "$server_script" ]]; then
        err "找不到服务文件: $server_script"
        return 1
    fi

    # 日志轮转
    rotate_log

    # 获取唤醒锁
    if command -v termux-wake-lock &>/dev/null; then
        termux-wake-lock 2>/dev/null || true
    fi

    # 启动
    mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")" "$RUN_DIR"
    echo -e "  ${C}🚀${N} 启动 Android MCP Server..."
    echo -e "  ${D}  主机: ${HOST}:${PORT}${N}"
    echo -e "  ${D}  日志: $LOG_FILE${N}"

    HOST="$HOST" PORT="$PORT" nohup "$PYTHON" "$server_script" \
        >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    echo "$pid" > "$PID_LINK" 2>/dev/null || true

    # 等待就绪
    if wait_port 15; then
        local actual_pid
        actual_pid=$(get_pid)
        ok "服务已就绪 — http://${HOST}:${PORT}/mcp  (PID: ${actual_pid:-$pid})"
        echo -e "  ${D}  🩺 健康检查: http://${HOST}:${PORT}/health${N}"
        return 0
    else
        err "启动超时 (${PORT} 端口未就绪)"
        if ! kill -0 "$pid" 2>/dev/null; then
            err "进程已异常退出，最后 10 行日志:"
            tail -10 "$LOG_FILE" 2>/dev/null | sed 's/^/    /'
        fi
        return 1
    fi
}

# ── 命令: stop ──
cmd_stop() {
    local pid
    pid=$(get_pid) || true
    if [[ -z "$pid" ]]; then
        warn "服务未运行"
        [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"
        return 0
    fi

    echo -e "  ${Y}🛑${N} 停止服务 (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    # 等待进程退出（最长 5 秒）
    local i=0
    while kill -0 "$pid" 2>/dev/null && [[ $i -lt 5 ]]; do
        sleep 1; i=$((i + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "强制终止..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE" "$PID_LINK"
    ok "服务已停止"

    # 释放唤醒锁（如果没有其他 MCP 服务在运行）
    if command -v termux-wake-unlock &>/dev/null; then
        # 检查是否还有其他 Python MCP 服务
        if ! pgrep -f "mcp.*server\|mcp.*\.py" 2>/dev/null | grep -v "$$" | grep -q .; then
            termux-wake-unlock 2>/dev/null || true
        fi
    fi
}

# ── 命令: status ──
cmd_status() {
    local pid
    pid=$(get_pid) || true

    if [[ -n "$pid" ]] && port_busy; then
        local cmdline
        cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || echo "N/A")
        # 用 ps 获取进程运行时间（最可靠的方式）
        local run_time=0
        local ps_out
        ps_out=$(ps -o etimes= -p "$pid" 2>/dev/null) && run_time=$((ps_out))
        [[ $run_time -lt 0 ]] && run_time=0
        local hours=$(( run_time / 3600 ))
        local mins=$(( (run_time % 3600) / 60 ))

        echo ""
        echo -e "  ${B}╭──────────────────────────────────────────────╮${N}"
        echo -e "  ${B}│${N}  🤖  ${B}Android MCP Server${N}                    ${B}│${N}"
        echo -e "  ${B}├──────────────────────────────────────────────┤${N}"
        printf "  ${B}│${N}  状态:  ${G}🟢 运行中${N}                         ${B}│${N}\n"
        printf "  ${B}│${N}  PID:   %-35s ${B}│${N}\n" "$pid"
        printf "  ${B}│${N}  端口:  :%-34s ${B}│${N}\n" "$PORT"
        printf "  ${B}│${N}  运行:  ${hours}h ${mins}m${N}                        ${B}│${N}\n"
        echo -e "  ${B}│${N}  端点:  ${C}http://127.0.0.1:${PORT}/mcp${N}          ${B}│${N}"
        echo -e "  ${B}│${N}  健康:  ${C}http://127.0.0.1:${PORT}/health${N}       ${B}│${N}"
        echo -e "  ${B}╰──────────────────────────────────────────────╯${N}"
        echo ""
    else
        echo ""
        echo -e "  ${B}╭──────────────────────────────────────────────╮${N}"
        echo -e "  ${B}│${N}  🤖  ${B}Android MCP Server${N}                    ${B}│${N}"
        echo -e "  ${B}├──────────────────────────────────────────────┤${N}"
        echo -e "  ${B}│${N}  状态:  ${R}🔴 未运行${N}                         ${B}│${N}"
        echo -e "  ${B}╰──────────────────────────────────────────────╯${N}"
        echo ""
    fi
}

# ── 命令: restart ──
cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

# ── 命令: log ──
cmd_log() {
    if [[ ! -f "$LOG_FILE" ]]; then
        err "日志文件不存在: $LOG_FILE"
        return 1
    fi
    local lines="${1:-50}"
    echo -e "  ${D}📋 最近 ${lines} 行日志 (${LOG_FILE}):${N}"
    tail -n "$lines" "$LOG_FILE"
    echo ""
    echo -e "  ${D}💡 实时跟踪: tail -f ${LOG_FILE}${N}"
}

# ── 命令: diagnose ──
cmd_diagnose() {
    # 直接调用 diagnose.sh
    local diag="$BASE_DIR/diagnose.sh"
    if [[ -f "$diag" ]]; then
        bash "$diag"
    else
        err "找不到 diagnose.sh"
        return 1
    fi
}

# ── 主入口 ──
case "${1:-start}" in
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    status|st)  cmd_status ;;
    restart|re) cmd_restart ;;
    log)        shift; cmd_log "${1:-50}" ;;
    diagnose)   cmd_diagnose ;;
    help|--help|-h)
        echo "用法: bash start.sh {command}"
        echo ""
        echo "  命令:"
        echo "    start      启动服务（默认）"
        echo "    stop       停止服务"
        echo "    status     查看运行状态"
        echo "    restart    重启服务"
        echo "    log [行数]  查看最近日志 (默认 50 行)"
        echo "    diagnose   运行环境诊断"
        echo ""
        echo "  环境变量:"
        echo "    PORT=3000  服务端口 (默认 3000)"
        echo "    HOST=0.0.0.0  绑定地址 (默认 0.0.0.0)"
        echo ""
        echo "  示例:"
        echo "    bash start.sh           # 启动"
        echo "    bash start.sh status    # 状态"
        echo "    PORT=3001 bash start.sh  # 指定端口启动"
        ;;
    *)
        err "未知命令: $1"
        echo "用法: bash start.sh {start|stop|status|restart|log|diagnose}"
        exit 1
        ;;
esac
