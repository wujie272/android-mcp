"""ADB connection management — library layer."""

from termux_mcp.lib.utils import run, adb_connected, adb_shell, ensure_path_env


async def check_setup_status() -> str:
    """Check ADB/Shizuku status."""
    from termux_mcp.lib.utils import shizuku_available
    if shizuku_available():
        return ("✅ Shizuku is available via rish! "
                "Most tools work without ADB. ADB is fallback only.")

    r = run(['which', 'adb'], timeout=5)
    if not r['success']:
        return "ADB not installed. Run: pkg install android-tools\nOr use Shizuku (~/rish)."

    connected = adb_connected()
    if connected:
        devices = run(['adb', 'devices'], timeout=5)
        return f"ADB connected!\n{devices.get('stdout', '')}"

    return ("ADB installed but not connected.\n\n"
            "💡 Shizuku (~/rish) is preferred and auto-used when available.\n"
            "ADB only used as fallback.\n\n"
            "To connect ADB:\n"
            "1. Settings → Developer Options → Wireless Debugging → ON\n"
            "2. Tap 'Pair device with pairing code'\n"
            "3. Use adb_connect() tool")


async def connect(pair_code: str = "", pair_port: str = "", connect_port: str = "") -> str:
    """Connect ADB wirelessly. pair from Settings → Wireless Debugging."""
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

    port = connect_port or '5555'
    r = run(f'adb connect localhost:{port}', shell=True, timeout=10)
    results.append(f"Connect: {r.get('stdout', '')} {r.get('stderr', '')}")

    connected = adb_connected()
    results.append(f"\nADB: {'✅ connected' if connected else '❌ not connected'}")
    if not connected:
        results.append("💡 Wireless Debugging must be ON in Developer Options.")
    return "\n".join(results)