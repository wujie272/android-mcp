#!/usr/bin/env python3
"""android-mcp: Control Android phone from AI via Model Context Protocol.

Usage:
    python server.py              # Run as stdio MCP server
    python http_server.py         # Run as HTTP/SSE server on port 3000
"""

from android_mcp import mcp


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
