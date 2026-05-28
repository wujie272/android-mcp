import sys, asyncio
sys.path.insert(0, '.')
from android_mcp import mcp

# Force load all layers
import android_mcp.tools.file_system
import android_mcp.tools.app_management
import android_mcp.tools.communication
import android_mcp.tools.system_control
import android_mcp.tools.media
import android_mcp.tools.adb
import android_mcp.tools.github

async def list_tools():
    tools = await mcp.list_tools()
    names = [t.name for t in tools]
    print(f'Total tools (all layers): {len(tools)}')
    
    # Check for duplicates
    seen = {}
    for t in tools:
        if t.name in seen:
            print(f'DUPLICATE FOUND: {t.name}')
        seen[t.name] = t
    print(f'Unique names: {len(seen)}')
    
    if len(tools) != len(seen):
        print('!!! ERROR: Duplicate tool names detected !!!')
        from collections import Counter
        c = Counter(names)
        for name, count in c.most_common():
            if count > 1:
                print(f'  {name}: {count} occurrences')
    else:
        print('All tool names are unique')

asyncio.run(list_tools())
