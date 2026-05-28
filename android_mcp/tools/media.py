"""Media: camera, photos, media player, sharing, downloads, screen recording."""

import base64
import logging
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json, run, privileged_available, privileged_shell
from android_mcp.lib.constants import (
    HOME, SDCARD, SDCARD_SHORT, DCIM_CAMERA,
    PHOTO_DEFAULT, PHOTO_ALT_DIRS,
)

logger = logging.getLogger('android-mcp.media')


# ──────────────────────────────────────────────
# Screen Recording
# ──────────────────────────────────────────────

@mcp.tool()
async def screen_record(
    duration_secs: int = 15,
    output_path: str = "",
    show_taps: bool = True,
    bit_rate_mbps: int = 4,
) -> str:
    """Record the phone screen as a video file.

    Uses Android's built-in screenrecord command. Requires Shizuku or ADB.
    录制完成后自动停止，返回视频文件路径。

    Args:
        duration_secs: Recording duration in seconds (max 180, default: 15)
        show_taps: Show touch taps as visual feedback on screen (default: True)
        bit_rate_mbps: Video bitrate in Mbps (higher = better quality, default: 4)
        output_path: Save path (default: /sdcard/screen_record_TIMESTAMP.mp4)
    """
    import time as _time

    duration_secs = max(3, min(180, duration_secs))
    bit_rate = max(1, min(50, bit_rate_mbps)) * 1_000_000

    if not output_path:
        ts = _time.strftime('%Y%m%d_%H%M%S')
        output_path = str(SDCARD / f'screen_record_{ts}.mp4')

    # Build screenrecord command
    cmd_parts = [
        'screenrecord',
        '--time-limit', str(duration_secs),
        '--bit-rate', str(bit_rate),
    ]
    if show_taps:
        cmd_parts.append('--show-taps')
    cmd_parts.append(output_path)

    cmd = ' '.join(cmd_parts)

    try:
        if privileged_available():
            r = privileged_shell(cmd, timeout=duration_secs + 10)
        else:
            r = run(cmd, shell=True, timeout=duration_secs + 10)

        if r.get('success'):
            return (
                f"🎬 屏幕录制完成\n"
                f"   • 时长: {duration_secs}s\n"
                f"   • 文件: {output_path}\n"
                f"   • 码率: {bit_rate_mbps}Mbps\n"
                f"   • 触摸反馈: {'✅' if show_taps else '❌'}\n"
                f"   • 大小: {Path(output_path).stat().st_size:,} bytes\n"
                f"\n💡 视频保存在手机存储中，可手动查看或使用 share_file() 分享"
            )
        return f"❌ 录制失败: {r.get('stderr', r.get('error', 'Unknown'))}"
    except Exception as e:
        return f"❌ 录制失败: {e}"


# ──────────────────────────────────────────────
# Camera
# ──────────────────────────────────────────────

@mcp.tool()
async def take_photo(camera_id: str = "0", output_path: str = "") -> str:
    """Take a photo using the phone camera.

    Args:
        camera_id: Camera ID - '0' for back camera, '1' for front camera
        output_path: Where to save the photo (default: ~/photo.jpg)
    """
    if not output_path:
        output_path = str(PHOTO_DEFAULT)
    result = termux('termux-camera-photo', ['-c', camera_id, output_path], timeout=15)
    if Path(output_path).exists():
        size = Path(output_path).stat().st_size
        return f"Photo saved to {output_path} ({size:,} bytes)"
    return result or "Failed to take photo"


@mcp.tool()
async def get_camera_info() -> str:
    """Get information about available cameras on the device."""
    return format_json(termux('termux-camera-info'))


# ──────────────────────────────────────────────
# Photos
# ──────────────────────────────────────────────

@mcp.tool()
async def list_photos(directory: str = "", limit: int = 30) -> str:
    """List photo files in a directory.

    Args:
        directory: Directory to list photos from (default: phone camera folder)
        limit: Maximum number of files to list (default: 30)
    """
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
            return f"Error: Photo directory not found. Tried {directory} and common alternatives."

    photo_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp'}
    photos = []
    try:
        for f in sorted(path.rglob('*'), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
            if f.is_file() and f.suffix.lower() in photo_exts:
                stat = f.stat()
                photos.append(f"{f.name:<50} {stat.st_size:>12,} bytes  {_time.ctime(stat.st_mtime)}")
                if len(photos) >= limit:
                    break
    except PermissionError:
        return f"Error: Permission denied accessing {path}. Run 'termux-setup-storage' first."

    if not photos:
        return f"No photos found in {path}"

    return f"Photos in {path} ({len(photos)} shown):\n\n" + "\n".join(photos)


@mcp.tool()
async def read_photo(file_path: str) -> str:
    """Read a photo file and return it as base64 encoded data for viewing.

    Args:
        file_path: Path to the image file
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    if path.stat().st_size > 5 * 1024 * 1024:
        return f"Error: File too large ({path.stat().st_size:,} bytes). Max 5MB."

    try:
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        ext = path.suffix.lower().lstrip('.')
        mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'gif': 'gif', 'webp': 'webp'}.get(ext, 'jpeg')
        return f"data:image/{mime};base64,{data}"
    except Exception as e:
        return f"Error reading photo: {e}"


# ──────────────────────────────────────────────
# Media Player
# ──────────────────────────────────────────────

@mcp.tool()
async def media_player(action: str, file_path: str = "") -> str:
    """Control the media player.

    Args:
        action: One of 'play', 'pause', 'stop', 'info'. Use 'play' with file_path to play a file.
        file_path: Path to media file (required for 'play' action)
    """
    if action == 'play' and file_path:
        return termux('termux-media-player', ['play', file_path])
    elif action in ('pause', 'stop', 'info'):
        return format_json(termux('termux-media-player', [action]))
    return "Error: Use action='play' with a file_path, or 'pause'/'stop'/'info'"


# ──────────────────────────────────────────────
# Share & Download
# ──────────────────────────────────────────────

@mcp.tool()
async def share_file(file_path: str) -> str:
    """Share a file using Android's share dialog.

    Args:
        file_path: Path to the file to share
    """
    if not Path(file_path).exists():
        return f"Error: File not found: {file_path}"
    return termux('termux-share', [file_path]) or f"Share dialog opened for {file_path}"


@mcp.tool()
async def download_file(url: str, description: str = "MCP Download") -> str:
    """Download a file using Android's download manager.

    Args:
        url: URL to download
        description: Download description shown in notification
    """
    return termux('termux-download', ['-d', description, url]) or f"Download started: {url}"
