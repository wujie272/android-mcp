"""Media: camera, photos, media player, sharing, downloads."""

import base64
from pathlib import Path

from android_mcp.app import mcp
from android_mcp.lib.utils import termux, format_json


# ──────────────────────────────────────────────
# Camera
# ──────────────────────────────────────────────

@mcp.tool()
async def take_photo(camera_id: str = "0", output_path: str = "/data/data/com.termux/files/home/photo.jpg") -> str:
    """Take a photo using the phone camera.

    Args:
        camera_id: Camera ID - '0' for back camera, '1' for front camera
        output_path: Where to save the photo
    """
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
async def list_photos(directory: str = "/storage/emulated/0/DCIM/Camera", limit: int = 30) -> str:
    """List photo files in a directory.

    Args:
        directory: Directory to list photos from (default: phone camera folder)
        limit: Maximum number of files to list (default: 30)
    """
    import time as _time
    path = Path(directory)
    if not path.exists():
        for alt in ['/storage/emulated/0/DCIM', '/storage/emulated/0/Pictures',
                    '/sdcard/DCIM/Camera', '/sdcard/DCIM', '/sdcard/Pictures']:
            if Path(alt).exists():
                path = Path(alt)
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
