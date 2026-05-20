#!/usr/bin/env python3
"""Streamable HTTP MCP server with auto-restart protection.

Same as http_server.py, kept for compatibility.
Features:
  - 自动重启：进程异常退出后自动恢复
  - 优雅关闭：SIGINT/SIGTERM 正常退出
  - 状态文件：记录服务状态（方便外部监控）
"""

import sys
import os
import time
import signal

sys.path.insert(0, '/data/data/com.termux/files/home/mcp-servers/android-mcp')

from android_mcp import mcp
import uvicorn

# ── 配置 ──
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '3000'))
STATUS_FILE = '/data/data/com.termux/files/home/mcp-servers/run/android-mcp.pid'
MAX_RESTART_DELAY = 30  # 最大等待秒数（指数退避）
MIN_RESTART_DELAY = 1   # 初始等待秒数

# ── 全局状态 ──
running = True
restart_count = 0


def signal_handler(signum, frame):
    """处理退出信号，优雅关闭"""
    global running
    signame = signal.Signals(signum).name
    print(f"\n👋 收到 {signame}，优雅关闭...")
    running = False


def write_status_file(pid: int):
    """写入状态文件，方便外部监控"""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, 'w') as f:
        f.write(str(pid))


def remove_status_file():
    """清理状态文件"""
    try:
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)
    except Exception:
        pass


# ── 注册信号处理 ──
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print(f"🚀 android-mcp Streamable HTTP → http://{HOST}:{PORT}/mcp")
write_status_file(os.getpid())

# ── 带自动重启的主循环 ──
while running:
    try:
        app = mcp.streamable_http_app()
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            timeout_keep_alive=65,
            limit_concurrency=20,
            log_level="info",
        )
        # uvicorn.run() 正常返回 → 收到退出信号
        break

    except KeyboardInterrupt:
        print("\n👋 用户中断退出")
        break

    except Exception as e:
        restart_count += 1
        delay = min(MIN_RESTART_DELAY * (2 ** min(restart_count - 1, 5)), MAX_RESTART_DELAY)

        print(f"\n⚠️ 服务异常退出 (第{restart_count}次): {e}")
        print(f"   {delay}秒后自动重启...")
        print(f"   📝 查看日志: cat ~/mcp-servers/logs/android.log")

        # 重新写入 PID（重启后 PID 不变）
        write_status_file(os.getpid())

        time.sleep(delay)

# ── 清理退出 ──
remove_status_file()
print("✅ android-mcp 已安全停止")
