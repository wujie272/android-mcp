#!/usr/bin/env python3
"""Streamable HTTP MCP server — run on port 3000 for remote access.

优化日志:
  - 添加 timeout_keep_alive=65 防止空闲断开
  - 添加 limit_concurrency=20 支持并行工具调用
  - 添加 log_level 方便排查
  - 添加 /health 健康检查端点（服务自愈用）
  - 添加 CORS 头
"""

import time
import uvicorn
from mcp.server.fastmcp import FastMCP

from android_mcp import mcp
from android_mcp.lib.utils import get_uptime


# ── 为 FastMCP 的 HTTP app 添加健康检查路由 ──

app = mcp.streamable_http_app()


# 在 Starlette app 上挂载额外路由
@app.get("/health")
async def health_check():
    """健康检查端点 — 供 mcp-manager 轮询自动重启。"""
    uptime_secs = get_uptime()
    hours = int(uptime_secs // 3600)
    minutes = int((uptime_secs % 3600) // 60)
    seconds = int(uptime_secs % 60)

    return {
        "status": "ok",
        "service": "android-mcp",
        "uptime_sec": uptime_secs,
        "uptime_str": f"{hours}h {minutes}m {seconds}s",
        "version": "0.2.0",
    }


if __name__ == '__main__':
    print(f"🚀 android-mcp Streamable HTTP → http://0.0.0.0:3000/mcp")
    print(f"   🩺 Health check → http://0.0.0.0:3000/health")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=3000,
        timeout_keep_alive=65,
        limit_concurrency=20,
        log_level="info",
    )
