import sys
sys.path.insert(0, '/data/data/com.termux/files/home/termux-mcp-server')
from termux_mcp_server import mcp
import uvicorn

app = mcp.sse_app()
print("🚀 启动 Streamable HTTP MCP 服务 → http://0.0.0.0:3000/mcp")
uvicorn.run(app, host="0.0.0.0", port=3000)
