"""Media: camera, photos, media player, share, download, screen recording."""

import logging
from pathlib import Path
from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run, privileged_available, privileged_shell
from android_mcp.lib.constants import HOME, SDCARD, DCIM_CAMERA, PHOTO_DEFAULT, PHOTO_ALT_DIRS

logger = logging.getLogger('android-mcp.media')


@mcp.tool()
async def screen_record(
    duration_secs: int = 15, output_path: str = "",
    show_taps: bool = True, bit_rate_mbps: int = 4,
) -> str:
    """Record screen as MP4 (max 180s). Requires Shizuku or ADB.

    Uses Android's built-in screenrecord command.
    """
    import time as _time
    duration_secs = max(3, min(180, duration_secs))
    bit_rate = max(1, min(50, bit_rate_mbps)) * 1_000_000
    if not output_path:
        output_path = str(SDCARD / f'screen_record_{_time.strftime("%Y%m%d_%H%M%S")}.mp4')

    cmd = f'screenrecord --time-limit {duration_secs} --bit-rate {bit_rate}' + \
          (' --show-taps' if show_taps else '') + f' {output_path}'

    try:
        r = privileged_shell(cmd, timeout=duration_secs + 10) if privileged_available() \
            else run(cmd, shell=True, timeout=duration_secs + 10)
        if r.get('success'):
            return (f"🎬 录制完成: {duration_secs}s | {Path(output_path).stat().st_size:,} bytes\n"
                    f"💡 文件: {output_path}\n用 share_file() 分享")
        return f"❌ 录制失败: {r.get('stderr', r.get('error', 'Unknown'))}"
    except Exception as e:
        return f"❌ 录制失败: {e}"


# ── Camera ──

@mcp.tool()
async def take_photo(camera_id: str = "0", output_path: str = "") -> str:
    """Take a photo. camera_id: '0' for back, '1' for front."""
    if not output_path:
        output_path = str(PHOTO_DEFAULT)
    result = termux('termux-camera-photo', ['-c', camera_id, output_path], timeout=15)
    if Path(output_path).exists():
        return f"Photo saved to {output_path} ({Path(output_path).stat().st_size:,} bytes)"
    return result or "Failed"


@mcp.tool()
async def get_camera_info() -> str:
    """Get available camera info."""
    return format_json(termux('termux-camera-info'))


# ── Photos ──

@mcp.tool()
async def list_photos(directory: str = "", limit: int = 30) -> str:
    """List photo files (jpg/png/gif/webp/heic)."""
    import time as _time
    if not directory:
        directory = str(DCIM_CAMERA)
    path = Path(directory)
    if not path.exists():
        for alt in PHOTO_ALT_DIRS:
            if alt.exists():
                path = alt
                break
        else:
            return f"Error: Photo directory not found."
    exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp'}
    photos = []
    try:
        for f in sorted(path.rglob('*'), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
            if f.is_file() and f.suffix.lower() in exts:
                s = f.stat()
                photos.append(f"{f.name:<50} {s.st_size:>12,} bytes  {_time.ctime(s.st_mtime)}")
                if len(photos) >= limit:
                    break
    except PermissionError:
        return f"Error: Permission denied. Run 'termux-setup-storage'."
    return f"Photos in {path} ({len(photos)} shown):\n\n" + "\n".join(photos) if photos else f"No photos in {path}"


# ── Media Player ──

@mcp.tool()
async def media_player(action: str, file_path: str = "") -> str:
    """Control media player: play/pause/stop/info. Use 'play' with file_path."""
    if action == 'play' and file_path:
        return termux('termux-media-player', ['play', file_path])
    elif action in ('pause', 'stop', 'info'):
        return format_json(termux('termux-media-player', [action]))
    return "Usage: action='play' with file_path, or 'pause'/'stop'/'info'"


# ── Share & Download ──

@mcp.tool()
async def share_file(file_path: str) -> str:
    """Share a file via Android share dialog."""
    if not Path(file_path).exists():
        return f"Error: File not found: {file_path}"
    return termux('termux-share', [file_path]) or f"Share dialog opened"


@mcp.tool()
async def download_file(url: str, description: str = "MCP Download") -> str:
    """Download a file via Android download manager."""
    return termux('termux-download', ['-d', description, url]) or f"Download started: {url}"