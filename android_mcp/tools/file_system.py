"""File System: read, write, edit, search, tree, directory listing, info, execution."""

import os
import subprocess
from pathlib import Path
from datetime import datetime

from android_mcp.app import mcp
from android_mcp.lib.utils import run, BLOCKED_COMMANDS, format_json, ensure_path_env


# ──────────────────────────────────────────────
# Read / Write
# ──────────────────────────────────────────────

@mcp.tool()
async def read_file(file_path: str) -> str:
    """Read the contents of a text file.

    Args:
        file_path: Path to the file to read
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    if path.stat().st_size > 10 * 1024 * 1024:
        return f"Error: File too large ({path.stat().st_size:,} bytes)"

    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return f"Error: Cannot decode file with supported encodings"


@mcp.tool()
async def write_file(file_path: str, content: str) -> str:
    """Write content to a file (creates parent directories if needed).

    Args:
        file_path: Path to the file
        content: Content to write
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return f"Written {len(content)} chars to {file_path}"
    except Exception as e:
        return f"Error: {e}"


# ──────────────────────────────────────────────
# Edit File — NEW (port from filesystem-mcp)
# ──────────────────────────────────────────────

@mcp.tool()
async def edit_file(file_path: str, old_text: str, new_text: str, dry_run: bool = False) -> str:
    """Make a selective edit to a file using text replacement.

    Finds the first occurrence of old_text in the file and replaces it with new_text.
    Supports dry-run mode to preview changes before applying.

    Args:
        file_path: Path to the file to edit
        old_text: Text to search for (can be a substring/line)
        new_text: Text to replace with
        dry_run: If True, preview changes without modifying the file (default: False)
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading file: {e}"

    if old_text not in content:
        return f"Error: Could not find the specified text in {file_path}"

    new_content = content.replace(old_text, new_text, 1)

    if dry_run:
        # Show a simple diff
        import difflib
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=file_path, tofile=file_path,
        )
        return "--- DRY RUN (changes NOT applied) ---\n" + "".join(diff)

    try:
        path.write_text(new_content, encoding='utf-8')
        return f"✅ Edited {file_path}: replaced \"{old_text[:50]}\" → \"{new_text[:50]}\""
    except Exception as e:
        return f"Error writing file: {e}"


# ──────────────────────────────────────────────
# Search Files — NEW
# ──────────────────────────────────────────────

@mcp.tool()
async def search_files(path: str = ".", pattern: str = "*", exclude_patterns: list[str] | None = None) -> str:
    """Recursively search for files/directories matching a glob pattern.

    Args:
        path: Starting directory (default: current directory)
        pattern: Glob pattern to match (e.g. '*.md', '**/*.py', 'data*')
        exclude_patterns: Optional list of glob patterns to exclude
    """
    import fnmatch

    root = Path(path)
    if not root.exists():
        return f"Error: Directory not found: {path}"
    if not root.is_dir():
        return f"Error: Not a directory: {path}"

    exclude = exclude_patterns or []
    results = []

    try:
        for f in sorted(root.rglob(pattern)):
            # Check exclusions
            rel = str(f.relative_to(root)) if f != root else ''
            if any(fnmatch.fnmatch(rel, exc) for exc in exclude):
                continue
            if any(fnmatch.fnmatch(f.name, exc) for exc in exclude):
                continue
            try:
                stat = f.stat()
                kind = "📁" if f.is_dir() else "📄"
                size = f"({stat.st_size:,} bytes)" if f.is_file() else ""
                results.append(f"{kind} {f} {size}")
            except Exception:
                results.append(f"? {f}")
    except PermissionError:
        return f"Error: Permission denied reading {path}"

    if not results:
        return f"No files matching '{pattern}' in {root}"

    return f"Found {len(results)} results in {root}:\n\n" + "\n".join(results)


# ──────────────────────────────────────────────
# Directory Tree — NEW
# ──────────────────────────────────────────────

@mcp.tool()
async def directory_tree(path: str = ".", exclude_patterns: list[str] | None = None) -> str:
    """Get a recursive tree of directory contents as JSON.

    Args:
        path: Starting directory (default: current directory)
        exclude_patterns: Optional list of glob patterns to exclude (e.g. ['*.pyc', '__pycache__'])
    """
    import fnmatch

    def build_tree(dir_path: Path) -> list[dict]:
        items = []
        try:
            for item in sorted(dir_path.iterdir()):
                # Check exclusion
                if exclude_patterns:
                    if any(fnmatch.fnmatch(item.name, exc) for exc in exclude_patterns):
                        continue
                if item.is_dir():
                    children = build_tree(item)
                    items.append({
                        'name': item.name,
                        'type': 'directory',
                        'children': children,
                    })
                else:
                    items.append({
                        'name': item.name,
                        'type': 'file',
                    })
        except PermissionError:
            items.append({'name': '(permission denied)', 'type': 'file'})
        return items

    root = Path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: Invalid directory: {path}"

    tree = [{
        'name': str(root.absolute()),
        'type': 'directory',
        'children': build_tree(root),
    }]

    import json
    return json.dumps(tree, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────
# Get File Info — NEW
# ──────────────────────────────────────────────

@mcp.tool()
async def get_file_info(file_path: str) -> str:
    """Get detailed file/directory metadata.

    Args:
        file_path: Path to the file or directory
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        stat = path.stat()
        import pwd, grp

        info = {
            'name': path.name,
            'path': str(path.absolute()),
            'type': 'directory' if path.is_dir() else 'file',
            'size_bytes': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'accessed': datetime.fromtimestamp(stat.st_atime).isoformat(),
            'permissions': oct(stat.st_mode)[-3:],
            'owner': pwd.getpwuid(stat.st_uid).pw_name,
            'group': grp.getgrgid(stat.st_gid).gr_name,
        }

        if path.is_symlink():
            info['symlink_target'] = str(path.resolve())

        return format_json(info)
    except Exception as e:
        return f"Error getting file info: {e}"


# ──────────────────────────────────────────────
# List Directory (enhanced) + size variant
# ──────────────────────────────────────────────

@mcp.tool()
async def list_directory(directory_path: str = ".", show_hidden: bool = False) -> str:
    """List contents of a directory.

    Args:
        directory_path: Path to directory (default: current directory)
        show_hidden: Show hidden files (default: False)
    """
    path = Path(directory_path)
    if not path.exists():
        return f"Error: Directory not found: {directory_path}"
    if not path.is_dir():
        return f"Error: Not a directory: {directory_path}"

    items = []
    try:
        for item in sorted(path.iterdir()):
            if not show_hidden and item.name.startswith('.'):
                continue
            try:
                stat = item.stat()
                kind = "DIR " if item.is_dir() else "FILE"
                size = stat.st_size if item.is_file() else 0
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%m-%d %H:%M')
                items.append(f"{kind} {item.name:<45} {size:>12,} bytes  {mtime}")
            except Exception:
                items.append(f"ERR  {item.name}")
    except PermissionError:
        return f"Error: Permission denied: {directory_path}"

    if not items:
        return f"Directory is empty: {path.absolute()}"

    header = f"Contents of: {path.absolute()}\n{'─' * 70}"
    return f"{header}\n" + "\n".join(items)


@mcp.tool()
async def list_directory_with_sizes(path: str = ".", sort_by: str = "name") -> str:
    """List directory contents with size info, sorted by name or size.

    Args:
        path: Directory path to list (default: current directory)
        sort_by: Sort by 'name' (default) or 'size'
    """
    root = Path(path)
    if not root.exists() or not root.is_dir():
        return f"Error: Invalid directory: {path}"

    items = []
    total_files = 0
    total_dirs = 0
    total_size = 0

    try:
        for item in root.iterdir():
            try:
                stat = item.stat()
                if item.is_dir():
                    total_dirs += 1
                    items.append({
                        'name': item.name,
                        'type': 'directory',
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                else:
                    total_files += 1
                    total_size += stat.st_size
                    items.append({
                        'name': item.name,
                        'type': 'file',
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
            except Exception:
                pass
    except PermissionError:
        return f"Error: Permission denied: {path}"

    if sort_by == 'size':
        items.sort(key=lambda x: x['size'], reverse=True)
    else:
        items.sort(key=lambda x: x['name'].lower())

    lines = [f"Contents of {root} (sorted by {sort_by}):\n"]
    for item in items:
        size_str = f"{item['size']:>12,}" if item['type'] == 'file' else f"{'':>12}"
        icon = "📁" if item['type'] == 'directory' else "📄"
        lines.append(f"{icon} {item['name']:<45} {size_str} bytes")

    lines.append(f"\n── Summary ──")
    lines.append(f"Files: {total_files}   Directories: {total_dirs}   Total size: {total_size:,} bytes")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# List Allowed Directories
# ──────────────────────────────────────────────

@mcp.tool()
async def list_allowed_directories() -> str:
    """List directories that this server can access (based on filesystem permissions).
    Note: On Android, access is gated by app permissions (termux-setup-storage)."""
    # Common accessible paths on Termux
    accessible = []
    for p in [HOME, '/sdcard', '/storage/emulated/0']:
        path = Path(p)
        if path.exists():
            rw = "R/W" if os.access(p, os.R_OK | os.W_OK) else \
                 "R/O" if os.access(p, os.R_OK) else "N/A"
            accessible.append(f"  {rw}  {p}")

    return "Accessible directories:\n" + "\n".join(accessible) if accessible else "No accessible directories found."


# ──────────────────────────────────────────────
# Execute Command
# ──────────────────────────────────────────────

@mcp.tool()
async def execute_command(command: str, working_directory: str = ".", timeout: int = 30) -> str:
    """Execute a shell command on the phone.

    Args:
        command: Shell command to execute
        working_directory: Working directory (default: current)
        timeout: Timeout in seconds (default: 30)
    """
    cmd_parts = command.strip().split()
    if cmd_parts and cmd_parts[0].lower() in BLOCKED_COMMANDS:
        return f"Error: Command '{cmd_parts[0]}' is blocked for safety"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=working_directory,
            encoding='utf-8', errors='replace',
            env=ensure_path_env(),
        )
        output = []
        if result.stdout.strip():
            output.append(result.stdout.strip())
        if result.stderr.strip():
            output.append(f"[stderr] {result.stderr.strip()}")
        output.append(f"[exit code: {result.returncode}]")
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
