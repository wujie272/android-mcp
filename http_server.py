#!/usr/bin/env python3
"""Streamable HTTP MCP server — run on port 3000 for remote access.

优化日志:
  v2.0 — 2026-05-19
  - 添加 timeout_keep_alive=65 防止空闲断开
  - 添加 limit_concurrency=20 支持并行工具调用
  - 添加 log_level 方便排查
"""

import uvicorn
from android_mcp import mcp

app = mcp.streamable_http_app()

if __name__ == '__main__':
    print("🚀 android-mcp Streamable HTTP → http://0.0.0.0:3000/mcp")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=3000,
        timeout_keep_alive=65,
        limit_concurrency=20,
        log_level="info",
    )