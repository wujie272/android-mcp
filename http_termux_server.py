#!/usr/bin/env python3
"""Termux MCP Server — Streamable HTTP 模式，带自动重启 + 健康检查。

工作模式：
  - 默认以 Streamable HTTP 运行（端口 3000）
  - 支持 HOST/PORT 环境变量配置
  - 进程异常退出后自动重启（指数退避，最长 30s）
  - 输入 SIGINT/SIGTERM 优雅关闭

关键端点：
  - POST /mcp  — MCP 协议端点
  - GET  /health — 健康检查（供 mcp-manager 轮询用）
"""

import os
import sys
import time
import signal
import logging
from typing import Optional

# ── 确保能找到项目模块 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from termux_mcp import mcp
from termux_mcp.lib.utils import get_uptime

from starlette.responses import JSONResponse
from starlette.routing import Route

# ── 配置（支持环境变量覆盖） ──
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '3000'))

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BASE_DIR, 'run.pid')
LOG_FILE = os.path.join(BASE_DIR, 'run.log')

# ── 重启策略 ──
MIN_RESTART_DELAY = 1      # 初始等待秒数
MAX_RESTART_DELAY = 30     # 最大等待秒数（指数退避上限）
RESTART_BACKOFF = 2        # 退避倍率
RESTART_BACKOFF_CAP = 5    # 多少次后退避不再增长

# ── 全局状态 ──
running = True
restart_count = 0


# ══════════════════════════════════════════════
#  Signal Handling
# ══════════════════════════════════════════════

def signal_handler(signum: int, frame):
    """处理退出信号，设置 running=False 触发主循环退出"""
    global running
    signame = signal.Signals(signum).name
    print(f"\n👋 收到 {signame}，优雅关闭...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ══════════════════════════════════════════════
#  PID 文件管理
# ══════════════════════════════════════════════

def write_pid_file():
    """写入 PID 文件供 start.sh 外部管理"""
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """清理 PID 文件"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass


# ══════════════════════════════════════════════
#  健康检查端点（挂载到 MCP 的 HTTP app 上）
# ══════════════════════════════════════════════

app = mcp.streamable_http_app()


# ── 健康检查端点（供 mcp-manager 轮询自动重启） ──

async def health_check(request):
    """GET /health — 返回服务运行状态"""
    uptime_secs = get_uptime()
    hours = int(uptime_secs // 3600)
    minutes = int((uptime_secs % 3600) // 60)
    seconds = int(uptime_secs % 60)

    return JSONResponse({
        "status": "ok",
        "service": "termux-mcp",
        "version": "0.4.0",
        "pid": os.getpid(),
        "port": PORT,
        "host": HOST,
        "uptime_sec": uptime_secs,
        "uptime_str": f"{hours}h {minutes}m {seconds}s",
        "restart_count": restart_count,
    })


app.add_route("/health", health_check, methods=["GET"])


# ══════════════════════════════════════════════
#  带自动重启的主循环
# ══════════════════════════════════════════════

def run_server():
    """运行 uvicorn server，返回是否正常退出（非崩溃）"""
    import uvicorn

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        timeout_keep_alive=65,
        limit_concurrency=20,
        log_level="info",
    )
    # uvicorn.run() 正常返回 → 收到退出信号
    return True


def run_with_auto_restart():
    """主循环：带指数退避的自动重启"""
    global restart_count

    write_pid_file()

    while running:
        try:
            print(f"🚀 termux-mcp Streamable HTTP → http://{HOST}:{PORT}/mcp")
            print(f"   🩺 Health check → http://{HOST}:{PORT}/health")
            print(f"   📝 PID: {os.getpid()}")
            if restart_count > 0:
                print(f"   🔄 已自动重启 {restart_count} 次")

            run_server()
            # 正常退出
            break

        except KeyboardInterrupt:
            print("\n👋 用户中断退出")
            break

        except Exception as e:
            restart_count += 1
            delay = min(
                MIN_RESTART_DELAY * (RESTART_BACKOFF ** min(restart_count - 1, RESTART_BACKOFF_CAP)),
                MAX_RESTART_DELAY,
            )

            print(f"\n⚠️ 服务异常退出 (第{restart_count}次): {e}")
            print(f"   {delay}秒后自动重启...")
            print(f"   📝 查看日志: tail -f {LOG_FILE}")

            # 重新写入 PID（重启后 PID 不变）
            write_pid_file()

            time.sleep(delay)


# ══════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════

if __name__ == '__main__':
    try:
        run_with_auto_restart()
    finally:
        remove_pid_file()
        print("✅ termux-mcp 已安全停止")
