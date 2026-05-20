"""ADB connection management — library layer used by tools/adb.py."""

from android_mcp.lib.utils import run, adb_connected, adb_shell, ensure_path_env


async def check_setup_status() -> str:
    """Check if ADB is installed and connected."""
    # First check if Shizuku is available (preferred)
    from android_mcp.lib.utils import shizuku_available
    if shizuku_available():
        return ("✅ Shizuku is available via rish! "
                "Most tools will work without ADB.\n"
                "ADB is still available as a fallback if needed.")

    r = run(['which', 'adb'], timeout=5)
    if not r['success']:
        return ("ADB not installed.\n"
                "Run: pkg install android-tools\n"
                "Or use Shizuku (already set up at ~/rish) for privilege elevation.")

    connected = adb_connected()
    if connected:
        devices = run(['adb', 'devices'], timeout=5)
        return f"ADB is connected!\n{devices.get('stdout', '')}"

    return ("ADB is installed but not connected.\n\n"
            "💡 Shizuku 已配置（~/rish），它会自动优先使用。\n"
            "   ADB 只在 Shizuku 不可用时作为后备。\n\n"
            "如需连接 ADB：\n"
            "1. Settings → Developer Options → Wireless Debugging → ON\n"
            "2. Tap 'Pair device with pairing code'\n"
            "3. Note the pairing code and port\n"
            "4. Use the adb_connect tool")


async def connect(pair_code: str = "", pair_port: str = "", connect_port: str = "") -> str:
    """Connect ADB to this device wirelessly. Required on Android 12+.

    Args:
        pair_code: Pairing code from wireless debugging
        pair_port: Pairing port (e.g. '37123')
        connect_port: Connection port from main page (e.g. '5555')
    """
    import subprocess
    results = []

    if pair_code and pair_port:
        try:
            proc = subprocess.Popen(
                ['adb', 'pair', f'localhost:{pair_port}'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=ensure_path_env(),
            )
            stdout, stderr = proc.communicate(input=f'{pair_code}\n', timeout=15)
            results.append(f"Pair: {stdout.strip()} {stderr.strip()}")
        except Exception as e:
            results.append(f"Pair error: {e}")

    if connect_port:
        r = run(f'adb connect localhost:{connect_port}', shell=True, timeout=10)
        results.append(f"Connect: {r.get('stdout', '')} {r.get('stderr', '')}")
    elif not pair_code:
        r = run('adb connect localhost:5555', shell=True, timeout=10)
        results.append(f"Connect: {r.get('stdout', '')} {r.get('stderr', '')}")

    connected = adb_connected()
    results.append(f"\nADB connected: {'Yes ✓' if connected else 'No ✗'}")

    if not connected:
        results.append("\nTip: Make sure 'Wireless debugging' is ON in Developer Options.")

    return "\n".join(results)
