#!/usr/bin/env python3
"""HTTP/SSE MCP server — run on port 3000 for remote access."""

import uvicorn
from android_mcp import mcp

app = mcp.sse_app()

if __name__ == '__main__':
    print("🚀 android-mcp HTTP server → http://0.0.0.0:3000/mcp")
    uvicorn.run(app, host="0.0.0.0", port=3000)
