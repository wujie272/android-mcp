"""Backward-compatible shim — delegates to the new modular structure."""
import warnings

warnings.warn(
    "termux_mcp_server.py is deprecated. Use server.py or the android_mcp package instead.",
    DeprecationWarning, stacklevel=2,
)

from android_mcp import mcp as _mcp  # noqa: F401
# Expose mcp at module level for `from termux_mcp_server import mcp`
mcp = _mcp
