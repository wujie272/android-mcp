"""Backward-compatible shim — re-exports from the new modular structure."""
import sys
import warnings

warnings.warn(
    "termux_mcp_server.py is deprecated. Use server.py or the android_mcp package instead.",
    DeprecationWarning, stacklevel=2,
)

from android_mcp import mcp
from android_mcp.app import mcp as _mcp  # noqa: F401

# Re-export module-level alias for scripts that do `from termux_mcp_server import mcp`
sys.modules[__name__] = mcp  # type: ignore[assignment]
