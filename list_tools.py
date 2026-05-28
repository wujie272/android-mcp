import sys, asyncio
sys.path.insert(0, '.')
from android_mcp import mcp
import android_mcp.tools.file_system
import android_mcp.tools.app_management
import android_mcp.tools.communication
import android_mcp.tools.system_control
import android_mcp.tools.media
import android_mcp.tools.adb
import android_mcp.tools.github

async def main():
    tools = await mcp.list_tools()
    for t in sorted(tools, key=lambda x: x.name):
        print(t.name)
    print(f"\nTotal: {len(tools)}")

asyncio.run(main())
